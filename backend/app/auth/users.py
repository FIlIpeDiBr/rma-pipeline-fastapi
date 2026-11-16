"""Resolução de org/usuário no login (tenant único nesta fase)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Org, User


def get_or_create_org(db: Session) -> Org:
    """Org única do escritório, criada/recuperada pelo nome configurado."""
    nome = get_settings().org_nome
    org = db.scalar(select(Org).where(Org.nome == nome))
    if org is None:
        org = Org(nome=nome)
        db.add(org)
        db.flush()
    return org


def upsert_user(db: Session, claims: dict) -> User:
    """Cria/atualiza o usuário a partir dos claims do Entra e vincula à org."""
    oid = claims.get("oid") or claims.get("sub") or ""
    email = claims.get("email") or claims.get("preferred_username") or ""
    nome = claims.get("name") or ""

    org = get_or_create_org(db)
    user = db.scalar(select(User).where(User.entra_oid == oid))
    if user is None:
        user = User(entra_oid=oid, org_id=org.id, email=email, nome=nome)
        db.add(user)
    else:
        user.email = email or user.email
        user.nome = nome or user.nome
        user.org_id = org.id
    db.flush()
    return user
