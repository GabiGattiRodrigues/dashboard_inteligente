"""
O que a Abigail responde que nenhum outro agente responde: a mensuração de
uma campanha de CRM do jeito que quem opera CRM mede.

Duas intenções, avaliadas ANTES do planejador genérico:

- **mensuracao** — como foi uma campanha (ou todas): de quem recebeu, quem
                   abriu e quem comprou em 7 dias, a resposta de quem abriu
                   contra o controle, o ticket médio e a receita incremental;
- **disparo**    — o último disparo de uma campanha, sozinho, com a mesma
                   régua.

Pergunta agregada ("qual o ROAS por canal?", "por que o CAC subiu?") segue
para o motor genérico.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

import pandas as pd

from .. import i18n
from .. import incrementalidade as inc
from ..dados import periodo_disponivel
from ..formatacao import moeda, pct
from ..i18n import L, V, num

INTENCOES = {
    "mensuracao": "como foi uma campanha de CRM: recebeu, abriu, comprou em 7 "
                  "dias, contra o grupo controle, com ticket médio",
    "disparo": "o resultado do último disparo de uma campanha de CRM",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


# Apelidos de campanha de CRM -> nome no dado. O "black friday" aqui é o
# e-mail: a de social é mídia paga e não tem grupo controle.
CAMPANHAS = {
    "newsletter": "E-mail • Newsletter semanal",
    "carrinho": "E-mail • Carrinho abandonado",
    "abandoned cart": "E-mail • Carrinho abandonado",
    "cart": "E-mail • Carrinho abandonado",
    "reativacao": "E-mail • Reativação 90 dias",
    "win-back": "E-mail • Reativação 90 dias",
    "winback": "E-mail • Reativação 90 dias",
    "black friday": "E-mail • Black Friday 2017",
    "push": "Push • Ofertas relâmpago",
    "whatsapp": "WhatsApp • Recompra pós-entrega",
    "zap": "WhatsApp • Recompra pós-entrega",
}

MENSURA = ["mensur", "como foi a campanha", "como foi o disparo",
           "como foi a newsletter", "como foi o push", "como foi o whatsapp",
           "como foi o carrinho", "como foi a reativacao",
           "resultado da campanha", "resultado do disparo", "resultado do crm",
           "deu resultado", "funcionou", "valeu a pena", "performou",
           "quem abriu", "respondentes", "taxa de resposta", "7 dias",
           "sete dias", "contra o controle", "grupo controle por campanha",
           "lift do crm por campanha", "lift por campanha",
           "campanhas de crm", "campanha de crm",
           # English
           "measure", "how did the campaign", "how did the send",
           "how did the newsletter", "campaign result", "send result",
           "did it work", "was it worth", "openers", "responders",
           "response rate", "7 days", "seven days", "against the control",
           "lift by campaign", "crm campaigns"]
ULTIMO = ["ultimo disparo", "ultima newsletter", "ultimo envio",
          "disparo de ontem", "disparo da semana", "last send",
          "latest send", "last newsletter", "last blast"]
TEMPORAL = ["por que", "porque", "caiu", "subiu", "tendencia", "crescendo",
            "why", "dropped", "trend"]


def _campanha(t: str) -> Optional[str]:
    for k, v in CAMPANHAS.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            return v
    return None


def interpretar(pergunta: str, ctx) -> Optional[dict[str, Any]]:
    t = _norm(pergunta)
    from ..conversa import pergunta_de_conceito
    if pergunta_de_conceito(pergunta):
        return None
    if any(x in t for x in TEMPORAL):
        return None
    camp = _campanha(t)
    if any(x in t for x in ULTIMO):
        return {"intencao": "disparo", "metrica": "taxa_resp_impactados",
                "campanha": camp or "E-mail • Newsletter semanal"}
    if any(x in t for x in MENSURA) or (camp and re.search(
            r"\b(como foi|como esta|como ta|resultado|lift|resposta|"
            r"how did|how is|result)\b", t)):
        return {"intencao": "mensuracao", "metrica": "lift_crm",
                "campanha": camp}
    return None


def tabela(df: pd.DataFrame) -> pd.DataFrame:
    """A tabela de mensuração, uma linha por campanha ou disparo."""
    primeira = ("disparo" if "disparo" in df else "campanha")
    rot = (df[primeira].map(lambda d: i18n.data(d.date() if hasattr(d, "date")
                                                else d))
           if primeira == "disparo" else df["campanha"].map(V))
    return pd.DataFrame({
        (L("Disparo", "Send") if primeira == "disparo"
         else L("Campanha", "Campaign")): rot,
        L("Receberam", "Received"): [num(x) for x in df["recebeu"]],
        L("Abriram", "Opened"): [pct(x, 1, False) for x in df["taxa_abertura"]],
        L("Resposta de quem abriu", "Openers' response"):
            [pct(x, 2, False) for x in df["r_abriu"]],
        L("Resposta do controle", "Control response"):
            [pct(x, 2, False) if x == x else "—" for x in df["r_controle"]],
        L("Lift clássico (abriu)", "Classic lift (opened)"):
            [pct(x, 0) if x == x else "—" for x in df["lift_aparente"]],
        L("Lift real (recebeu)", "Real lift (received)"):
            [pct(x, 0) if x == x else "—" for x in df["lift"]],
        L("IC 95%", "95% CI"): [f"{pct(a, 0)} a {pct(b, 0)}" if a == a
                                else "—"
                                for a, b in zip(df["ic_inf"], df["ic_sup"])],
        L("Ticket abriu", "Openers' ticket"):
            [moeda(x, 0) if x == x else "—" for x in df["ticket_abriu"]],
        L("Ticket controle", "Control ticket"):
            [moeda(x, 0) if x == x else "—" for x in df["ticket_controle"]],
        L("Receita incremental", "Incremental revenue"):
            [moeda(x, 0) if x == x else "—"
             for x in df["receita_incremental"]],
    })


def _recomendar(r: pd.Series) -> str:
    """O que fazer com a campanha, a partir do lift real e do ticket."""
    if r["ic_inf"] == r["ic_inf"] and r["ic_inf"] > 0:
        if r["ticket_abriu"] < r["ticket_controle"] * 0.95:
            return L(
                "Funciona, mas compra com ticket menor que o do controle — "
                "o incentivo pode estar dando desconto para quem pagaria "
                "cheio. Testar a mesma régua sem cupom.",
                "It works, but buyers spend less than the control — the "
                "incentive may be discounting people who'd pay full price. "
                "Test the same flow without the coupon.")
        return L(
            "Efeito comprovado: vale escalar — mais audiência elegível ou "
            "mais frequência —, de olho no opt-out.",
            "Proven effect: worth scaling — more eligible audience or more "
            "frequency —, keeping an eye on opt-out.")
    if r["ic_sup"] == r["ic_sup"] and r["ic_sup"] < 0:
        return L("Efeito negativo comprovado: pausar e revisar oferta e "
                 "frequência antes de voltar a disparar.",
                 "Proven negative effect: pause and review offer and "
                 "frequency before sending again.")
    if r["lift_aparente"] == r["lift_aparente"] and r["lift_aparente"] > 0.5:
        return L(
            "Na leitura clássica parece ótima, mas o lift real não se "
            "distingue de zero: quem abre já compraria. Antes de cortar, "
            "testar outro criativo ou outro momento de envio; antes de "
            "escalar, provar o efeito com mais volume de controle.",
            "In the classic reading it looks great, but the real lift can't "
            "be told from zero: openers would have bought anyway. Before "
            "cutting it, test another creative or send time; before scaling, "
            "prove the effect with more control volume.")
    return L("Sem efeito comprovado: segurar escala e testar outra oferta.",
             "No proven effect: hold off on scaling and test another offer.")


def executar(con, plano: dict[str, Any], ctx):
    dom = ctx.dominio
    fatos: dict[str, Any] = {"dominio": dom.nome,
                             "intencao": plano["intencao"],
                             "janela": L("7 dias depois do disparo",
                                         "7 days after the send"),
                             "aviso_de_dado": L(
                                 "Camada de campanha SIMULADA sobre pedidos "
                                 "reais do Olist.",
                                 "SIMULATED campaign layer over real Olist "
                                 "orders.")}
    linhas: list[str] = []
    camp = plano.get("campanha")
    _, dmax = periodo_disponivel(con)

    if plano["intencao"] == "disparo":
        d = inc.por_disparo(con, dom, camp, ctx.inicio, min(ctx.fim, dmax),
                            ctx.filtros)
        if d.empty:
            linhas.append(L(
                f"Não achei disparo de **{V(camp)}** com os 7 dias de resposta "
                f"inteiros no período. Os disparos dos últimos 6 dias da base "
                f"ainda não fecharam a janela.",
                f"I couldn't find a **{V(camp)}** send with the full 7-day "
                f"window in the period. Sends in the last 6 days of the data "
                f"haven't closed the window yet."))
            return fatos, None, None, linhas
        r = d.iloc[-1]
        nome = f"{V(camp)} · {i18n.data(r['disparo'])}"
        linhas += inc.relatorio(r, nome)
        if len(d) >= 4:
            ant = d.iloc[-5:-1]
            media = ant["r_abriu"].mean()
            linhas.append(L(
                f"Contra os 4 disparos anteriores, a resposta de quem abriu "
                f"{'subiu' if r['r_abriu'] > media else 'caiu'}: "
                f"{pct(r['r_abriu'], 2, False)} contra "
                f"{pct(media, 2, False)} de média. Disparo sozinho tem "
                f"controle pequeno — leia a tendência, não o ponto.",
                f"Against the previous 4 sends, the openers' response "
                f"{'rose' if r['r_abriu'] > media else 'fell'}: "
                f"{pct(r['r_abriu'], 2, False)} against a "
                f"{pct(media, 2, False)} average. A single send has a small "
                f"control — read the trend, not the point."))
        linhas.append(L("**O que fazer:** ", "**What to do:** ")
                      + _recomendar(r))
        fatos["disparo"] = r.to_dict()
        return fatos, tabela(d.tail(8)), None, linhas

    df = inc.por_campanha(con, dom, ctx.inicio, min(ctx.fim, dmax),
                          ctx.filtros)
    if df.empty:
        linhas.append(L("Sem disparo de CRM com a janela de 7 dias completa "
                        "nesse período e filtro.",
                        "No CRM send with a full 7-day window in this period "
                        "and filter."))
        return fatos, None, None, linhas
    periodo = f"{i18n.data(ctx.inicio)} – {i18n.data(min(ctx.fim, dmax))}"
    fatos["periodo"] = periodo
    if camp:
        sel = df[df["campanha"] == camp]
        if sel.empty:
            linhas.append(L(f"**{V(camp)}** não teve disparo com janela "
                            f"completa em {periodo}.",
                            f"**{V(camp)}** had no send with a full window "
                            f"in {periodo}."))
            return fatos, tabela(df), None, linhas
        r = sel.iloc[0]
        linhas += inc.relatorio(r, V(camp))
        linhas.append(L("**O que fazer:** ", "**What to do:** ")
                      + _recomendar(r))
        fatos["campanha"] = r.to_dict()
        return fatos, tabela(sel), None, linhas

    # Todas as campanhas
    t = inc.total(con, dom, ctx.inicio, min(ctx.fim, dmax), ctx.filtros)
    linhas.append(L(
        f"Mensurando o CRM de {periodo}, com 7 dias de resposta depois de "
        f"cada disparo: a resposta de quem abriu foi "
        f"**{pct(t['r_abriu'], 2, False)}** contra "
        f"**{pct(t['r_controle'], 2, False)}** do controle — mas o lift de "
        f"quem recebeu, que compara grupos sorteados, é "
        f"**{pct(t['lift'], 0)}**.",
        f"Measuring CRM from {periodo}, with 7 days of response after each "
        f"send: the openers' response was **{pct(t['r_abriu'], 2, False)}** "
        f"against **{pct(t['r_controle'], 2, False)}** for the control — but "
        f"the recipients' lift, which compares randomized groups, is "
        f"**{pct(t['lift'], 0)}**."))
    prov = df[df["ic_inf"] > 0]
    nada = df[(df["ic_inf"] <= 0) & (df["lift_aparente"] > 0.5)]
    if not prov.empty:
        linhas.append(L(
            "**Efeito comprovado:** " + ", ".join(
                f"{V(r.campanha)} ({pct(r.lift, 0)})"
                for r in prov.sort_values("lift", ascending=False)
                .itertuples()) + ".",
            "**Proven effect:** " + ", ".join(
                f"{V(r.campanha)} ({pct(r.lift, 0)})"
                for r in prov.sort_values("lift", ascending=False)
                .itertuples()) + "."))
    if not nada.empty:
        linhas.append(L(
            "**Parecem boas e não são:** " + ", ".join(
                f"{V(r.campanha)} (clássico {pct(r.lift_aparente, 0)}, real "
                f"{pct(r.lift, 0)})" for r in nada.itertuples())
            + " — quem abre já compraria.",
            "**Look good and aren't:** " + ", ".join(
                f"{V(r.campanha)} (classic {pct(r.lift_aparente, 0)}, real "
                f"{pct(r.lift, 0)})" for r in nada.itertuples())
            + " — openers would have bought anyway."))
    melhor = df.sort_values("receita_incremental", ascending=False).iloc[0]
    linhas.append(L(
        f"**O que fazer:** proteger e escalar **{V(melhor['campanha'])}**, "
        f"que é quem mais gera receita incremental "
        f"({moeda(melhor['receita_incremental'], 0)} em 7 dias); nas que não "
        f"provam efeito, testar criativo e momento antes de cortar.",
        f"**What to do:** protect and scale **{V(melhor['campanha'])}**, the "
        f"biggest incremental revenue driver "
        f"({moeda(melhor['receita_incremental'], 0)} in 7 days); for those "
        f"without proven effect, test creative and timing before cutting."))
    return fatos, tabela(df), None, linhas
