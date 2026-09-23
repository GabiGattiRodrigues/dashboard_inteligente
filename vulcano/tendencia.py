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
from . import i18n
from .i18n import L
from .semantica import Dominio

DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DIAS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
           "Sunday"]


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
    dias = DIAS_EN if i18n.en() else DIAS_PT
    perfil["dia"] = [dias[i] for i in perfil["dia_semana"]]
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

    incl = numero(tend.inclinacao_dia, m, sinal=True)
    nivel = numero(tend.nivel_medio, m)
    if tend.direcao == "estavel":
        out.append(L(
            f"**{m.rotulo} está estável** no período. A reta ajustada inclina "
            f"{incl} por dia, mas com t = "
            f"{tend.t_stat:.2f} (p = {tend.p_valor:.2f}) isso não se distingue de "
            f"ruído. Nível médio de {nivel} em {tend.n_dias} dias.",
            f"**{m.rotulo} is stable** in the period. The fitted line slopes "
            f"{incl} per day, but with t = {tend.t_stat:.2f} "
            f"(p = {tend.p_valor:.2f}) that is indistinguishable from noise. "
            f"Average level of {nivel} over {tend.n_dias} days."
        ))
    else:
        out.append(L(
            f"**{m.rotulo} em {tend.direcao}**: {incl} "
            f"por dia, o equivalente a {pct(tend.inclinacao_pct_mes)} ao mês sobre o "
            f"nível médio de {nivel}. A inclinação é "
            f"estatisticamente distinguível de zero (t = {tend.t_stat:.2f}, "
            f"p = {tend.p_valor:.3f}), em {tend.n_dias} dias.",
            f"**{m.rotulo} "
            f"{'trending up' if tend.direcao == 'alta' else 'trending down'}**: "
            f"{incl} per day, equivalent to {pct(tend.inclinacao_pct_mes)} a "
            f"month over the average level of {nivel}. The slope is "
            f"statistically distinguishable from zero (t = {tend.t_stat:.2f}, "
            f"p = {tend.p_valor:.3f}), over {tend.n_dias} days."
        ))

    if tend.momento is not None and np.isfinite(tend.momento):
        m7, m28 = numero(tend.media_7, m), numero(tend.media_28_anterior, m)
        if abs(tend.momento) < 0.03:
            out.append(L(
                f"**Sem aceleração.** Os últimos 7 dias rodaram a "
                f"{m7}, praticamente o mesmo dos 28 anteriores ({m28}).",
                f"**No acceleration.** The last 7 days ran at {m7}, "
                f"practically the same as the previous 28 ({m28})."
            ))
        else:
            sobe = tend.momento > 0
            out.append(L(
                f"**A métrica {'acelerou' if sobe else 'desacelerou'}**: "
                f"últimos 7 dias a {m7} contra {m28} nos 28 dias anteriores, "
                f"{pct(tend.momento)}.",
                f"**The metric {'accelerated' if sobe else 'decelerated'}**: "
                f"last 7 days at {m7} against {m28} in the previous 28 days, "
                f"{pct(tend.momento)}."
            ))

    if abs(tend.sequencia) >= 4:
        acima = tend.sequencia > 0
        out.append(L(
            f"**{abs(tend.sequencia)} dias seguidos "
            f"{'acima' if acima else 'abaixo'} da mediana móvel de 28 "
            f"dias.** Sequência desse tamanho é mais compatível com mudança de "
            f"patamar do que com oscilação.",
            f"**{abs(tend.sequencia)} days in a row "
            f"{'above' if acima else 'below'} the 28-day rolling median.** A "
            f"streak that long fits a change of level better than an "
            f"oscillation."
        ))

    if tend.amplitude_semanal and tend.amplitude_semanal > 0.15:
        p = tend.perfil_semanal.dropna(subset=["indice"])
        if not p.empty:
            alto = p.loc[p["indice"].idxmax()]
            baixo = p.loc[p["indice"].idxmin()]
            out.append(L(
                f"**Tem sazonalidade semanal forte**: {alto['dia']} roda "
                f"{pct(alto['indice'] - 1)} contra a média e {baixo['dia']} "
                f"{pct(baixo['indice'] - 1)}. Comparar dia com dia anterior aqui "
                f"mistura calendário com desempenho — o certo é comparar com D-7.",
                f"**There is strong weekly seasonality**: {alto['dia']} runs "
                f"{pct(alto['indice'] - 1)} against the average and "
                f"{baixo['dia']} {pct(baixo['indice'] - 1)}. Comparing a day "
                f"with the previous day here mixes calendar with performance "
                f"— the right comparison is against D-7."
            ))

    return out
