"""SSE — push de progresso para o portal (RNF-04 / RF-50).

`/api/events/stream` empurra ao cliente cada evento novo de `job_events` da organização.
Com o barramento ativo (LISTEN/NOTIFY, ver `app.eventos`), o stream dorme até ser avisado
e só então consulta o banco. Sem o barramento (banco fora, SQLite nos testes) ele volta a
consultar em intervalo curto — o comportamento anterior, mantido como reserva.
"""

import asyncio
import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..auth.deps import current_org_id
from ..eventos import BarramentoEventos, barramento

router = APIRouter()

_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}

ESPERA_AVISO = 20.0  # com o barramento ativo: teto de espera; ao estourar, manda um ping
ESPERA_CONSULTA = 1.5  # sem o barramento: intervalo da consulta periódica


def _buscar_eventos(org_id: uuid.UUID, desde: dt.datetime) -> list[dict]:
    from ..db import SessionLocal
    from ..models import JobEvent

    db = SessionLocal()
    try:
        eventos = db.scalars(
            select(JobEvent)
            .where(JobEvent.org_id == org_id, JobEvent.criado_em >= desde)
            .order_by(JobEvent.criado_em.asc())
            .limit(200)
        ).all()
        return [
            {
                "id": str(e.id),
                "document_id": str(e.document_id) if e.document_id else None,
                "etapa": e.etapa,
                "progresso": e.progresso,
                "status": e.status,
                "mensagem": e.mensagem,
                "criado_em": e.criado_em.isoformat(),
            }
            for e in eventos
        ]
    finally:
        db.close()


async def fluxo_eventos(
    org_id: uuid.UUID,
    *,
    buscar: Callable[[uuid.UUID, dt.datetime], Awaitable[list[dict]]],
    desconectado: Callable[[], Awaitable[bool]],
    barramento: BarramentoEventos,
    espera_aviso: float = ESPERA_AVISO,
    espera_consulta: float = ESPERA_CONSULTA,
) -> AsyncIterator[str]:
    """Gera as linhas do stream. Isolado da rota para ser testável sem HTTP nem banco."""
    # Assina antes da primeira consulta: um aviso que chegue durante a consulta fica
    # registrado no sinal e provoca nova consulta, em vez de se perder.
    sinal = barramento.assinar(org_id)
    desde = dt.datetime.now(dt.UTC)
    vistos: set[str] = set()
    try:
        yield ": conectado\n\n"
        while True:
            if await desconectado():
                break
            sinal.clear()
            try:
                eventos = await buscar(org_id, desde)
            except Exception:  # noqa: BLE001 - não derruba o stream por falha transitória de DB
                eventos = []
            for ev in eventos:
                if ev["id"] in vistos:
                    continue
                vistos.add(ev["id"])
                desde = dt.datetime.fromisoformat(ev["criado_em"])
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if len(vistos) > 2000:
                vistos.clear()

            if not barramento.ativo:
                await asyncio.sleep(espera_consulta)
                continue
            try:
                await asyncio.wait_for(sinal.wait(), timeout=espera_aviso)
            except TimeoutError:
                # Mantém a conexão viva em proxies e serve de consulta de segurança.
                yield ": ping\n\n"
    finally:
        barramento.cancelar(org_id, sinal)


@router.get("/events/stream")
async def stream(
    request: Request,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
) -> StreamingResponse:
    async def buscar(org: uuid.UUID, desde: dt.datetime) -> list[dict]:
        return await asyncio.to_thread(_buscar_eventos, org, desde)

    gen = fluxo_eventos(
        org_id, buscar=buscar, desconectado=request.is_disconnected, barramento=barramento
    )
    return StreamingResponse(gen, media_type="text/event-stream", headers=_HEADERS)
