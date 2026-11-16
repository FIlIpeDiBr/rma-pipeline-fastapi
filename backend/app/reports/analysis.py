"""Blocos de análise via IA (RF-35). Best-effort: falha não derruba o relatório (RF-39)."""

import structlog

from .. import ai

log = structlog.get_logger()


def _tabela_texto(rows, periodo_ant, periodo_atu) -> str:
    linhas = [f"Períodos comparados: {periodo_ant} e {periodo_atu}."]
    for r in rows:
        linhas.append(
            f"{r['conta']}: {periodo_ant}={r['anterior']} (AV {r['av_ant']}), "
            f"{periodo_atu}={r['atual']} (AV {r['av_atu']}), AH {r['ah']}%"
        )
    return "\n".join(linhas)


def _serie_texto(series, labels) -> str:
    out = []
    for nome, valores in series:
        pares = ", ".join(f"{lab}={v}" for lab, v in zip(labels, valores, strict=False))
        out.append(f"{nome}: {pares}")
    return "\n".join(out)


def analisar_tabela(titulo, rows, periodo_ant, periodo_atu) -> tuple[str, object]:
    if not rows:
        return "", None
    r = ai.gerar_analise(titulo, _tabela_texto(rows, periodo_ant, periodo_atu))
    if not r.sucesso:
        log.warning("analise_tabela_falhou", titulo=titulo, erro=r.erro[:150])
        return "", r
    return r.texto.strip(), r


def analisar_grafico(titulo, series, labels) -> tuple[str, object]:
    r = ai.gerar_analise(titulo, _serie_texto(series, labels))
    if not r.sucesso:
        log.warning("analise_grafico_falhou", titulo=titulo, erro=r.erro[:150])
        return "", r
    return r.texto.strip(), r
