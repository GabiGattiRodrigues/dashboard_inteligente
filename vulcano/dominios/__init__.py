"""
Registro de domínios.

Acrescentar um domínio ao Vulcano é escrever um arquivo neste pacote e
inclui-lo na lista abaixo. Nenhum motor precisa ser tocado.
"""

from ..semantica import Dominio
from .credito import DOMINIO as CREDITO
from .marketing import DOMINIO as MARKETING
from .produto import DOMINIO as PRODUTO

DOMINIOS: dict[str, Dominio] = {
    d.chave: d for d in (MARKETING, CREDITO, PRODUTO)
}

ORDEM = ["marketing", "credito", "produto"]


def obter(chave: str) -> Dominio:
    if chave not in DOMINIOS:
        raise KeyError(f"domínio desconhecido: {chave}")
    return DOMINIOS[chave]


def listar() -> list[Dominio]:
    return [DOMINIOS[c] for c in ORDEM if c in DOMINIOS]
