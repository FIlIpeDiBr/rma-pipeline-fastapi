"""Dependencies de autenticação."""

import uuid

from fastapi import HTTPException, Request


def current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado.")
    return user


def current_org_id(request: Request) -> uuid.UUID:
    """org_id do usuário logado. 401 se não autenticado, 409 se a sessão é antiga."""
    user = current_user(request)
    org_id = user.get("org_id")
    if not org_id:
        raise HTTPException(409, "Sessão sem organização — faça login novamente.")
    return uuid.UUID(org_id)
