"""Formatação de números no padrão brasileiro."""

from __future__ import annotations

import math
from typing import Optional

from .semantica import Metrica


def _br(x: float, casas: int) -> str:
    s = f"{x:,.{casas}f}"
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def numero(valor: Optional[float], m: Metrica, sinal: bool = False) -> str:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"

    pre = "+" if (sinal and valor > 0) else ("-" if valor < 0 else "")
    v = abs(valor)

    if m.formato == "moeda":
        if v >= 1_000_000 and m.casas == 0:
            return f"{pre}R$ {_br(v / 1_000_000, 2)} mi"
        if v >= 10_000 and m.casas == 0:
            return f"{pre}R$ {_br(v / 1_000, 1)} mil"
        return f"{pre}R$ {_br(v, max(m.casas, 2) if v < 1000 else m.casas)}"

    if m.formato == "percentual":
        return f"{pre}{_br(v * 100, m.casas)}%"

    if m.formato == "decimal":
        return f"{pre}{_br(v, m.casas)}"

    if v >= 1_000_000:
        return f"{pre}{_br(v / 1_000_000, 2)} mi"
    return f"{pre}{_br(v, 0)}"


def moeda(v: Optional[float], casas: int = 2) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return ("-" if v < 0 else "") + f"R$ {_br(abs(v), casas)}"


def variacao_pct(atual: Optional[float], anterior: Optional[float]) -> Optional[float]:
    if atual is None or anterior is None:
        return None
    if isinstance(atual, float) and math.isnan(atual):
        return None
    if isinstance(anterior, float) and (math.isnan(anterior) or anterior == 0):
        return None
    return (atual - anterior) / abs(anterior)


def pct(v: Optional[float], casas: int = 1, sinal: bool = True) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    pre = "+" if (sinal and v > 0) else ("-" if v < 0 else "")
    return f"{pre}{_br(abs(v) * 100, casas)}%"


# Abaixo disso a variação arredonda para "0,0%" na tela. Pintar de vermelho
# um "-0,0%" faz o painel gritar por ruído de arredondamento, então o
# julgamento fica neutro quando o número que o usuário lê é zero.
DESPREZIVEL = 5e-4


def julgar(delta: Optional[float],
           bom_quando_sobe: bool = True) -> Optional[bool]:
    """True (melhorou), False (piorou) ou None (não deu para dizer).

    None cobre os dois casos em que colorir seria mentira: variação ausente
    e variação que some no arredondamento da tela.
    """
    if delta is None or (isinstance(delta, float) and math.isnan(delta)):
        return None
    if abs(delta) < DESPREZIVEL:
        return None
    return (delta > 0) == bom_quando_sobe


def seta(delta: Optional[float], bom_quando_sobe: bool = True) -> str:
    """Emoji de direção já lido em termos de negócio, não de sinal."""
    if julgar(delta, bom_quando_sobe) is None:
        return "▪"
    return "▲" if delta > 0 else "▼"


def cor_delta(delta: Optional[float], bom_quando_sobe: bool = True) -> str:
    bom = julgar(delta, bom_quando_sobe)
    if bom is None:
        return "#6b7280"
    return "#15803d" if bom else "#b91c1c"
