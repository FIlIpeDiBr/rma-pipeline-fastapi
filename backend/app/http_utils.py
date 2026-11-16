"""Utilitários de resposta HTTP."""

import re
import unicodedata
from urllib.parse import quote


def content_disposition(nome_arquivo: str) -> str:
    """Cabeçalho Content-Disposition para download, seguro para qualquer nome.

    Os nomes vêm de fora (upload, anexo de email, razão social extraída pela IA).
    Montar o cabeçalho com o nome cru permite injetar cabeçalhos com aspas e quebras
    de linha, e nomes fora do Latin-1 derrubam a resposta. Aqui o nome vai duas vezes
    (RFC 6266): uma versão ASCII para clientes antigos e a original em UTF-8.
    """
    limpo = re.sub(r'[\x00-\x1f\x7f"\\/]+', "_", nome_arquivo or "").strip(" .") or "arquivo"
    ascii_ = unicodedata.normalize("NFKD", limpo).encode("ascii", "ignore").decode("ascii")
    ascii_ = ascii_.strip(" .") or "arquivo"
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(limpo, safe='')}"
