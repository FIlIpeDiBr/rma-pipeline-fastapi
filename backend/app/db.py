"""Engine e sessões SQLAlchemy (psycopg 3)."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def sqlalchemy_url() -> str:
    url = get_settings().database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


# Sem tempo limite, uma conexão a um host que não responde fica pendurada para sempre,
# inclusive no /healthz. O parâmetro só existe no driver do Postgres.
_connect_args = {"connect_timeout": 5} if sqlalchemy_url().startswith("postgresql") else {}
engine = create_engine(
    sqlalchemy_url(), pool_pre_ping=True, pool_size=5, connect_args=_connect_args
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Dependency do FastAPI: uma sessão por request."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
