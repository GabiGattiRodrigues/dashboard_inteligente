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

Métrica que não tem leitura diária
----------------------------------
Over30 no MOB3, falso positivo de alerta maduro, turnover precoce: são
métricas de maturação. No mês selecionado a safra ainda não amadureceu, a
série diária vem vazia e "não há dias suficientes" seria verdade e inútil.
Nesses casos a leitura cai para a **série mensal dos últimos 12 meses**,
que é como essas métricas são acompanhadas de verdade. Com poucos pontos a
aproximação normal deixa de ser honesta, então a significância usa o t
crítico da distribuição t de Student para os graus de liberdade da série.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

import duckdb
import numpy as np
import pandas as pd

from .dados import Filtros, agregar, serie_diaria
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
    granularidade: str = "dia"   # "dia" ou "mes"
    ultimo_ponto: Optional[date] = None
    projecao: Optional[float] = None   # só com tendência significante
    horizonte: int = 1                 # dias (diário) ou meses (mensal)


# t crítico bilateral a 5% por graus de liberdade (tabela da t de Student).
_T_CRITICO = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
              7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201,
              12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 20: 2.086,
              30: 2.042}


def _t_critico(gl: int) -> float:
    if gl <= 0:
        return float("inf")
    chaves = [k for k in _T_CRITICO if k <= gl]
    return _T_CRITICO[max(chaves)] if gl <= 30 else 1.96


