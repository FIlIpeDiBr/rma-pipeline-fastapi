"""Prompts de triagem e extração estruturada (RF-02/08/10).

As listas de categorias sintéticas são injetadas a partir de app.domain.categories
para manter uma única fonte de verdade.
"""

from ..domain.categories import SINTETICOS_BALANCO, SINTETICOS_DRE

SYSTEM_TRIAGEM = (
    "Você classifica documentos contábeis brasileiros (balancetes e DREs). "
    "Responda APENAS com JSON válido, sem comentários nem cercas de markdown."
)

SYSTEM_EXTRACAO = (
    "Você é um especialista contábil que extrai dados de balancetes e DREs brasileiros. "
    "Devolva APENAS JSON válido, sem comentários, sem texto fora do JSON e sem cercas markdown."
)


def prompt_triagem(nome_arquivo: str) -> str:
    return f"""Analise o documento contábil em anexo (nome do arquivo: "{nome_arquivo}").

Identifique e devolva ESTE JSON:
{{
  "tipo": "BALANCO" | "DRE" | "INDEFINIDO",
  "empresa": "razão social da empresa",
  "cnpj": "apenas dígitos ou vazio",
  "mes": número de 1 a 12 (mês de referência) ou null,
  "ano": ano com 4 dígitos ou null,
  "competencia_texto": "o período exatamente como aparece no documento",
  "confianca": número de 0 a 1
}}

Regras:
- BALANCO = balancete/balanço (contas com saldo anterior, débito, crédito, saldo atual; plano de contas 1,2,3...).
- DRE = demonstração de resultado (receita, custos, despesas, lucro/prejuízo).
- "empresa" é a razão social; ignore títulos como "DRE", "Balanço Patrimonial", "Balancete".
- Período: se for um intervalo (ex.: 01/10/2025 a 31/12/2025), use o MÊS e ANO do FIM do período.
  Documento anual (01/01 a 31/12) => mês = 12.
- Se não conseguir determinar o tipo, use "INDEFINIDO".
Responda só o JSON."""


def prompt_extracao_balanco() -> str:
    cats = "\n".join(f"  - {c}" for c in SINTETICOS_BALANCO)
    return f"""Extraia os dados deste BALANCETE e devolva ESTE JSON:
{{
  "empresa": "razão social",
  "cnpj": "apenas dígitos ou vazio",
  "mes": número de 1 a 12,
  "ano": ano com 4 dígitos,
  "linhas": [
    {{"conta": "código + descrição da conta", "saldo_anterior": 0, "debito": 0, "credito": 0, "saldo_atual": 0}}
  ],
  "sinteticos": [
    {{"categoria": "<categoria sintética>", "saldo_anterior": 0, "debito": 0, "credito": 0, "saldo_atual": 0}}
  ]
}}

Categorias sintéticas válidas (use exatamente estas strings em "categoria"):
{cats}

Regras:
- Em "linhas", liste as contas do balancete preservando a ordem de leitura (de cima para baixo).
- Em "sinteticos", classifique os saldos agregados nas categorias acima (uma entrada por categoria presente).
- Sufixos "D"/"C" ao lado dos valores NÃO viram sinal — registre apenas o número.
- Todos os valores são NÚMEROS finais: use ponto como separador decimal, sem separador de milhar,
  sem aspas, sem expressões aritméticas (ex.: 1234567.89, não "1.234.567,89" nem 100+200).
- Se o balancete só tiver a coluna "Saldo", preencha "saldo_atual" e deixe os demais como 0.
- Não invente contas nem valores; o que não existir, omita."""


def prompt_extracao_dre() -> str:
    cats = "\n".join(f"  - {c}" for c in SINTETICOS_DRE)
    return f"""Extraia os dados desta DRE (Demonstração do Resultado) e devolva ESTE JSON:
{{
  "empresa": "razão social",
  "cnpj": "apenas dígitos ou vazio",
  "mes": número de 1 a 12,
  "ano": ano com 4 dígitos,
  "linhas": [
    {{"categoria": "<categoria sintética>", "valor_atual": 0, "valor_anterior": 0}}
  ]
}}

Categorias sintéticas válidas (use exatamente estas strings, nesta ordem quando existirem):
{cats}

Regras:
- Use SOMENTE as categorias sintéticas acima (agregue as contas analíticas nelas).
- "valor_anterior" = valor da coluna do período anterior, se o documento tiver; senão 0.
- Categorias derivadas: calcule quando não vierem explícitas
  (Receita Líquida = Receita Bruta − Deduções; Lucro Bruto = Receita Líquida − Custos; etc.).
- Mantenha o sinal como aparece no documento (custos/deduções/despesas normalmente negativos).
- Valores são NÚMEROS finais: ponto decimal, sem separador de milhar, sem aspas, sem expressões.
- O que não existir no documento, omita (não invente)."""


def prompt_dre_de_balanco() -> str:
    cats = "\n".join(f"  - {c}" for c in SINTETICOS_DRE)
    return f"""As linhas abaixo são as CONTAS DE UM BALANCETE (inclui contas de resultado:
receitas, custos e despesas — tipicamente classes 3/4/5/6/7). Monte a DRE do período
classificando APENAS as contas de resultado nas categorias sintéticas. Ignore as contas
patrimoniais (ativo, passivo, patrimônio líquido). Devolva ESTE JSON:
{{
  "linhas": [
    {{"categoria": "<categoria sintética>", "valor_atual": 0}}
  ]
}}

Categorias sintéticas válidas (use exatamente estas strings, nesta ordem quando existirem):
{cats}

Regras:
- Receita Bruta = soma das receitas operacionais brutas; Deduções (-) = impostos/devoluções sobre vendas.
- Receita Líquida = Receita Bruta − Deduções; Lucro Bruto = Receita Líquida − Custos;
  Resultado Operacional = Lucro Bruto − Despesas Operacionais; Lucro ou Prejuízo do Exercício = resultado final.
- Calcule as categorias derivadas quando não houver uma conta direta para elas.
- Mantenha o sinal contábil (custos/deduções/despesas normalmente negativos).
- Valores numéricos finais: ponto decimal, sem separador de milhar, sem aspas, sem expressões.
- Some os saldos das subcontas na categoria sintética correspondente."""
