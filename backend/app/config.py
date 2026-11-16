"""Configuração tipada via variáveis de ambiente (12-factor)."""

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# O .env fica na RAIZ do repositório. Também aceita backend/.env e
# o cwd como fallbacks. Em produção (Render) nada disso é usado: as variáveis
# vêm do ambiente e têm precedência sobre qualquer .env.
_RAIZ = Path(__file__).resolve().parents[2]
_ENV_FILES = (_RAIZ / ".env", _RAIZ / "backend" / ".env", ".env")

# Valor de desenvolvimento. Em produção ele é recusado (ver Settings).
SECRET_KEY_DEV = "dev-secret-troque-em-producao"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore"
    )

    service_role: str = "web"  # web | worker
    environment: str = "development"
    app_base_url: str = "http://localhost:8000"
    # Em dev, a SPA roda no Vite; o pós-login redireciona para cá. Vazio = "/".
    frontend_url: str = ""
    secret_key: str = SECRET_KEY_DEV
    # Tenant único nesta fase: org criada/recuperada por este nome no 1º login.
    org_nome: str = "Escritório Demonstração"
    max_upload_mb: int = 25

    database_url: str = "postgresql://postgres:postgres@localhost:5432/rma"

    anthropic_api_key: str = ""

    storage_endpoint: str = ""
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_bucket: str = "rma-arquivos"

    sentry_dsn_backend: str = ""

    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    rma_mailbox: str = ""
    email_poll_enabled: bool = True  # polling periódico da caixa rma@

    @field_validator("app_base_url", "frontend_url")
    @classmethod
    def _normaliza_url(cls, v: str) -> str:
        """Garante URL absoluta: remove barra final e prefixa https:// se faltar
        o esquema (evita AADSTS90102 quando APP_BASE_URL vem sem http/https)."""
        v = (v or "").strip().rstrip("/")
        if v and not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v

    @model_validator(mode="after")
    def _exige_segredo_em_producao(self) -> Self:
        """A chave assina o cookie de sessão. Com o valor padrão, que é público,
        qualquer pessoa forja uma sessão; em produção a aplicação não sobe assim."""
        if self.is_production and self.secret_key == SECRET_KEY_DEV:
            raise ValueError("SECRET_KEY é obrigatória quando ENVIRONMENT=production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
