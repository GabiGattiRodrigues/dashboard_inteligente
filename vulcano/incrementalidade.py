"""
Mensuração de CRM: resposta em 7 dias contra o grupo controle.

É a régua de quem opera CRM, na ordem em que a pergunta chega:

    recebeu  →  abriu (foi impactado)  →  comprou em até 7 dias

Compara-se a taxa de resposta de quem abriu com a do grupo controle (10% da
audiência, sorteados, que não recebem nada) e o ticket médio dos dois.

Duas leituras, sempre juntas
----------------------------
**Quem abriu × controle** é a leitura clássica, e superestima o efeito: quem
abre e-mail já compra mais por natureza. O controle é a audiência INTEIRA
sorteada -- tem gente que abriria e gente que não abriria --, então comparar
só os que abriram com ele mistura o efeito do disparo com a diferença de
perfil de quem abre.

**Quem recebeu × controle** compara grupos sorteados da mesma audiência, e
por isso a diferença é efeito do disparo. Dividindo esse ganho pela taxa de
abertura (ajuste de Bloom: quem não abriu não pode ter sido afetado) sai o
**efeito sobre quem abriu** -- a pergunta que a leitura clássica queria
responder.

Volume
------
O controle compra pouco. Com dez compras no controle, +40% e -20% cabem no
mesmo ruído; por isso nenhum lift sai deste projeto sem intervalo. O
intervalo é o da razão de duas proporções no log (Katz):

    log(RR) ± 1,96 · raiz(1/a − 1/n1 + 1/c − 1/n2)
"""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

import pandas as pd

from .dados import Filtros
from .formatacao import moeda, pct
from .i18n import L, num

# Abaixo disso o intervalo é largo demais para dizer qualquer coisa.
COMPRAS_MINIMAS_CONTROLE = 10
JANELA_DIAS = 7


def lift_com_intervalo(resp: float, n: float, resp_ctrl: float,
                       n_ctrl: float, z: float = 1.96
                       ) -> Optional[tuple[float, float, float]]:
    """(lift, limite inferior, limite superior) ou None sem volume."""
    if not (n and n_ctrl and resp and resp_ctrl):
        return None
    p1, p2 = resp / n, resp_ctrl / n_ctrl
    if p1 <= 0 or p2 <= 0:
        return None
    rr = p1 / p2
    ep = math.sqrt(max(1 / resp - 1 / n + 1 / resp_ctrl - 1 / n_ctrl, 0.0))
    return (rr - 1, math.exp(math.log(rr) - z * ep) - 1,
            math.exp(math.log(rr) + z * ep) - 1)


def leitura(ic: Optional[tuple[float, float, float]]) -> str:
    """Uma frase curta sobre o que o intervalo permite afirmar."""
    if ic is None:
        return L("sem compras no controle para medir",
                 "no control purchases to measure")
    _, inf, sup = ic
    if inf > 0:
        return L("efeito comprovado", "proven effect")
    if sup < 0:
        return L("efeito negativo comprovado", "proven negative effect")
    return L("não se distingue de zero", "not distinguishable from zero")


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #

_SOMAS = """
    SUM(CASE WHEN janela_7d = 1 THEN envios END)          AS recebeu,
    SUM(CASE WHEN janela_7d = 1 THEN aberturas END)       AS abriu,
    SUM(CASE WHEN janela_7d = 1 THEN grupo_controle END)  AS controle,
    SUM(resp_abriu)        AS resp_abriu,
    SUM(resp_recebeu)      AS resp_recebeu,
    SUM(resp_controle)     AS resp_controle,
    SUM(receita_abriu)     AS receita_abriu,
    SUM(receita_recebeu)   AS receita_recebeu,
    SUM(receita_controle)  AS receita_controle,
    COUNT(DISTINCT CASE WHEN janela_7d = 1 THEN CAST(data AS DATE) END)
                           AS disparos
"""


def _onde(dom, inicio: date, fim: date, filtros: Optional[Filtros]) -> str:
    c = [f"data BETWEEN DATE '{inicio}' AND DATE '{fim}'",
         "tipo_campanha = 'CRM'"]
    if filtros:
        c += [x for x in filtros.clausulas(dom)]
    return " AND ".join(c)


