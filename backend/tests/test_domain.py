from decimal import Decimal

from app.domain.categories import (
    SINTETICOS_BALANCO,
    SINTETICOS_DRE,
    normalizar_categoria_balanco,
    normalizar_categoria_dre,
)
from app.domain.json_repair import carregar_json
from app.domain.textutil import canonical, parse_valor_brl, proximo_periodo_anterior


def test_parse_valor_brl():
    assert parse_valor_brl("1.234.567,89") == Decimal("1234567.89")
    assert parse_valor_brl("(1.870,10)") == Decimal("-1870.10")
    assert parse_valor_brl("1388622.18") == Decimal("1388622.18")
    assert parse_valor_brl("-9334") == Decimal("-9334")
    assert parse_valor_brl("") == Decimal("0")
    assert parse_valor_brl(None) == Decimal("0")
    assert parse_valor_brl(1234.5) == Decimal("1234.5")


def test_canonical():
    assert canonical("Iguiporã Agro Ltda – Holding") == "IGUIPORAAGROLTDAHOLDING"
    assert canonical("EBT - Empresa") == canonical("ebt empresa")


def test_normalizacao_categorias():
    assert normalizar_categoria_balanco("ATIVO N CIRCULANTE") == "ATIVO NÃO CIRCULANTE"
    assert normalizar_categoria_balanco("Caixa e Bancos") == "CONTAS/BANCOS"
    assert normalizar_categoria_dre("RECEITAS BRUTAS") == "Receita Bruta"
    assert normalizar_categoria_dre("(-) CUSTOS") == "Custos (-)"
    assert normalizar_categoria_dre("xyz inexistente") is None


def test_listas_completas():
    assert len(SINTETICOS_BALANCO) == 9
    assert len(SINTETICOS_DRE) == 12


def test_json_repair():
    assert carregar_json('```json\n{"a": 100 + 200, "b": [1,2,]}\n```') == {"a": 300, "b": [1, 2]}


def test_periodo_anterior():
    assert proximo_periodo_anterior(1, 2025) == (12, 2024)
    assert proximo_periodo_anterior(9, 2025) == (8, 2025)


def test_json_truncado_recupera_linhas_completas():
    truncado = (
        '{"empresa": "EBT", "mes": 12, "ano": 2025, "linhas": ['
        '{"conta": "1 ATIVO", "saldo_atual": 100.0},'
        '{"conta": "1.1 CIRC", "saldo_atual": 90.0},'
        '{"conta": "1.1.1 DISP", "saldo_at'
    )
    d = carregar_json(truncado)
    assert len(d["linhas"]) == 2
    assert d["linhas"][-1]["conta"] == "1.1 CIRC"
