"""Progresso em tempo real: barramento em memória e gerador do stream SSE.

Nada aqui usa banco ou HTTP: o barramento é exercitado direto e o gerador recebe
uma consulta falsa. O caminho com Postgres real (NOTIFY → LISTEN) está nos testes
de integração.
"""

import asyncio
import datetime as dt
import json
import uuid

from app.api.events import fluxo_eventos
from app.eventos import BarramentoEventos

ORG = uuid.uuid4()
OUTRA = uuid.uuid4()


def _evento(n: int) -> dict:
    return {
        "id": f"ev-{n}",
        "document_id": None,
        "etapa": "extracao",
        "progresso": n,
        "status": "info",
        "mensagem": "",
        "criado_em": dt.datetime(2026, 1, 1, 12, 0, n, tzinfo=dt.UTC).isoformat(),
    }


class _Fonte:
    """Consulta falsa: devolve o que estiver na fila e conta as chamadas."""

    def __init__(self) -> None:
        self.pendentes: list[dict] = []
        self.chamadas = 0

    async def buscar(self, org_id, desde) -> list[dict]:
        self.chamadas += 1
        prontos, self.pendentes = self.pendentes, []
        return prontos


async def _nunca() -> bool:
    return False


def _dados(linha: str) -> dict:
    assert linha.startswith("data: ")
    return json.loads(linha[len("data: ") :])


# --- barramento -----------------------------------------------------------------


def test_aviso_acorda_so_os_assinantes_da_organizacao():
    async def cenario():
        b = BarramentoEventos()
        a1, a2, outro = b.assinar(ORG), b.assinar(ORG), b.assinar(OUTRA)
        assert b.avisar(ORG) == 2
        assert a1.is_set() and a2.is_set() and not outro.is_set()

    asyncio.run(cenario())


def test_aviso_aceita_o_id_como_texto():
    """O payload do NOTIFY chega como texto; a assinatura é feita com UUID."""

    async def cenario():
        b = BarramentoEventos()
        sinal = b.assinar(ORG)
        assert b.avisar(str(ORG)) == 1
        assert sinal.is_set()

    asyncio.run(cenario())


def test_cancelar_remove_o_assinante_e_limpa_o_grupo():
    async def cenario():
        b = BarramentoEventos()
        s1, s2 = b.assinar(ORG), b.assinar(ORG)
        b.cancelar(ORG, s1)
        assert b.assinantes == 1
        b.cancelar(ORG, s2)
        assert b.assinantes == 0
        assert b.avisar(ORG) == 0
        b.cancelar(ORG, s2)  # cancelar de novo não quebra

    asyncio.run(cenario())


def test_avisar_todos_acorda_todas_as_organizacoes():
    async def cenario():
        b = BarramentoEventos()
        s1, s2 = b.assinar(ORG), b.assinar(OUTRA)
        b.avisar_todos()
        assert s1.is_set() and s2.is_set()

    asyncio.run(cenario())


def test_ouvinte_sem_banco_fica_inativo_e_para_limpo():
    """Sem Postgres acessível o barramento não derruba nada: segue inativo."""

    async def cenario():
        b = BarramentoEventos()
        await b.iniciar("postgresql://ninguem@127.0.0.1:1/nada")
        await asyncio.sleep(0.05)
        assert b.ativo is False
        await b.parar()
        assert b._tarefa is None

    asyncio.run(cenario())


# --- gerador do stream -----------------------------------------------------------


def test_stream_com_barramento_dorme_ate_o_aviso():
    async def cenario():
        b = BarramentoEventos()
        b.ativo = True
        fonte = _Fonte()
        gen = fluxo_eventos(
            ORG, buscar=fonte.buscar, desconectado=_nunca, barramento=b, espera_aviso=30
        )
        assert await gen.__anext__() == ": conectado\n\n"

        proximo = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)
        # Uma consulta ao conectar e depois silêncio: nada de consulta periódica.
        assert fonte.chamadas == 1
        assert not proximo.done()

        fonte.pendentes = [_evento(1)]
        b.avisar(ORG)
        linha = await asyncio.wait_for(proximo, timeout=2)
        assert _dados(linha)["id"] == "ev-1"
        assert fonte.chamadas == 2
        await gen.aclose()
        assert b.assinantes == 0

    asyncio.run(cenario())