def _ler(df: pd.DataFrame) -> pd.DataFrame:
    """As taxas, os lifts com intervalo e o efeito sobre quem abriu."""
    if df.empty:
        return df
    df = df.copy()
    for c in df.columns:
        if c not in ("campanha", "canal", "disparo"):
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    df["taxa_abertura"] = df["abriu"] / df["recebeu"]
    df["r_abriu"] = df["resp_abriu"] / df["abriu"]
    df["r_recebeu"] = df["resp_recebeu"] / df["recebeu"]
    df["r_controle"] = df["resp_controle"] / df["controle"]
    df["ticket_abriu"] = df["receita_abriu"] / df["resp_abriu"]
    df["ticket_controle"] = df["receita_controle"] / df["resp_controle"]
    df["incrementais"] = df["resp_recebeu"] - df["recebeu"] * df["r_controle"]
    df["receita_incremental"] = (df["receita_recebeu"] - df["recebeu"]
                                 * df["receita_controle"] / df["controle"])

    ap = [lift_com_intervalo(a, b, c, d) for a, b, c, d in
          zip(df["resp_abriu"], df["abriu"], df["resp_controle"],
              df["controle"])]
    re_ = [lift_com_intervalo(a, b, c, d) for a, b, c, d in
           zip(df["resp_recebeu"], df["recebeu"], df["resp_controle"],
               df["controle"])]
    df["lift_aparente"] = [x[0] if x else float("nan") for x in ap]
    df["lift"] = [x[0] if x else float("nan") for x in re_]
    df["ic_inf"] = [x[1] if x else float("nan") for x in re_]
    df["ic_sup"] = [x[2] if x else float("nan") for x in re_]
    df["leitura"] = [leitura(x) for x in re_]

    # Ajuste de Bloom: o ganho de quem recebeu, em pontos, só pode ter vindo
    # de quem abriu. Dividindo pela taxa de abertura sai o ganho POR quem
    # abriu; o que sobra da resposta deles é o que comprariam de qualquer
    # jeito.
    ganho = (df["r_recebeu"] - df["r_controle"]) / df["taxa_abertura"]
    sem_disparo = df["r_abriu"] - ganho
    df["efeito_abriu"] = ganho / sem_disparo.where(sem_disparo > 0)
    return df


def por_campanha(con, dom, inicio: date, fim: date,
                 filtros: Optional[Filtros] = None) -> pd.DataFrame:
    """A mensuração de 7 dias de cada campanha de CRM no período."""
    df = con.execute(f"""
        SELECT campanha, canal, {_SOMAS}
          FROM fato WHERE {_onde(dom, inicio, fim, filtros)}
         GROUP BY 1, 2 HAVING SUM(CASE WHEN janela_7d = 1 THEN envios END) > 0
         ORDER BY recebeu DESC
    """).fetchdf()
    return _ler(df)


def total(con, dom, inicio: date, fim: date,
          filtros: Optional[Filtros] = None) -> pd.Series:
    df = con.execute(f"""
        SELECT {_SOMAS} FROM fato WHERE {_onde(dom, inicio, fim, filtros)}
    """).fetchdf()
    d = _ler(df)
    return d.iloc[0] if not d.empty else pd.Series(dtype=float)


def por_disparo(con, dom, campanha: str, inicio: date, fim: date,
                filtros: Optional[Filtros] = None) -> pd.DataFrame:
    """Um disparo por linha: a data em que saiu e o que ele fez em 7 dias."""
    nome = campanha.replace("'", "''")
    df = con.execute(f"""
        SELECT CAST(data AS DATE) AS disparo, {_SOMAS}
          FROM fato
         WHERE {_onde(dom, inicio, fim, filtros)} AND campanha = '{nome}'
           AND janela_7d = 1
         GROUP BY 1 ORDER BY 1
    """).fetchdf()
    return _ler(df)


def campanhas_crm(con) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT campanha FROM fato WHERE tipo_campanha = 'CRM' "
        "ORDER BY 1").fetchall()]


# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #

def formula(con, dom, inicio: date, fim: date,
            filtros: Optional[Filtros] = None,
            chave: str = "lift_crm") -> Optional[str]:
    """A conta do lift com as duas taxas, em vez dos produtos cruzados que o
    SQL usa por baixo (e que não dizem nada a quem lê)."""
    t = total(con, dom, inicio, fim, filtros)
    if t.empty or not (t.get("controle") and t.get("resp_controle")):
        return None
    m = dom.metrica(chave)
    a = t["r_abriu"] if chave == "lift_impactados" else t["r_recebeu"]
    return (f"{m.rotulo} = {m.formula} = {pct(a, 3, False)} ÷ "
            f"{pct(t['r_controle'], 3, False)} − 1 = "
            f"**{pct(a / t['r_controle'] - 1, 0, False)}**")


