"""Fluxo de ponta a ponta pela API: upload → fila → pipeline → indicadores → relatório."""

import io

import pytest
from dados_de_teste import EMPRESA
from sqlalchemy import text

pytestmark = pytest.mark.integracao

BALANCETE = "balancete_acme_2025_03.csv"
DRE = "dre_acme_2025_03.csv"


def _empresa(cliente) -> dict:
    (empresa,) = cliente.get("/api/companies").json()["empresas"]
    return empresa


def _indicadores(cliente, company_id: str) -> dict:
    r = cliente.get("/api/indicators", params={"mes": 3, "ano": 2025, "company_id": company_id})
    assert r.status_code == 200, r.text
    return {i["key"]: i["valor"] for i in r.json()["indicadores"]}


def _contar(banco, tabela: str, document_id: str) -> int:
    with banco.connect() as conn:
        return conn.execute(
            text(f"SELECT count(*) FROM {tabela} WHERE document_id = :d"), {"d": document_id}
        ).scalar()


def _dre_por_origem(banco) -> dict[bool, int]:
    """Quantas linhas de DRE existem, separadas em derivada (True) e real (False)."""
    with banco.connect() as conn:
        linhas = conn.execute(text("SELECT derivada, count(*) FROM dre_lines GROUP BY derivada"))
        return {derivada: total for derivada, total in linhas}


def _texto_docx(conteudo: bytes) -> str:
    from docx import Document as Docx

    doc = Docx(io.BytesIO(conteudo))
    partes = [p.text for p in doc.paragraphs]
    for tabela in doc.tables:
        for linha in tabela.rows:
            partes.extend(celula.text for celula in linha.cells)
    return "\n".join(partes)


def test_balancete_do_upload_aos_indicadores(cliente, processar, ia, banco):
    doc_id, resultado = processar(BALANCETE)
    assert resultado["status"] == "PROCESSADO"
    assert resultado["resumo"] == {"linhas": 5, "sinteticos": 9}

    det = cliente.get(f"/api/documents/{doc_id}").json()
    assert (det["status"], det["tipo"], det["empresa"], det["mes"], det["ano"]) == (
        "PROCESSADO", "BALANCO", EMPRESA, 3, 2025,
    )
    assert det["qtd_linhas"] == 5
    sinteticos = {s["categoria"]: s["saldo_atual"] for s in det["sinteticos"]}
    assert len(sinteticos) == 9  # todas as categorias, mesmo as que o arquivo não trouxe
    assert sinteticos["ATIVO CIRCULANTE"] == 3000.0
    assert sinteticos["ATIVO"] == 0.0
    assert [e["etapa"] for e in det["eventos"]] == [
        "Triagem", "Extraindo", "Estruturando", "Indicadores", "Concluído",
    ]

    empresa = _empresa(cliente)
    assert (empresa["nome"], empresa["cnpj"]) == (EMPRESA, "12345678000190")

    indicadores = _indicadores(cliente, empresa["id"])
    assert len(indicadores) == 23
    assert indicadores["liquidez_corrente"] == 2.0  # 3000 / 1500
    assert indicadores["liquidez_imediata"] == 0.67  # 1000 / 1500

    # Sem DRE no período, o pipeline deriva uma do balancete e a marca como derivada.
    assert ia.chamadas == ["triagem", "extracao:BALANCO", "dre_derivada"]
    assert _dre_por_origem(banco) == {True: 12}
    assert _contar(banco, "ai_calls", doc_id) == 3  # toda chamada de IA fica auditada


def test_dre_real_substitui_a_derivada(cliente, processar, banco):
    processar(BALANCETE)
    assert _dre_por_origem(banco) == {True: 12}

    _, resultado = processar(DRE)
    assert (resultado["status"], resultado["tipo"]) == ("PROCESSADO", "DRE")
    assert _dre_por_origem(banco) == {False: 12}

    indicadores = _indicadores(cliente, _empresa(cliente)["id"])
    assert indicadores["receita_bruta"] == 10000.0
    assert indicadores["lucratividade_percentual"] == 27.78  # 2500 / 9000
    assert indicadores["liquidez_corrente"] == 2.0  # o balancete continua valendo


