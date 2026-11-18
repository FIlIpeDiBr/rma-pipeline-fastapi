"""Adaptador de IA (RF-11): interface única, Claude como implementação padrão.

Cobre a triagem (modelo barato), a extração estruturada (modelo padrão, multimodal)
e o cálculo de custo/tokens de cada chamada para auditoria em ai_calls (RF-14).
"""

import base64
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import anthropic

from .config import get_settings
from .domain.json_repair import carregar_json
from .extraction.converter import EntradaIA
from .extraction.prompts import (
    SYSTEM_EXTRACAO,
    SYSTEM_TRIAGEM,
    prompt_dre_de_balanco,
    prompt_extracao_balanco,
    prompt_extracao_dre,
    prompt_triagem,
)

MODELO_TRIAGEM = "claude-haiku-4-5-20251001"
MODELO_PADRAO = "claude-sonnet-4-6"

# Preço em USD por 1 milhão de tokens (entrada, saída), usado só para estimar custo.
# Preço muda sem aviso de deploy: a variável AI_PRECOS sobrepõe esta tabela.
PRECOS: dict[str, tuple[float, float]] = {
    MODELO_TRIAGEM: (1.0, 5.0),
    MODELO_PADRAO: (3.0, 15.0),
}
_PRECO_PADRAO = (3.0, 15.0)


def modelo_triagem() -> str:
    return get_settings().ai_modelo_triagem or MODELO_TRIAGEM


def modelo_padrao() -> str:
    return get_settings().ai_modelo_padrao or MODELO_PADRAO


def tabela_precos() -> dict[str, tuple[float, float]]:
    """Tabela padrão com as sobreposições de AI_PRECOS por cima."""
    return {**PRECOS, **get_settings().ai_precos}


@dataclass
class AiResultado:
    """Resultado de uma chamada de IA, pronto para virar um registro AiCall."""

    tipo: str  # triagem | extracao | texto
    modelo: str
    texto: str = ""
    parsed: Any = None
    input_tokens: int = 0
    output_tokens: int = 0
    custo_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    duracao_ms: int = 0
    prompt: str = ""
    sucesso: bool = True
    erro: str = ""


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _custo(modelo: str, entrada_tok: int, saida_tok: int) -> Decimal:
    """Custo estimado da chamada. Modelo fora da tabela usa o preço do modelo padrão."""
    pin, pout = tabela_precos().get(modelo, _PRECO_PADRAO)
    valor = entrada_tok / 1_000_000 * pin + saida_tok / 1_000_000 * pout
    return Decimal(str(round(valor, 6)))


def _blocos_usuario(instrucao: str, entrada: EntradaIA) -> list[dict]:
    """Monta os content blocks do usuário a partir do modo da entrada."""
    if entrada.modo == "texto":
        texto = entrada.texto or ""
        return [{"type": "text", "text": f"{instrucao}\n\n--- DOCUMENTO ---\n{texto}"}]

    b64 = base64.standard_b64encode(entrada.data or b"").decode("ascii")
    if entrada.modo == "imagem":
        return [
            {"type": "text", "text": instrucao},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": entrada.media_type or "image/png",
                    "data": b64,
                },
            },
        ]
    if entrada.modo == "pdf":
        return [
            {"type": "text", "text": instrucao},
            {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
            },
        ]
    raise ValueError(f"Modo de entrada desconhecido: {entrada.modo}")


def _resumo_prompt(instrucao: str, entrada: EntradaIA) -> str:
    """Texto guardado no ai_calls (RF-14). Binários viram um marcador."""
    if entrada.modo == "texto":
        return f"{instrucao}\n\n--- DOCUMENTO ---\n{entrada.texto or ''}"
    tam = len(entrada.data or b"")
    return f"{instrucao}\n\n[anexo {entrada.modo} {entrada.media_type}, {tam} bytes]"


def _chamar(
    tipo: str,
    modelo: str,
    system: str,
    instrucao: str,
    entrada: EntradaIA,
    *,
    max_tokens: int = 8192,
    parse_json: bool = True,
) -> AiResultado:
    """Executa a chamada, mede tempo/custo e (opcionalmente) parseia JSON.

    Nunca levanta: em falha devolve AiResultado com sucesso=False e erro preenchido,
    para o pipeline registrar a tentativa e marcar o documento como ERRO.
    """
    res = AiResultado(tipo=tipo, modelo=modelo, prompt=_resumo_prompt(instrucao, entrada))
    inicio = time.monotonic()
    try:
        # Streaming: necessário quando max_tokens é alto (o SDK recusa chamadas
        # não-streaming que possam passar de 10 min). get_final_message() junta tudo.
        with get_client().messages.stream(
            model=modelo,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": _blocos_usuario(instrucao, entrada)}],
        ) as stream:
            msg = stream.get_final_message()
    except Exception as exc:  # noqa: BLE001 - falha de API/transitória é tratada pelo pipeline
        res.sucesso = False
        res.erro = f"{exc.__class__.__name__}: {exc}"
        res.duracao_ms = int((time.monotonic() - inicio) * 1000)
        return res

    res.duracao_ms = int((time.monotonic() - inicio) * 1000)
    res.input_tokens = getattr(msg.usage, "input_tokens", 0) or 0
    res.output_tokens = getattr(msg.usage, "output_tokens", 0) or 0
    res.custo_usd = _custo(modelo, res.input_tokens, res.output_tokens)
    res.texto = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

    if parse_json:
        try:
            res.parsed = carregar_json(res.texto)
        except ValueError as exc:
            res.sucesso = False
            res.erro = str(exc)
    return res


def triar(entrada: EntradaIA, nome_arquivo: str) -> AiResultado:
    """Triagem barata: empresa, período e tipo (RF-02/08)."""
    return _chamar(
        "triagem",
        modelo_triagem(),
        SYSTEM_TRIAGEM,
        prompt_triagem(nome_arquivo),
        entrada,
        max_tokens=1024,
    )


def extrair(entrada: EntradaIA, tipo: str) -> AiResultado:
    """Extração estruturada por tipo (RF-10)."""
    instrucao = prompt_extracao_balanco() if tipo == "BALANCO" else prompt_extracao_dre()
    return _chamar(
        "extracao", modelo_padrao(), SYSTEM_EXTRACAO, instrucao, entrada, max_tokens=32000
    )


def derivar_dre_de_balanco(linhas_texto: str) -> AiResultado:
    """Deriva uma DRE a partir das contas de resultado de um balancete (RF-19)."""
    entrada = EntradaIA(modo="texto", texto=linhas_texto)
    return _chamar(
        "extracao", modelo_padrao(), SYSTEM_EXTRACAO, prompt_dre_de_balanco(), entrada,
        max_tokens=4096,
    )


SYSTEM_ANALISE = (
    "Você é um analista contábil-financeiro. Escreva em português do Brasil, tom formal e "
    "objetivo, sem markdown e sem inventar números — baseie-se apenas nos dados fornecidos."
)


def gerar_analise(titulo: str, dados_texto: str) -> AiResultado:
    """Gera um parágrafo analítico (RF-35) a partir de uma tabela ou série de gráfico."""
    entrada = EntradaIA(modo="texto", texto=dados_texto)
    instrucao = (
        f"Escreva um único parágrafo (2 a 4 frases) analisando: {titulo}. "
        "Comente variações relevantes entre os períodos. Não use listas nem títulos."
    )
    return _chamar(
        "texto", modelo_padrao(), SYSTEM_ANALISE, instrucao, entrada,
        max_tokens=600, parse_json=False,
    )