def test_stream_ignora_aviso_de_outra_organizacao():
    async def cenario():
        b = BarramentoEventos()
        b.ativo = True
        fonte = _Fonte()
        gen = fluxo_eventos(
            ORG, buscar=fonte.buscar, desconectado=_nunca, barramento=b, espera_aviso=30
        )
        await gen.__anext__()
        proximo = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.05)
        b.avisar(OUTRA)
        await asyncio.sleep(0.05)
        assert fonte.chamadas == 1
        assert not proximo.done()
        proximo.cancel()
        await asyncio.gather(proximo, return_exceptions=True)
        await gen.aclose()

    asyncio.run(cenario())


def test_stream_sem_barramento_consulta_em_intervalo():
    async def cenario():
        b = BarramentoEventos()  # inativo
        fonte = _Fonte()
        gen = fluxo_eventos(
            ORG, buscar=fonte.buscar, desconectado=_nunca, barramento=b, espera_consulta=0.01
        )
        await gen.__anext__()
        proximo = asyncio.create_task(gen.__anext__())
        await asyncio.sleep(0.25)
        assert fonte.chamadas >= 3  # consultou várias vezes sem ninguém avisar
        fonte.pendentes = [_evento(2)]
        linha = await asyncio.wait_for(proximo, timeout=2)
        assert _dados(linha)["id"] == "ev-2"
        await gen.aclose()

    asyncio.run(cenario())


def test_stream_manda_ping_quando_nada_acontece():
    async def cenario():
        b = BarramentoEventos()
        b.ativo = True
        fonte = _Fonte()
        gen = fluxo_eventos(
            ORG, buscar=fonte.buscar, desconectado=_nunca, barramento=b, espera_aviso=0.02
        )
        await gen.__anext__()
        assert await asyncio.wait_for(gen.__anext__(), timeout=2) == ": ping\n\n"
        await gen.aclose()

    asyncio.run(cenario())


def test_stream_nao_repete_evento_ja_enviado():
    async def cenario():
        b = BarramentoEventos()
        fonte = _Fonte()
        gen = fluxo_eventos(
            ORG, buscar=fonte.buscar, desconectado=_nunca, barramento=b, espera_consulta=0.01
        )
        await gen.__anext__()
        fonte.pendentes = [_evento(1)]
        assert _dados(await asyncio.wait_for(gen.__anext__(), timeout=2))["id"] == "ev-1"
        # A consulta usa ">= desde": o mesmo evento volta e não pode ser reenviado.
        fonte.pendentes = [_evento(1), _evento(2)]
        assert _dados(await asyncio.wait_for(gen.__anext__(), timeout=2))["id"] == "ev-2"
        await gen.aclose()

    asyncio.run(cenario())


def test_stream_sobrevive_a_falha_da_consulta():
    async def cenario():
        b = BarramentoEventos()
        chamadas = 0

        async def buscar(org_id, desde):
            nonlocal chamadas
            chamadas += 1
            if chamadas == 1:
                raise RuntimeError("banco fora")
            return [_evento(3)]

        gen = fluxo_eventos(
            ORG, buscar=buscar, desconectado=_nunca, barramento=b, espera_consulta=0.01
        )
        await gen.__anext__()
        assert _dados(await asyncio.wait_for(gen.__anext__(), timeout=2))["id"] == "ev-3"
        await gen.aclose()

    asyncio.run(cenario())


def test_stream_encerra_e_cancela_assinatura_ao_desconectar():
    async def cenario():
        b = BarramentoEventos()
        fonte = _Fonte()
        respostas = iter([False, True])

        async def desconectado() -> bool:
            return next(respostas)

        gen = fluxo_eventos(
            ORG, buscar=fonte.buscar, desconectado=desconectado, barramento=b, espera_consulta=0.01
        )
        linhas = [linha async for linha in gen]
        assert linhas == [": conectado\n\n"]
        assert b.assinantes == 0

    asyncio.run(cenario())
