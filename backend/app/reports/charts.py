"""Gráficos de colunas internos (matplotlib), portados do protótipo de relatório."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Paleta do template v1 (verde-oliva/creme).
CORES = ["#606c38", "#bc6c25", "#283618", "#a3b18a", "#dda15e", "#588157"]


def fmt(v) -> str:
    if v is None:
        return ""
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def grafico_colunas(path, titulo, labels_periodos, series) -> str:
    """series: lista de (rótulo, [valores...]). A cor vem da paleta por posição."""
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    n = max(len(series), 1)
    largura = 0.8 / n
    for i, (nome, valores) in enumerate(series):
        x = [j + i * largura for j in range(len(labels_periodos))]
        barras = ax.bar(
            x, [v or 0 for v in valores], width=largura, label=nome,
            color=CORES[i % len(CORES)], edgecolor="#999999", linewidth=0.5,
        )
        ax.bar_label(barras, labels=[fmt(v) for v in valores], fontsize=7, padding=2)
    ax.set_xticks([j + largura * (n - 1) / 2 for j in range(len(labels_periodos))])
    ax.set_xticklabels(labels_periodos)
    ax.set_title(titulo)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=min(n, 4), fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(lambda v, _: fmt(v))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return str(path)


# Definição dos 6 gráficos do RMA (rótulo do indicador -> série), na ordem do v1.
GRAFICOS = [
    ("grafico_lucratividade", "Lucratividade e Lucro Acumulado", [
        ("Lucro Líquido (R$)", "Lucro Liquido (R$)"),
        ("Lucratividade Acumulada (%)", "Lucratividade Acumulada (%)"),
        ("Lucratividade (%)", "Lucratividade (%)"),
    ]),
    ("grafico_receita", "Receita Bruta e Líquida", [
        ("Receita Bruta (R$)", "Receita Bruta (R$)"),
        ("Receita Líquida (R$)", "Receita Liquida (R$)"),
    ]),
    ("grafico_deducoes", "Deduções da Receita Bruta", [
        ("Total Deduções (R$)", "Total Deducoes (R$)"),
        ("Peso das Deduções (%)", "Peso das Deducoes (%)"),
    ]),
    ("grafico_lucro", "Lucro Bruto e Líquido", [
        ("Lucro Bruto (R$)", "Lucro Bruto (R$)"),
        ("Lucro Líquido (R$)", "Lucro Liquido (R$)"),
    ]),
    ("grafico_ebitda", "EBITDA", [
        ("EBITDA (R$)", "EBITDA (R$)"),
        ("EBITDA (%)", "EBITDA (%)"),
    ]),
    ("grafico_liquidez", "Liquidez", [
        ("Liquidez Geral", "Liquidez Geral"),
        ("Liquidez Seca", "Liquidez Seca"),
        ("Liquidez Imediata", "Liquidez Imediata"),
        ("Liquidez Corrente", "Liquidez Corrente"),
    ]),
]
