"""Saúde da aplicação e exigência de login, sem depender de banco ou rede."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import health
from app.main import app

client = TestClient(app)


class _BancoNoAr:
    class _Conexao:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, _sql):
            return None

    def connect(self):
        return self._Conexao()


class _BancoForaDoAr:
    def connect(self):
        raise OperationalError("SELECT 1", None, Exception("conexão recusada em db.interno:5432"))


def test_healthz_com_banco_no_ar(monkeypatch):
    monkeypatch.setattr(health, "engine", _BancoNoAr())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok", "storage": "não configurado"}


def test_healthz_reporta_banco_fora_do_ar_sem_vazar_detalhes(monkeypatch):
    monkeypatch.setattr(health, "engine", _BancoForaDoAr())
    resp = client.get("/healthz")
    assert resp.status_code == 200, "o health check responde mesmo sem banco"
    assert resp.json()["db"] == "erro: OperationalError"
    assert "db.interno" not in resp.text


def test_me_exige_autenticacao():
    assert client.get("/api/me").status_code == 401


def test_api_sem_sessao_responde_401_e_nao_toca_no_banco():
    for metodo, caminho in [
        ("get", "/api/documents"),
        ("get", "/api/companies"),
        ("get", "/api/reports"),
        ("post", "/api/indicators/generate-pending"),
        ("get", "/api/email/messages"),
    ]:
        assert getattr(client, metodo)(caminho).status_code == 401, caminho
