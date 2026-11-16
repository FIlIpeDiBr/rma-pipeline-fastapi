"""Motor de indicadores: trava a lógica de cálculo (sem depender da planilha)."""

from app.domain.indicadores import calcular_indicadores, safe_divide

DRE = [
    {"conta": "Receita Bruta", "valor_atual": 1000},
    {"conta": "Deduções (-)", "valor_atual": -100},
    {"conta": "Receita Líquida", "valor_atual": 900},
    {"conta": "Custos (-)", "valor_atual": -300},
    {"conta": "Lucro Bruto", "valor_atual": 600},
    {"conta": "Despesas Operacionais (-)", "valor_atual": -50},
    {"conta": "Resultado Operacional", "valor_atual": 200},
    {"conta": "Lucro ou Prejuízo do Exercício", "valor_atual": 150},
]
BAL = [
    {"conta": "ATIVO TOTAL", "saldo_atual": 5000},
    {"conta": "ATIVO CIRCULANTE", "saldo_atual": 2000},
    {"conta": "ATIVO NÃO CIRCULANTE", "saldo_atual": 3000},
    {"conta": "IMOBILIZADO", "saldo_atual": 1500},
    {"conta": "CONTAS/BANCOS", "saldo_atual": 400},
    {"conta": "PASSIVO CIRCULANTE", "saldo_atual": 1000},
    {"conta": "PASSIVO NÃO CIRCULANTE", "saldo_atual": 500},
    {"conta": "PATRIMÔNIO LÍQUIDO", "saldo_atual": 3000},
]


def test_safe_divide():
    assert safe_divide(10, 2) == 5
    assert safe_divide(10, 0) is None
    assert safe_divide("x", 2) is None


def test_indicadores_principais():
    r = calcular_indicadores(DRE, BAL)
    assert r["receita_bruta"] == 1000
    assert r["receita_liquida"] == 900
    assert r["total_deducoes"] == -100
    assert r["lucro_liquido"] == 150
    assert r["ebitda"] == 200  # resultado_operacional + dep/amort(0)
    assert r["endividamento"] == 0.33  # PC/PL = 1000/3000
    assert r["liquidez_corrente"] == 2.0  # AC/PC
    assert r["solvencia_geral"] == 3.33  # ativo_total/(PC+PNC)
    assert r["lucratividade_percentual"] == 16.67  # 150/900*100
    assert r["ebitda_percentual"] == 22.22  # 200/900*100
    assert r["peso_deducoes_percentual"] == -10.0  # -100/1000*100


def test_divisao_por_zero_vira_none():
    dre0 = [
        {"conta": "Receita Bruta", "valor_atual": 0},
        {"conta": "Receita Líquida", "valor_atual": 0},
        {"conta": "Lucro ou Prejuízo do Exercício", "valor_atual": 150},
    ]
    r = calcular_indicadores(dre0, BAL)
    assert r["lucratividade_percentual"] is None  # /0 -> None


def test_acumulada_usa_somas_do_ano():
    r = calcular_indicadores(DRE, BAL, soma_lucro=300, soma_receita=1500)
    assert r["lucratividade_acumulada_percentual"] == 20.0  # 300/1500*100
