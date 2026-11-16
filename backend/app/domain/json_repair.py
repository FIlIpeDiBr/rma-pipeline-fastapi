"""Tolerância a JSON malformado da IA (RF-13).

Porta a lógica da v1 (`openai_service.gs`): remove cercas markdown, avalia
expressões aritméticas simples em campos numéricos e remove vírgulas sobrando.
Acrescenta salvamento de JSON truncado (resposta cortada no limite de tokens):
recupera os elementos completos das listas em vez de descartar tudo.
"""

import json
import re

_CERCA_INICIO = re.compile(r"^```[a-zA-Z]*\s*\n?")
_CERCA_FIM = re.compile(r"\n?```\s*$")
# ": 100 + 200," / ": 1.5 - 0.3 }" — expressão de soma/subtração de números.
_EXPR_NUM = re.compile(
    r"(:\s*)([-+]?\d+(?:\.\d+)?(?:\s*[+\-]\s*[-+]?\d+(?:\.\d+)?)+)(\s*[,}\]])"
)
_VIRGULA_SOBRANDO = re.compile(r",\s*([}\]])")


def limpar_cercas(texto: str) -> str:
    s = (texto or "").strip()
    if s.startswith("```"):
        s = _CERCA_INICIO.sub("", s)
        s = _CERCA_FIM.sub("", s)
    return s.strip()


def _avaliar_soma_sub(expr: str) -> str | None:
    s = re.sub(r"\s+", "", expr or "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[+\-]\d+(?:\.\d+)?)+", s):
        return None
    partes = re.findall(r"[+\-]?\d+(?:\.\d+)?", s)
    try:
        total = sum(float(p) for p in partes)
    except ValueError:
        return None
    if total == int(total):
        return str(int(total))
    return f"{total:.10f}".rstrip("0").rstrip(".")


def _reparar_expressoes(texto: str) -> str:
    def repl(m: re.Match) -> str:
        valor = _avaliar_soma_sub(m.group(2))
        return m.group(0) if valor is None else f"{m.group(1)}{valor}{m.group(3)}"

    return _EXPR_NUM.sub(repl, texto)


def _salvar_truncado(texto: str) -> str | None:
    """Recupera um JSON cortado: trunca no último elemento completo de uma lista
    e fecha os colchetes/chaves ainda abertos. Retorna None se nada salvável."""
    inicio = texto.find("{")
    abre_lista = texto.find("[")
    if abre_lista != -1 and (inicio == -1 or abre_lista < inicio):
        inicio = abre_lista
    if inicio < 0:
        return None

    pilha: list[str] = []
    in_str = False
    esc = False
    ultimo: tuple[int, list[str]] | None = None
    for i in range(inicio, len(texto)):
        ch = texto[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            pilha.append(ch)
        elif ch in "}]":
            if not pilha:
                break
            pilha.pop()
            # fechou um elemento e ainda estamos dentro de uma lista -> ponto seguro
            if pilha and pilha[-1] == "[":
                ultimo = (i, list(pilha))
    if ultimo is None:
        return None
    idx, pilha_restante = ultimo
    fechos = "".join("]" if c == "[" else "}" for c in reversed(pilha_restante))
    return texto[inicio : idx + 1] + fechos


def carregar_json(texto: str):
    """json.loads; em falha, repara; em último caso, salva JSON truncado.

    Levanta ValueError se nem assim for parseável.
    """
    bruto = limpar_cercas(texto)
    if not bruto:
        raise ValueError("Resposta vazia após limpeza de markdown.")
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        pass

    reparado = _reparar_expressoes(bruto)
    reparado = _VIRGULA_SOBRANDO.sub(r"\1", reparado)
    try:
        return json.loads(reparado)
    except json.JSONDecodeError:
        pass

    salvo = _salvar_truncado(reparado)
    if salvo is not None:
        try:
            return json.loads(salvo)
        except json.JSONDecodeError:
            pass

    amostra = bruto[:500]
    raise ValueError(f"JSON irreparável. Conteúdo: {amostra}")
