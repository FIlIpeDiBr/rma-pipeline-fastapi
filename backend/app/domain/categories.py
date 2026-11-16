"""Categorias sintéticas (plano de contas padronizado) e normalização de contas.

Fontes: §2 dos requisitos e `constants.gs` da v1. As strings canônicas são as
que a IA deve devolver e as que os templates/relatórios consomem (Passo 5).
O mapa de aliases (RF-17) é a rede de segurança para variações de nomenclatura.
"""

from .textutil import remover_acentos

# Ordem canônica (usada na ordenação de tabelas e na garantia do RF-18).
SINTETICOS_BALANCO: list[str] = [
    "ATIVO",
    "ATIVO TOTAL",
    "ATIVO CIRCULANTE",
    "CONTAS/BANCOS",
    "ATIVO NÃO CIRCULANTE",
    "IMOBILIZADO",
    "PASSIVO CIRCULANTE",
    "PASSIVO NÃO CIRCULANTE",
    "PATRIMÔNIO LÍQUIDO",
]

SINTETICOS_DRE: list[str] = [
    "Receita Bruta",
    "Deduções (-)",
    "Receita Líquida",
    "Custos (-)",
    "Lucro Bruto",
    "Despesas Operacionais (-)",
    "Depreciação",
    "Amortização",
    "Depreciação e Amortização",
    "Resultado Operacional",
    "Distribuição de Resultados (-)",
    "Lucro ou Prejuízo do Exercício",
]


def _chave(texto: str) -> str:
    """Normaliza p/ comparação: sem acento, maiúsculo, sem '(-)', espaços colapsados."""
    s = remover_acentos(texto or "").upper()
    s = s.replace("(-)", " ").replace("(+)", " ")
    s = s.replace("-", " ").replace("/", " ")
    return " ".join(s.split())


# alias normalizado -> categoria canônica
_ALIAS_BALANCO: dict[str, str] = {}
_ALIAS_DRE: dict[str, str] = {}


def _reg(mapa: dict[str, str], canonica: str, *aliases: str) -> None:
    mapa[_chave(canonica)] = canonica
    for a in aliases:
        mapa[_chave(a)] = canonica


for _c in SINTETICOS_BALANCO:
    _reg(_ALIAS_BALANCO, _c)
_reg(_ALIAS_BALANCO, "ATIVO TOTAL", "TOTAL DO ATIVO", "TOTAL ATIVO")
_reg(
    _ALIAS_BALANCO,
    "CONTAS/BANCOS",
    "CAIXA E BANCOS",
    "CAIXA E EQUIVALENTES",
    "CAIXA E EQUIVALENTES DE CAIXA",
    "DISPONIBILIDADES",
    "DISPONIVEL",
    "BANCOS",
    "CAIXA",
)
_reg(_ALIAS_BALANCO, "ATIVO NÃO CIRCULANTE", "ATIVO N CIRCULANTE", "ATIVO NAO-CIRCULANTE")
_reg(_ALIAS_BALANCO, "IMOBILIZADO", "ATIVO IMOBILIZADO", "IMOBILIZADO LIQUIDO")
_reg(_ALIAS_BALANCO, "PASSIVO NÃO CIRCULANTE", "PASSIVO N CIRCULANTE", "EXIGIVEL A LONGO PRAZO")
_reg(
    _ALIAS_BALANCO,
    "PATRIMÔNIO LÍQUIDO",
    "PATRIMONIO LIQUIDO PL",
    "PL",
    "PATRIMONIO LIQUIDO (PL)",
)

for _c in SINTETICOS_DRE:
    _reg(_ALIAS_DRE, _c)
_reg(_ALIAS_DRE, "Receita Bruta", "RECEITAS BRUTAS", "RECEITA OPERACIONAL BRUTA", "FATURAMENTO")
_reg(
    _ALIAS_DRE,
    "Deduções (-)",
    "DEDUCOES",
    "DEDUCAO",
    "DEDUCOES DA RECEITA",
    "IMPOSTOS SOBRE VENDAS",
)
_reg(_ALIAS_DRE, "Receita Líquida", "RECEITAS LIQUIDAS", "RECEITA OPERACIONAL LIQUIDA")
_reg(
    _ALIAS_DRE,
    "Custos (-)",
    "CUSTO",
    "CMV",
    "CPV",
    "CSP",
    "CUSTO DOS PRODUTOS VENDIDOS",
    "CUSTO DAS MERCADORIAS VENDIDAS",
    "CUSTO DOS SERVICOS PRESTADOS",
)
_reg(_ALIAS_DRE, "Lucro Bruto", "RESULTADO BRUTO")
_reg(_ALIAS_DRE, "Despesas Operacionais (-)", "DESPESAS", "DESPESAS OPERACIONAIS")
_reg(_ALIAS_DRE, "Depreciação e Amortização", "DEPRECIACAO/AMORTIZACAO", "D A")
_reg(_ALIAS_DRE, "Resultado Operacional", "LUCRO OPERACIONAL", "EBIT", "RESULTADO ANTES DO IR")
_reg(_ALIAS_DRE, "Distribuição de Resultados (-)", "DISTRIBUICAO DE LUCROS", "DIVIDENDOS")
_reg(
    _ALIAS_DRE,
    "Lucro ou Prejuízo do Exercício",
    "LUCRO LIQUIDO",
    "LUCRO LIQUIDO DO EXERCICIO",
    "RESULTADO DO EXERCICIO",
    "RESULTADO LIQUIDO",
    "LUCRO PREJUIZO DO EXERCICIO",
)


def normalizar_categoria_balanco(raw: str) -> str | None:
    return _ALIAS_BALANCO.get(_chave(raw))


def normalizar_categoria_dre(raw: str) -> str | None:
    return _ALIAS_DRE.get(_chave(raw))


def ordem_balanco(categoria: str) -> int:
    try:
        return SINTETICOS_BALANCO.index(categoria)
    except ValueError:
        return len(SINTETICOS_BALANCO)


def ordem_dre(categoria: str) -> int:
    try:
        return SINTETICOS_DRE.index(categoria)
    except ValueError:
        return len(SINTETICOS_DRE)
