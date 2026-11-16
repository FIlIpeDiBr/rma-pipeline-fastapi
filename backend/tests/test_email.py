"""Email/Graph: parsing, filtro de anexos e formatação (sem rede)."""

import base64

from app.email import graph, ingest


class FakeResp:
    def __init__(self, data, status=200):
        self._d = data
        self.status_code = status
        self.text = ""

    def json(self):
        return self._d


def test_remetente():
    msg = {"from": {"emailAddress": {"address": "cliente@x.com"}}}
    assert graph.remetente(msg) == "cliente@x.com"
    assert graph.remetente({}) == ""


def test_ext_e_extensoes():
    assert ingest._ext("Balancete.PDF") == "pdf"
    assert ingest._ext("semext") == ""
    assert {"pdf", "xlsx", "png"} <= ingest.EXTS_DOC


def test_baixar_anexos_filtra_inline_e_nao_arquivo(monkeypatch):
    monkeypatch.setattr(graph, "obter_token", lambda: "tok")
    monkeypatch.setattr(graph, "_mailbox", lambda: "rma@x")
    b64 = base64.b64encode(b"abc").decode()
    payload = {"value": [
        {"@odata.type": "#microsoft.graph.fileAttachment", "name": "b.pdf",
         "contentType": "application/pdf", "contentBytes": b64},
        {"@odata.type": "#microsoft.graph.fileAttachment", "name": "sig.png",
         "isInline": True, "contentType": "image/png", "contentBytes": b64},
        {"@odata.type": "#microsoft.graph.itemAttachment", "name": "encaminhado"},
    ]}
    monkeypatch.setattr(graph.httpx, "get", lambda *a, **k: FakeResp(payload))
    out = graph.baixar_anexos("mid")
    assert len(out) == 1
    assert out[0]["nome"] == "b.pdf" and out[0]["data"] == b"abc"

