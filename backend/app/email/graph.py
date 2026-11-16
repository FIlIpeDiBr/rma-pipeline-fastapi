"""Cliente Microsoft Graph (app-only / client credentials) para a caixa dedicada.

Usa as credenciais do Entra já configuradas (AZURE_*) e a RMA_MAILBOX. Escopo
restrito à caixa rma@ pela Application Access Policy criada no provisionamento.
"""

import base64
import re
import time

import httpx
import structlog

from ..config import get_settings

log = structlog.get_logger()
GRAPH = "https://graph.microsoft.com/v1.0"
_TOKEN_CACHE: dict = {"valor": None, "expira": 0.0}


class GraphError(RuntimeError):
    pass


def _settings():
    return get_settings()


def configurado() -> bool:
    s = _settings()
    return bool(s.azure_tenant_id and s.azure_client_id and s.azure_client_secret and s.rma_mailbox)


def obter_token() -> str:
    agora = time.time()
    if _TOKEN_CACHE["valor"] and _TOKEN_CACHE["expira"] - 60 > agora:
        return _TOKEN_CACHE["valor"]
    s = _settings()
    url = f"https://login.microsoftonline.com/{s.azure_tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": s.azure_client_id,
        "client_secret": s.azure_client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    r = httpx.post(url, data=data, timeout=30)
    if r.status_code >= 400:
        raise GraphError(f"Falha no token Graph ({r.status_code}): {r.text[:300]}")
    j = r.json()
    _TOKEN_CACHE["valor"] = j["access_token"]
    _TOKEN_CACHE["expira"] = agora + int(j.get("expires_in", 3600))
    return _TOKEN_CACHE["valor"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {obter_token()}"}


def _mailbox() -> str:
    return _settings().rma_mailbox


def listar_nao_lidas(top: int = 25) -> list[dict]:
    """Mensagens não lidas da caixa de entrada com anexos (id, assunto, remetente)."""
    url = (
        f"{GRAPH}/users/{_mailbox()}/mailFolders/inbox/messages"
        "?$filter=isRead eq false and hasAttachments eq true"
        "&$select=id,subject,from,receivedDateTime,bodyPreview,body&$top=" + str(top)
    )
    r = httpx.get(url, headers=_headers(), timeout=30)
    if r.status_code >= 400:
        raise GraphError(f"Falha ao listar mensagens ({r.status_code}): {r.text[:300]}")
    return r.json().get("value", [])


def assunto(msg: dict) -> str:
    return msg.get("subject", "") or ""


def recebido_em(msg: dict) -> str:
    return msg.get("receivedDateTime", "") or ""


def _strip_html(html: str) -> str:
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", html or "")
    txt = re.sub(r"(?i)<br\s*/?>", "\n", txt)
    txt = re.sub(r"(?i)</p>", "\n", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", txt)).strip()


def texto_corpo(msg: dict, limite: int = 8000) -> str:
    """Corpo do email em texto puro (limitado). Usa body.content; cai no bodyPreview."""
    body = msg.get("body") or {}
    conteudo = body.get("content") or ""
    if (body.get("contentType") or "").lower() == "html":
        conteudo = _strip_html(conteudo)
    conteudo = (conteudo or msg.get("bodyPreview") or "").strip()
    return conteudo[:limite]


def remetente(msg: dict) -> str:
    return (msg.get("from", {}).get("emailAddress", {}) or {}).get("address", "") or ""


def baixar_anexos(message_id: str) -> list[dict]:
    """Anexos de arquivo da mensagem: [{nome, content_type, data(bytes)}]."""
    url = f"{GRAPH}/users/{_mailbox()}/messages/{message_id}/attachments"
    r = httpx.get(url, headers=_headers(), timeout=60)
    if r.status_code >= 400:
        raise GraphError(f"Falha ao baixar anexos ({r.status_code}): {r.text[:300]}")
    out = []
    for a in r.json().get("value", []):
        if a.get("@odata.type") != "#microsoft.graph.fileAttachment":
            continue
        if a.get("isInline"):  # ignora imagens de assinatura embutidas
            continue
        conteudo = a.get("contentBytes")
        if not conteudo:
            continue
        out.append({
            "nome": a.get("name", "anexo"),
            "content_type": a.get("contentType", ""),
            "data": base64.b64decode(conteudo),
        })
    return out


def marcar_lida(message_id: str) -> None:
    url = f"{GRAPH}/users/{_mailbox()}/messages/{message_id}"
    r = httpx.patch(url, headers=_headers(), json={"isRead": True}, timeout=30)
    if r.status_code >= 400:
        log.warning("graph_marcar_lida_falhou", erro=r.text[:200])


def responder(message_id: str, comentario: str) -> None:
    """Responde à mensagem original (mantém a thread)."""
    url = f"{GRAPH}/users/{_mailbox()}/messages/{message_id}/reply"
    r = httpx.post(url, headers=_headers(), json={"comment": comentario}, timeout=30)
    if r.status_code >= 400:
        log.warning("graph_responder_falhou", erro=r.text[:200])


def enviar_email(destino: str, assunto: str, corpo: str) -> None:
    """Envia um email novo (usado quando não há mensagem original para responder)."""
    url = f"{GRAPH}/users/{_mailbox()}/sendMail"
    payload = {
        "message": {
            "subject": assunto,
            "body": {"contentType": "Text", "content": corpo},
            "toRecipients": [{"emailAddress": {"address": destino}}],
        },
        "saveToSentItems": True,
    }
    r = httpx.post(url, headers=_headers(), json=payload, timeout=30)
    if r.status_code >= 400:
        log.warning("graph_enviar_falhou", erro=r.text[:200])
