"""Storage de arquivos S3-compatible (Cloudflare R2)."""

import boto3
from botocore.config import Config

from .config import get_settings


def _client():
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.storage_endpoint,
        aws_access_key_id=s.storage_access_key,
        aws_secret_access_key=s.storage_secret_key,
        config=Config(signature_version="s3v4", region_name="auto"),
    )


def save_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    s = get_settings()
    _client().put_object(Bucket=s.storage_bucket, Key=key, Body=data, ContentType=content_type)
    return key


def get_bytes(key: str) -> bytes:
    s = get_settings()
    obj = _client().get_object(Bucket=s.storage_bucket, Key=key)
    return obj["Body"].read()


def delete(key: str) -> None:
    s = get_settings()
    _client().delete_object(Bucket=s.storage_bucket, Key=key)


def healthcheck() -> str:
    """Retorna 'ok' ou o tipo do erro (não levanta exceção).

    O /healthz é público: devolve só a classe da exceção, sem endpoint nem bucket.
    """
    s = get_settings()
    if not s.storage_endpoint:
        return "não configurado"
    try:
        _client().head_bucket(Bucket=s.storage_bucket)
        return "ok"
    except Exception as exc:  # noqa: BLE001 - health check reporta qualquer falha
        return f"erro: {exc.__class__.__name__}"
