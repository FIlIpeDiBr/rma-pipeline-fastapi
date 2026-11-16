"""Gera um template docx padrão (docxtpl/Jinja) espelhando a estrutura do RMA da v1.

Serve para individual e grupo (o laço `integrantes` cobre 1 ou n entidades).
A org pode subir os modelos oficiais depois pela biblioteca de templates.
"""

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from .charts import GRAFICOS

_HDR = ["Conta", "{{ periodo_anterior }}", "AV%", "{{ periodo_atual }}", "AV%", "AH%"]


def _tabela_loop(doc, fonte):
    t = doc.add_table(rows=4, cols=6)
    t.style = "Light Grid Accent 1"
    for c, txt in enumerate(_HDR):
        t.rows[0].cells[c].text = txt
    t.rows[1].cells[0].text = "{%tr for l in " + fonte + " %}"
    celulas = ["{{ l.conta }}", "{{ l.anterior }}", "{{ l.av_ant }}",
               "{{ l.atual }}", "{{ l.av_atu }}", "{{ l.ah }}"]
    for c, txt in enumerate(celulas):
        t.rows[2].cells[c].text = txt
    t.rows[3].cells[0].text = "{%tr endfor %}"


def gerar_template_bytes() -> bytes:
    doc = Document()

    def p(texto, style=None, align=None, italic=False):
        par = doc.add_paragraph(texto, style=style)
        if align:
            par.alignment = align
        if italic:
            for run in par.runs:
                run.italic = True
        return par

    capa = doc.add_table(rows=3, cols=1)
    capa.style = "Table Grid"
    capa.rows[0].cells[0].text = "RELATÓRIO MENSAL DE ATIVIDADES"
    capa.rows[1].cells[0].text = "{{ entidade }}"
    capa.rows[2].cells[0].text = "{{ periodo_atual }}"
    p("")

    p("I. INTRODUÇÃO", style="Heading 1")
    p("Esta análise tomou por base os Balancetes de Verificação e as Demonstrações dos "
      "Resultados referentes à competência de {{ mes_nome }} de {{ ano }}.")

    p("II. DAS ANÁLISES CONTÁBEIS, FINANCEIRAS E ECONÔMICAS", style="Heading 1")

    p("{%p for integrante in integrantes %}")
    p("II.I - ANÁLISE VERTICAL E HORIZONTAL DO BALANÇO — {{ integrante.nome }}", style="Heading 2")
    p("{{ integrante.analise_balanco }}", italic=True)
    _tabela_loop(doc, "integrante.balanco")
    p("")
    p("II.II - ANÁLISE VERTICAL E HORIZONTAL DA DRE — {{ integrante.nome }}", style="Heading 2")
    p("{%p if integrante.dre %}")
    p("{{ integrante.analise_dre }}", italic=True)
    _tabela_loop(doc, "integrante.dre")
    p("{%p else %}")
    p("Sem dados de DRE no período para esta entidade.", italic=True)
    p("{%p endif %}")
    p("")
    p("{%p endfor %}")

    p("II.III - INDICADORES FINANCEIROS E ECONÔMICOS", style="Heading 1")
    p("Os gráficos abaixo comparam {{ periodo_anterior }} e {{ periodo_atual }}.")
    for var, titulo, _series in GRAFICOS:
        sufixo = var.split("_", 1)[1]
        p(titulo, style="Heading 2")
        img = doc.add_paragraph("{{ " + var + " }}")
        img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p("{{ analise_" + sufixo + " }}", italic=True)

    p("III. CONCLUSÃO", style="Heading 1")
    p("Estas são as informações apuradas acerca da competência de {{ mes_nome }} de {{ ano }}.")

    for s in doc.styles:
        if s.name == "Normal":
            s.font.size = Pt(11)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
