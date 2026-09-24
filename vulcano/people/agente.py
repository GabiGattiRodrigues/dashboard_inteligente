"""
O que a Tomoyo responde que nenhum outro agente responde.

Três intenções, todas determinísticas e avaliadas ANTES do planejador genérico
(mesmo desenho da Ravena):

- **gap**    — gap salarial de gênero bruto vs ajustado por nível e área. O
               bruto está no painel e sai do motor; o ajustado compara mulheres
               e homens DENTRO do mesmo cargo, e a diferença entre os dois é a
               parte que vem de composição (quem ocupa os cargos que pagam
               mais), não de pagar diferente pelo mesmo trabalho.
- **risco**  — onde tem risco de saída. Não é modelo e não é previsão
               individual: é uma soma de sinais nomeados, por grupo
               (área × nível), com a conta aparecendo na tabela. Os sinais
               são os que vêm ANTES do pedido de demissão — clima caindo,
               promoção parada, ausência subindo — porque o turnover em si só
               aparece quando já é tarde.
- **pessoa** — a pergunta sobre um indivíduo. A Tomoyo recusa com jeito e
               devolve a leitura do grupo. People Analytics que aponta quem vai
               sair vira ferramenta de vigilância, e a pesquisa de clima deixa
               de ter resposta sincera no mês seguinte.

Recorte com menos de GRUPO_MINIMO pessoas não aparece em nenhuma das três.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd

from ..dados import Filtros, agregar, periodo_disponivel
from ..dominios.people import GRUPO_MINIMO
from .. import i18n
from ..formatacao import moeda, numero, pct
from ..i18n import L, V

INTENCOES = {
    "gap": "gap salarial de gênero bruto vs ajustado por nível e área",
    "risco": "onde há risco de saída nos próximos meses, por área e nível, "
             "a partir dos sinais que antecedem o pedido de demissão",
    "pessoa": "pergunta sobre um indivíduo — a Tomoyo responde só por grupo",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


PESSOA = re.compile(
    r"(quem (vai|pode|deve|esta para|ta para|tende a) (sair|pedir|se demitir)"
    r"|quais (pessoas|colaboradores|funcionarios)( especificamente)? (vao|podem)"
    r"|(nome|nomes|lista) d[eoa]s? (pessoas|colaboradores|funcionarios)"
    r"|qual (colaborador|funcionario|pessoa)\b"
    r"|pessoa_id|matricula|\bcpf\b"
    r"|salario d[oa] (fulan|ciclan|beltran|joao|maria|[a-z]+ da )"
    # "a Mariana vai pedir demissao?" -- artigo + nome proprio + saida. A lista
    # negativa segura os coletivos ("a area vai sair", "o time vai sair"), que
    # sao pergunta de grupo e seguem para a leitura de risco.
    r"|\b(o|a) (?!(area|empresa|time|equipe|galera|gente|turma|lideranca|"
    r"diretoria|gestao|pessoal|setor|loja|nivel|grupo|safra)\b)[a-z]+ "
    r"(vai|pode|deve|esta para|ta pra|tende a) (sair|pedir|se demitir)"
    # English
    r"|who (is going to|will|might|may|is about to|is likely to) "
    r"(leave|quit|resign)"
    r"|which (people|employees|person|employee)( specifically)? "
    r"(will|might|are going to|is going to)"
    r"|(names?|list) of (the )?(people|employees)"
    r"|employee id|\bssn\b"
    r"|(john|jane|mary)'s salary"
    r"|\b(will|is|does) (?!(anyone|someone|anybody|somebody|the|it|this|"
    r"that|there|turnover|attrition|our|my|team|people|staff)\b)[a-z]+ "
    r"(leave|quit|resign|going to (leave|quit|resign)|want to (leave|quit)))")

GAP = ["gap", "equidade salarial", "diferenca salarial", "desigualdade salarial",
       "pay gap", "ganham menos", "ganha menos", "mulheres ganham",
       "diferenca de salario", "salario de mulher", "salario das mulheres",
       "pay equity", "wage gap", "women earn", "women make less",
       "earn less", "women's salary", "womens salary"]
TEMPORAL = ["crescendo", "caindo", "subindo", "tendencia", "variacao", "mudou",
            "mudanca", "contra o mes", "mes passado", "evolucao", "por dia",
            "serie", "ao longo",
            "growing", "falling", "rising", "trend", "change", "changed",
            "vs last month", "last month", "over time", "per day",
            "evolution"]
RISCO = ["risco de saida", "risco de turnover", "risco de perder",
         "risco de pedido", "onde tem risco", "onde ha risco", "vai sair",
         "vao sair", "podem sair", "pode sair", "sinal de saida",
         "sinais de saida", "sinal antecedente", "sinais antecedentes",
         "indicador antecedente", "antes de sair", "proxima onda",
         "quem esta insatisfeito", "onde esta insatisfeito", "flight risk",
         "risco de fuga", "vamos perder gente",
         # English
         "flight risk", "attrition risk", "risk of leaving", "turnover risk",
         "risk of losing", "going to leave", "might leave", "may leave",
         "exit risk", "signs of leaving", "leading indicator",
         "leading signal", "before they leave", "next wave",
         "who is unhappy", "where are people unhappy",
         "are we going to lose people"]


def interpretar(pergunta: str, ctx) -> Optional[dict[str, Any]]:
    t = _norm(pergunta)
    if PESSOA.search(t):
        return {"intencao": "pessoa"}

    from ..conversa import pergunta_de_conceito
    if pergunta_de_conceito(pergunta) or re.search(
            r"o que e |como funciona|como e calculad|como voce calcula|"
            r"what is (a |an )?(gap|adjusted|raw)|how is .* calculated|"
            r"how do you calculate", t):
        return None

    if any(g in t for g in RISCO):
        return {"intencao": "risco"}
    if any(g in t for g in GAP) and not any(x in t for x in TEMPORAL):
        return {"intencao": "gap", "metrica": "gap_genero"}
    return None


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #

def _onde(dom, inicio: date, fim: date, filtros: Optional[Filtros]) -> str:
    c = [f"data BETWEEN DATE '{inicio}' AND DATE '{fim}'"]
    if filtros:
        c += filtros.clausulas(dom)
    return " AND ".join(c)


def gap_ajustado(con, dom, inicio: date, fim: date,
                 filtros: Optional[Filtros] = None) -> dict[str, Any]:
    """
    Gap bruto (o mesmo número do card) e gap ajustado por nível × área.

    Ajustado = 1 − média ponderada, célula a célula, de
    salário médio feminino ÷ salário médio masculino. O peso é a base
    (pessoa-dia) da célula. Só entram células com pelo menos GRUPO_MINIMO
    mulheres E GRUPO_MINIMO homens: com menos, o salário médio é o salário
    de alguém.
    """
    bruto_df = agregar(con, dom, ["gap_genero"], inicio, fim, filtros=filtros)
    bruto = float(bruto_df.iloc[0]["gap_genero"]) if not bruto_df.empty and \
        pd.notna(bruto_df.iloc[0]["gap_genero"]) else float("nan")

    cel = con.execute(f"""
        SELECT area, nivel, genero,
               COUNT(DISTINCT pessoa_id) AS pessoas,
               SUM(salario) / SUM(ativo) AS salario,
               SUM(ativo) AS base
          FROM fato
         WHERE {_onde(dom, inicio, fim, filtros)}
         GROUP BY 1, 2, 3
    """).fetchdf()
    if cel.empty:
        return {"bruto": bruto, "ajustado": float("nan"), "celulas": cel,
                "cobertura": 0.0, "representacao": pd.DataFrame()}

    cel["area"] = cel["area"].astype(str)
    cel["nivel"] = cel["nivel"].astype(str)
    cel["genero"] = cel["genero"].astype(str)
    f = cel[cel["genero"] == "Feminino"].set_index(["area", "nivel"])
    m = cel[cel["genero"] == "Masculino"].set_index(["area", "nivel"])
    j = f.join(m, lsuffix="_f", rsuffix="_m", how="inner").reset_index()
    j["valida"] = (j["pessoas_f"] >= GRUPO_MINIMO) & (j["pessoas_m"] >= GRUPO_MINIMO)
    j["razao"] = j["salario_f"] / j["salario_m"]
    j["gap"] = 1 - j["razao"]
    j["peso"] = j["base_f"] + j["base_m"]
    v = j[j["valida"]]
    ajustado = (1 - (v["razao"] * v["peso"]).sum() / v["peso"].sum()
                ) if not v.empty else float("nan")
    cobertura = v["peso"].sum() / cel["base"].sum() if cel["base"].sum() else 0

    ordem_nivel = ["Operacional", "Júnior", "Pleno", "Sênior", "Liderança"]
    rep = (cel.groupby(["nivel", "genero"])["base"].sum().unstack(fill_value=0))
    rep = (rep.get("Feminino", 0) / rep.sum(axis=1)).rename("mulheres")
    rep = rep.reindex([n for n in ordem_nivel if n in rep.index]).reset_index()
    return {"bruto": bruto, "ajustado": ajustado, "celulas": j,
            "cobertura": cobertura, "representacao": rep}


# Pesos do score de risco. Cada fator tem teto, e a tabela mostra a conta.
PESOS_RISCO = {
    "queda_enps": 40,        # até 40: queda do eNPS contra o trimestre anterior
    "enps_baixo": 15,        # até 15: eNPS negativo agora
    "turnover_acelerando": 20,  # até 20: turnover voluntário do trimestre > 12m
    "sem_promocao": 15,      # 15: grupo sem promoção nos últimos 12 meses
    "ausencia_subindo": 10,  # até 10: absenteísmo subindo contra o trimestre anterior
}


def sinais_de_risco(con, dom, ref: date,
                    filtros: Optional[Filtros] = None) -> pd.DataFrame:
    """
    Sinais antecedentes de saída por área × nível, na data de referência.

    Três janelas: o trimestre que termina em `ref`, o trimestre anterior e os
    12 meses até `ref`. Nada aqui olha para o futuro de `ref` — a mesma
    pergunta feita em fevereiro responde com o que se sabia em fevereiro.
    """
    t0, t1 = ref - timedelta(days=89), ref
    p0, p1 = ref - timedelta(days=179), ref - timedelta(days=90)
    a0 = ref - timedelta(days=364)
    extra = "".join(" AND " + c for c in (filtros.clausulas(dom) if filtros else []))

    df = con.execute(f"""
        WITH b AS (
          SELECT area, nivel, data, pessoa_id, ativo, desl_voluntario, promocao,
                 respondeu_enps, promotor, detrator, horas_ausencia,
                 horas_previstas,
                 data BETWEEN DATE '{t0}' AND DATE '{t1}' AS tri,
                 data BETWEEN DATE '{p0}' AND DATE '{p1}' AS ant
            FROM fato
           WHERE data BETWEEN DATE '{a0}' AND DATE '{t1}' {extra}
        )
        SELECT CAST(area AS VARCHAR) AS area, CAST(nivel AS VARCHAR) AS nivel,
               COUNT(DISTINCT CASE WHEN data = DATE '{t1}' THEN pessoa_id END)
                   AS pessoas,
               SUM(CASE WHEN tri THEN respondeu_enps END) AS resp_tri,
               SUM(CASE WHEN ant THEN respondeu_enps END) AS resp_ant,
               (SUM(CASE WHEN tri THEN promotor END)
                - SUM(CASE WHEN tri THEN detrator END)) * 100.0
                 / NULLIF(SUM(CASE WHEN tri THEN respondeu_enps END), 0)
                   AS enps_tri,
               (SUM(CASE WHEN ant THEN promotor END)
                - SUM(CASE WHEN ant THEN detrator END)) * 100.0
                 / NULLIF(SUM(CASE WHEN ant THEN respondeu_enps END), 0)
                   AS enps_ant,
               SUM(CASE WHEN tri THEN desl_voluntario END) * 365.0
                 / NULLIF(SUM(CASE WHEN tri THEN ativo END), 0) AS vol_tri,
               SUM(desl_voluntario) * 365.0 / NULLIF(SUM(ativo), 0) AS vol_12m,
               SUM(promocao) AS promocoes_12m,
               SUM(CASE WHEN tri THEN horas_ausencia END)
                 / NULLIF(SUM(CASE WHEN tri THEN horas_previstas END), 0)
                   AS abs_tri,
               SUM(CASE WHEN ant THEN horas_ausencia END)
                 / NULLIF(SUM(CASE WHEN ant THEN horas_previstas END), 0)
                   AS abs_ant
          FROM b
         GROUP BY 1, 2
    """).fetchdf()

    df = df[(df["pessoas"] >= GRUPO_MINIMO)
            & (df["resp_tri"] >= 20) & (df["resp_ant"] >= 20)].copy()
    if df.empty:
        return df

    df["delta_enps"] = df["enps_tri"] - df["enps_ant"]
    w = PESOS_RISCO
    df["p_queda_enps"] = (-df["delta_enps"]).clip(lower=0, upper=w["queda_enps"])
    df["p_enps_baixo"] = (-df["enps_tri"]).clip(lower=0, upper=w["enps_baixo"])
    acel = (df["vol_tri"] / df["vol_12m"].where(df["vol_12m"] > 0) - 1).fillna(0)
    df["p_turnover"] = (acel * 20).clip(lower=0, upper=w["turnover_acelerando"])
    df["p_promocao"] = (df["promocoes_12m"] == 0) * float(w["sem_promocao"])
    # Nível operacional e Liderança têm dinâmica de promoção própria; o
    # fator só conta onde promoção é o caminho esperado.
    df.loc[df["nivel"].isin(["Operacional", "Liderança"]), "p_promocao"] = 0.0
    d_abs = (df["abs_tri"] - df["abs_ant"]).fillna(0)
    df["p_ausencia"] = (d_abs * 1000).clip(lower=0, upper=w["ausencia_subindo"])
    df["risco"] = df[["p_queda_enps", "p_enps_baixo", "p_turnover",
                      "p_promocao", "p_ausencia"]].sum(axis=1).round(0)
    return df.sort_values(["risco", "pessoas"], ascending=[False, False])


def _motivos(r) -> list[str]:
    m = []
    if r.p_queda_enps >= 5:
        m.append(L(f"eNPS caiu {abs(r.delta_enps):.0f} pontos no trimestre "
                   f"(de {r.enps_ant:+.0f} para {r.enps_tri:+.0f})",
                   f"eNPS fell {abs(r.delta_enps):.0f} points in the quarter "
                   f"(from {r.enps_ant:+.0f} to {r.enps_tri:+.0f})"))
    elif r.p_enps_baixo >= 5:
        m.append(L(f"eNPS negativo ({r.enps_tri:+.0f})",
                   f"negative eNPS ({r.enps_tri:+.0f})"))
    if r.p_turnover >= 5:
        tri, ano = pct(r.vol_tri, 0, False), pct(r.vol_12m, 0, False)
        m.append(L(f"turnover voluntário do trimestre em {tri} a.a., acima "
                   f"dos {ano} dos 12 meses",
                   f"quarterly voluntary turnover at {tri} annualized, above "
                   f"the 12-month {ano}"))
    if r.p_promocao:
        m.append(L("nenhuma promoção em 12 meses", "no promotions in 12 months"))
    if r.p_ausencia >= 3:
        de, para = pct(r.abs_ant, 1, False), pct(r.abs_tri, 1, False)
        m.append(L(f"absenteísmo subindo ({de} → {para})",
                   f"absenteeism rising ({de} → {para})"))
    return m


def _grupo(area, nivel) -> str:
    return f"{V(area)} · {V(nivel)}"


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #

def _ref(con, ctx) -> date:
    _, dmax = periodo_disponivel(con)
    return min(ctx.fim, dmax)


def _executar_risco(con, dom, ctx, fatos, linhas):
    ref = _ref(con, ctx)
    df = sinais_de_risco(con, dom, ref, ctx.filtros)
    fatos.update({"referencia": i18n.data(ref),
                  "filtros_ativos": ctx.filtros.resumo(dom),
                  "grupo_minimo": GRUPO_MINIMO,
                  "pesos_do_score": PESOS_RISCO})
    if df.empty:
        linhas.append(L(
            f"Com o filtro atual não sobra nenhum grupo com pelo "
            f"menos {GRUPO_MINIMO} pessoas e respostas de pesquisa "
            f"suficientes para ler sinal. Tire um filtro e pergunte "
            f"de novo.",
            f"With the current filter no group is left with at least "
            f"{GRUPO_MINIMO} people and enough survey responses to read a "
            f"signal. Remove a filter and ask again."))
        return None
    topo = df[df["risco"] >= 20].head(5)
    fatos["grupos_em_atencao"] = [
        {"grupo": _grupo(r.area, r.nivel), "pessoas": int(r.pessoas),
         "risco": int(r.risco), "sinais": _motivos(r)}
        for r in topo.itertuples()]
    data_ref = i18n.data(ref)
    if topo.empty:
        linhas.append(L(
            f"Em {data_ref} nenhum grupo acende sinal de "
            f"saída: clima estável, turnover no ritmo dos 12 meses e promoção "
            f"andando. Vale repetir a pergunta no fim do próximo pulso.",
            f"On {data_ref} no group lights up an exit signal: stable "
            f"engagement, turnover at the 12-month pace and promotions "
            f"moving. Worth asking again after the next pulse survey."))
    else:
        n = len(topo)
        linhas.append(L(
            f"Lendo os sinais que vêm **antes** do pedido de demissão, até "
            f"{data_ref}, **{n} "
            f"{'grupo pede' if n == 1 else 'grupos pedem'} atenção**:",
            f"Reading the signals that come **before** a resignation, up to "
            f"{data_ref}, **{n} {'group needs' if n == 1 else 'groups need'} "
            f"attention**:"))
        for r in topo.itertuples():
            linhas.append(
                f"- **{_grupo(r.area, r.nivel)}** ({int(r.pessoas)} "
                + L(f"pessoas, risco {int(r.risco)}): ",
                    f"people, risk {int(r.risco)}): ")
                + "; ".join(_motivos(r)) + ".")
        r0 = topo.iloc[0]
        permanencia = r0.p_promocao or r0.p_queda_enps >= 15
        acao = (L("conversa de permanência com a liderança do grupo e revisão "
                  "de mérito/promoção antes do próximo ciclo",
                  "a stay conversation with the group's leadership and a "
                  "merit/promotion review before the next cycle")
                if permanencia else
                L("ouvir o grupo (pulso aberto ou grupo focal) antes de mexer "
                  "em política",
                  "listen to the group (open pulse or focus group) before "
                  "changing policy"))
        g0 = _grupo(r0.area, r0.nivel)
        linhas.append(L(
            f"**O que fazer:** começar por {g0} — "
            f"{acao}. Queda de clima costuma chegar ao turnover em "
            f"dois a quatro meses; a janela para agir é agora.",
            f"**What to do:** start with {g0} — {acao}. An engagement drop "
            f"usually reaches turnover in two to four months; the window to "
            f"act is now."))
    linhas.append(L(
        f"*O score é uma soma de sinais nomeados (a conta está na "
        f"tabela), por grupo de pelo menos {GRUPO_MINIMO} pessoas. "
        f"Não é previsão de quem vai sair — é onde olhar primeiro.*",
        f"*The score is a sum of named signals (the math is in the table), "
        f"per group of at least {GRUPO_MINIMO} people. It's not a "
        f"prediction of who will leave — it's where to look first.*"))
    t = df.head(8)
    return pd.DataFrame({
        L("Grupo", "Group"): [_grupo(a, n) for a, n in zip(t["area"], t["nivel"])],
        L("Pessoas", "People"): t["pessoas"].astype(int),
        L("Risco", "Risk"): t["risco"].astype(int),
        L("eNPS (tri)", "eNPS (qtr)"): t["enps_tri"].round(0).astype(int),
        "Δ eNPS": t["delta_enps"].round(0).astype(int),
        L("Vol. tri (a.a.)", "Vol. qtr (ann.)"): [pct(x, 0, False) for x in t["vol_tri"]],
        L("Vol. 12m (a.a.)", "Vol. 12m (ann.)"): [pct(x, 0, False) for x in t["vol_12m"]],
        L("Promoções 12m", "Promotions 12m"): t["promocoes_12m"].astype(int),
        L("Pts clima", "Pts engagement"): (t["p_queda_enps"] + t["p_enps_baixo"]).round(0).astype(int),
        "Pts turnover": t["p_turnover"].round(0).astype(int),
        L("Pts promoção", "Pts promotion"): t["p_promocao"].round(0).astype(int),
        L("Pts ausência", "Pts absence"): t["p_ausencia"].round(0).astype(int),
    })


def executar(con, plano: dict[str, Any], ctx):
    dom = ctx.dominio
    fatos: dict[str, Any] = {"dominio": dom.nome, "intencao": plano["intencao"],
                             "aviso_de_dado": L("Domínio com dado SIMULADO.",
                                                "SIMULATED data domain.")}
    linhas: list[str] = []

    if plano["intencao"] == "pessoa":
        fatos["recusa"] = L("pergunta sobre indivíduo; respondido só por "
                            f"grupo de pelo menos {GRUPO_MINIMO} pessoas",
                            "question about an individual; answered only by "
                            f"group of at least {GRUPO_MINIMO} people")
        linhas.append(L(
            "Ah, essa eu não respondo sobre alguém em específico — e não é "
            "limitação técnica, é de propósito. People Analytics que aponta "
            "quem vai sair vira vigilância, e no mês seguinte ninguém responde "
            "a pesquisa de clima com sinceridade. Eu leio grupo, com pelo "
            f"menos {GRUPO_MINIMO} pessoas.",
            "Ah, I don't answer that about anyone specific — and it's not a "
            "technical limitation, it's on purpose. People Analytics that "
            "points at who will leave becomes surveillance, and the next "
            "month nobody answers the engagement survey honestly. I read "
            f"groups, of at least {GRUPO_MINIMO} people."))
        linhas.append(L("O que eu posso fazer é mostrar **onde** o risco está:",
                        "What I can do is show **where** the risk is:"))
        tabela = _executar_risco(con, dom, ctx, fatos, linhas)
        return fatos, tabela, None, linhas

    if plano["intencao"] == "risco":
        tabela = _executar_risco(con, dom, ctx, fatos, linhas)
        return fatos, tabela, None, linhas

    # gap
    g = gap_ajustado(con, dom, ctx.inicio, ctx.fim, ctx.filtros)
    bruto, ajust = g["bruto"], g["ajustado"]
    m_gap = dom.metrica("gap_genero")
    fatos.update({
        "periodo": f"{i18n.data(ctx.inicio)} – {i18n.data(ctx.fim)}",
        "filtros_ativos": ctx.filtros.resumo(dom),
        "gap_bruto": numero(bruto, m_gap),
        "gap_ajustado_nivel_area": numero(ajust, m_gap),
        "cobertura_do_ajuste": pct(g["cobertura"], 0, False),
        "grupo_minimo": GRUPO_MINIMO,
    })
    if not (ajust == ajust):
        linhas.append(L(
            f"O gap bruto no período é de **{numero(bruto, m_gap)}**, mas com "
            f"o filtro atual nenhum cargo tem pelo menos {GRUPO_MINIMO} "
            f"mulheres e {GRUPO_MINIMO} homens — sem isso, comparar salário "
            f"médio é comparar o salário de pessoas. Tire um filtro para eu "
            f"calcular o ajustado.",
            f"The raw gap in the period is **{numero(bruto, m_gap)}**, but "
            f"with the current filter no job has at least {GRUPO_MINIMO} "
            f"women and {GRUPO_MINIMO} men — without that, comparing average "
            f"salaries means comparing individual people's salaries. Remove a "
            f"filter so I can calculate the adjusted gap."))
        return fatos, None, None, linhas

    parte_mix = (bruto - ajust) / bruto if bruto and bruto > 0 else float("nan")
    fatos["parcela_explicada_por_composicao"] = pct(parte_mix, 0, False)
    b_, a_ = numero(bruto, m_gap), numero(ajust, m_gap)
    linhas.append(L(
        f"O gap **bruto** é de **{b_}**: é quanto o salário "
        f"médio das mulheres fica abaixo do dos homens, sem ajuste. Comparando "
        f"mulheres e homens **no mesmo nível e na mesma área**, o gap cai para "
        f"**{a_}**.",
        f"The **raw** gap is **{b_}**: how far women's average salary sits "
        f"below men's, with no adjustment. Comparing women and men **at the "
        f"same level and in the same area**, the gap drops to **{a_}**."))
    if parte_mix == parte_mix and parte_mix > 0:
        pm = pct(parte_mix, 0, False)
        linhas.append(L(
            f"Ou seja, cerca de **{pm} do gap é de "
            f"composição** — há menos mulheres nos cargos e áreas que pagam "
            f"mais — e o resto é diferença de salário no mesmo cargo.",
            f"In other words, about **{pm} of the gap is composition** — "
            f"there are fewer women in the jobs and areas that pay more — and "
            f"the rest is a pay difference within the same job."))
    rep = g["representacao"]
    if not rep.empty:
        linhas.append(L("Representação feminina por nível: ",
                        "Female representation by level: ") + ", ".join(
            f"{V(r.nivel)} {pct(r.mulheres, 0, False)}"
            for r in rep.itertuples()) + ".")
    v = g["celulas"]
    v = v[v["valida"]].sort_values("gap", ascending=False)
    if not v.empty:
        r0 = v.iloc[0]
        linhas.append(L(
            f"O maior gap no mesmo cargo está em **{r0.area} · {r0.nivel}**: "
            f"{pct(r0.gap, 1, False)} ({moeda(r0.salario_f, 0)} contra "
            f"{moeda(r0.salario_m, 0)}).",
            f"The largest same-job gap is in **{_grupo(r0.area, r0.nivel)}**: "
            f"{pct(r0.gap, 1, False)} ({moeda(r0.salario_f, 0)} against "
            f"{moeda(r0.salario_m, 0)})."))
    linhas.append(L(
        "**O que fazer:** as duas partes pedem ações diferentes. A de "
        "composição é pipeline — promoção e contratação de mulheres para "
        "Liderança e Tecnologia. A do mesmo cargo é revisão salarial, "
        "começando pelas células com maior gap. Tratar o bruto como se fosse "
        "tudo equiparação erra o remédio.",
        "**What to do:** the two parts call for different actions. The "
        "composition part is pipeline — promoting and hiring women into "
        "Leadership and Technology. The same-job part is a pay review, "
        "starting with the cells with the largest gap. Treating the raw gap "
        "as if it were all pay equity gets the remedy wrong."))
    cob = pct(g['cobertura'], 0, False)
    linhas.append(L(
        f"*Ajuste por nível × área, com peso pela base de cada "
        f"cargo. Entram só cargos com pelo menos {GRUPO_MINIMO} "
        f"mulheres e {GRUPO_MINIMO} homens ({cob} da base).*",
        f"*Adjusted by level × area, weighted by each job's base. Only jobs "
        f"with at least {GRUPO_MINIMO} women and {GRUPO_MINIMO} men count "
        f"({cob} of the base).*"))
    t = v.head(10)
    tabela = pd.DataFrame({
        L("Área", "Area"): t["area"].map(V), L("Nível", "Level"): t["nivel"].map(V),
        L("Mulheres", "Women"): t["pessoas_f"].astype(int),
        L("Homens", "Men"): t["pessoas_m"].astype(int),
        L("Salário médio F", "Avg salary F"): [moeda(x, 0) for x in t["salario_f"]],
        L("Salário médio M", "Avg salary M"): [moeda(x, 0) for x in t["salario_m"]],
        L("Gap no cargo", "Same-job gap"): [pct(x, 1, False) for x in t["gap"]],
    })
    return fatos, tabela, None, linhas
