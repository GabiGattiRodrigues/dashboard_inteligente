"""
O que o Vulcão responde que nenhum outro agente responde.

Quatro intenções determinísticas, avaliadas ANTES do planejador genérico
(mesmo desenho da Ravena e da Tomoyo):

- **travados** — a fila do dia: o que venceu e não chegou, em que faixa da
                 régua cada pedido está e de quem é a vez de agir;
- **regua**    — se a régua D+3/D+7 se sustenta neste dado: dos pendentes em
                 cada dia depois do prometido, quantos ainda chegam, com
                 intervalo de Wilson;
- **controle** — o gráfico de controle semanal por origem: quem passou do
                 limite e se o atraso de agora é ruído ou mudança de nível;
- **pedido**   — a linha do tempo de um pedido pelo código, com o que a régua
                 mandava fazer em cada data.

Pergunta agregada ("por que o no prazo caiu?", "qual origem atrasa mais?")
segue para o motor genérico, como em qualquer domínio.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd

from .. import i18n
from ..dados import periodo_disponivel
from ..formatacao import moeda, pct
from ..i18n import L, V
from . import dados as ld

INTENCOES = {
    "travados": "a fila de pedidos vencidos e não entregues numa data, com a "
                "ação da régua D+3/D+7",
    "regua": "se a régua D+3/D+7 se sustenta: quantos pendentes ainda chegam "
             "em cada dia depois do prometido",
    "controle": "gráfico de controle semanal da taxa fora do prazo por origem",
    "pedido": "a linha do tempo de um pedido específico, pelo código",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# Código de pedido do Olist: 32 caracteres hexadecimais. Aceita a partir de 6,
# com pelo menos um dígito e uma letra -- "decade" e "123456" não são pedido.
CODIGO = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{6,32}\b")

TRAVADOS = ["travado", "travados", "travada", "parado", "parados",
            "fila", "pendentes", "pendente", "vencidos e nao entregues",
            "venceu e nao chegou", "venceram e nao chegaram",
            "nao chegou", "nao chegaram", "quem acionar", "quem cobrar",
            "o que acionar", "o que fazer hoje", "por onde comeco",
            "por onde comecar", "esquecido", "esquecidos", "backlog",
            # English
            "stuck", "queue", "pending", "overdue", "didn't arrive",
            "did not arrive", "who to chase", "where do i start",
            "where should i start", "what to do today", "forgotten"]
REGUA = ["regua", "d+3/d+7", "d3/d7", "d+3 e d+7", "d+3 e o d+7",
         "ponto de nao retorno", "ponto sem volta", "quando reenviar",
         "quando estornar", "quando cobrar", "quando falar com o cliente",
         "ainda chegam", "ainda chega", "vale esperar", "vale a pena esperar",
         "chance de chegar",
         # English
         "rule", "point of no return", "when to resend", "when to refund",
         "when to chase", "still arrive", "worth waiting", "odds of arriving"]
CONTROLE = ["fora de controle", "sob controle", "em controle",
            "saiu do controle", "semana passada", "ultima semana",
            "como foi a semana", "qual regiao puxou", "quem puxou",
            "last week", "which region", "who drove",
            "grafico de controle", "carta de controle", "controle estatistico",
            "p-chart", "p chart", "pchart", "controle por origem",
            "ruido ou", "e ruido", "mudou de nivel", "limite de controle",
            # English
            "out of control", "in control", "control chart", "control limit",
            "is it noise", "just noise", "special cause"]
TEMPORAL = ["mes passado", "contra o mes", "por que", "porque", "caiu",
            "subiu", "piorou", "melhorou", "tendencia", "crescendo",
            "why", "dropped", "rose", "trend", "vs last"]


def interpretar(pergunta: str, ctx) -> Optional[dict[str, Any]]:
    t = _norm(pergunta)
    m = CODIGO.search(t)
    if m:
        return {"intencao": "pedido", "codigo": m.group(0)}

    # "e por origem?" logo depois da régua continua a régua, aberta por
    # origem. Sem isso o planejador genérico pegaria a pergunta e devolveria
    # um ranking de uma métrica só, sem a curva nem a margem de erro.
    anterior = (ctx.ultimo_plano or {}).get("intencao")
    if anterior in INTENCOES and anterior != "pedido" and len(t.split()) <= 5 \
            and re.search(r"\b(origem|origens|origin|origins|uf|ufs)\b", t):
        if anterior == "regua":
            return {"intencao": "regua", "metrica": "chegam_d7",
                    "por": "origem"}
        if anterior == "controle":
            return {"intencao": "controle", "metrica": "pct_fora_prazo"}

    from ..conversa import pergunta_de_conceito
    if pergunta_de_conceito(pergunta):
        return None

    por = "origem" if re.search(r"\b(origem|origens|origin|origins|uf|ufs|"
                                r"por estado|by state)\b", t) else None
    if any(g in t for g in CONTROLE):
        return {"intencao": "controle", "metrica": "pct_fora_prazo"}
    if any(g in t for g in REGUA) and not any(x in t for x in TEMPORAL):
        return {"intencao": "regua", "metrica": "chegam_d7", "por": por}
    if any(g in t for g in TRAVADOS) and not any(x in t for x in TEMPORAL):
        return {"intencao": "travados", "metrica": "pct_nao_entregue"}
    return None


# --------------------------------------------------------------------------- #

def _ref(con, ctx) -> date:
    _, dmax = periodo_disponivel(con)
    return min(ctx.fim, dmax)


def _regua_txt() -> tuple:
    from ..dominios.logistica import REGUA as R_PT, REGUA_EN as R_EN
    return R_EN if i18n.en() else R_PT


def acao(faixa: str, quem: str) -> str:
    """A frase da régua para um pedido, na língua ativa."""
    alvo = {"transportadora": L("transportadora", "carrier"),
            "seller": L("seller", "seller"),
            "pagamento": L("pagamento (não aprovou)",
                           "payment (not approved)")}.get(quem, quem)
    if faixa == "vencido":
        return L(f"Acompanhar ({alvo})", f"Monitor ({alvo})")
    if faixa == "d3":
        return L(f"D+3: cobrar {alvo}", f"D+3: chase {alvo}")
    if faixa == "d7":
        return L("D+7: falar com o cliente", "D+7: contact the customer")
    return L("Esquecido: decidir baixa/estorno",
             "Forgotten: decide write-off/refund")


def tabela_fila(f: pd.DataFrame, n: Optional[int] = None) -> pd.DataFrame:
    t = f if n is None else f.head(n)
    etapa = {"transito": L("Em trânsito", "In transit"),
             "postagem": L("Aguardando postagem", "Awaiting shipping"),
             "aprovacao": L("Aguardando aprovação", "Awaiting approval")}
    return pd.DataFrame({
        L("Pedido", "Order"): t["pedido"],
        L("Prometido", "Promised"): [i18n.data_curta(_d(x))
                                     for x in t["prometida"]],
        L("Dias vencido", "Days overdue"): t["dias_vencido"].astype(int),
        L("Onde parou", "Where it stopped"): t["etapa"].map(etapa),
        L("Parado há", "Idle for"): [f"{int(x)} d" for x in t["dias_parado"]],
        L("Ação da régua", "Rule action"): [acao(a, b) for a, b in
                                            zip(t["faixa"], t["quem"])],
        L("Rota", "Route"): [f"{V(o)} → {d}" for o, d in
                             zip(t["uf_origem"], t["estado_destino"])],
        L("Valor", "Value"): [moeda(x, 0) for x in t["valor"]],
    })


def _d(x) -> date:
    return x.date() if hasattr(x, "date") else x


def _executar_travados(con, dom, ctx, fatos, linhas):
    ref = _ref(con, ctx)
    f = ld.fila(con, dom, ref, ctx.filtros)
    r = ld.resumo_fila(f)
    ativa = r["vencido"] + r["d3"] + r["d7"]
    data_ref = i18n.data(ref)
    fatos.update({"referencia": data_ref,
                  "filtros_ativos": ctx.filtros.resumo(dom), **{
                      f"fila_{k}": v for k, v in r.items()}})
    if r["total"] == 0:
        linhas.append(L(
            f"Em {data_ref} não tem nenhum pedido vencido sem entrega com esse "
            f"filtro. Fila zerada — raro, aproveita.",
            f"On {data_ref} there's no overdue undelivered order with this "
            f"filter. Empty queue — rare, enjoy it."))
        return None

    linhas.append(L(
        f"Em **{data_ref}**, **{ativa} pedidos** estão na fila ativa — "
        f"venceram há até 30 dias e não chegaram:",
        f"On **{data_ref}**, **{ativa} orders** are in the active queue — "
        f"due up to 30 days ago and not delivered:"))
    linhas.append(L(
        f"- **{r['d7']}** já passaram do **D+7**: hora de falar com o "
        f"cliente (reenviar ou estornar){_hoje(r['hoje_d7'])};\n"
        f"- **{r['d3']}** estão entre o **D+3 e o D+6**: cobrar quem está com "
        f"o pedido{_hoje(r['hoje_d3'])};\n"
        f"- **{r['vencido']}** venceram há um ou dois dias: só acompanhar.",
        f"- **{r['d7']}** are past **D+7**: time to contact the customer "
        f"(resend or refund){_hoje(r['hoje_d7'])};\n"
        f"- **{r['d3']}** are between **D+3 and D+6**: chase whoever has the "
        f"order{_hoje(r['hoje_d3'])};\n"
        f"- **{r['vencido']}** came due one or two days ago: just monitor."))
    fa = f[f["faixa"].isin(["vencido", "d3", "d7"])]
    if not fa.empty:
        tr = int((fa["quem"] == "transportadora").sum())
        se = len(fa) - tr
        linhas.append(L(
            f"De quem é a vez: **{tr}** já foram postados (transportadora) e "
            f"**{se}** nem saíram do seller.",
            f"Whose turn it is: **{tr}** were already shipped (carrier) and "
            f"**{se}** never left the seller."))
    if r["esquecido"]:
        linhas.append(L(
            f"E tem **{r['esquecido']} esquecidos** — vencidos há mais de 30 "
            f"dias, {moeda(f.loc[f['faixa'] == 'esquecido', 'valor'].sum(), 0)}"
            f" parados. A régua não serve mais para eles: é decidir baixa e "
            f"estorno de uma vez. Cada um deles é um D+7 que ninguém fez.",
            f"And there are **{r['esquecido']} forgotten ones** — overdue for "
            f"more than 30 days, "
            f"{moeda(f.loc[f['faixa'] == 'esquecido', 'valor'].sum(), 0)} "
            f"stuck. The rule no longer helps them: it's time to decide "
            f"write-off and refund in one go. Each of them is a D+7 nobody "
            f"did."))
    linhas.append(L(
        "**O que fazer:** começar pelos do D+7 — cliente sem produto há mais "
        "de uma semana é a pior experiência da fila. Os do D+3 são cobrança "
        "em lote, por transportadora ou seller.",
        "**What to do:** start with the D+7 ones — a customer without the "
        "product for more than a week is the worst experience in the queue. "
        "The D+3 ones are batch chasing, by carrier or seller."))
    linhas.append(L(
        "*A fila está como se sabia nesse dia: pedido entregue depois dele "
        "conta como travado.*",
        "*The queue is as it stood that day: an order delivered afterwards "
        "counts as stuck.*"))
    return tabela_fila(fa if not fa.empty else f, 12)


def _hoje(n: int) -> str:
    if not n:
        return ""
    return L(f" — {n} entraram hoje", f" — {n} entered today")


def _executar_regua(con, dom, ctx, plano, fatos, linhas):
    por = plano.get("por")
    curva = ld.ponto_sem_volta(con, dom, ctx.inicio, ctx.fim, ctx.filtros)
    if curva.empty or curva["pendentes"].max() < 30:
        linhas.append(L(
            "Com esse período e filtro sobram pendentes de menos para ler a "
            "curva. Amplia o período na barra lateral (seis meses ou mais).",
            "With this period and filter there are too few pending orders to "
            "read the curve. Widen the period in the sidebar (six months or "
            "more)."))
        return None, None
    def _linha(k):
        r = curva[curva["k"] == k]
        return r.iloc[0] if not r.empty else None
    r3, r7 = _linha(3), _linha(7)
    virada = ld.dia_da_virada(curva)
    fatos.update({
        "periodo": f"{i18n.data(ctx.inicio)} – {i18n.data(ctx.fim)}",
        "ainda_chegam_d3": pct(r3["taxa"], 0, False),
        "ic95_d3": f"{pct(r3['ic_inf'], 0, False)}–{pct(r3['ic_sup'], 0, False)}",
        "pendentes_d3": int(r3["pendentes"]),
        "ainda_chegam_d7": pct(r7["taxa"], 0, False),
        "ic95_d7": f"{pct(r7['ic_inf'], 0, False)}–{pct(r7['ic_sup'], 0, False)}",
        "pendentes_d7": int(r7["pendentes"]),
        "dia_em_que_menos_da_metade_chega": virada,
    })
    p3, p7 = pct(r3["taxa"], 0, False), pct(r7["taxa"], 0, False)
    linhas.append(L(
        f"Dos pedidos que passaram do **D+3** sem chegar, **{p3}** ainda "
        f"chegaram depois (IC95% {fatos['ic95_d3']}, "
        f"{int(r3['pendentes'])} pedidos). No **D+7**, **{p7}** "
        f"(IC95% {fatos['ic95_d7']}, {int(r7['pendentes'])} pedidos).",
        f"Of the orders past **D+3** without arriving, **{p3}** still "
        f"arrived later (95% CI {fatos['ic95_d3']}, "
        f"{int(r3['pendentes'])} orders). At **D+7**, **{p7}** "
        f"(95% CI {fatos['ic95_d7']}, {int(r7['pendentes'])} orders)."))
    if r7["ic_sup"] < r3["ic_inf"]:
        linhas.append(L(
            "As faixas não se cruzam: a chance cai de verdade entre um marco e "
            "outro, não é variação de amostra.",
            "The ranges don't overlap: the odds really drop between one mark "
            "and the other — it's not sampling noise."))
    if r3["taxa"] >= 0.5:
        linhas.append(L(
            "No D+3 a maioria ainda chega — **cobrar e esperar** é a ação "
            "certa.",
            "At D+3 most still arrive — **chase and wait** is the right "
            "move."))
    if r7["taxa"] >= 0.5:
        dv = (L(f"só a partir do **D+{virada}** menos da metade chega",
                f"only from **D+{virada}** do fewer than half arrive")
              if virada else L("a chance não cai abaixo de 50% em 30 dias",
                               "the odds don't drop below 50% within 30 days"))
        linhas.append(L(
            f"Mas no D+7 ainda chega **mais da metade** — reenviar nesse "
            f"ponto duplicaria o envio em {p7} dos casos. Neste dado o D+7 "
            f"serve para **avisar o cliente e dar a escolha**, não para "
            f"reenviar no automático; {dv}.",
            f"But at D+7 **more than half** still arrive — resending at that "
            f"point would duplicate the shipment in {p7} of cases. In this "
            f"data D+7 is for **telling the customer and giving them the "
            f"choice**, not for an automatic resend; {dv}."))
        linhas.append(L(
            "**O que fazer:** manter o D+3 como está e trocar a ação do D+7 "
            "por contato proativo; o reenvio automático entra quando a chance "
            "cai abaixo de 50%. O ajuste fino depende do custo de um envio "
            "duplicado contra o de um cliente perdido — esse número não está "
            "na base.",
            "**What to do:** keep D+3 as is and change the D+7 action to "
            "proactive contact; the automatic resend kicks in when the odds "
            "drop below 50%. Fine-tuning depends on the cost of a duplicate "
            "shipment versus a lost customer — that number isn't in the "
            "data."))
    else:
        linhas.append(L(
            "No D+7 já chega **menos da metade**: esperar mais só piora a "
            "experiência. A régua se sustenta — **D+3 cobra, D+7 resolve** "
            "(reenvio ou estorno, o cliente escolhe).",
            "At D+7 **fewer than half** arrive: waiting longer only makes "
            "things worse. The rule holds — **D+3 chases, D+7 resolves** "
            "(resend or refund, the customer chooses)."))

    tabela = None
    if por:
        c = ld.ponto_sem_volta(con, dom, ctx.inicio, ctx.fim, ctx.filtros,
                               por=por)
        c = c[c["k"].isin([3, 7])]
        piv = []
        for seg, gk in c.groupby("segmento"):
            a = gk[gk["k"] == 3].iloc[0]
            b = gk[gk["k"] == 7].iloc[0]
            if a["pendentes"] < 20:
                continue
            piv.append({
                L("Origem", "Origin"): V(seg),
                L("Pendentes no D+3", "Pending at D+3"): int(a["pendentes"]),
                L("Ainda chegam (D+3)", "Still arrive (D+3)"):
                    f"{pct(a['taxa'], 0, False)} ({pct(a['ic_inf'], 0, False)}–"
                    f"{pct(a['ic_sup'], 0, False)})",
                L("Pendentes no D+7", "Pending at D+7"): int(b["pendentes"]),
                L("Ainda chegam (D+7)", "Still arrive (D+7)"):
                    f"{pct(b['taxa'], 0, False)} ({pct(b['ic_inf'], 0, False)}–"
                    f"{pct(b['ic_sup'], 0, False)})",
                "_t7": b["taxa"],
            })
        if piv:
            tabela = pd.DataFrame(piv).sort_values("_t7").drop(columns="_t7")
            pior = tabela.iloc[0]
            linhas.append(L(
                f"Por origem, a chance cai mais rápido em "
                f"**{pior[L('Origem', 'Origin')]}** — lá a régua pode ser "
                f"mais curta. Origem com pouco pendente tem faixa larga: "
                f"nela vale a régua geral.",
                f"By origin, the odds drop fastest in "
                f"**{pior[L('Origem', 'Origin')]}** — the rule can be shorter "
                f"there. Origins with few pending orders have wide ranges: "
                f"the overall rule applies to them."))
    if tabela is None:
        t = curva[curva["k"].isin([0, 1, 3, 5, 7, 10, 14, 21, 30])]
        tabela = pd.DataFrame({
            L("Dias depois do prometido", "Days after promise"):
                [f"D+{k}" for k in t["k"]],
                L("Ainda pendentes", "Still pending"): t["pendentes"].astype(int),
            L("Chegaram depois", "Arrived later"): t["chegaram"].astype(int),
            L("Ainda chegam", "Still arrive"): [pct(x, 0, False)
                                                for x in t["taxa"]],
            "IC95%": [f"{pct(a, 0, False)}–{pct(b, 0, False)}"
                      for a, b in zip(t["ic_inf"], t["ic_sup"])],
        })
    return tabela, curva


def ler_semana(r: dict, rot_dim: Optional[str] = None) -> list[str]:
    """O aviso da segunda-feira: a última semana fechada saiu do controle, e
    quem puxou. Mesmo texto no chat, na aba de alertas e na de controle."""
    if not r:
        return []
    rot_dim = rot_dim or L("região", "region")
    sem = i18n.data(r["semana"])
    if not r["acima"]:
        linhas = [L(
            f"🌋 A semana de {sem} fechou **dentro do controle**: "
            f"{pct(r['p'], 1, False)} fora do prazo, abaixo do limite de "
            f"{pct(r['lsc'], 1, False)} para o volume dela.",
            f"🌋 The week of {sem} closed **in control**: "
            f"{pct(r['p'], 1, False)} late, below the "
            f"{pct(r['lsc'], 1, False)} limit for its volume.")]
        if r["semanas_acima_8"]:
            linhas.append(L(
                f"Nas últimas 8 semanas, {r['semanas_acima_8']} saíram do "
                f"controle — vale olhar o mapa na aba Controle por origem.",
                f"In the last 8 weeks, {r['semanas_acima_8']} went out of "
                f"control — worth checking the map in the Control by origin "
                f"tab."))
        return linhas
    linhas = [L(
        f"🌋 **A semana de {sem} saiu do controle:** "
        f"{pct(r['p'], 1, False)} dos pedidos fora do prazo, acima do "
        f"limite de {pct(r['lsc'], 1, False)} (o normal é "
        f"{pct(r['p_bar'], 1, False)}).",
        f"🌋 **The week of {sem} went out of control:** "
        f"{pct(r['p'], 1, False)} of orders late, above the "
        f"{pct(r['lsc'], 1, False)} limit (normal is "
        f"{pct(r['p_bar'], 1, False)}).")]
    c = r["contribuicoes"]
    fora = c[c["acima"]] if not c.empty else c
    pux = r["puxou"]
    if len(fora) >= 3:
        nomes = ", ".join(V(x) for x in fora["segmento"])
        linhas.append(L(
            f"Saíram do próprio padrão ao mesmo tempo: {nomes}. Quando a "
            f"malha toda estoura junta, a causa é comum — pico de demanda, "
            f"greve, feriado —, não uma {rot_dim}."
            + (f" Em volume, **{V(pux['segmento'])}** puxou "
               f"{pct(pux['parte'], 0, False)} do atraso a mais." if pux
               else ""),
            f"Out of their own pattern at the same time: {nomes}. When the "
            f"whole network breaks out together, the cause is common — "
            f"demand peak, strike, holiday —, not one {rot_dim}."
            + (f" By volume, **{V(pux['segmento'])}** drove "
               f"{pct(pux['parte'], 0, False)} of the extra delay." if pux
               else "")))
        acao = L("rever a promessa do checkout para todo mundo enquanto o "
                 "pico durar, e avisar o atendimento antes da reclamação.",
                 "revise the checkout promise for everyone while the peak "
                 "lasts, and warn customer service before the complaints.")
    elif pux:
        linhas.append(L(
            f"**Quem puxou foi {V(pux['segmento'])}:** "
            f"{pct(pux['p'], 1, False)} fora do prazo contra "
            f"{pct(pux['p_bar'], 1, False)} do normal dela — "
            f"{pct(pux['parte'], 0, False)} de todo o atraso a mais da "
            f"semana.",
            f"**{V(pux['segmento'])} drove it:** {pct(pux['p'], 1, False)} "
            f"late against its normal {pct(pux['p_bar'], 1, False)} — "
            f"{pct(pux['parte'], 0, False)} of the week's extra delay."))
        acao = L(f"abrir a fila de {V(pux['segmento'])} na aba Pedidos "
                 f"travados (filtro de {rot_dim}) e cobrar quem opera ali "
                 f"ainda esta semana.",
                 f"open the {V(pux['segmento'])} queue in the Stuck orders "
                 f"tab ({rot_dim} filter) and chase whoever operates there "
                 f"this week.")
    else:
        acao = L("olhar a fila do D+3 antes que vire D+7.",
                 "look at the D+3 queue before it becomes D+7.")
    linhas.append(L("**O que fazer:** ", "**What to do:** ") + acao)
    return linhas


def _executar_controle(con, dom, ctx, fatos, linhas, com_semana=True):
    ref = _ref(con, ctx)
    dmin, _ = periodo_disponivel(con)
    semana = (ld.semana_da_malha(con, dom, ref, ctx.filtros, dmin)
              if com_semana else {})
    if semana:
        linhas += ler_semana(semana)
        fatos["ultima_semana_fechada"] = {
            k: (str(v) if k == "semana" else v) for k, v in semana.items()
            if k != "contribuicoes"}
    # Origem e malha na mesma régua: só semanas completas.
    ini, fim = ld.janela_controle(ld.ultimo_domingo(ref), dmin)
    c = ld.controle(con, dom, ini, fim, ctx.filtros, por="origem")
    s = ld.resumo_controle(c)
    s = s[s["pedidos"] >= 200] if not s.empty else s
    fatos.update({"janela": f"{i18n.data(ini)} – {i18n.data(fim)}",
                  "regra": "p̄ ± 3·√(p̄(1−p̄)/n), semanal, por origem"})
    if s.empty:
        linhas.append(L("Sem volume suficiente para o gráfico de controle "
                        "com esse filtro.",
                        "Not enough volume for the control chart with this "
                        "filter."))
        return None, None
    agora = s[s["ultima_acima"] | (s["ultima_sequencia"] > 0)]
    melhorou = s[~s["ultima_acima"] & (s["ultima_sequencia"] < 0)]
    sem = i18n.data(_d(s["ultima_semana"].max()))
    fatos["origens_fora_de_controle_na_ultima_semana"] = list(agora["segmento"])
    if agora.empty:
        linhas.append(L(
            f"Por origem, na mesma semana, **nenhuma está fora de "
            f"controle**.",
            f"By origin, in the same week, **none is out of control**."))
    else:
        for r in agora.itertuples():
            motivo = (L(f"{pct(r.p_ultima, 1, False)} fora do prazo, acima do "
                        f"limite de {pct(r.lsc_ultima, 1, False)}",
                        f"{pct(r.p_ultima, 1, False)} late, above the "
                        f"{pct(r.lsc_ultima, 1, False)} limit")
                      if r.ultima_acima else
                      L("oito semanas seguidas acima da média — o nível mudou",
                        "eight weeks in a row above average — the level "
                        "shifted"))
            linhas.append(L(f"- Origem **{V(r.segmento)}** fora de controle "
                            f"na mesma semana: {motivo}.",
                            f"- Origin **{V(r.segmento)}** out of control in "
                            f"the same week: {motivo}."))
    if not melhorou.empty:
        quem = ", ".join(V(x) for x in melhorou["segmento"])
        linhas.append(L(
            f"Do outro lado, **{quem}** "
            f"{'está' if len(melhorou) == 1 else 'estão'} há oito semanas ou "
            f"mais abaixo da própria média: o nível mudou para melhor. Vale "
            f"conferir se é operação melhor ou promessa folgada demais no "
            f"checkout — as duas coisas aparecem igual neste gráfico.",
            f"On the other side, **{quem}** "
            f"{'has' if len(melhorou) == 1 else 'have'} been below "
            f"{'its' if len(melhorou) == 1 else 'their'} own average for "
            f"eight weeks or more: the level shifted for the better. Worth "
            f"checking whether it's better operations or a checkout promise "
            f"that's too loose — both look the same on this chart."))
    janela = s[s["semanas_acima"] > 0]
    if not janela.empty:
        r0 = janela.sort_values("semanas_acima", ascending=False).iloc[0]
        linhas.append(L(
            f"Nas últimas {ld.SEMANAS_CONTROLE} semanas, quem mais passou do "
            f"limite foi **{V(r0.segmento)}**: {int(r0.semanas_acima)} semanas, "
            f"a pior em {i18n.data(_d(r0.pior_semana))} "
            f"({pct(r0.p_pior, 0, False)} fora do prazo, contra "
            f"{pct(r0.p_bar, 1, False)} de média).",
            f"Over the last {ld.SEMANAS_CONTROLE} weeks, the origin that "
            f"crossed the limit most was **{V(r0.segmento)}**: "
            f"{int(r0.semanas_acima)} weeks, the worst starting "
            f"{i18n.data(_d(r0.pior_semana))} ({pct(r0.p_pior, 0, False)} "
            f"late, against a {pct(r0.p_bar, 1, False)} average)."))
        # Semanas em que VÁRIAS origens estouram juntas são da malha, não de
        # uma origem: Black Friday, greve, Carnaval.
        juntas = (c[c["acima"] & c["segmento"].isin(s["segmento"])]
                  .groupby("semana")["segmento"].nunique())
        comuns = juntas[juntas >= 3]
        if not comuns.empty:
            semanas = ", ".join(i18n.data_curta(_d(x))
                                for x in comuns.index[:4])
            linhas.append(L(
                f"Em {len(comuns)} semanas três ou mais origens estouraram "
                f"juntas ({semanas}) — isso é causa comum da malha "
                f"(pico de demanda, greve), não problema de uma origem.",
                f"In {len(comuns)} weeks three or more origins broke out "
                f"together ({semanas}) — that's a network-wide cause (demand "
                f"peak, strike), not one origin's problem."))
    if not semana:
        linhas.append(L(
            "**O que fazer:** origem fora de controle sozinha pede conversa "
            "com quem opera ela naquela semana; várias juntas pedem revisar a "
            "promessa do checkout enquanto o pico durar. Dentro do limite, "
            "não mexe — é ruído.",
            "**What to do:** a single origin out of control calls for a talk "
            "with whoever runs it that week; several together call for "
            "revising the checkout promise while the peak lasts. Within the "
            "limit, leave it — it's noise."))
    tabela = pd.DataFrame({
        L("Origem", "Origin"): s["segmento"].map(V),
        L("Pedidos", "Orders"): [i18n.num(x, 0) for x in s["pedidos"]],
        L("Média fora do prazo", "Average late"): [pct(x, 1, False)
                                                   for x in s["p_bar"]],
        L("Semanas acima do limite", "Weeks above limit"): s["semanas_acima"],
        L("Última semana", "Last week"): [pct(x, 1, False)
                                          for x in s["p_ultima"]],
        L("Limite da última", "Last week's limit"): [pct(x, 1, False)
                                                     for x in s["lsc_ultima"]],
    })
    return tabela, c


def _executar_pedido(con, dom, ctx, plano, fatos, linhas):
    df = ld.achar_pedido(con, plano["codigo"])
    if df.empty:
        linhas.append(L(
            f"Não achei pedido começando com `{plano['codigo']}`. Pode ser "
            f"cancelado (fica fora deste painel) ou com prazo fora de "
            f"fev/2017–ago/2018.",
            f"I couldn't find an order starting with `{plano['codigo']}`. It "
            f"may be canceled (left out of this dashboard) or due outside Feb "
            f"2017–Aug 2018."))
        return None
    if len(df) > 1:
        linhas.append(L(f"Achei {len(df)} pedidos com esse começo — mostro o "
                        f"primeiro. Manda mais caracteres para eu ter certeza.",
                        f"I found {len(df)} orders with that prefix — showing "
                        f"the first. Send more characters so I can be sure."))
    p = df.iloc[0]
    prom = _d(p["data"])
    ref = _ref(con, ctx)
    ent = _d(p["dt_entrega"]) if pd.notna(p["dt_entrega"]) else None
    post = _d(p["dt_postagem"]) if pd.notna(p["dt_postagem"]) else None
    d3, d7 = prom + timedelta(days=3), prom + timedelta(days=7)
    fatos.update({"pedido": p["order_id"], "prometido": i18n.data(prom),
                  "entrega": i18n.data(ent) if ent else None})
    linhas.append(L(
        f"Pedido **{p['pedido']}** — {V(p['categoria'])}, de "
        f"{p['uf_origem']} para {p['estado_destino']}, "
        f"{moeda(p['valor'], 2)}. Comprado em "
        f"{i18n.data(_d(p['dt_compra']))}, prometido para "
        f"**{i18n.data(prom)}** ({int(p['dias_promessa'])} dias).",
        f"Order **{p['pedido']}** — {V(p['categoria'])}, from "
        f"{p['uf_origem']} to {p['estado_destino']}, "
        f"{moeda(p['valor'], 2)}. Bought on {i18n.data(_d(p['dt_compra']))}, "
        f"promised for **{i18n.data(prom)}** ({int(p['dias_promessa'])} "
        f"days)."))
    eventos = [(_d(p["dt_compra"]), L("Compra", "Purchase"))]
    if pd.notna(p["dt_aprovacao"]):
        eventos.append((_d(p["dt_aprovacao"]), L("Pagamento aprovado",
                                                 "Payment approved")))
    if post:
        eventos.append((post, L("Postado", "Shipped")))
    eventos.append((prom, L("Data prometida", "Promised date")))
    if not ent or ent > prom:
        quem = "transportadora" if (post and post <= d3) else "seller"
        if not ent or ent > d3:
            eventos.append((d3, L("Régua D+3 — ", "Rule D+3 — ")
                            + acao("d3", quem)))
        if not ent or ent > d7:
            eventos.append((d7, L("Régua D+7 — ", "Rule D+7 — ")
                            + acao("d7", quem)))
    if ent:
        eventos.append((ent, L("Entregue", "Delivered")))
    eventos.sort(key=lambda x: x[0])

    if ent and ent <= prom:
        linhas.append(L(f"Chegou **no prazo**, em {i18n.data(ent)}.",
                        f"Arrived **on time**, on {i18n.data(ent)}."))
    elif ent:
        linhas.append(L(
            f"Chegou **{(ent - prom).days} dias atrasado**, em "
            f"{i18n.data(ent)}.",
            f"Arrived **{(ent - prom).days} days late**, on "
            f"{i18n.data(ent)}."))
    else:
        linhas.append(L(
            "**Nunca chegou** — até o último evento da base, "
            "17/out/2018.",
            "**Never arrived** — up to the last event in the dataset, "
            "Oct 17, 2018."))
    if ref > prom and (not ent or ent > ref):
        linhas.append(L(
            f"Em {i18n.data(ref)}, data de referência da barra lateral, ele "
            f"estava na fila há {(ref - prom).days} dias: "
            f"**{acao(ld.faixa((ref - prom).days), 'transportadora' if post and post <= ref else 'seller')}**.",
            f"On {i18n.data(ref)}, the sidebar's reference date, it had been "
            f"in the queue for {(ref - prom).days} days: "
            f"**{acao(ld.faixa((ref - prom).days), 'transportadora' if post and post <= ref else 'seller')}**."))
    return pd.DataFrame({L("Data", "Date"): [i18n.data(d) for d, _ in eventos],
                         L("Evento", "Event"): [e for _, e in eventos]})


def executar(con, plano: dict[str, Any], ctx):
    dom = ctx.dominio
    fatos: dict[str, Any] = {"dominio": dom.nome,
                             "intencao": plano["intencao"]}
    linhas: list[str] = []
    grafico = None
    if plano["intencao"] == "travados":
        tabela = _executar_travados(con, dom, ctx, fatos, linhas)
    elif plano["intencao"] == "regua":
        tabela, grafico = _executar_regua(con, dom, ctx, plano, fatos, linhas)
    elif plano["intencao"] == "controle":
        tabela, grafico = _executar_controle(con, dom, ctx, fatos, linhas)
    else:
        tabela = _executar_pedido(con, dom, ctx, plano, fatos, linhas)
    return fatos, tabela, grafico, linhas
