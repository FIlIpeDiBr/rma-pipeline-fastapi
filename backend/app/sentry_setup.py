"""Inicialização do Sentry (só quando o DSN está configurado)."""

import sentry_sdk

from .config import get_settings


def setup_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn_backend:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn_backend,
        environment=settings.environment,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