def _limitar(valor: float, m) -> float:
    """Projeção não atravessa o que a métrica permite: percentual fica entre
    0 e 100%, contagem e dinheiro não ficam negativos."""
    if m.formato == "percentual":
        return min(max(valor, 0.0), 1.0)
    if m.formato in ("moeda", "inteiro") and valor < 0:
        return 0.0
    return valor


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
    if not df.empty:
        df = df[["data", chave_metrica]].rename(columns={chave_metrica: "valor"})
        df = df.dropna(subset=["valor"]).sort_values("data").reset_index(drop=True)
    if df.empty or len(df) < 5:
        return analisar_mensal(con, dom, chave_metrica, fim, filtros)

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

    # Onde a reta ajustada chega se o ritmo continuar. Extrapolação linear,
    # não modelo de previsão -- e o texto diz isso. Só projeta metade do
    # tamanho da janela para a frente (prolongar 23 dias de reta por 30 é
    # inventar), e cala quando a reta bate no limite da métrica: "a receita
    # chega a zero" não dimensiona problema nenhum.
    projecao, horizonte = None, 0
    if significante and len(y) >= 14:
        horizonte = min(30, len(y) // 2)
        ajuste_fim = float(np.mean(y) + b * ((len(y) - 1) / 2))
        bruto = ajuste_fim + b * horizonte
        lim = _limitar(bruto, dom.metrica(chave_metrica))
        if lim == bruto and bruto != 0:
            projecao = bruto

    return Tendencia(
        dominio=dom, chave_metrica=chave_metrica, serie=df,
        inclinacao_dia=b, inclinacao_pct_mes=incl_pct_mes,
        t_stat=t, p_valor=p, significante=significante, direcao=direcao,
        nivel_medio=nivel, media_7=m7, media_28_anterior=m28, momento=momento,
        sequencia=int(seq), amplitude_semanal=amp, perfil_semanal=perfil,
        n_dias=len(df), ultimo_ponto=pd.Timestamp(df["data"].iloc[-1]).date(),
        projecao=projecao, horizonte=horizonte,
    )


def analisar_mensal(
    con: duckdb.DuckDBPyConnection, dom: Dominio, chave_metrica: str,
    fim: date, filtros: Optional[Filtros] = None, meses: int = 12,
) -> Optional[Tendencia]:
    """Tendência sobre a série mensal dos últimos `meses` até `fim`.

    Cada mês é agregado inteiro pelo motor (o mesmo `agregar` das abas), então
    o valor do mês é o valor que o painel mostraria para aquele mês. Mês sem
    valor -- safra ainda imatura, antes do início da base -- sai da série.
    """
    ref = pd.Timestamp(fim).to_period("M")
    linhas = []
    for i in range(meses - 1, -1, -1):
        per = ref - i
        ini_m = per.start_time.date()
        fim_m = min(per.end_time.date(), fim)
        v = agregar(con, dom, [chave_metrica], ini_m, fim_m, filtros=filtros)
        valor = float(v.iloc[0][chave_metrica]) if (
            not v.empty and pd.notna(v.iloc[0][chave_metrica])) else np.nan
        linhas.append({"data": pd.Timestamp(ini_m), "valor": valor})
    df = pd.DataFrame(linhas).dropna(subset=["valor"]).reset_index(drop=True)
    if len(df) < 4:
        # Safra longa (default no MOB12) quase não tem mês maduro em um ano:
        # olha dois antes de desistir.
        if meses < 24:
            return analisar_mensal(con, dom, chave_metrica, fim, filtros, 24)
        return None

    y = df["valor"].to_numpy(dtype=float)
    b, _, t = _ols(y)
    gl = len(y) - 2
    significante = bool(np.isfinite(t) and abs(t) > _t_critico(gl))
    direcao = "estavel" if not significante else ("alta" if b > 0 else "baixa")
    nivel = float(np.nanmean(y))
    df["media_movel"] = df["valor"].rolling(3, min_periods=2).mean()

    ultimo = float(y[-1])
    anteriores = y[-4:-1]
    m_ant = float(np.mean(anteriores)) if len(anteriores) else float("nan")
    momento = ((ultimo - m_ant) / abs(m_ant)) if (
        np.isfinite(m_ant) and m_ant != 0) else None

    projecao = None
    if significante and len(y) >= 6:
        ajuste_fim = float(np.mean(y) + b * ((len(y) - 1) / 2))
        bruto = ajuste_fim + b
        if _limitar(bruto, dom.metrica(chave_metrica)) == bruto and bruto != 0:
            projecao = bruto

    return Tendencia(
        dominio=dom, chave_metrica=chave_metrica, serie=df,
        inclinacao_dia=b, inclinacao_pct_mes=(b / nivel) if nivel else float("nan"),
        t_stat=t, p_valor=float("nan"), significante=significante,
        direcao=direcao, nivel_medio=nivel, media_7=ultimo,
        media_28_anterior=m_ant, momento=momento, sequencia=0,
        amplitude_semanal=None, perfil_semanal=pd.DataFrame(
            columns=["dia_semana", "valor", "dia", "indice"]),
        n_dias=len(df), granularidade="mes",
        ultimo_ponto=pd.Timestamp(df["data"].iloc[-1]).date(),
        projecao=projecao,
    )


def descrever(tend: Tendencia) -> list[str]:
    """Lê a tendência em português, dizendo também quando NÃO há tendência."""
    if tend.granularidade == "mes":
        return _descrever_mensal(tend)
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

    out += _frase_projecao(tend, m, L(f"nos próximos {tend.horizonte} dias",
                                      f"over the next {tend.horizonte} days"))

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


def _frase_projecao(tend: Tendencia, m, horizonte: str) -> list[str]:
    if tend.projecao is None:
        return []
    alvo = numero(tend.projecao, m)
    return [L(
        f"**Se o ritmo continuar**, {m.rotulo} chega perto de {alvo} "
        f"{horizonte}. É a reta prolongada, não um modelo de previsão: serve "
        f"para dimensionar o problema, não para prometer número.",
        f"**If the pace holds**, {m.rotulo} gets close to {alvo} "
        f"{horizonte}. That's the line extended, not a forecasting model: it "
        f"sizes the problem, it doesn't promise a number."
    )]


def _descrever_mensal(tend: Tendencia) -> list[str]:
    """A mesma leitura, na escala de mês, para métrica de maturação."""
    m = tend.dominio.metrica(tend.chave_metrica)
    out: list[str] = []
    incl = numero(tend.inclinacao_dia, m, sinal=True)
    nivel = numero(tend.nivel_medio, m)
    ate = i18n.mes_ano(tend.ultimo_ponto.strftime("%Y-%m"))
    out.append(L(
        f"{m.rotulo} não tem leitura diária suficiente no período selecionado "
        f"(métrica que só fecha depois de maturar, ou rala por dia), então "
        f"olhei a série **mensal** dos últimos "
        f"{tend.n_dias} meses com valor, até {ate}.",
        f"{m.rotulo} has no usable daily reading in the selected period (a "
        f"metric that only closes after maturing, or sparse by day), so I "
        f"looked at the **monthly** series over the "
        f"last {tend.n_dias} months with a value, up to {ate}."
    ))
    if tend.direcao == "estavel":
        out.append(L(
            f"**{m.rotulo} está estável**: a reta inclina {incl} por mês, mas "
            f"com t = {tend.t_stat:.2f} em {tend.n_dias} meses isso não se "
            f"distingue de ruído. Nível médio de {nivel}.",
            f"**{m.rotulo} is stable**: the line slopes {incl} a month, but "
            f"with t = {tend.t_stat:.2f} over {tend.n_dias} months that is "
            f"indistinguishable from noise. Average level of {nivel}."
        ))
    else:
        out.append(L(
            f"**{m.rotulo} em {tend.direcao}**: {incl} por mês sobre um nível "
            f"médio de {nivel}. A inclinação passa no teste t para "
            f"{tend.n_dias} meses (t = {tend.t_stat:.2f}).",
            f"**{m.rotulo} "
            f"{'trending up' if tend.direcao == 'alta' else 'trending down'}**"
            f": {incl} a month over an average level of {nivel}. The slope "
            f"passes the t test for {tend.n_dias} months (t = "
            f"{tend.t_stat:.2f})."
        ))
    out += _frase_projecao(tend, m, L("no próximo mês", "next month"))
    if tend.momento is not None and np.isfinite(tend.momento):
        ult, ant = numero(tend.media_7, m), numero(tend.media_28_anterior, m)
        out.append(L(
            f"O último mês com valor fechou em {ult}, contra {ant} na média "
            f"dos três anteriores ({pct(tend.momento)}).",
            f"The last month with a value closed at {ult}, against {ant} on "
            f"average over the three before ({pct(tend.momento)})."
        ))
    return out
