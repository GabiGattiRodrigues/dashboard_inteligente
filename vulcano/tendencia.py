"""
Leitura de tendência.

Existe porque "subiu vs ontem" e "está subindo" são perguntas diferentes, e a
segunda e a que o executivo faz. Um dia acima do anterior não é tendência: pode
ser ruído, pode ser dia da semana.

O que este modulo separa
------------------------
- **Inclinação** por mínimos quadrados sobre o tempo, com erro padrão e
  estatística t. Sem o t, qualquer série tem inclinação diferente de zero e
  todo ruído vira "tendência de alta".
- **Sazonalidade semanal**, medida antes de ler o nível. No varejo o efeito de
  dia da semana costuma ser maior que o efeito que se quer medir.
- **Momento**: últimos 7 dias contra os 28 anteriores, que responde
  "acelerou ou desacelerou" sem depender da reta.
- **Sequência**: quantos dias seguidos acima ou abaixo da mediana movel. E o
  sinal mais legível de mudanca de patamar para quem não lê gráfico.

Sem dependência de scipy: a inclinação e o t são contas fechadas de OLS
simples, e o p-valor sai de uma aproximação normal, honesta para n > 30.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

from .dados import Filtros, serie_diaria
from .formatacao import numero, pct
from .semantica import Dominio

DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


@dataclass
class Tendencia:
    dominio: Dominio
    chave_metrica: str
    serie: pd.DataFrame          # data, valor, media_movel
    inclinacao_dia: float        # unidades da metrica por dia
    inclinacao_pct_mes: float    # % ao mes sobre o nivel medio
    t_stat: float
    p_valor: float
    significante: bool
    direcao: str                 # "alta", "baixa", "estavel"
    nivel_medio: float
    media_7: float
    media_28_anterior: float
    momento: Optional[float]     # variacao % entre os dois
    sequencia: int               # dias seguidos acima(+)/abaixo(-) da mediana
    amplitude_semanal: Optional[float]
    perfil_semanal: pd.DataFrame
    n_dias: int


def _ols(y: np.ndarray) -> tuple[float, float, float]:
    """Inclinação, erro padrão e t de uma regressão de y sobre o índice."""
    n = len(y)
    if n < 3:
        return 0.0, float("nan"), 0.0
    x = np.arange(n, dtype=float)
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    if sxx == 0:
        return 0.0, float("nan"), 0.0
    b = ((x - xm) * (y - ym)).sum() / sxx
    resid = y - (ym + b * (x - xm))
    gl = n - 2
    s2 = (resid ** 2).sum() / gl if gl > 0 else float("nan")
    ep = math.sqrt(s2 / sxx) if s2 == s2 and s2 > 0 else float("nan")
    t = b / ep if ep and ep == ep and ep > 0 else 0.0
    return float(b), float(ep), float(t)


def _p_bilateral(t: float) -> float:
    """Aproximação normal do p-valor bilateral. Adequada para n > 30."""
    if not np.isfinite(t):
        return float("nan")
    return float(2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))))


def analisar(
    con: duckdb.DuckDBPyConnection,
    dom: Dominio,
    chave_metrica: str,
    inicio: date,
    fim: date,
    filtros: Optional[Filtros] = None,
    janela_movel: int = 7,
) -> Optional[Tendencia]:
    df = serie_diaria(con, dom, [chave_metrica], inicio, fim, filtros)
    if df.empty or len(df) < 5:
        return None

    df = df[["data", chave_metrica]].rename(columns={chave_metrica: "valor"})
    df = df.dropna(subset=["valor"]).sort_values("data").reset_index(drop=True)
    if len(df) < 5:
        return None

    df["media_movel"] = df["valor"].rolling(janela_movel, min_periods=2).mean()
    y = df["valor"].to_numpy(dtype=float)

    b, _, t = _ols(y)
    p = _p_bilateral(t)
    nivel = float(np.nanmean(y))
    significante = bool(np.isfinite(p) and p < 0.05 and len(df) >= 14)

    if not significante:
        direcao = "estavel"
    elif b > 0:
        direcao = "alta"
    else:
        direcao = "baixa"

    incl_pct_mes = (b * 30 / nivel) if nivel else float("nan")

    m7 = float(np.nanmean(y[-7:])) if len(y) >= 7 else float("nan")
    anteriores = y[-35:-7] if len(y) >= 35 else y[:-7] if len(y) > 7 else np.array([])
    m28 = float(np.nanmean(anteriores)) if len(anteriores) else float("nan")
    momento = ((m7 - m28) / abs(m28)) if (m28 and np.isfinite(m28) and m28 != 0) else None

    mediana_movel = df["valor"].rolling(28, min_periods=7).median()
    acima = (df["valor"] > mediana_movel).to_numpy()
    seq = 0
    for i in range(len(acima) - 1, -1, -1):
        if pd.isna(mediana_movel.iloc[i]):
            break
        passo = 1 if acima[i] else -1
        if seq == 0 or (seq > 0) == (passo > 0):
            seq += passo
        else:
            break

    df["dia_semana"] = pd.to_datetime(df["data"]).dt.dayofweek
    perfil = (
        df.groupby("dia_semana")["valor"].mean().reindex(range(7)).reset_index()
    )
    perfil["dia"] = [DIAS_PT[i] for i in perfil["dia_semana"]]
    perfil["indice"] = perfil["valor"] / nivel if nivel else np.nan
    amp = (
        float(perfil["indice"].max() - perfil["indice"].min())
        if perfil["indice"].notna().any() else None
    )

    return Tendencia(
        dominio=dom, chave_metrica=chave_metrica, serie=df,
        inclinacao_dia=b, inclinacao_pct_mes=incl_pct_mes,
        t_stat=t, p_valor=p, significante=significante, direcao=direcao,
        nivel_medio=nivel, media_7=m7, media_28_anterior=m28, momento=momento,
        sequencia=int(seq), amplitude_semanal=amp, perfil_semanal=perfil,
        n_dias=len(df),
    )


def descrever(tend: Tendencia) -> list[str]:
    """Lê a tendência em português, dizendo também quando NÃO há tendência."""
    m = tend.dominio.metrica(tend.chave_metrica)
    out: list[str] = []

    if tend.direcao == "estavel":
        out.append(
            f"**{m.rotulo} está estável** no período. A reta ajustada inclina "
            f"{numero(tend.inclinacao_dia, m, sinal=True)} por dia, mas com t = "
            f"{tend.t_stat:.2f} (p = {tend.p_valor:.2f}) isso não se distingue de "
            f"ruído. Nível médio de {numero(tend.nivel_medio, m)} em "
            f"{tend.n_dias} dias."
        )
    else:
        out.append(
            f"**{m.rotulo} em {tend.direcao}**: {numero(tend.inclinacao_dia, m, sinal=True)} "
            f"por dia, o equivalente a {pct(tend.inclinacao_pct_mes)} ao mês sobre o "
            f"nível médio de {numero(tend.nivel_medio, m)}. A inclinação e "
            f"estatisticamente distinguível de zero (t = {tend.t_stat:.2f}, "
            f"p = {tend.p_valor:.3f}), em {tend.n_dias} dias."
        )

    if tend.momento is not None and np.isfinite(tend.momento):
        if abs(tend.momento) < 0.03:
            out.append(
                f"**Sem aceleração.** Os últimos 7 dias rodaram a "
                f"{numero(tend.media_7, m)}, praticamente o mesmo dos 28 anteriores "
                f"({numero(tend.media_28_anterior, m)})."
            )
        else:
            verbo = "acelerou" if tend.momento > 0 else "desacelerou"
            out.append(
                f"**A métrica {verbo}**: últimos 7 dias a {numero(tend.media_7, m)} "
                f"contra {numero(tend.media_28_anterior, m)} nos 28 dias anteriores, "
                f"{pct(tend.momento)}."
            )

    if abs(tend.sequencia) >= 4:
        lado = "acima" if tend.sequencia > 0 else "abaixo"
        out.append(
            f"**{abs(tend.sequencia)} dias seguidos {lado} da mediana movel de 28 "
            f"dias.** Sequência desse tamanho e mais compatível com mudanca de "
            f"patamar do que com oscilação."
        )

    if tend.amplitude_semanal and tend.amplitude_semanal > 0.15:
        p = tend.perfil_semanal.dropna(subset=["indice"])
        if not p.empty:
            alto = p.loc[p["indice"].idxmax()]
            baixo = p.loc[p["indice"].idxmin()]
            out.append(
                f"**Tem sazonalidade semanal forte**: {alto['dia']} roda "
                f"{pct(alto['indice'] - 1)} contra a média e {baixo['dia']} "
                f"{pct(baixo['indice'] - 1)}. Comparar dia com dia anterior aqui "
                f"mistura calendário com desempenho — o certo e comparar com D-7."
            )

    return out