def test_reenvio_do_mesmo_periodo_fica_so_com_o_mais_recente(cliente, processar, banco):
    primeiro, _ = processar(BALANCETE)
    segundo, resultado = processar("balancete_acme_2025_03_corrigido.csv")
    assert resultado["dedup_removidos"] == 1

    documentos = cliente.get("/api/documents").json()["documentos"]
    assert [d["id"] for d in documentos] == [segundo]
    assert cliente.get(f"/api/documents/{primeiro}").status_code == 404
    # As linhas e os eventos do documento antigo caem pela FK ON DELETE CASCADE do banco.
    assert _contar(banco, "balance_lines", primeiro) == 0
    assert _contar(banco, "job_events", primeiro) == 0
    assert _contar(banco, "balance_lines", segundo) == 14  # 5 contas + 9 sintéticos


def test_excluir_documento_leva_linhas_eventos_e_indicadores(cliente, processar, banco, arquivos):
    doc_id, _ = processar(BALANCETE)
    empresa = _empresa(cliente)
    assert _indicadores(cliente, empresa["id"])
    assert any(doc_id in chave for chave in arquivos)

    r = cliente.delete(f"/api/documents/{doc_id}")
    assert r.json() == {"id": doc_id, "excluido": True}

    for tabela in ("balance_lines", "dre_lines", "job_events"):
        assert _contar(banco, tabela, doc_id) == 0, tabela
    assert not any(doc_id in chave for chave in arquivos)  # o arquivo saiu do storage
    assert _indicadores(cliente, empresa["id"]) == {}  # recalculados a partir do que sobrou
    # A auditoria de IA permanece, só perde o vínculo (ON DELETE SET NULL).
    with banco.connect() as conn:
        total, vinculadas = conn.execute(
            text("SELECT count(*), count(document_id) FROM ai_calls")
        ).one()
    assert (total, vinculadas) == (3, 0)


def test_relatorio_do_pedido_ao_download(cliente, processar, fila):
    from app.jobs.tasks import gerar_relatorio

    processar(BALANCETE)
    processar(DRE)
    empresa = _empresa(cliente)
    (modelo,) = cliente.get("/api/templates").json()["templates"]  # cria o modelo padrão

    r = cliente.post(
        "/api/reports",
        params={"template_id": modelo["id"], "ano": 2025, "mes": 3, "company_id": empresa["id"]},
    )
    assert r.status_code == 200, r.text
    pedido = r.json()
    assert (pedido["status"], pedido["erro"], pedido["pronto"]) == ("FILA", "", False)
    assert fila.pendentes("gerar_relatorio", report_id=pedido["id"]) == 1
    assert cliente.get(f"/api/reports/{pedido['id']}/download").status_code == 409  # ainda não

    assert gerar_relatorio(report_id=pedido["id"])["status"] == "CONCLUIDO"

    det = cliente.get(f"/api/reports/{pedido['id']}").json()
    assert (det["status"], det["progresso"], det["pronto"]) == ("CONCLUIDO", 100, True)
    assert det["entidade"] == EMPRESA

    baixado = cliente.get(f"/api/reports/{pedido['id']}/download")
    assert baixado.status_code == 200
    assert baixado.headers["content-disposition"].startswith("attachment; filename=")
    texto = _texto_docx(baixado.content)
    assert EMPRESA in texto
    assert "Análise de teste" in texto  # os blocos de análise vieram do dublê de IA


def test_uma_organizacao_nao_enxerga_os_dados_da_outra(cliente, processar, sessao, outra_org):
    doc_id, _ = processar(BALANCETE)
    empresa = _empresa(cliente)
    dona = sessao["org_id"]

    sessao["org_id"] = outra_org.id
    assert cliente.get("/api/documents").json()["total"] == 0
    assert cliente.get("/api/companies").json()["empresas"] == []
    assert _indicadores(cliente, empresa["id"]) == {}
    for metodo, caminho in (
        ("get", f"/api/documents/{doc_id}"),
        ("get", f"/api/documents/{doc_id}/download"),
        ("post", f"/api/documents/{doc_id}/reprocess"),
        ("delete", f"/api/documents/{doc_id}"),
    ):
        assert getattr(cliente, metodo)(caminho).status_code == 404, f"{metodo} {caminho}"
    # Nem com um modelo próprio dá para gerar relatório da empresa alheia.
    (modelo,) = cliente.get("/api/templates").json()["templates"]
    r = cliente.post(
        "/api/reports",
        params={"template_id": modelo["id"], "ano": 2025, "mes": 3, "company_id": empresa["id"]},
    )
    assert r.status_code == 404

    sessao["org_id"] = dona
    assert cliente.get(f"/api/documents/{doc_id}").json()["status"] == "PROCESSADO"  # intacto
