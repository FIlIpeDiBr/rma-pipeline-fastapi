"""Utilitários de requisição e resposta HTTP."""

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


class ArquivoGrandeDemais(Exception):
    """O upload passou do limite configurado."""


async def ler_com_limite(arquivo, limite_bytes: int, bloco: int = 1024 * 1024) -> bytes:
    """Lê um upload em blocos e para assim que ele passa do limite.

    `await arquivo.read()` traria o arquivo inteiro para a memória antes de qualquer
    checagem: um envio de 2 GB ocuparia 2 GB para só então ser recusado. Aqui a leitura
    para no primeiro bloco além do limite.
    """
    partes: list[bytes] = []
    total = 0
    while True:
        pedaco = await arquivo.read(bloco)
        if not pedaco:
            break
        total += len(pedaco)
        if total > limite_bytes:
            raise ArquivoGrandeDemais(f"arquivo excede {limite_bytes} bytes")
        partes.append(pedaco)
    return b"".join(partes)
