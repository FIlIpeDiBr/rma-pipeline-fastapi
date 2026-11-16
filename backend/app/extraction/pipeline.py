"""Orquestrador da ingestão: triagem -> extração -> persistência (RF-49).

Idempotente e retomável (RNF-01/02): roda no worker sem limite de tempo e pode
ser reexecutado para o mesmo documento (substitui os dados — RF-16). Emite
eventos de progresso para o SSE do portal.
"""

import re

import structlog

from .. import ai, storage
from ..models import (
    STATUS_ERRO,
    STATUS_EXTRAINDO,
    STATUS_PROCESSADO,
    STATUS_TRIANDO,
    Document,
)
from .converter import preparar_entrada_ia
from .persist import (
    as_uuid,
    coerce_periodo,
    dedup_por_chave,
    emitir_evento,
    get_or_create_company,
    registrar_ai_call,
    salvar_balanco,
    salvar_dre,
)

log = structlog.get_logger()


def inferir_tipo_nome(nome: str) -> str:
    chave = re.sub(r"[^a-z0-9]", "", (nome or "").lower())
    if "balanc" in chave or "balan" in chave:
        return "BALANCO"
    if "dre" in chave or "resultado" in chave or "demonstra" in chave:
        return "DRE"
    return "INDEFINIDO"


def _falhar(db, document: Document, mensagem: str) -> dict:
    document.status = STATUS_ERRO
    document.mensagem = mensagem[:2000]
    db.commit()
    emitir_evento(document.org_id, document.id, "Erro", 100, status="erro", mensagem=mensagem)
    log.warning("documento_erro", document_id=str(document.id), mensagem=mensagem)
    return {"status": STATUS_ERRO, "mensagem": mensagem}


def processar_documento(document_id) -> dict:
    """Processa um documento de ponta a ponta. Retorna um resumo do resultado."""
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        document = db.get(Document, as_uuid(document_id))
        if document is None:
            return {"status": "NAO_ENCONTRADO", "document_id": str(document_id)}
        org_id = document.org_id

        document.status = STATUS_TRIANDO
        document.mensagem = ""
        db.commit()
        emitir_evento(org_id, document.id, "Triagem", 10)

        data = storage.get_bytes(document.storage_key)
        try:
            entrada = preparar_entrada_ia(document.nome_arquivo, document.content_type, data)
        except ValueError as exc:
            return _falhar(db, document, f"Conversão: {exc}")
        document.aviso = entrada.aviso or ""

        # --- Triagem (RF-02/08) ---
        rt = ai.triar(entrada, document.nome_arquivo)
        registrar_ai_call(rt, org_id, document.id)
        if not rt.sucesso:
            return _falhar(db, document, f"Triagem falhou: {rt.erro}")
        tri = rt.parsed or {}
        tipo = str(tri.get("tipo") or "").upper()
        if tipo not in ("BALANCO", "DRE"):
            tipo = inferir_tipo_nome(document.nome_arquivo)
        if tipo not in ("BALANCO", "DRE"):
            return _falhar(db, document, "Tipo indefinido (IA e nome do arquivo inconclusivos).")

        document.status = STATUS_EXTRAINDO
        db.commit()
        emitir_evento(org_id, document.id, "Extraindo", 40)

        # --- Extração estruturada (RF-10) ---
        rx = ai.extrair(entrada, tipo)
        registrar_ai_call(rx, org_id, document.id)
        if not rx.sucesso:
            return _falhar(db, document, f"Extração falhou: {rx.erro}")
        dados = rx.parsed or {}

        emitir_evento(org_id, document.id, "Estruturando", 70)

        # --- Metadados: IA prevalece (RF-15) ---
        empresa = str(
            dados.get("empresa") or tri.get("empresa") or document.empresa_nome or ""
        ).strip()
        cnpj = re.sub(r"\D", "", str(dados.get("cnpj") or tri.get("cnpj") or ""))
        mes, ano = coerce_periodo(dados, tri)
        if not empresa or not mes or not ano:
            return _falhar(
                db,
                document,
                f"Metadados insuficientes (empresa={empresa!r}, mes={mes}, ano={ano}).",
            )
        document.empresa_nome = empresa
        document.tipo = tipo
        document.mes = mes
        document.ano = ano
        company = get_or_create_company(db, org_id, empresa, cnpj)
        document.company_id = company.id

        # --- Persistência transacional + dedup (RF-16/03) ---
        if tipo == "BALANCO":
            resumo = salvar_balanco(db, document, dados)
        else:
            resumo = salvar_dre(db, document, dados)
        removidos = dedup_por_chave(db, document)
        document.status = STATUS_PROCESSADO
        document.mensagem = ""
        db.commit()

        # Pós-processamento (RF-20/21/26): não afeta o status já gravado.
        emitir_evento(org_id, document.id, "Indicadores", 90)
        try:
            from ..calculations import (
                calcular_av_ah_balanco,
                calcular_av_ah_dre,
                preencher_periodo_anterior,
            )
            from ..indicadores_service import (
                calcular_e_salvar_indicadores,
                calcular_e_salvar_indicadores_grupo,
            )
            from .dre_sintetica import derivar_e_salvar, remover_dre_sintetica

            if tipo == "BALANCO":
                calcular_av_ah_balanco(db, org_id, company.id, mes, ano)
                derivar_e_salvar(db, document)  # DRE sintética se não houver DRE real (RF-19)
            else:
                calcular_av_ah_dre(db, org_id, company.id, mes, ano)
                remover_dre_sintetica(db, org_id, company.id, mes, ano)  # real substitui sintética
            preencher_periodo_anterior(db, org_id, company.id, mes, ano)
            calcular_e_salvar_indicadores(db, org_id, company.id, mes, ano)
            if company.grupo:  # consolidado do grupo se a empresa pertence a um (RF-25)
                calcular_e_salvar_indicadores_grupo(db, org_id, company.grupo, mes, ano)
            db.commit()
        except Exception:  # noqa: BLE001 - cálculo é best-effort; documento já está PROCESSADO
            db.rollback()
            log.warning("pos_processamento_falhou", document_id=str(document.id), exc_info=True)

        emitir_evento(
            org_id, document.id, "Concluído", 100, status="ok",
            mensagem=f"{tipo} · {empresa} · {mes:02d}/{ano}",
        )
        custo = rt.custo_usd + rx.custo_usd
        log.info(
            "documento_processado", document_id=str(document.id), tipo=tipo, custo_usd=str(custo)
        )
        return {
            "status": STATUS_PROCESSADO,
            "tipo": tipo,
            "empresa": empresa,
            "mes": mes,
            "ano": ano,
            "resumo": resumo,
            "dedup_removidos": removidos,
            "custo_usd": str(custo),
        }
    except Exception as exc:  # noqa: BLE001 - marca o documento como ERRO e propaga p/ retry
        db.rollback()
        doc = db.get(Document, as_uuid(document_id))
        if doc is not None:
            _falhar(db, doc, f"Erro inesperado: {exc.__class__.__name__}: {exc}")
        raise
    finally:
        db.close()
