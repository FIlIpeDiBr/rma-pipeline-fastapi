"""Informações do usuário logado."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ..auth.deps import current_user

router = APIRouter()


@router.get("/me")
def me(user: Annotated[dict, Depends(current_user)]) -> dict:
    return user
