"""Motor de indicadores (RF-26/27/28/29) — porte fiel de indicators.gs (v1).

A planilha v1 calculava os valores pela cadeia de fallbacks por indicador (as
fórmulas "legíveis" gravadas não tinham {{}} e falhavam). Reproduzimos os dois
caminhos: avaliação da fórmula com tokens e, em caso de lacuna, o fallback.
"""

import math
import re
import unicodedata
from dataclasses import dataclass


def normalizar_chave(nome: str) -> str:
    s = unicodedata.normalize("NFD", str(nome or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


def safe_divide(num, den):
    try:
        a = float(num)
        b = float(den)
    except (TypeError, ValueError):
        return None
    if b == 0 or a != a or b != b:  # inclui NaN
        return None
    return a / b


@dataclass(frozen=True)
class Definicao:
    key: str
    label: str
    formula: str
    formato: str  # rs | pct | indice
    aliases: tuple[str, ...] = ()


# As 23 definições (seed do RF-27b). Fórmulas em sintaxe simplificada: apenas
# chaves de indicadores/contas, operações aritméticas, potência (x**y), raiz
# (x/-y) e parênteses. As contas do balancete/DRE são referenciadas pela chave
# plana (ex.: passivo_circulante), sem os prefixos dre./bal./acum.
INDICADORES: list[Definicao] = [
    Definicao("receita_bruta", "Receita Bruta (R$)", "receita_bruta", "rs"),
    Definicao("custos", "Custos (R$)", "custos", "rs"),
    Definicao("despesas", "Despesas (R$)", "despesas_operacionais", "rs"),
    Definicao("lucro_bruto", "Lucro Bruto (R$)", "lucro_bruto", "rs"),
    Definicao(
        "lucro_liquido", "Lucro Liquido (R$)", "lucro_ou_prejuizo_do_exercicio", "rs"
    ),
    Definicao(
        "ebitda",
        "EBITDA (R$)",
        "resultado_operacional + depreciacao_amortizacao_total",
        "rs",
    ),
    Definicao(
        "ebitda_percentual", "EBITDA (%)", "ebitda / receita_liquida * 100", "pct"
    ),
    Definicao(
        "endividamento",
        "Endividamento (Passivo/PL)",
        "passivo_circulante / patrimonio_liquido",
        "indice",
    ),
    Definicao(
        "imobilizacao",
        "Imobilizacao (ANC/PL)",
        "(imobilizado + ativo_nao_circulante) / patrimonio_liquido",
        "indice",
    ),
    Definicao(
        "solvencia_geral",
        "Solvencia Geral (Ativo/Passivo)",
        "ativo_total / (passivo_circulante + passivo_nao_circulante)",
        "indice",
    ),
    Definicao(
        "distribuicao_resultados_percentual",
        "Distribuicao de Resultados (% sobre Lucro)",
        "distribuicao_de_resultados / lucro_liquido * 100",
        "pct",
    ),
    Definicao(
        "liquidez_geral",
        "Liquidez Geral",
        "(ativo_circulante + realizavel_a_longo_prazo)"
        " / (passivo_circulante + passivo_nao_circulante)",
        "indice",
    ),
    Definicao(
        "liquidez_corrente",
        "Liquidez Corrente",
        "ativo_circulante / passivo_circulante",
        "indice",
    ),
    Definicao(
        "liquidez_seca",
        "Liquidez Seca",
        "(ativo_circulante - estoques) / passivo_circulante",
        "indice",
    ),
    Definicao(
        "liquidez_imediata",
        "Liquidez Imediata",
        "contas_bancos / passivo_circulante",
        "indice",
    ),
    Definicao(
        "lucratividade_percentual",
        "Lucratividade (%)",
        "lucro_liquido / receita_liquida * 100",
        "pct",
    ),
    Definicao(
        "margem_operacional",
        "Margem Operacional (%)",
        "resultado_operacional / receita_liquida * 100",
        "pct",
    ),
    Definicao(
        "margem_liquida",
        "Margem Liquida (%)",
        "lucro_liquido / receita_liquida * 100",
        "pct",
    ),
    Definicao("fluxo_resultados", "Fluxo de Resultados (R$)", "lucro_liquido", "rs"),
    Definicao(
        "lucratividade_acumulada_percentual",
        "Lucratividade Acumulada (%)",
        "lucro_liquido_acumulado / receita_liquida_acumulado * 100",
        "pct",
    ),
    Definicao("receita_liquida", "Receita Liquida (R$)", "receita_liquida", "rs"),
    Definicao("total_deducoes", "Total Deducoes (R$)", "deducoes", "rs"),
    Definicao(
        "peso_deducoes_percentual",
        "Peso das Deducoes (%)",
        "total_deducoes / receita_bruta * 100",
        "pct",
    ),
]

# ── Parser de fórmulas simplificado (sem eval) ───────────────────────────────
# Gramática (precedência da mais alta para a mais baixa):
#   átomo/parênteses  >  unário (+/-)  >  potência (**)  >  raiz (/-)  >
#   multiplicação/divisão (* /)  >  soma/subtração (+ -)
# Operandos: números e chaves de indicadores/contas (identificadores).


def _finito(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _potencia(a, b):
    if a is None or b is None:
        return None
    try:
        if a < 0 and not float(b).is_integer():
            return None  # base negativa com expoente fracionário -> complexo
        return _finito(float(a) ** float(b))
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def _raiz(a, b):
    """Raiz de índice b de a (x /- y). Equivale a a ** (1/b)."""
    if a is None or b is None or b == 0:
        return None
    try:
        if a < 0:
            if float(b).is_integer() and int(b) % 2 == 1:  # só raiz de índice ímpar
                return _finito(-((-float(a)) ** (1.0 / float(b))))
            return None
        return _finito(float(a) ** (1.0 / float(b)))
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def _reescrever_safe_divide(expr: str) -> str:
    """Compat retroativa: safe_divide(A, B) -> ((A)/(B)) (divisão já trata /0)."""
    for nome in ("safe_divide", "safeDivide"):
        while True:
            idx = expr.find(nome + "(")
            if idx == -1:
                break
            inicio = idx + len(nome)  # posição do "("
            profundidade = 0
            virgula = -1
            j = inicio
            while j < len(expr):
                ch = expr[j]
                if ch == "(":
                    profundidade += 1
                elif ch == ")":
                    profundidade -= 1
                    if profundidade == 0:
                        break
                elif ch == "," and profundidade == 1 and virgula == -1:
                    virgula = j
                j += 1
            if profundidade != 0 or virgula == -1:
                return expr  # malformado -> deixa como está (cairá no fallback)
            a = expr[inicio + 1:virgula]
            b = expr[virgula + 1:j]
            expr = expr[:idx] + "((" + a + ")/(" + b + "))" + expr[j + 1:]
    return expr


def _tokenizar(expr: str):
    toks: list[tuple[str, object]] = []
    i, n = 0, len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c == "*":
            if i + 1 < n and expr[i + 1] == "*":
                toks.append(("POW", None))
                i += 2
            else:
                toks.append(("MUL", None))
                i += 1
            continue
        if c == "/":
            if i + 1 < n and expr[i + 1] == "-":  # operador de raiz x/-y
                toks.append(("ROOT", None))
                i += 2
            else:
                toks.append(("DIV", None))
                i += 1
            continue
        if c == "+":
            toks.append(("ADD", None))
            i += 1
            continue
        if c == "-":
            toks.append(("SUB", None))
            i += 1
            continue
        if c == "(":
            toks.append(("LP", None))
            i += 1
            continue
        if c == ")":
            toks.append(("RP", None))
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            try:
                toks.append(("NUM", float(expr[i:j])))
            except ValueError:
                return None
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] in "_."):
                j += 1
            toks.append(("ID", expr[i:j]))
            i = j
            continue
        return None  # caractere inválido
    return toks


def _resolver_ref(nome, indicadores: dict, base: dict):
    """Resolve uma chave: indicador (já calculado) ou conta-base. (valor, achou)."""
    raw = str(nome).strip()
    low = raw.lower()
    if low.startswith("dre.") or low.startswith("bal."):
        raw = raw.split(".", 1)[1]
    elif low.startswith("acum."):
        raw = raw.split(".", 1)[1] + "_acumulado"
    k = normalizar_chave(raw)
    if k in indicadores and indicadores[k] not in (None, ""):
        return _finito(indicadores[k]), True
    if k in base and base[k] not in (None, ""):
        return _finito(base[k]), True
    return None, False


def _avaliar_tokens(toks, resolver):
    pos = 0
    invalido = {"v": False}

    def peek():
        return toks[pos][0] if pos < len(toks) else None

    def eat():
        nonlocal pos
        t = toks[pos]
        pos += 1
        return t

    def parse_expr():
        v = parse_termo()
        while peek() in ("ADD", "SUB"):
            op = eat()[0]
            r = parse_termo()
            if v is None or r is None:
                v = None
            else:
                v = v + r if op == "ADD" else v - r
        return v

    def parse_termo():
        v = parse_raiz()
        while peek() in ("MUL", "DIV"):
            op = eat()[0]
            r = parse_raiz()
            if v is None or r is None:
                v = None
            elif op == "MUL":
                v = v * r
            else:  # DIV — divisão por zero -> None (propaga)
                v = None if r == 0 else v / r
        return v

    def parse_raiz():
        v = parse_potencia()
        while peek() == "ROOT":
            eat()
            r = parse_potencia()
            v = _raiz(v, r)
        return v

    def parse_potencia():
        v = parse_unario()
        if peek() == "POW":
            eat()
            r = parse_potencia()  # associatividade à direita
            v = _potencia(v, r)
        return v

    def parse_unario():
        if peek() == "ADD":
            eat()
            return parse_unario()
        if peek() == "SUB":
            eat()
            u = parse_unario()
            return None if u is None else -u
        return parse_atomo()

    def parse_atomo():
        t = peek()
        if t == "NUM":
            return eat()[1]
        if t == "ID":
            nome = eat()[1]
            val, achou = resolver(nome)
            if not achou:
                invalido["v"] = True
                return 0.0
            return val
        if t == "LP":
            eat()
            v = parse_expr()
            if peek() == "RP":
                eat()
            else:
                invalido["v"] = True
            return v
        invalido["v"] = True
        return None

    valor = parse_expr()
    if pos != len(toks):  # sobrou token -> sintaxe inválida
        return None, True
    return valor, invalido["v"]


def avaliar_formula(formula, indicadores: dict, base: dict):
    if formula is None or formula == "":
        return None
    if isinstance(formula, (int, float)):
        return _finito(formula)
    expr = str(formula).strip().lstrip("=")
    if not expr:
        return None
    expr = expr.replace("{{", " ").replace("}}", " ")  # compat: chaves antigas
    expr = _reescrever_safe_divide(expr)

    toks = _tokenizar(expr)
    if not toks:
        return None
    valor, invalido = _avaliar_tokens(
        toks, lambda nome: _resolver_ref(nome, indicadores, base)
    )
    if invalido or valor is None:
        return None
    return _finito(valor)


# ── Lookup base (contexto dre.*/bal.*/acum.*) com aliases e derivações ───────
def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def pegar_primeiro_valor(base: dict, nomes):
    for nome in nomes:
        k = normalizar_chave(nome)
        if k in base:
            return base[k]
    return None


def criar_lookup_base(dre_rows, bal_rows) -> dict:
    """dre_rows: [{conta, valor_atual}]; bal_rows: [{conta, saldo_anterior, saldo_atual}].

    Cada conta é registrada com o prefixo (compat: 'dre x'/'bal x') e também com a
    chave plana (nova sintaxe: 'x'), permitindo fórmulas sem dre./bal./acum.
    """
    base: dict[str, float] = {}

    def _por_conta(prefixo: str, conta: str, valor: float) -> None:
        base[normalizar_chave(f"{prefixo} {conta}")] = valor
        bare = normalizar_chave(conta)
        if bare and bare not in base:  # 1ª ocorrência vence em caso de colisão
            base[bare] = valor

    for r in dre_rows or []:
        conta = str(r.get("conta", "")).strip()
        if conta:
            _por_conta("dre", conta, _num(r.get("valor_atual", r.get("valorAtual"))))
    for r in bal_rows or []:
        conta = str(r.get("conta", "")).strip()
        if not conta:
            continue
        atual = r.get("saldo_atual", r.get("saldoAtual"))
        anterior = r.get("saldo_anterior", r.get("saldoAnterior"))
        _por_conta("bal", conta, _num(atual if atual is not None else anterior))

    def alias(origem, destino):
        ko, kd = normalizar_chave(origem), normalizar_chave(destino)
        if ko in base and kd not in base:
            base[kd] = base[ko]

    alias("dre lucro operacional", "dre resultado operacional")
    alias("dre resultado operacional", "dre lucro operacional")
    alias("bal ativo", "bal ativo_total")
    alias("bal patrimonio liquido", "bal pl")
    # Aliases na forma plana (chaves usadas pelas fórmulas simplificadas)
    alias("lucro operacional", "resultado operacional")
    alias("resultado operacional", "lucro operacional")
    alias("ativo", "ativo_total")
    alias("patrimonio liquido", "pl")

    kpc = normalizar_chave("bal passivo circulante")
    kpnc = normalizar_chave("bal passivo nao circulante")
    kpt = normalizar_chave("bal passivo_total")
    base[kpt] = base.get(kpc, 0.0) + base.get(kpnc, 0.0)
    if kpnc not in base and kpt in base:
        base[kpnc] = base[kpt] - base.get(kpc, 0.0)
    base[normalizar_chave("passivo_total")] = base[kpt]
    if normalizar_chave("passivo_nao_circulante") not in base and kpnc in base:
        base[normalizar_chave("passivo_nao_circulante")] = base[kpnc]

    def sum_substr(prefixo, substr, skip=None):
        total, achou = 0.0, False
        for k, v in base.items():
            if prefixo and not k.startswith(prefixo):
                continue
            if skip and skip in k:
                continue
            if substr not in k:
                continue
            total += _num(v)
            achou = True
        return total if achou else None

    estoques = pegar_primeiro_valor(
        base, ["bal.estoques", "bal.estoques_de_mercadorias", "bal.estoques_de_mercadorias_mtz"]
    )
    if estoques is None:
        estoques = sum_substr("bal", "estoques")
    if estoques is not None:
        base[normalizar_chave("bal estoques")] = _num(estoques)
        base[normalizar_chave("estoques")] = _num(estoques)

    realizavel = pegar_primeiro_valor(
        base, ["bal.realizavel_a_longo_prazo", "bal.realizavel_a_longo_prazo_mtz"]
    )
    if realizavel is None:
        realizavel = sum_substr("bal", "realizavelalongoprazo")
    if realizavel is not None:
        base[normalizar_chave("bal realizavel a longo prazo")] = _num(realizavel)
        base[normalizar_chave("realizavel_a_longo_prazo")] = _num(realizavel)

    dep_amort = pegar_primeiro_valor(
        base, ["dre.depreciacao_e_amortizacao", "dre.depreciacao_amortizacao"]
    )
    if dep_amort is None:
        dep = pegar_primeiro_valor(base, ["dre.depreciacao", "dre.depreciacoes"])
        amort = pegar_primeiro_valor(base, ["dre.amortizacao", "dre.amortizacoes"])
        if dep is not None or amort is not None:
            dep_amort = (dep or 0) + (amort or 0)
    if dep_amort is None:
        depp = sum_substr("dre", "depreciacao", "depreciacaoeamortizacao") or 0
        amop = sum_substr("dre", "amortizacao", "depreciacaoeamortizacao") or 0
        comb = sum_substr("dre", "depreciacaoeamortizacao") or 0
        if (depp + amop + comb) != 0:
            dep_amort = depp + amop + comb
    if dep_amort is not None:
        base[normalizar_chave("dre depreciacao_amortizacao_total")] = _num(dep_amort)
        base[normalizar_chave("depreciacao_amortizacao_total")] = _num(dep_amort)
    return base


def adicionar_acumulados(base: dict, soma_lucro: float, soma_receita: float) -> None:
    base[normalizar_chave("acum.lucro_liquido")] = _num(soma_lucro)
    base[normalizar_chave("acum.receita_liquida")] = _num(soma_receita)
    # chaves planas usadas pelas fórmulas simplificadas
    base[normalizar_chave("lucro_liquido_acumulado")] = _num(soma_lucro)
    base[normalizar_chave("receita_liquida_acumulado")] = _num(soma_receita)


def _k(nome):  # atalho
    return normalizar_chave(nome)


def calcular_linha(defs, base, formula_overrides=None, mapa_ia=None) -> dict:
    """Resolve os indicadores em 3 passadas (fórmula -> fallback) + IA nas lacunas."""
    ind: dict[str, object] = {}
    overrides = formula_overrides or {}
    for _ in range(3):
        for idx, d in enumerate(defs):
            kn = _k(d.key or d.label)
            if ind.get(kn) not in (None, "") and kn in ind:
                continue
            formula = overrides.get(idx) or d.formula
            valor = avaliar_formula(formula, ind, base)
            if valor is None:
                valor = _fallback(kn, ind, base)
            ind[kn] = "" if valor in (None, "") else (float(valor) if _isnum(valor) else valor)

    if mapa_ia:
        for d in defs:
            kn = _k(d.key or d.label)
            if ind.get(kn) not in (None, ""):
                continue
            for cand in (d.key, d.label, *d.aliases):
                v = mapa_ia.get(_k(cand))
                if v not in (None, ""):
                    ind[kn] = float(v) if _isnum(v) else v
                    break
    return ind


def _isnum(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _fallback(kn, ind, base):
    """Cadeia de fallbacks por indicador (idêntica à v1) — produz os valores da planilha."""
    P = lambda nomes: pegar_primeiro_valor(base, nomes)  # noqa: E731
    iv = lambda nome: ind.get(_k(nome))  # noqa: E731

    def num(v):
        return 0 if v in (None, "") else v

    if kn == _k("receita_bruta"):
        return P(["dre.receita_bruta"])
    if kn == _k("total_deducoes"):
        return P(["dre.deducoes"])
    if kn == _k("receita_liquida"):
        rb, td = iv("receita_bruta"), iv("total_deducoes")
        if rb not in (None, ""):
            return rb - num(td)
        return P(["dre.receita_liquida"])
    if kn == _k("custos"):
        return P(["dre.custos", "dre.custos_operacionais"])
    if kn == _k("despesas"):
        return P(["dre.despesas_operacionais", "dre.despesas"])
    if kn == _k("lucro_bruto"):
        v = P(["dre.lucro_bruto"])
        if v is None:
            rl, c = iv("receita_liquida"), iv("custos")
            if rl not in (None, "") and c not in (None, ""):
                return rl - c
        return v
    if kn == _k("lucro_liquido"):
        v = P(["dre.lucro_ou_prejuizo_do_exercicio", "dre.resultado_operacional"])
        if v is None:
            lb, d = iv("lucro_bruto"), iv("despesas")
            if lb not in (None, "") and d not in (None, ""):
                return lb - d
        return v
    if kn == _k("ebitda"):
        ro = P(["dre.resultado_operacional", "dre.lucro_operacional"])
        dep = P(["dre.depreciacao_amortizacao_total"]) or 0
        return None if ro is None else num(ro) + num(dep)
    if kn == _k("ebitda_percentual"):
        e, rl = iv("ebitda"), iv("receita_liquida")
        if e not in (None, "") and rl not in (None, ""):
            d = safe_divide(e, rl)
            return d * 100 if d is not None else None
        return None
    if kn == _k("liquidez_corrente"):
        return safe_divide(P(["bal.ativo_circulante"]), P(["bal.passivo_circulante"]))
    if kn == _k("liquidez_geral"):
        return safe_divide(
            num(P(["bal.ativo_circulante"])) + num(P(["bal.realizavel_a_longo_prazo"])),
            num(P(["bal.passivo_circulante"])) + num(P(["bal.passivo_nao_circulante"])),
        )
    if kn == _k("liquidez_seca"):
        return safe_divide(
            num(P(["bal.ativo_circulante"])) - num(P(["bal.estoques"])),
            P(["bal.passivo_circulante"]),
        )
    if kn == _k("liquidez_imediata"):
        return safe_divide(P(["bal.contas_bancos"]), P(["bal.passivo_circulante"]))
    if kn == _k("distribuicao_resultados_percentual"):
        d = safe_divide(P(["dre.distribuicao_de_resultados"]), iv("lucro_liquido"))
        return d * 100 if d is not None else None
    if kn == _k("lucratividade_percentual"):
        d = safe_divide(iv("lucro_liquido"), iv("receita_liquida"))
        return d * 100 if d is not None else None
    if kn == _k("margem_operacional"):
        d = safe_divide(P(["dre.resultado_operacional", "dre.lucro_operacional"]), iv("receita_liquida"))
        return d * 100 if d is not None else None
    if kn == _k("margem_liquida"):
        d = safe_divide(iv("lucro_liquido"), iv("receita_liquida"))
        return d * 100 if d is not None else None
    if kn == _k("peso_deducoes_percentual"):
        d = safe_divide(iv("total_deducoes"), iv("receita_bruta"))
        return d * 100 if d is not None else None
    if kn == _k("endividamento"):
        return safe_divide(
            num(P(["bal.passivo_circulante"])) + num(P(["bal.passivo_nao_circulante"])),
            P(["bal.patrimonio_liquido", "bal.pl"]),
        )
    if kn == _k("imobilizacao"):
        return safe_divide(
            num(P(["bal.imobilizado"])) + num(P(["bal.ativo_nao_circulante"])),
            P(["bal.patrimonio_liquido", "bal.pl"]),
        )
    if kn == _k("solvencia_geral"):
        return safe_divide(
            P(["bal.ativo_total"]),
            num(P(["bal.passivo_circulante"])) + num(P(["bal.passivo_nao_circulante"])),
        )
    if kn == _k("lucratividade_acumulada_percentual"):
        d = safe_divide(P(["acum.lucro_liquido"]), P(["acum.receita_liquida"]))
        return d * 100 if d is not None else iv("lucratividade_percentual")
    if kn == _k("fluxo_resultados"):
        return iv("lucro_liquido")
    return None


def limitar_casas(val, casas=2):
    """Arredonda como o Math.round da v1 (meio para +infinito)."""
    if not _isnum(val):
        return val
    fator = 10 ** casas
    return math.floor(float(val) * fator + 0.5) / fator


def calcular_indicadores(dre_rows, bal_rows, *, soma_lucro=None, soma_receita=None,
                         formula_overrides=None, mapa_ia=None, defs=None) -> dict:
    """Retorna {key: valor_arredondado_2_casas|None} para as 23 definições."""
    defs = defs or INDICADORES
    base = criar_lookup_base(dre_rows, bal_rows)
    if soma_lucro is not None or soma_receita is not None:
        adicionar_acumulados(base, soma_lucro or 0, soma_receita or 0)
    bruto = calcular_linha(defs, base, formula_overrides, mapa_ia)
    saida = {}
    for d in defs:
        v = bruto.get(normalizar_chave(d.key))
        saida[d.key] = None if v in (None, "") else limitar_casas(v, 2)
    return saida
