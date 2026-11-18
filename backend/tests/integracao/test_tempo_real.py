"""Progresso em tempo real com o NOTIFY do Postgres de verdade."""

import asyncio
import json
import time

import pytest

pytestmark = pytest.mark.integracao


async def _nunca() -> bool:
    return False


def test_evento_gravado_chega_ao_stream_pelo_notify(org):
    """Grava um evento como o worker faria e espera vê-lo no stream.

    O stream fica parado à espera de aviso por até 30 s; se a linha chega em poucos
    segundos, foi o NOTIFY que o acordou, e não uma consulta periódica.
    """
    from app.api.events import _buscar_eventos, fluxo_eventos
    from app.eventos import BarramentoEventos
    from app.extraction.persist import emitir_evento
    from app.jobs import _conninfo

    async def buscar(org_id, desde):
        return await asyncio.to_thread(_buscar_eventos, org_id, desde)

    async def cenario() -> dict:
        barramento = BarramentoEventos()
        await barramento.iniciar(_conninfo())
        try:
            for _ in range(100):
                if barramento.ativo:
                    break
                await asyncio.sleep(0.05)
            assert barramento.ativo, "o LISTEN não subiu"

            stream = fluxo_eventos(
                org.id, buscar=buscar, desconectado=_nunca, barramento=barramento, espera_aviso=30
            )
            assert await stream.__anext__() == ": conectado\n\n"
            proxima = asyncio.create_task(stream.__anext__())
            await asyncio.sleep(0.5)
            assert not proxima.done()  # nada aconteceu ainda: o stream está dormindo

            await asyncio.to_thread(emitir_evento, org.id, None, "Extraindo", 40)
            linha = await asyncio.wait_for(proxima, timeout=5)
            await stream.aclose()
            return json.loads(linha.removeprefix("data: "))
        finally:
            await barramento.parar()

    evento = asyncio.run(cenario())
    assert (evento["etapa"], evento["progresso"], evento["status"]) == ("Extraindo", 40, "info")


def test_barramento_da_aplicacao_recebe_o_aviso(cliente, org):
    """Com a aplicação de pé (lifespan), o barramento global está em LISTEN e é avisado."""
    from app.eventos import barramento
    from app.extraction.persist import emitir_evento

    def esperar(condicao, segundos: float = 5.0) -> bool:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if condicao():
                return True
            time.sleep(0.05)
        return False

    assert esperar(lambda: barramento.ativo), "o LISTEN da aplicação não subiu"
    sinal = barramento.assinar(org.id)
    try:
        emitir_evento(org.id, None, "Triagem", 10)
        assert esperar(sinal.is_set), "o NOTIFY não chegou ao barramento"
    finally:
        barramento.cancelar(org.id, sinal)
