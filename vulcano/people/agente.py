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
from ..formatacao import moeda, numero, pct

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
    r"|salario d[oa] (fulan|ciclan|beltran|joao|maria|[a-z]+ da ))")

GAP = ["gap", "equidade salarial", "diferenca salarial", "desigualdade salarial",
       "pay gap", "ganham menos", "ganha menos", "mulheres ganham",
       "diferenca de salario", "salario de mulher", "salario das mulheres"]
TEMPORAL = ["crescendo", "caindo", "subindo", "tendencia", "variacao", "mudou",
            "mudanca", "contra o mes", "mes passado", "evolucao", "por dia",
            "serie", "ao longo"]
RISCO = ["risco de saida", "risco de turnover", "risco de perder",
         "risco de pedido", "onde tem risco", "onde ha risco", "vai sair",
         "vao sair", "podem sair", "pode sair", "sinal de saida",
         "sinais de saida", "sinal antecedente", "sinais antecedentes",
         "indicador antecedente", "antes de sair", "proxima onda",
         "quem esta insatisfeito", "onde esta insatisfeito", "flight risk",
         "risco de fuga", "vamos perder gente"]


def interpretar(pergunta: str, ctx) -> Optional[dict[str, Any]]:
    t = _norm(pergunta)
    if PESSOA.search(t):
        return {"intencao": "pessoa"}

    from ..conversa import pergunta_de_conceito
    if pergunta_de_conceito(pergunta) or re.search(
            r"o que e |como funciona|como e calculad|como voce calcula", t):
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
        m.append(f"eNPS caiu {abs(r.delta_enps):.0f} pontos no trimestre "
                 f"(de {r.enps_ant:+.0f} para {r.enps_tri:+.0f})")
    elif r.p_enps_baixo >= 5:
        m.append(f"eNPS negativo ({r.enps_tri:+.0f})")
    if r.p_turnover >= 5:
        m.append(f"turnover voluntário do trimestre em {pct(r.vol_tri, 0, False)} "
                 f"a.a., acima dos {pct(r.vol_12m, 0, False)} dos 12 meses")
    if r.p_promocao:
        m.append("nenhuma promoção em 12 meses")
    if r.p_ausencia >= 3:
        m.append(f"absenteísmo subindo ({pct(r.abs_ant, 1, False)} → "
                 f"{pct(r.abs_tri, 1, False)})")
    return m


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #

def _ref(con, ctx) -> date:
    _, dmax = periodo_disponivel(con)
    return min(ctx.fim, dmax)


def _executar_risco(con, dom, ctx, fatos, linhas):
    ref = _ref(con, ctx)
    df = sinais_de_risco(con, dom, ref, ctx.filtros)
    fatos.update({"referencia": ref.strftime("%d/%m/%Y"),
                  "filtros_ativos": ctx.filtros.resumo(dom),
                  "grupo_minimo": GRUPO_MINIMO,
                  "pesos_do_score": PESOS_RISCO})
    if df.empty:
        linhas.append(f"Com o filtro atual não sobra nenhum grupo com pelo "
                      f"menos {GRUPO_MINIMO} pessoas e respostas de pesquisa "
                      f"suficientes para ler sinal. Tire um filtro e pergunte "
                      f"de novo.")
        return None
    topo = df[df["risco"] >= 20].head(5)
    fatos["grupos_em_atencao"] = [
        {"grupo": f"{r.area} · {r.nivel}", "pessoas": int(r.pessoas),
         "risco": int(r.risco), "sinais": _motivos(r)}
        for r in topo.itertuples()]
    if topo.empty:
        linhas.append(
            f"Em {ref.strftime('%d/%m/%Y')} nenhum grupo acende sinal de "
            f"saída: clima estável, turnover no ritmo dos 12 meses e promoção "
            f"andando. Vale repetir a pergunta no fim do próximo pulso.")
    else:
        linhas.append(
            f"Lendo os sinais que vêm **antes** do pedido de demissão, até "
            f"{ref.strftime('%d/%m/%Y')}, **{len(topo)} "
            f"{'grupo pede' if len(topo) == 1 else 'grupos pedem'} atenção**:")
        for r in topo.itertuples():
            linhas.append(f"- **{r.area} · {r.nivel}** ({int(r.pessoas)} "
                          f"pessoas, risco {int(r.risco)}): "
                          + "; ".join(_motivos(r)) + ".")
        r0 = topo.iloc[0]
        acao = ("conversa de permanência com a liderança do grupo e revisão "
                "de mérito/promoção antes do próximo ciclo"
                if r0.p_promocao or r0.p_queda_enps >= 15 else
                "ouvir o grupo (pulso aberto ou grupo focal) antes de mexer em "
                "política")
        linhas.append(f"**O que fazer:** começar por {r0.area} · {r0.nivel} — "
                      f"{acao}. Queda de clima costuma chegar ao turnover em "
                      f"dois a quatro meses; a janela para agir é agora.")
    linhas.append(f"*O score é uma soma de sinais nomeados (a conta está na "
                  f"tabela), por grupo de pelo menos {GRUPO_MINIMO} pessoas. "
                  f"Não é previsão de quem vai sair — é onde olhar primeiro.*")
    t = df.head(8)
    return pd.DataFrame({
        "Grupo": t["area"] + " · " + t["nivel"],
        "Pessoas": t["pessoas"].astype(int),
        "Risco": t["risco"].astype(int),
        "eNPS (tri)": t["enps_tri"].round(0).astype(int),
        "Δ eNPS": t["delta_enps"].round(0).astype(int),
        "Vol. tri (a.a.)": [pct(x, 0, False) for x in t["vol_tri"]],
        "Vol. 12m (a.a.)": [pct(x, 0, False) for x in t["vol_12m"]],
        "Promoções 12m": t["promocoes_12m"].astype(int),
        "Pts clima": (t["p_queda_enps"] + t["p_enps_baixo"]).round(0).astype(int),
        "Pts turnover": t["p_turnover"].round(0).astype(int),
        "Pts promoção": t["p_promocao"].round(0).astype(int),
        "Pts ausência": t["p_ausencia"].round(0).astype(int),
    })