def frase(con, dom, inicio: date, fim: date,
          filtros: Optional[Filtros] = None) -> Optional[str]:
    """O aviso que acompanha qualquer resposta sobre lift: volume do
    controle, intervalo e a diferença entre as duas leituras."""
    t = total(con, dom, inicio, fim, filtros)
    if t.empty:
        return None
    c = t.get("resp_controle", 0) or 0
    ic = lift_com_intervalo(t["resp_recebeu"], t["recebeu"],
                            t["resp_controle"], t["controle"])
    if ic is None or c < COMPRAS_MINIMAS_CONTROLE:
        return L(
            f"**Cuidado com o volume:** o grupo controle teve só "
            f"{num(c)} compras em 7 dias nesse recorte — pouco para medir "
            f"lift. Amplie o período (90 dias ou mais) antes de concluir.",
            f"**Mind the volume:** the control group had only {num(c)} "
            f"purchases within 7 days in this slice — too few to measure "
            f"lift. Widen the period (90 days or more) before concluding.")
    partes = [L(
        f"**Cuidado com o volume:** o controle teve {num(c)} compras em 7 "
        f"dias, e o intervalo de 95% do lift de quem recebeu vai de "
        f"{pct(ic[1], 0)} a {pct(ic[2], 0)} — {leitura(ic)}.",
        f"**Mind the volume:** the control had {num(c)} purchases within 7 "
        f"days, and the 95% interval of the recipients' lift runs from "
        f"{pct(ic[1], 0)} to {pct(ic[2], 0)} — {leitura(ic)}.")]
    if t["lift_aparente"] == t["lift_aparente"] and t["lift"] == t["lift"]:
        partes.append(L(
            f"Comparando só quem abriu com o controle, o lift seria "
            f"{pct(t['lift_aparente'], 0)} — a maior parte disso é perfil "
            f"(quem abre já compra mais), não efeito do disparo.",
            f"Comparing only openers with the control, the lift would be "
            f"{pct(t['lift_aparente'], 0)} — most of that is profile "
            f"(openers already buy more), not the send's effect."))
    return " ".join(partes)


def relatorio(r: pd.Series, nome: str) -> list[str]:
    """A leitura de uma campanha (ou de um disparo) no formato de quem opera
    CRM: funil, resposta contra o controle, ticket e o que fazer."""
    linhas = []
    n = int(r["disparos"])
    quantos = (L("no disparo, com a janela de 7 dias completa",
                 "in the send, with the full 7-day window") if n == 1 else
               L(f"em {n} disparos com janela de 7 dias completa",
                 f"in {n} sends with a full 7-day window"))
    linhas.append(L(
        f"**{nome}** — {quantos}: **{num(r['recebeu'])}** receberam, "
        f"**{num(r['abriu'])}** abriram ({pct(r['taxa_abertura'], 1, False)}) "
        f"e **{num(r['resp_abriu'])}** dos que abriram compraram em até 7 "
        f"dias.",
        f"**{nome}** — {quantos}: **{num(r['recebeu'])}** received, "
        f"**{num(r['abriu'])}** "
        f"opened ({pct(r['taxa_abertura'], 1, False)}) and "
        f"**{num(r['resp_abriu'])}** of the openers bought within 7 days."))
    linhas.append(L(
        f"**Resposta de quem abriu: {pct(r['r_abriu'], 2, False)}**, contra "
        f"**{pct(r['r_controle'], 2, False)} no controle** "
        f"({num(r['resp_controle'])} de {num(r['controle'])}) — lift de "
        f"{pct(r['lift_aparente'], 0)} na leitura clássica.",
        f"**Openers' response: {pct(r['r_abriu'], 2, False)}**, against "
        f"**{pct(r['r_controle'], 2, False)} in the control** "
        f"({num(r['resp_controle'])} of {num(r['controle'])}) — a "
        f"{pct(r['lift_aparente'], 0)} lift in the classic reading."))
    ic_txt = (f"{pct(r['ic_inf'], 0)} a {pct(r['ic_sup'], 0)}"
              if r["ic_inf"] == r["ic_inf"] else "—")
    ic_en = (f"{pct(r['ic_inf'], 0)} to {pct(r['ic_sup'], 0)}"
             if r["ic_inf"] == r["ic_inf"] else "—")
    ef = r["efeito_abriu"]
    linhas.append(L(
        f"Só que quem abre já compra mais. Comparando grupos sorteados — "
        f"todo mundo que recebeu contra o controle —, o lift é "
        f"**{pct(r['lift'], 0)}** (IC95% {ic_txt}, {r['leitura']})"
        + (f", e o efeito real sobre quem abriu fica em **{pct(ef, 0)}**."
           if ef == ef else "."),
        f"But openers already buy more. Comparing randomized groups — "
        f"everyone who received against the control —, the lift is "
        f"**{pct(r['lift'], 0)}** (95% CI {ic_en}, {r['leitura']})"
        + (f", and the real effect on openers is **{pct(ef, 0)}**."
           if ef == ef else ".")))
    if r["ticket_abriu"] == r["ticket_abriu"] and \
            r["ticket_controle"] == r["ticket_controle"]:
        dt = r["ticket_abriu"] / r["ticket_controle"] - 1
        linhas.append(L(
            f"**Ticket médio:** {moeda(r['ticket_abriu'], 2)} de quem abriu "
            f"contra {moeda(r['ticket_controle'], 2)} do controle "
            f"({pct(dt, 0)}). Receita incremental em 7 dias: "
            f"**{moeda(r['receita_incremental'], 0)}** "
            f"({num(r['incrementais'])} compras a mais).",
            f"**Average ticket:** {moeda(r['ticket_abriu'], 2)} for openers "
            f"against {moeda(r['ticket_controle'], 2)} for the control "
            f"({pct(dt, 0)}). Incremental 7-day revenue: "
            f"**{moeda(r['receita_incremental'], 0)}** "
            f"({num(r['incrementais'])} extra purchases)."))
    return linhas
