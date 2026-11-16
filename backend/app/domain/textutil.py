"""Normalização de texto e parsing de valores monetários pt-BR."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation


def remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def canonical(nome: str) -> str:
    """Chave canônica de empresa: sem acentos, sem pontuação, maiúscula, sem espaços.

    Usada apenas para comparação/dedup (RF-03/17/22). O nome humano é guardado à parte.
    Ex.: "Iguiporã Agro Ltda – Holding" -> "IGUIPORAAGROLTDAHOLDING".
    """
    base = remover_acentos(nome or "").upper()
    return re.sub(r"[^A-Z0-9]", "", base)


def normalizar_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip())


# Aceita "1.234.567,89", "-1.870,10", "1388622.18", "1.234", "(123,45)", "123 D".
_LIMPAR_VALOR = re.compile(r"[^0-9,.\-]")


def parse_valor_brl(valor) -> Decimal:
    """Converte representações de valor (str pt-BR/EN ou número) em Decimal.

    Não interpreta sufixos D/C como sinal (regra do RF-10 — fica a cargo da IA).
    Parênteses indicam negativo. Retorna Decimal("0") quando vazio/ilegível.
    """
    if valor is None or valor == "":
        return Decimal("0")
    if isinstance(valor, (int, float, Decimal)):
        try:
            return Decimal(str(valor))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    s = str(valor).strip()
    negativo = s.startswith("(") and s.endswith(")")
    s = _LIMPAR_VALOR.sub("", s)
    if not s or s in {"-", ".", ","}:
        return Decimal("0")

    tem_virgula = "," in s
    tem_ponto = "." in s
    if tem_virgula and tem_ponto:
        # pt-BR: ponto é milhar, vírgula é decimal -> "1.234.567,89"
        s = s.replace(".", "").replace(",", ".")
    elif tem_virgula:
        # só vírgula: decimal pt-BR -> "1234,89"
        s = s.replace(",", ".")
    # só ponto (ou nenhum): já está em formato decimal/inteiro

    # Remove sinais de menos internos espúrios, mantendo o prefixo
    neg_prefix = s.startswith("-")
    s = s.replace("-", "")
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    if negativo or neg_prefix:
        d = -d
    return d


def proximo_periodo_anterior(mes: int, ano: int) -> tuple[int, int]:
    """Mês imediatamente anterior, com virada de ano."""
    if mes <= 1:
        return 12, ano - 1
    return mes - 1, ano
