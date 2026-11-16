"""SSE — push de progresso para o portal (RNF-04 / RF-50).

`/api/events/stream` faz polling em job_events (por org) e empurra cada novo
evento ao cliente.
"""

import asyncio
import datetime as dt
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..auth.deps import current_org_id

router = APIRouter()

_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


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


@router.get("/events/stream")
async def stream(
    request: Request,
    org_id: Annotated[uuid.UUID, Depends(current_org_id)],
) -> StreamingResponse:
    async def gen():
        desde = dt.datetime.now(dt.UTC)
        vistos: set[str] = set()
        yield ": conectado\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                eventos = await asyncio.to_thread(_buscar_eventos, org_id, desde)
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
            await asyncio.sleep(1.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_HEADERS)