def executar(con, plano: dict[str, Any], ctx):
    dom = ctx.dominio
    fatos: dict[str, Any] = {"dominio": dom.nome, "intencao": plano["intencao"],
                             "aviso_de_dado": "Domínio com dado SIMULADO."}
    linhas: list[str] = []

    if plano["intencao"] == "pessoa":
        fatos["recusa"] = ("pergunta sobre indivíduo; respondido só por grupo "
                           f"de pelo menos {GRUPO_MINIMO} pessoas")
        linhas.append(
            "Essa eu não respondo sobre alguém em específico — e não é "
            "limitação técnica, é de propósito. People Analytics que aponta "
            "quem vai sair vira vigilância, e no mês seguinte ninguém responde "
            "a pesquisa de clima com sinceridade. Eu leio grupo, com pelo "
            f"menos {GRUPO_MINIMO} pessoas.")
        linhas.append("O que eu posso fazer é mostrar **onde** o risco está:")
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
        "periodo": f"{ctx.inicio.strftime('%d/%m/%Y')} a "
                   f"{ctx.fim.strftime('%d/%m/%Y')}",
        "filtros_ativos": ctx.filtros.resumo(dom),
        "gap_bruto": numero(bruto, m_gap),
        "gap_ajustado_nivel_area": numero(ajust, m_gap),
        "cobertura_do_ajuste": pct(g["cobertura"], 0, False),
        "grupo_minimo": GRUPO_MINIMO,
    })
    if not (ajust == ajust):
        linhas.append(
            f"O gap bruto no período é de **{numero(bruto, m_gap)}**, mas com "
            f"o filtro atual nenhum cargo tem pelo menos {GRUPO_MINIMO} "
            f"mulheres e {GRUPO_MINIMO} homens — sem isso, comparar salário "
            f"médio é comparar o salário de pessoas. Tire um filtro para eu "
            f"calcular o ajustado.")
        return fatos, None, None, linhas

    parte_mix = (bruto - ajust) / bruto if bruto and bruto > 0 else float("nan")
    fatos["parcela_explicada_por_composicao"] = pct(parte_mix, 0, False)
    linhas.append(
        f"O gap **bruto** é de **{numero(bruto, m_gap)}**: é quanto o salário "
        f"médio das mulheres fica abaixo do dos homens, sem ajuste. Comparando "
        f"mulheres e homens **no mesmo nível e na mesma área**, o gap cai para "
        f"**{numero(ajust, m_gap)}**.")
    if parte_mix == parte_mix and parte_mix > 0:
        linhas.append(
            f"Ou seja, cerca de **{pct(parte_mix, 0, False)} do gap é de "
            f"composição** — há menos mulheres nos cargos e áreas que pagam "
            f"mais — e o resto é diferença de salário no mesmo cargo.")
    rep = g["representacao"]
    if not rep.empty:
        linhas.append("Representação feminina por nível: " + ", ".join(
            f"{r.nivel} {pct(r.mulheres, 0, False)}" for r in rep.itertuples())
            + ".")
    v = g["celulas"]
    v = v[v["valida"]].sort_values("gap", ascending=False)
    if not v.empty:
        r0 = v.iloc[0]
        linhas.append(
            f"O maior gap no mesmo cargo está em **{r0.area} · {r0.nivel}**: "
            f"{pct(r0.gap, 1, False)} ({moeda(r0.salario_f, 0)} contra "
            f"{moeda(r0.salario_m, 0)}).")
    linhas.append(
        "**O que fazer:** as duas partes pedem ações diferentes. A de "
        "composição é pipeline — promoção e contratação de mulheres para "
        "Liderança e Tecnologia. A do mesmo cargo é revisão salarial, "
        "começando pelas células com maior gap. Tratar o bruto como se fosse "
        "tudo equiparação erra o remédio.")
    linhas.append(f"*Ajuste por nível × área, com peso pela base de cada "
                  f"cargo. Entram só cargos com pelo menos {GRUPO_MINIMO} "
                  f"mulheres e {GRUPO_MINIMO} homens "
                  f"({pct(g['cobertura'], 0, False)} da base).*")
    t = v.head(10)
    tabela = pd.DataFrame({
        "Área": t["area"], "Nível": t["nivel"],
        "Mulheres": t["pessoas_f"].astype(int),
        "Homens": t["pessoas_m"].astype(int),
        "Salário médio F": [moeda(x, 0) for x in t["salario_f"]],
        "Salário médio M": [moeda(x, 0) for x in t["salario_m"]],
        "Gap no cargo": [pct(x, 1, False) for x in t["gap"]],
    })
    return fatos, tabela, None, linhas
