"""
Leitura analítica: o que o número quer dizer, para onde ele vai, e o que fazer.

O motor sabe calcular. Este módulo é o que transforma cálculo em leitura — as
três camadas que toda resposta do agente carrega:

    o número   →   o que explica   →   o que fazer

E o faz **sem depender do modelo de linguagem**. As frases aqui saem de regras
sobre números já calculados, então continuam existindo quando não há chave de
API. Com chave, o LLM reescreve isso em prosa mais solta; sem chave, o texto é
mais seco e igualmente correto. O que nunca muda é a substância.

Por que a recomendação é derivada, e não escrita pelo modelo
-----------------------------------------------------------
"O que fazer" depende de coisas que o modelo não tem como saber olhando o
número: se a variação é de taxa ou de mix, se a série tem sazonalidade forte, se
o desvio se concentra num segmento ou está espalhado. Essas distinções mudam a
recomendação de lado — mix pede aquisição, taxa pede operação. Deixá-las para o
modelo é convidar conselho genérico. Aqui elas são calculadas e viram regra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

import duckdb
import numpy as np
import pandas as pd

from . import alertas as mod_alertas
from . import causa_raiz as mod_causa
from . import tendencia as mod_tendencia
from .dados import Filtros, agregar, comparar
from . import i18n
from .formatacao import numero, pct
from .i18n import L as tr, V
from .periodos import Comparacao, montar_preset
from .semantica import Dominio


# --------------------------------------------------------------------------- #
# Fórmula com números de verdade
# --------------------------------------------------------------------------- #

def formula_com_numeros(
    con: duckdb.DuckDBPyConnection, dom: Dominio, mk: str,
    inicio: date, fim: date, filtros: Optional[Filtros] = None,
) -> Optional[str]:
    """
    Mostra a conta da métrica com os valores do período.

    Só existe quando há conta. Métrica que é uma soma pura não ganha fórmula —
    escrever "Receita = soma da receita" não ensina nada e vira ruído.
    """
    m = dom.metrica(mk)
    if not m.formula or not m.eh_razao:
        return None
    df = agregar(con, dom, [mk], inicio, fim, filtros=filtros)
    if df.empty:
        return None
    num, den, val = (df.iloc[0][f"{mk}__num"], df.iloc[0][f"{mk}__den"],
                     df.iloc[0][mk])
    if pd.isna(num) or pd.isna(den) or not den:
        return None

    def _n(x: float) -> str:
        return i18n.num(x, 0 if abs(x) >= 1000 else 2)

    return (f"{m.rotulo} = {m.formula} = {_n(float(num))} ÷ {_n(float(den))} "
            f"= **{numero(float(val), m)}**")


# --------------------------------------------------------------------------- #
# Enriquecimento: as três camadas
# --------------------------------------------------------------------------- #

@dataclass
class Leitura:
    insights: list[str] = field(default_factory=list)
    tendencia: list[str] = field(default_factory=list)
    recomendacoes: list[str] = field(default_factory=list)
    formula: Optional[str] = None

    def vazia(self) -> bool:
        return not (self.insights or self.tendencia or self.recomendacoes)

    def para_fatos(self) -> dict[str, Any]:
        saida: dict[str, Any] = {}
        if self.insights:
            saida["insights"] = self.insights
        if self.tendencia:
            saida["tendencia"] = self.tendencia
        if self.recomendacoes:
            saida["recomendacoes"] = self.recomendacoes
        if self.formula:
            saida["formula_com_numeros"] = self.formula
        return saida


def _melhor_dimensao(con, dom, mk, comp, filtros, preferida=None):
    """
    Escolhe por qual dimensão vale a pena decompor.

    Nem toda dimensão discrimina. Em Produto, "etapa da jornada" concentra 100%
    de qualquer métrica de tempo de entrega em "Entregue" -- por definição, só
    pedido entregue tem tempo de entrega. A frase sai tecnicamente correta e
    completamente inútil.

    A regra: fica a primeira dimensão que produza pelo menos DOIS segmentos com
    contribuição não desprezível. Uma decomposição de um segmento só não é uma
    decomposição.
    """
    if comp.composta:
        return None, None

    candidatas = ([preferida] if preferida else []) + \
                 list(dom.alertar_dims) + list(dom.dims_filtro)
    vistas = set()
    reserva = (None, None)
    for dk in candidatas:
        if not dk or dk in vistas or dk not in dom.dimensoes:
            continue
        vistas.add(dk)
        try:
            dec = mod_causa.decompor(con, dom, mk, dk, comp, filtros, top_n=5)
        except Exception:
            continue
        if not np.isfinite(dec.delta) or abs(dec.delta) < 1e-12:
            continue
        relevantes = (dec.df["contribuicao"].abs()
                      > abs(dec.delta) * 0.02).sum()
        if relevantes >= 2:
            return dk, dec
        if reserva == (None, None):
            reserva = (dk, dec)
    return reserva


def ler(
    con: duckdb.DuckDBPyConnection, dom: Dominio, mk: str,
    inicio: date, fim: date, comp: Comparacao,
    filtros: Optional[Filtros] = None, dim_preferida: Optional[str] = None,
) -> Leitura:
    """Monta insight, tendência e recomendação para uma métrica."""
    m = dom.metrica(mk)
    L = Leitura()
    L.formula = formula_com_numeros(con, dom, mk, inicio, fim, filtros)

    # --- 1. o que explica: comparação e decomposição ---------------------- #
    comparado = comparar(con, dom, [mk], comp, filtros).get(mk, {})
    dp = comparado.get("delta_pct")
    if dp is not None and np.isfinite(dp):
        melhorou = (dp > 0) == m.bom_quando_sobe
        L.insights.append(tr(
            f"Contra {comp.rotulo_base()}, {m.rotulo.lower()} "
            f"{'subiu' if dp > 0 else 'caiu'} {pct(abs(dp), 1, sinal=False)} "
            f"— movimento {'a favor do' if melhorou else 'contra o'} negócio.",
            f"Against {comp.rotulo_base()}, {m.rotulo.lower()} "
            f"{'rose' if dp > 0 else 'fell'} {pct(abs(dp), 1, sinal=False)} "
            f"— a move {'in favor of' if melhorou else 'against'} the "
            f"business."
        ))

    dim, dec = _melhor_dimensao(con, dom, mk, comp, filtros, dim_preferida)

    if dec is not None and np.isfinite(dec.delta) and abs(dec.delta) > 0:
        reais = dec.df[~dec.df["segmento"].str.startswith("Outros (")]
        if not reais.empty:
            topo = reais.iloc[0]
            seg = V(topo["segmento"])
            rot_dim = dom.dimensao(dim).rotulo.lower()
            parte = abs(float(topo["share_da_variacao"]))
            if parte >= 0.3:
                L.insights.append(tr(
                    f"A variação se concentra: **{seg}** responde "
                    f"por {pct(parte, 0, sinal=False)} dela sozinho(a).",
                    f"The change is concentrated: **{seg}** alone accounts "
                    f"for {pct(parte, 0, sinal=False)} of it."
                ))
                L.recomendacoes.append(tr(
                    f"Comece por {rot_dim} = **{seg}** — é onde o movimento "
                    f"está, e olhar o total primeiro só adia a conversa.",
                    f"Start with {rot_dim} = **{seg}** — that's where the "
                    f"movement is, and looking at the total first only delays "
                    f"the conversation."
                ))
            else:
                L.insights.append(tr(
                    f"A variação está **espalhada** por {rot_dim}: "
                    f"o maior contribuinte responde por só "
                    f"{pct(parte, 0, sinal=False)}. Isso aponta causa geral, "
                    f"não um segmento.",
                    f"The change is **spread out** across {rot_dim}: the "
                    f"largest contributor accounts for only "
                    f"{pct(parte, 0, sinal=False)}. That points to a general "
                    f"cause, not a segment."
                ))

        if dec.eh_razao:
            taxa = float(dec.df["efeito_taxa"].sum())
            mix = float(dec.df["efeito_mix"].sum())
            if abs(taxa) + abs(mix) > 1e-12:
                if abs(taxa) >= abs(mix) * 1.5:
                    L.insights.append(tr(
                        "Predomina **efeito taxa**: os segmentos mudaram de "
                        "patamar de verdade, não é só composição.",
                        "**Rate effect** dominates: the segments really "
                        "changed level, it is not just composition."
                    ))
                    L.recomendacoes.append(tr(
                        "Como é efeito taxa, a ação é dentro do segmento — "
                        "operação, preço ou processo. Mexer em aquisição aqui "
                        "não resolve.",
                        "Since it's a rate effect, the action is inside the "
                        "segment — operations, price or process. Touching "
                        "acquisition won't fix it."
                    ))
                elif abs(mix) >= abs(taxa) * 1.5:
                    L.insights.append(tr(
                        "Predomina **efeito mix**: nenhum segmento mudou muito "
                        "de patamar; mudou quem entrou na base.",
                        "**Mix effect** dominates: no segment changed level "
                        "much; what changed is who came into the base."
                    ))
                    L.recomendacoes.append(tr(
                        "Como é efeito mix, a ação é em aquisição e canal — "
                        "cobrar a operação do segmento seria cobrar a pessoa "
                        "errada.",
                        "Since it's a mix effect, the action is in acquisition "
                        "and channel — pushing the segment's operations would "
                        "be pushing the wrong person."
                    ))

    # --- 2. para onde vai: tendência --------------------------------------- #
    t = None
    try:
        t = mod_tendencia.analisar(con, dom, mk, inicio, fim, filtros)
    except Exception:
        t = None

    if t is not None:
        L.tendencia = mod_tendencia.descrever(t)
        if t.direcao != "estavel":
            bom = (t.inclinacao_dia > 0) == m.bom_quando_sobe
            if not bom:
                ritmo = pct(abs(t.inclinacao_pct_mes), 0, sinal=False)
                L.recomendacoes.append(tr(
                    f"A inclinação é sustentada, não um ponto fora da curva: "
                    f"{m.rotulo.lower()} vem piorando {ritmo} ao mês. Tratar "
                    f"como incidente do dia subestima o problema.",
                    f"The slope is sustained, not an outlier: "
                    f"{m.rotulo.lower()} has been getting worse by {ritmo} a "
                    f"month. Treating it as a one-day incident underestimates "
                    f"the problem."
                ))
        if t.amplitude_semanal and t.amplitude_semanal > 0.15:
            L.recomendacoes.append(tr(
                "A série tem sazonalidade semanal forte. Compare o dia com "
                "**D-7** ou com a média dos mesmos dias da semana; contra "
                "ontem, o número mistura calendário com desempenho.",
                "The series has strong weekly seasonality. Compare the day "
                "with **D-7** or with the average of the same weekdays; "
                "against yesterday, the number mixes calendar with "
                "performance."
            ))
        if abs(t.sequencia) >= 5:
            L.insights.append(tr(
                f"São {abs(t.sequencia)} dias seguidos "
                f"{'acima' if t.sequencia > 0 else 'abaixo'} da mediana móvel "
                f"— mudança de patamar, não oscilação.",
                f"That's {abs(t.sequencia)} days in a row "
                f"{'above' if t.sequencia > 0 else 'below'} the rolling median "
                f"— a change of level, not an oscillation."
            ))

    # --- 3. o que já está gritando: alertas do dia ------------------------- #
    try:
        al = [a for a in mod_alertas.varrer(con, dom, fim, filtros)
              if a.chave_metrica == mk]
    except Exception:
        al = []
    if al:
        a = al[0]
        L.insights.append(tr(
            f"Esta métrica já está em alerta em {i18n.data_curta(fim)}: "
            f"{a.texto.replace('**', '')}",
            f"This metric is already on alert on {i18n.data_curta(fim)}: "
            f"{a.texto.replace('**', '')}"
        ))

    if not L.recomendacoes:
        outras = ', '.join(dom.dimensao(k).rotulo.lower()
                           for k in dom.dims_filtro[1:4])
        L.recomendacoes.append(tr(
            f"Nada aqui pede ação imediata. Se quiser aprofundar, peça a causa "
            f"raiz por outra dimensão — {outras}.",
            f"Nothing here calls for immediate action. To go deeper, ask for "
            f"the root cause by another dimension — {outras}."
        ))
    return L


# --------------------------------------------------------------------------- #
# Análise geral da situação
# --------------------------------------------------------------------------- #

def analise_geral(
    con: duckdb.DuckDBPyConnection, dom: Dominio, inicio: date, fim: date,
    comp: Comparacao, filtros: Optional[Filtros] = None,
) -> dict[str, Any]:
    """
    Um raio-x do domínio: o que está bem, o que está mal, o que está mudando
    e o que fazer primeiro.

    A ordem não é a das métricas no painel — é a da urgência. Primeiro o que
    piorou mais, porque é isso que a pessoa precisa saber antes de qualquer
    outra coisa; o que melhorou vem depois, e serve de contexto.
    """
    metricas = dom.metricas_painel
    comparado = comparar(con, dom, metricas, comp, filtros)

    movimentos = []
    for mk in metricas:
        m = dom.metrica(mk)
        c = comparado[mk]
        dp = c.get("delta_pct")
        if dp is None or not np.isfinite(dp):
            continue
        melhorou = (dp > 0) == m.bom_quando_sobe
        movimentos.append({
            "chave": mk, "rotulo": m.rotulo,
            "atual": numero(c["atual"], m), "base": numero(c["base"], m),
            "variacao": pct(dp), "melhorou": melhorou, "magnitude": abs(dp),
        })

    pioras = sorted([x for x in movimentos if not x["melhorou"]],
                    key=lambda x: -x["magnitude"])
    melhoras = sorted([x for x in movimentos if x["melhorou"]],
                      key=lambda x: -x["magnitude"])

    al = mod_alertas.varrer(con, dom, fim, filtros)
    alertas_altos = [a for a in al if a.severidade == "alta"]

    # Leitura profunda só da métrica que mais piorou: é onde a atenção deve ir.
    foco = pioras[0]["chave"] if pioras else (
        melhoras[0]["chave"] if melhoras else metricas[0])
    leitura = ler(con, dom, foco, inicio, fim, comp, filtros)

    motivos = []
    for a in al[:3]:
        mt = mod_alertas.motivo_provavel(con, dom, a, filtros,
                                         nomear_metrica=True)
        if mt:
            motivos.append({"alerta": a.texto, "motivo": mt})

    return {
        "dominio": dom.nome,
        "periodo": f"{i18n.data(inicio)} – {i18n.data(fim)}",
        "comparacao": comp.descricao,
        "base_da_comparacao": comp.rotulo_base(),
        "filtros": (filtros.resumo(dom) if filtros else tr("sem filtro",
                                                            "no filter")),
        "piorou": pioras[:4],
        "melhorou": melhoras[:4],
        "alertas_no_dia": mod_alertas.resumir(al, fim),
        "alertas_severidade_alta": len(alertas_altos),
        "alertas_com_motivo": motivos,
        "metrica_em_foco": dom.metrica(foco).rotulo,
        "leitura_do_foco": leitura.para_fatos(),
    }


def narrar_analise_geral(dom: Dominio, dados: dict[str, Any]) -> list[str]:
    """Versão em texto da análise geral, sem depender do modelo."""
    linhas: list[str] = []
    pior = dados["piorou"][0] if dados["piorou"] else None
    melhor = dados["melhorou"][0] if dados["melhorou"] else None

    if pior:
        linhas.append(tr(
            f"**O que mais preocupa:** {pior['rotulo']} está em "
            f"{pior['atual']}, contra {pior['base']} na base — "
            f"{pior['variacao']}. É o maior movimento contra o negócio no "
            f"período.",
            f"**What worries me most:** {pior['rotulo']} is at "
            f"{pior['atual']}, against {pior['base']} in the baseline — "
            f"{pior['variacao']}. It's the biggest move against the business "
            f"in the period."
        ))
    else:
        linhas.append(tr(
            "**Nenhuma métrica do painel piorou** nesta comparação. O período "
            "está limpo.",
            "**No dashboard metric got worse** in this comparison. The period "
            "is clean."
        ))

    if len(dados["piorou"]) > 1:
        outras = ", ".join(f"{x['rotulo']} ({x['variacao']})"
                           for x in dados["piorou"][1:4])
        linhas.append(tr(f"Também no vermelho: {outras}.",
                         f"Also in the red: {outras}."))

    if melhor:
        linhas.append(tr(
            f"**Do lado bom:** {melhor['rotulo']} em {melhor['atual']} "
            f"({melhor['variacao']} contra a base).",
            f"**On the bright side:** {melhor['rotulo']} at {melhor['atual']} "
            f"({melhor['variacao']} against the baseline)."
        ))

    linhas.append(tr("**Alertas.** ", "**Alerts.** ") + dados['alertas_no_dia'])
    for m in dados["alertas_com_motivo"][:2]:
        linhas.append(m["motivo"])

    leitura = dados["leitura_do_foco"]
    for i in leitura.get("insights", [])[:3]:
        linhas.append(i)
    for t in leitura.get("tendencia", [])[:2]:
        linhas.append(t)

    recs = leitura.get("recomendacoes", [])
    if recs:
        linhas.append(tr("**O que fazer primeiro**", "**What to do first**"))
        for i, r in enumerate(recs[:3], 1):
            linhas.append(f"{i}. {r}")

    return linhas
