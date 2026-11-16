"""Login com Microsoft Entra ID (OIDC) — RF-50/RNF-08."""

import structlog
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

from ..config import get_settings
from ..db import SessionLocal
from .users import upsert_user

router = APIRouter()
settings = get_settings()
log = structlog.get_logger()

oauth = OAuth()
if settings.azure_client_id:
    oauth.register(
        name="entra",
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        server_metadata_url=(
            f"https://login.microsoftonline.com/{settings.azure_tenant_id}"
            "/v2.0/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid profile email"},
    )


def _entra():
    client = getattr(oauth, "entra", None)
    if client is None:
        raise HTTPException(503, "Login não configurado (AZURE_CLIENT_ID ausente).")
    return client


@router.get("/login")
async def login(request: Request):
    redirect_uri = f"{settings.app_base_url}/auth/callback"
    return await _entra().authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request):
    token = await _entra().authorize_access_token(request)
    claims = token.get("userinfo") or {}
    oid = claims.get("oid") or claims.get("sub")
    if not oid:
        raise HTTPException(401, "Resposta do Entra sem identificador de usuário.")

    # Upsert do usuário + vínculo com a org (tenant único nesta fase).
    db = SessionLocal()
    try:
        user = upsert_user(db, claims)
        db.commit()
        sess = {
            "id": str(user.id),
            "org_id": str(user.org_id),
            "oid": oid,
            "email": user.email,
            "nome": user.nome,
        }
    except Exception:  # noqa: BLE001 - sem DB ainda dá pra navegar; loga e segue com claims
        db.rollback()
        log.warning("upsert_user_falhou", exc_info=True)
        sess = {
            "id": "",
            "org_id": "",
            "oid": oid,
            "email": claims.get("email") or claims.get("preferred_username") or "",
            "nome": claims.get("name") or "",
        }
    finally:
        db.close()

    request.session["user"] = sess
    return RedirectResponse(settings.frontend_url or "/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(settings.frontend_url or "/")
