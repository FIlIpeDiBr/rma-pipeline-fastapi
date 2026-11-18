"""Limite de upload durante a leitura e configuração de modelos e preços de IA."""

import asyncio
from decimal import Decimal

import pytest

from app import ai
from app.config import Settings
from app.http_utils import ArquivoGrandeDemais, ler_com_limite


class _Upload:
    """Dublê de UploadFile: entrega o conteúdo em blocos e conta quanto foi lido."""

    def __init__(self, tamanho: int):
        self._resta = tamanho
        self.lido = 0

    async def read(self, n: int = -1) -> bytes:
        pedaco = min(self._resta, n if n > 0 else self._resta)
        self._resta -= pedaco
        self.lido += pedaco
        return b"x" * pedaco


def test_arquivo_dentro_do_limite_e_lido_inteiro():
    up = _Upload(2500)
    dados = asyncio.run(ler_com_limite(up, limite_bytes=3000, bloco=1000))
    assert len(dados) == 2500


def test_arquivo_exatamente_no_limite_e_aceito():
    assert len(asyncio.run(ler_com_limite(_Upload(3000), limite_bytes=3000, bloco=1000))) == 3000


def test_leitura_para_no_primeiro_bloco_alem_do_limite():
    up = _Upload(1_000_000)
    with pytest.raises(ArquivoGrandeDemais):
        asyncio.run(ler_com_limite(up, limite_bytes=3000, bloco=1000))
    assert up.lido == 4000, "só o necessário para saber que passou do limite"


def test_arquivo_vazio_devolve_bytes_vazios():
    assert asyncio.run(ler_com_limite(_Upload(0), limite_bytes=10)) == b""


# --- IA: modelos e preços ---------------------------------------------------

def _com_settings(monkeypatch, **campos):
    settings = Settings(_env_file=None, **campos)
    monkeypatch.setattr(ai, "get_settings", lambda: settings)


def test_sem_configuracao_valem_os_modelos_e_precos_do_codigo(monkeypatch):
    _com_settings(monkeypatch)
    assert ai.modelo_triagem() == ai.MODELO_TRIAGEM
    assert ai.modelo_padrao() == ai.MODELO_PADRAO
    # 1 milhão de tokens de entrada + 1 milhão de saída, na tabela padrão.
    pin, pout = ai.PRECOS[ai.MODELO_PADRAO]
    assert ai._custo(ai.MODELO_PADRAO, 1_000_000, 1_000_000) == Decimal(str(pin + pout))


def test_preco_e_modelo_podem_ser_trocados_por_variavel_de_ambiente(monkeypatch):
    _com_settings(
        monkeypatch,
        ai_modelo_padrao="modelo-novo",
        ai_precos={"modelo-novo": (2.0, 10.0), ai.MODELO_TRIAGEM: (0.5, 2.5)},
    )
    assert ai.modelo_padrao() == "modelo-novo"
    assert ai._custo("modelo-novo", 500_000, 100_000) == Decimal("2.0")  # 1.0 + 1.0
    assert ai._custo(ai.MODELO_TRIAGEM, 1_000_000, 0) == Decimal("0.5"), "sobrepõe o padrão"


def test_ai_precos_vem_do_ambiente_como_json(monkeypatch):
    monkeypatch.setenv("AI_PRECOS", '{"modelo-x": [4, 20]}')
    assert Settings(_env_file=None).ai_precos == {"modelo-x": (4.0, 20.0)}
