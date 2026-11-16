"""Conversão de arquivos para a entrada da IA (RF-06/07).

Decide, por arquivo, o melhor modo de envio à IA:
- texto:  PDF com texto útil, Excel/CSV, texto puro;
- imagem: png/jpg/webp/...;
- pdf:    PDF escaneado/sem texto útil -> enviado binário ao modelo de visão.
"""

import io
import re
from dataclasses import dataclass

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff"}
PLANILHA_EXTS = {"xlsx", "xlsm", "ods"}  # .xls legado não suportado por openpyxl
MEDIA_TYPE_IMG = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}


@dataclass
class EntradaIA:
    """Conteúdo preparado para a IA. `modo` em {texto, imagem, pdf}."""

    modo: str
    texto: str | None = None
    media_type: str | None = None
    data: bytes | None = None  # binário (imagem/pdf) a enviar em base64
    aviso: str = ""  # observação anexada aos detalhes do documento (ex.: abas ignoradas)


def extensao(nome: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]+)$", nome or "")
    return m.group(1).lower() if m else ""


def conteudo_binario(texto: str) -> bool:
    """Heurística de binário/ilegível (RF-07), portada da v1."""
    if not texto:
        return False
    if texto.startswith("%PDF-"):
        return True
    amostra = texto[:4000]
    if not amostra:
        return False
    nulos = 0
    nao_imprimiveis = 0
    for ch in amostra:
        c = ord(ch)
        if c == 0:
            nulos += 1
            nao_imprimiveis += 1
            continue
        imprimivel = (32 <= c != 127) or c in (9, 10, 13)
        if not imprimivel:
            nao_imprimiveis += 1
    if nulos / len(amostra) > 0.01:
        return True
    return nao_imprimiveis / len(amostra) > 0.30


def texto_util(texto: str) -> bool:
    """Texto extraído tem utilidade mínima (tamanho + letras + números) — RF-07."""
    s = (texto or "").strip()
    if len(s) < 120:
        return False
    tem_letras = bool(re.search(r"[A-Za-zÀ-ÿ]", s))
    tem_numeros = bool(re.search(r"\d", s))
    return tem_letras and tem_numeros


def pdf_para_texto(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    partes = []
    for page in reader.pages:
        try:
            partes.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - página problemática não derruba a extração
            partes.append("")
    return "\n".join(partes).strip()


def excel_para_texto(data: bytes) -> tuple[str, list[str]]:
    """Serializa SOMENTE a primeira aba (decisão de negócio: planilhas multi-aba).

    Retorna (texto_da_1a_aba, nomes_de_todas_as_abas) — o chamador usa a lista
    para anexar um aviso quando há abas ignoradas.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    abas = list(wb.sheetnames)
    linhas = []
    if wb.worksheets:
        ws = wb.worksheets[0]
        for row in ws.iter_rows(values_only=True):
            celulas = ["" if c is None else str(c) for c in row]
            if any(celulas):
                linhas.append(" | ".join(celulas))
        texto = (f"# Aba: {ws.title}\n" + "\n".join(linhas)).strip()
    else:
        texto = ""
    wb.close()
    return texto, abas


def preparar_entrada_ia(nome: str, content_type: str, data: bytes) -> EntradaIA:
    """Escolhe o modo de envio à IA. Levanta ValueError quando ilegível (RF-07)."""
    ext = extensao(nome)
    ct = (content_type or "").lower()
    eh_imagem = ct.startswith("image/") or ext in IMAGE_EXTS
    eh_pdf = ct == "application/pdf" or ext == "pdf"
    eh_planilha = (
        ext in PLANILHA_EXTS
        or "spreadsheet" in ct
        or "excel" in ct
        or ct == "application/vnd.ms-excel"
    )

    if eh_imagem:
        media = MEDIA_TYPE_IMG.get(ext) or (ct if ct.startswith("image/") else "image/png")
        return EntradaIA(modo="imagem", media_type=media, data=data)

    if eh_pdf:
        try:
            texto = pdf_para_texto(data)
        except Exception:  # noqa: BLE001 - cai para visão
            texto = ""
        if texto_util(texto) and not conteudo_binario(texto):
            return EntradaIA(modo="texto", texto=texto)
        # PDF escaneado/sem texto útil -> envia binário ao modelo de visão.
        return EntradaIA(modo="pdf", media_type="application/pdf", data=data)

    if eh_planilha:
        try:
            texto, abas = excel_para_texto(data)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Falha ao ler a planilha: {exc}") from exc
        if not texto_util(texto):
            raise ValueError("Planilha sem conteúdo útil para extração.")
        aviso = ""
        if len(abas) > 1:
            ignoradas = ", ".join(abas[1:])
            aviso = (
                f"Planilha com {len(abas)} abas; considerada apenas a primeira "
                f'("{abas[0]}"). Abas ignoradas: {ignoradas}.'
            )
        return EntradaIA(modo="texto", texto=texto, aviso=aviso)

    if ext == "csv" or ct in ("text/csv", "text/plain") or ct.startswith("text/"):
        texto = _decodificar(data)
        if texto_util(texto) and not conteudo_binario(texto):
            return EntradaIA(modo="texto", texto=texto)
        raise ValueError("Arquivo de texto sem conteúdo útil para extração.")

    # Último recurso: tenta decodificar como texto.
    texto = _decodificar(data)
    if texto and not conteudo_binario(texto) and texto_util(texto):
        return EntradaIA(modo="texto", texto=texto)
    raise ValueError(
        f"Formato nao suportado ou conteudo ilegivel "
        f"(nome={nome!r}, content_type={content_type!r})."
    )


def _decodificar(data: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
