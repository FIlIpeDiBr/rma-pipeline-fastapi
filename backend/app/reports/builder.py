"""Builder do relatório: contexto -> gráficos -> análise IA -> render docxtpl (RF-34/36/37)."""

import io
import tempfile
import zipfile
from pathlib import Path

from docx.shared import Mm
from docxtpl import DocxTemplate, InlineImage
from jinja2.sandbox import SandboxedEnvironment

from . import analysis
from .charts import GRAFICOS, grafico_colunas
from .context import montar_contexto


def _noop(_etapa, _pct):
    pass


def ambiente_jinja() -> SandboxedEnvironment:
    """Ambiente Jinja para renderizar templates enviados pelo portal.

    Um template docx é código Jinja. No ambiente padrão, quem sobe um template
    alcança os internos do Python a partir de qualquer valor (`''.__class__...`)
    e executa código no worker; o ambiente restrito bloqueia esse acesso.
    `autoescape` escapa `&` e `<` dos valores: sem ele, uma razão social como
    "Silva & Filhos <Matriz>" sai no relatório como "Silva  Filhos", sem aviso.
    """
    return SandboxedEnvironment(autoescape=True)


def eh_docx(data: bytes) -> bool:
    """True se os bytes são um .docx: um zip com o documento principal dentro."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return "word/document.xml" in z.namelist()
    except zipfile.BadZipFile:
        return False


def renderizar(
    template_bytes: bytes, ctx: dict, *, com_ia: bool = True, on_progress=_noop
) -> bytes:
    """Adiciona gráficos e análises ao contexto base e renderiza o docx. Retorna bytes."""
    tpl = DocxTemplate(io.BytesIO(template_bytes))
    ind = ctx.get("indicadores", {})
    chave_atu = ctx.get("_chave_atual")
    chave_ant = ctx.get("_chave_anterior")
    ind_atu = ind.get(chave_atu, {})
    ind_ant = ind.get(chave_ant, {})
    labels = [ctx["periodo_anterior"], ctx["periodo_atual"]]

    on_progress("Gerando gráficos", 55)
    with tempfile.TemporaryDirectory() as tmp:
        for var, titulo, defs in GRAFICOS:
            series = [
                (rotulo, [ind_ant.get(label), ind_atu.get(label)]) for rotulo, label in defs
            ]
            png = grafico_colunas(Path(tmp) / f"{var}.png", titulo, labels, series)
            ctx[var] = InlineImage(tpl, png, width=Mm(150))

            sufixo = var.split("_", 1)[1]
            if com_ia:
                texto, _ = analysis.analisar_grafico(titulo, series, labels)
                ctx["analise_" + sufixo] = texto
            else:
                ctx.setdefault("analise_" + sufixo, "")

        if com_ia:
            on_progress("Análise por IA", 75)
            for integrante in ctx.get("integrantes", []):
                tb, _ = analysis.analisar_tabela(
                    f"Balanço — {integrante['nome']}", integrante["balanco"],
                    ctx["periodo_anterior"], ctx["periodo_atual"],
                )
                integrante["analise_balanco"] = tb
                td, _ = analysis.analisar_tabela(
                    f"DRE — {integrante['nome']}", integrante["dre"],
                    ctx["periodo_anterior"], ctx["periodo_atual"],
                )
                integrante["analise_dre"] = td

        on_progress("Renderizando documento", 95)
        tpl.render(ctx, jinja_env=ambiente_jinja())
        out = io.BytesIO()
        tpl.save(out)
        return out.getvalue()


def gerar(db, org_id, *, template_bytes, mes, ano, company_id=None, grupo=None,
          anual=False, com_ia=True, on_progress=_noop) -> bytes:
    """Monta o contexto a partir do banco e renderiza o relatório."""
    on_progress("Montando dados", 30)
    ctx = montar_contexto(
        db, org_id, company_id=company_id, grupo=grupo, mes=mes, ano=ano, anual=anual
    )
    return renderizar(template_bytes, ctx, com_ia=com_ia, on_progress=on_progress)


def nome_arquivo(entidade: str, mes: int, ano: int, anual: bool = False) -> str:
    from .context import MESES

    seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in entidade).strip()
    if anual:
        return f"RMA {seguro} {ano}.docx"
    return f"RMA {seguro} {MESES[mes]}_{ano}.docx"
