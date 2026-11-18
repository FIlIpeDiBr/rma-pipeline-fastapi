"""Aviso de progresso em tempo real: NOTIFY do Postgres com um ouvinte por processo.

Quem grava um evento de progresso (worker) emite um NOTIFY na mesma transação. A API
mantém uma única conexão em LISTEN e repassa o aviso, em memória, às conexões SSE da
organização correspondente. Assim o stream só consulta o banco quando há algo novo,
em vez de consultar a cada segundo e meio por aba aberta.

O aviso não carrega o evento, só "há novidade para a organização X": a fonte de verdade
continua sendo a tabela `job_events`, e perder um aviso custa no máximo um atraso.
"""

import asyncio
import contextlib

import psycopg
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

CANAL = "rma_eventos"
RECONECTAR_APOS = 2.0  # segundos até a primeira nova tentativa quando o LISTEN cai
RECONECTAR_TETO = 60.0  # teto do intervalo, que dobra a cada falha seguida

log = structlog.get_logger()


def notificar(db: Session, org_id) -> None:
    """Emite o aviso na transação corrente; o Postgres só o entrega no commit.

    Fora do Postgres (testes em SQLite) não faz nada: o stream cai na consulta periódica.
    """
    if org_id is None or db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_notify(:canal, :org)"), {"canal": CANAL, "org": str(org_id)})


class BarramentoEventos:
    """Distribui, dentro do processo, o aviso "há evento novo para a organização X"."""

    def __init__(self) -> None:
        self._assinantes: dict[str, set[asyncio.Event]] = {}
        self._tarefa: asyncio.Task | None = None
        self.ativo = False  # True enquanto a conexão em LISTEN está de pé

    # --- assinatura (conexões SSE) -------------------------------------------

    def assinar(self, org_id) -> asyncio.Event:
        sinal = asyncio.Event()
        self._assinantes.setdefault(str(org_id), set()).add(sinal)
        return sinal

    def cancelar(self, org_id, sinal: asyncio.Event) -> None:
        grupo = self._assinantes.get(str(org_id))
        if not grupo:
            return
        grupo.discard(sinal)
        if not grupo:
            del self._assinantes[str(org_id)]

    def avisar(self, org_id) -> int:
        """Acorda os assinantes da organização. Devolve quantos foram acordados."""
        sinais = self._assinantes.get(str(org_id), ())
        for sinal in sinais:
            sinal.set()
        return len(sinais)

    def avisar_todos(self) -> None:
        for sinais in self._assinantes.values():
            for sinal in sinais:
                sinal.set()

    @property
    def assinantes(self) -> int:
        return sum(len(sinais) for sinais in self._assinantes.values())

    # --- ouvinte (um por processo) --------------------------------------------

    async def iniciar(self, conninfo: str) -> None:
        if self._tarefa is None or self._tarefa.done():
            self._tarefa = asyncio.create_task(self._escutar(conninfo), name="barramento-eventos")

    async def parar(self) -> None:
        if self._tarefa is not None:
            self._tarefa.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tarefa
        self._tarefa = None
        self.ativo = False

    async def _escutar(self, conninfo: str) -> None:
        """Mantém o LISTEN de pé, reconectando com intervalo crescente quando cai."""
        espera = RECONECTAR_APOS
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    conninfo, autocommit=True, connect_timeout=5
                ) as conn:
                    await conn.execute(f"LISTEN {CANAL}")
                    espera = RECONECTAR_APOS
                    log.info("barramento_eventos_ouvindo")
                    # Avisos emitidos enquanto a conexão esteve fora se perderam:
                    # acorda todos para que consultem o banco uma vez.
                    self.avisar_todos()
                    self.ativo = True
                    async for aviso in conn.notifies():
                        self.avisar(aviso.payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - sem LISTEN o stream volta a consultar
                log.warning("barramento_eventos_indisponivel", erro=exc.__class__.__name__)
            finally:
                # Quem estava dormindo à espera de aviso acorda e passa à consulta periódica.
                self.ativo = False
                self.avisar_todos()
            await asyncio.sleep(espera)
            espera = min(espera * 2, RECONECTAR_TETO)


barramento = BarramentoEventos()
