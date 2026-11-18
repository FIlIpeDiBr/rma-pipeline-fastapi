"""Dados e dublês dos testes de integração: um balancete e uma DRE pequenos e coerentes."""

import copy
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[2]

EMPRESA = "ACME Comércio Ltda"
CNPJ = "12.345.678/0001-90"

# Ativo total 5000 = circulante 3000 + não circulante 2000;
# passivo circulante 1500 + não circulante 500 + patrimônio líquido 3000.
BALANCETE = {
    "empresa": EMPRESA,
    "cnpj": CNPJ,
    "mes": 3,
    "ano": 2025,
    "linhas": [
        {"conta": "1.1.1 Caixa", "saldo_anterior": 400, "debito": 900, "credito": 800,
         "saldo_atual": 500},
        {"conta": "1.1.2 Bancos", "saldo_anterior": 600, "debito": 2000, "credito": 2100,
         "saldo_atual": 500},
        {"conta": "1.1.3 Clientes", "saldo_anterior": 1500, "debito": 3000, "credito": 2500,
         "saldo_atual": 2000},
        {"conta": "2.1.1 Fornecedores", "saldo_anterior": 1200, "debito": 700, "credito": 1000,
         "saldo_atual": 1500},
        {"conta": "3.1.1 Receita de vendas", "saldo_anterior": 0, "debito": 0, "credito": 9000,
         "saldo_atual": 9000},
    ],
    "sinteticos": [
        {"categoria": "ATIVO TOTAL", "saldo_anterior": 4500, "saldo_atual": 5000},
        {"categoria": "ATIVO CIRCULANTE", "saldo_anterior": 2500, "saldo_atual": 3000},
        {"categoria": "CONTAS/BANCOS", "saldo_anterior": 1000, "saldo_atual": 1000},
        {"categoria": "ATIVO NÃO CIRCULANTE", "saldo_anterior": 2000, "saldo_atual": 2000},
        {"categoria": "IMOBILIZADO", "saldo_anterior": 2000, "saldo_atual": 2000},
        {"categoria": "PASSIVO CIRCULANTE", "saldo_anterior": 1200, "saldo_atual": 1500},
        {"categoria": "PASSIVO NÃO CIRCULANTE", "saldo_anterior": 800, "saldo_atual": 500},
        {"categoria": "PATRIMÔNIO LÍQUIDO", "saldo_anterior": 2500, "saldo_atual": 3000},
    ],
}

DRE = {
    "empresa": EMPRESA,
    "cnpj": CNPJ,
    "mes": 3,
    "ano": 2025,
    "linhas": [
        {"categoria": "Receita Bruta", "valor_atual": 10000, "valor_anterior": 8000},
        {"categoria": "Deduções (-)", "valor_atual": 1000, "valor_anterior": 800},
        {"categoria": "Receita Líquida", "valor_atual": 9000, "valor_anterior": 7200},
        {"categoria": "Custos (-)", "valor_atual": 4000, "valor_anterior": 3500},
        {"categoria": "Lucro Bruto", "valor_atual": 5000, "valor_anterior": 3700},
        {"categoria": "Despesas Operacionais (-)", "valor_atual": 2000, "valor_anterior": 1900},
        {"categoria": "Resultado Operacional", "valor_atual": 3000, "valor_anterior": 1800},
        {"categoria": "Lucro ou Prejuízo do Exercício", "valor_atual": 2500,
         "valor_anterior": 1500},
    ],
}

# DRE que o dublê "deriva" do balancete quando o período ainda não tem DRE real.
DRE_DERIVADA = {
    "linhas": [
        {"categoria": "Receita Bruta", "valor_atual": 9000, "valor_anterior": 0},
        {"categoria": "Receita Líquida", "valor_atual": 9000, "valor_anterior": 0},
        {"categoria": "Lucro ou Prejuízo do Exercício", "valor_atual": 9000, "valor_anterior": 0},
    ]
}

# O conteúdo do arquivo só precisa passar pelo conversor; quem "lê" os números é o dublê.
ARQUIVO_TEXTO = (
    "Balancete de verificação — ACME Comércio Ltda — período 03/2025\n"
    "conta;saldo anterior;débito;crédito;saldo atual\n"
    "1.1.1 Caixa;400,00;900,00;800,00;500,00\n"
    "1.1.2 Bancos;600,00;2000,00;2100,00;500,00\n"
    "1.1.3 Clientes;1500,00;3000,00;2500,00;2000,00\n"
    "2.1.1 Fornecedores;1200,00;700,00;1000,00;1500,00\n"
).encode()


class IaFalsa:
    """Dublê das quatro chamadas de IA. Decide o tipo pelo nome do arquivo e anota os pedidos."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []

    def triar(self, entrada, nome_arquivo):
        from app.ai import AiResultado

        self.chamadas.append("triagem")
        tipo = "DRE" if "dre" in nome_arquivo.lower() else "BALANCO"
        return AiResultado(
            tipo="triagem", modelo="duble", texto="{}", input_tokens=10, output_tokens=5,
            parsed={"tipo": tipo, "empresa": EMPRESA, "mes": 3, "ano": 2025},
        )

    def extrair(self, entrada, tipo):
        from app.ai import AiResultado

        self.chamadas.append(f"extracao:{tipo}")
        dados = BALANCETE if tipo == "BALANCO" else DRE
        return AiResultado(
            tipo="extracao", modelo="duble", texto="{}", parsed=copy.deepcopy(dados)
        )

    def derivar_dre_de_balanco(self, linhas_texto):
        from app.ai import AiResultado

        self.chamadas.append("dre_derivada")
        return AiResultado(
            tipo="extracao", modelo="duble", texto="{}", parsed=copy.deepcopy(DRE_DERIVADA)
        )

    def gerar_analise(self, titulo, dados_texto):
        from app.ai import AiResultado

        self.chamadas.append("analise")
        return AiResultado(tipo="texto", modelo="duble", texto=f"Análise de teste: {titulo}.")
