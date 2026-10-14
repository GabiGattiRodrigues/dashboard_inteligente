"""
A tela que só existe no domínio de Marketing e CRM: a aba Campanhas.

Mesma regra do app.py e do telas_pld.py: aqui só tem tela. Todo número sai do
motor (`agregar`/`comparar`) com as métricas declaradas em
`vulcano/dominios/marketing.py` -- é o que garante que o ROAS desta aba é o
mesmo ROAS que a Abigail responde no chat.

    Cartões              investimento, receita de campanhas, ROAS, CAC,
                         receita de CRM e lift
    Mídia paga           por campanha: quanto custou e quanto voltou
    ROAS semanal         por canal pago, para ver a tendência
    Funis                mídia (impressão → clique → pedido) e CRM
                         (envio → abertura → clique → pedido)
    CRM e grupo controle lift por campanha com intervalo de confiança
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from vulcano import graficos as g
from vulcano import i18n
from vulcano.dados import Filtros, agregar, comparar
from vulcano.estilo import (cabecalho_comparacao, cartao_metrica,
                            descrever_janela, md, nota)
from vulcano.formatacao import moeda, numero, pct
from vulcano.graficos import (EIXO, JULGA_BOM, JULGA_RUIM, NEUTRO, SERIE,
                              TINTA_2, TINTA_MUDA)
from vulcano.i18n import L, V
from vulcano import incrementalidade as inc

PAGO, CRM = "Mídia paga", "CRM"

# Cor fixa por canal pago: o mesmo canal tem a mesma cor no gráfico de
# dispersão e no de ROAS semanal, para o olho ligar um ao outro sem legenda.
COR_CANAL = {"Busca paga": SERIE[0], "Social pago": SERIE[1],
             "Afiliados": SERIE[2]}


def _com(filtros: Filtros | None, **extra: list[str]) -> Filtros:
    """Os filtros da barra lateral mais um recorte desta tela. Se a pessoa já
    filtrou a mesma dimensão, vale a interseção -- nunca um número fora do
    que ela pediu."""
    vals = {k: list(v) for k, v in (filtros.valores if filtros else {}).items()}
    for k, v in extra.items():
        vals[k] = [x for x in v if x in vals[k]] if vals.get(k) else list(v)
    return Filtros(vals)


def _v(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df or pd.isna(df.iloc[0][col]):
        return float("nan")
    return float(df.iloc[0][col])


# --------------------------------------------------------------------------- #

def aba_campanhas(con, dom, inicio: date, fim: date, comp, filtros) -> None:
    st.markdown(md(L(
        "Mídia paga e CRM no mesmo lugar: quanto se investiu, quanto voltou e "
        "quanto o CRM **causou** — medido contra um grupo controle, não só "
        "pela atribuição.",
        "Paid media and CRM in one place: how much was invested, how much "
        "came back and how much CRM **caused** — measured against a control "
        "group, not just through attribution.")))
    st.markdown(nota(L(
        "<b>Camada simulada.</b> Os pedidos e a receita são os do Olist; canal, "
        "campanha, investimento, disparos e grupo controle foram gerados "
        "amarrados a esses pedidos (último clique). A modelagem é real; a "
        "atribuição não.",
        "<b>Simulated layer.</b> Orders and revenue are Olist's; channel, "
        "campaign, investment, sends and control group were generated tied "
        "to those orders (last click). The modeling is real; the attribution "
        "is not.")), unsafe_allow_html=True)

    # --- cartões ------------------------------------------------------------ #
    st.markdown(cabecalho_comparacao(comp), unsafe_allow_html=True)
    rot_ant, _ = descrever_janela(comp.anterior) if not comp.composta else \
        (comp.rotulo_base(), "")
    cards = ["investimento", "receita_campanhas", "roas", "cac",
             "receita_crm", "lift_crm"]
    valores = comparar(con, dom, cards, comp, filtros)
    cols = st.columns(len(cards), gap="small")
    for col, mk in zip(cols, cards):
        m = dom.metrica(mk)
        v = valores[mk]
        with col:
            st.markdown(cartao_metrica(m.rotulo, v["atual"], m, v["base"],
                                       v["delta_pct"], rot_ant),
                        unsafe_allow_html=True)
    st.write("")

    # --- mídia paga por campanha ------------------------------------------- #
    st.markdown(L("#### Mídia paga, campanha a campanha",
                  "#### Paid media, campaign by campaign"))
    f_pago = _com(filtros, tipo_campanha=[PAGO])
    mets = ["investimento", "receita_campanhas", "roas", "cac", "ctr", "cpc",
            "conversao_midia"]
    t = agregar(con, dom, mets, inicio, fim, dims=["campanha"],
                filtros=f_pago, ordenar_por="investimento")
    t = t[t["investimento"].fillna(0) > 0]
    if t.empty:
        st.info(L("Sem investimento em mídia paga com esse filtro.",
                  "No paid media investment with this filter."))
    else:
        c1, c2 = st.columns([1.15, 1], gap="large")
        with c1:
            tab = pd.DataFrame({L("Campanha", "Campaign"): t["campanha"].map(V)})
            for mk in mets:
                tab[dom.metrica(mk).rotulo] = [numero(x, dom.metrica(mk))
                                               if pd.notna(x) else "—"
                                               for x in t[mk]]
            st.dataframe(tab, use_container_width=True, hide_index=True)
            pior = t.dropna(subset=["roas"]).sort_values("roas").iloc[0]
            melhor = t.dropna(subset=["roas"]).sort_values("roas").iloc[-1]
            mr = dom.metrica("roas")
            st.caption(L(
                f"ROAS mais alto: {V(melhor['campanha'])} "
                f"({numero(melhor['roas'], mr)}). Mais baixo: "
                f"{V(pior['campanha'])} ({numero(pior['roas'], mr)}). "
                "Último clique favorece o fundo do funil — busca de marca e "
                "remarketing parecem melhores do que são.",
                f"Highest ROAS: {V(melhor['campanha'])} "
                f"({numero(melhor['roas'], mr)}). Lowest: "
                f"{V(pior['campanha'])} ({numero(pior['roas'], mr)}). "
                "Last click favors the bottom of the funnel — brand search "
                "and retargeting look better than they are."))
        with c2:
            st.markdown(L("**Quanto custou × quanto voltou**",
                          "**What it cost × what came back**"))
            fig = go.Figure()
            mapa = dict(con.execute(
                "SELECT DISTINCT campanha, canal FROM fato "
                "WHERE tipo_campanha = 'Mídia paga'").fetchall())
            canais = [mapa.get(c) for c in t["campanha"]]
            for i, canal in enumerate(dict.fromkeys(canais)):
                d = t[[mapa.get(c) == canal for c in t["campanha"]]]
                fig.add_trace(go.Scatter(
                    x=d["investimento"], y=d["roas"], mode="markers",
                    name=V(canal),
                    marker=dict(size=[max(8, min(40, (r / t["receita_campanhas"].max()) ** 0.5 * 40))
                                      for r in d["receita_campanhas"].fillna(0)],
                                color=COR_CANAL.get(canal, SERIE[3]),
                                opacity=0.8,
                                line=dict(color="white", width=1)),
                    customdata=[V(c) for c in d["campanha"]],
                    hovertemplate="<b>%{customdata}</b><br>"
                                  + L("Investimento", "Investment")
                                  + ": R$ %{x:,.0f}<br>ROAS: %{y:.2f}"
                                  "<extra></extra>"))
            fig.add_hline(y=1, line=dict(color=JULGA_RUIM, width=1,
                                         dash="dot"),
                          annotation_text=L("ROAS 1 = empata",
                                            "ROAS 1 = break-even"),
                          annotation_font=dict(size=10, color=JULGA_RUIM))
            fig = g._base(fig, 330)
            fig.update_xaxes(title=dict(text=L("investimento (R$)",
                                               "investment (R$)"),
                                        font=dict(size=11, color=TINTA_MUDA)))
            fig.update_yaxes(title=dict(text="ROAS",
                                        font=dict(size=11, color=TINTA_MUDA)))
            fig.update_layout(showlegend=True,
                              legend=dict(orientation="h", yanchor="top",
                                          y=-0.2, xanchor="left", x=0),
                              margin=dict(l=8, r=8, t=12, b=8))
            st.plotly_chart(fig, use_container_width=True, key="camp_disp")

    # --- ROAS semanal ------------------------------------------------------- #
    st.markdown(L("#### ROAS semanal por canal pago",
                  "#### Weekly ROAS by paid channel"))
    sem = con.execute(f"""
        SELECT CAST(date_trunc('week', data) AS DATE) AS semana, canal,
               SUM(CASE WHEN tipo_campanha IN ('Mídia paga', 'CRM')
                        THEN receita END) / NULLIF(SUM(investimento), 0) AS roas
          FROM fato
         WHERE data BETWEEN DATE '{inicio}' AND DATE '{fim}'
           AND tipo_campanha = 'Mídia paga'
           {"".join(" AND " + c for c in f_pago.clausulas(dom)
                    if "tipo_campanha" not in c)}
         GROUP BY 1, 2 ORDER BY 2, 1
    """).fetchdf()
    if not sem.empty:
        fig = go.Figure()
        for i, (canal, d) in enumerate(sem.groupby("canal")):
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(d["semana"]), y=d["roas"], name=V(canal),
                mode="lines+markers",
                line=dict(color=COR_CANAL.get(canal, SERIE[3]), width=2),
                marker=dict(size=4),
                hovertemplate=L("semana de ", "week of ") + "%{x|"
                              + i18n.formato_data_plotly()
                              + "}<br><b>%{y:.2f}</b><extra>" + V(canal)
                              + "</extra>"))
        fig = g._base(fig, 300)
        fig.update_layout(showlegend=True, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True, key="camp_roas_sem")
        st.caption(L(
            "A semana da data de compra. Semana incompleta nas pontas do "
            "período tem pouco pedido e oscila mais.",
            "Week of the purchase date. Incomplete weeks at the ends of the "
            "period have few orders and swing more."))

    # --- funis -------------------------------------------------------------- #
    st.markdown(L("#### Funis", "#### Funnels"))
    f1, f2 = st.columns(2, gap="large")
    tot_pago = agregar(con, dom, ["ctr", "conversao_midia"], inicio, fim,
                       filtros=f_pago)
    imp, cli = _v(tot_pago, "ctr__den"), _v(tot_pago, "ctr__num")
    ped = _v(tot_pago, "conversao_midia__num")
    with f1:
        if imp == imp and imp:
            st.plotly_chart(g.funil([
                (L("Impressões", "Impressions"), imp, i18n.num(imp)),
                (L("Cliques", "Clicks"), cli,
                 f"{i18n.num(cli)} · CTR {pct(cli / imp, 2, False)}"),
                (L("Pedidos", "Orders"), ped,
                 f"{i18n.num(ped)} · {pct(ped / cli, 2, False)} "
                 + L("dos cliques", "of clicks")),
            ], titulo=L("Mídia paga", "Paid media")),
                use_container_width=True, key="camp_funil_midia")
    f_crm = _com(filtros, tipo_campanha=[CRM])
    tot_crm = agregar(con, dom, ["taxa_abertura", "taxa_clique_crm",
                                 "conversao_crm"], inicio, fim, filtros=f_crm)
    env = _v(tot_crm, "taxa_abertura__den")
    abe = _v(tot_crm, "taxa_abertura__num")
    clc = _v(tot_crm, "taxa_clique_crm__num")
    pcr = _v(tot_crm, "conversao_crm__num")
    with f2:
        if env == env and env:
            st.plotly_chart(g.funil([
                (L("Envios", "Sends"), env, i18n.num(env)),
                (L("Aberturas", "Opens"), abe,
                 f"{i18n.num(abe)} · {pct(abe / env, 1, False)}"),
                (L("Cliques", "Clicks"), clc,
                 f"{i18n.num(clc)} · {pct(clc / env, 2, False)} "
                 + L("dos envios", "of sends")),
                (L("Pedidos", "Orders"), pcr,
                 f"{i18n.num(pcr)} · {pct(pcr / env, 3, False)} "
                 + L("dos envios", "of sends")),
            ], titulo="CRM"), use_container_width=True, key="camp_funil_crm")

    # --- CRM: mensuração em 7 dias --------------------------------------- #
    bloco_mensuracao(con, dom, inicio, fim, filtros)


def bloco_mensuracao(con, dom, inicio: date, fim: date, filtros) -> None:
    """A régua de quem opera CRM: recebeu → abriu → comprou em 7 dias, a
    resposta de quem abriu contra o controle e o ticket médio -- com a
    leitura que compara grupos sorteados logo ao lado."""
    from vulcano.marketing import agente as ext_mkt

    st.markdown(L("#### Mensuração de CRM — 7 dias depois do disparo",
                  "#### CRM measurement — 7 days after the send"))
    st.markdown(md(L(
        "Para cada disparo: quem **recebeu**, quem **abriu** (foi impactado) "
        "e quem **comprou em até 7 dias**. A resposta de quem abriu é "
        "comparada com a do **grupo controle** (10% sorteados que não "
        "recebem nada), junto com o ticket médio. Ao lado vem o **lift real**, "
        "que compara todo mundo que recebeu com o controle: quem abre e-mail "
        "já compra mais por natureza, e só grupos sorteados separam o efeito "
        "do disparo do perfil de quem abre.",
        "For each send: who **received**, who **opened** (was reached) and "
        "who **bought within 7 days**. The openers' response is compared "
        "with the **control group's** (a random 10% who get nothing), along "
        "with the average ticket. Next to it comes the **real lift**, which "
        "compares everyone who received with the control: people who open "
        "emails already buy more, and only randomized groups separate the "
        "send's effect from the profile of who opens.")))
    df = inc.por_campanha(con, dom, inicio, fim, filtros)
    if df.empty:
        st.info(L("Sem disparo de CRM com a janela de 7 dias completa nesse "
                  "período e filtro.",
                  "No CRM send with a full 7-day window in this period and "
                  "filter."))
        return

    # --- resposta de quem abriu × controle, por campanha ------------------- #
    c1, c2 = st.columns(2, gap="large")
    ordem = df.sort_values("lift")
    nomes = [V(c) for c in ordem["campanha"]]
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=nomes, x=ordem["r_abriu"], orientation="h",
            name=L("Quem abriu", "Openers"), marker_color=SERIE[0],
            hovertemplate="%{y}<br><b>%{x:.2%}</b><extra>"
                          + L("quem abriu", "openers") + "</extra>"))
        fig.add_trace(go.Bar(
            y=nomes, x=ordem["r_controle"], orientation="h",
            name=L("Controle", "Control"), marker_color=NEUTRO,
            hovertemplate="%{y}<br><b>%{x:.2%}</b><extra>"
                          + L("controle", "control") + "</extra>"))
        fig = g._base(fig, 80 + 52 * len(ordem),
                      L("Comprou em 7 dias: quem abriu × controle",
                        "Bought within 7 days: openers × control"))
        fig.update_layout(barmode="group", showlegend=True,
                          legend=dict(orientation="h", y=-0.12,
                                      yanchor="top"))
        fig.update_xaxes(tickformat=".1%", showgrid=True)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True, key="crm_resp")
    with c2:
        v = ordem.dropna(subset=["lift"])
        cores = [JULGA_BOM if a > 0 else (JULGA_RUIM if b < 0 else NEUTRO)
                 for a, b in zip(v["ic_inf"], v["ic_sup"])]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=v["lift_aparente"], y=[V(c) for c in v["campanha"]],
            mode="markers", name=L("Lift clássico (abriu)",
                                   "Classic lift (opened)"),
            marker=dict(symbol="diamond-open", size=11, color=TINTA_MUDA),
            hovertemplate="%{y}<br>" + L("clássico", "classic")
                          + " %{x:+.0%}<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=v["lift"], y=[V(c) for c in v["campanha"]], mode="markers",
            name=L("Lift real (recebeu) e IC 95%",
                   "Real lift (received) and 95% CI"),
            marker=dict(size=11, color=cores),
            error_x=dict(type="data", symmetric=False,
                         array=v["ic_sup"] - v["lift"],
                         arrayminus=v["lift"] - v["ic_inf"],
                         color=TINTA_2, thickness=1.4, width=5),
            hovertemplate="%{y}<br>" + L("real", "real")
                          + " %{x:+.0%}<extra></extra>"))
        fig.add_vline(x=0, line=dict(color=EIXO, width=1.2))
        fig = g._base(fig, 80 + 52 * len(v),
                      L("Lift clássico × lift real",
                        "Classic lift × real lift"))
        fig.update_layout(showlegend=True,
                          legend=dict(orientation="h", y=-0.12,
                                      yanchor="top"))
        fig.update_xaxes(tickformat="+.0%", showgrid=True)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True, key="crm_lift")

    st.dataframe(ext_mkt.tabela(df), use_container_width=True,
                 hide_index=True)
    pouco = df[df["resp_controle"] < inc.COMPRAS_MINIMAS_CONTROLE]
    st.caption(L(
        "Lift real em verde: o intervalo inteiro acima de zero (efeito "
        "comprovado). Em cinza: cruza o zero. O losango é a leitura clássica "
        "— a distância até o ponto é o quanto dela é perfil de quem abre, e "
        "não efeito do disparo."
        + (f" {len(pouco)} campanha(s) com menos de "
           f"{inc.COMPRAS_MINIMAS_CONTROLE} compras no controle: amplie o "
           "período antes de concluir." if not pouco.empty else ""),
        "Real lift in green: the whole interval above zero (proven effect). "
        "In gray: it crosses zero. The diamond is the classic reading — the "
        "distance to the dot is how much of it is the profile of who opens, "
        "not the send's effect."
        + (f" {len(pouco)} campaign(s) with fewer than "
           f"{inc.COMPRAS_MINIMAS_CONTROLE} control purchases: widen the "
           "period before concluding." if not pouco.empty else "")))

    # --- disparo a disparo -------------------------------------------------- #
    st.markdown(L("##### Disparo a disparo", "##### Send by send"))
    camps = df["campanha"].tolist()
    padrao = ("E-mail • Newsletter semanal"
              if "E-mail • Newsletter semanal" in camps else camps[0])
    escolha = st.selectbox(L("Campanha", "Campaign"), camps,
                           index=camps.index(padrao), format_func=V,
                           key="crm_disp_camp")
    d = inc.por_disparo(con, dom, escolha, inicio, fim, filtros)
    if d.empty:
        st.info(L("Nenhum disparo com janela fechada no período.",
                  "No send with a closed window in the period."))
        return
    # Campanha diária (carrinho, WhatsApp) vira semana: um ponto por dia
    # tem controle de duas ou três pessoas e só mostra ruído.
    if len(d) > 40:
        d = d.assign(disparo=pd.to_datetime(d["disparo"]).dt.to_period("W")
                     .dt.start_time)
        somas = [c for c in ["recebeu", "abriu", "controle", "resp_abriu",
                             "resp_recebeu", "resp_controle", "receita_abriu",
                             "receita_recebeu", "receita_controle",
                             "disparos"]]
        d = inc._ler(d.groupby("disparo", as_index=False)[somas].sum())
        st.caption(L("Campanha diária: agrupada por semana do disparo.",
                     "Daily campaign: grouped by week of send."))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(d["disparo"]), y=d["r_abriu"], mode="lines+markers",
        name=L("Resposta de quem abriu", "Openers' response"),
        line=dict(color=SERIE[0], width=2)))
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(d["disparo"]), y=d["r_recebeu"], mode="lines+markers",
        name=L("Resposta de quem recebeu", "Recipients' response"),
        line=dict(color=SERIE[1], width=2)))
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(d["disparo"]), y=d["r_controle"], mode="lines+markers",
        name=L("Resposta do controle", "Control response"),
        line=dict(color=TINTA_MUDA, width=1.6, dash="dot")))
    fig = g._base(fig, 320)
    fig.update_yaxes(tickformat=".2%")
    fig.update_layout(showlegend=True, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, key="crm_disp")
    st.markdown(md("\n\n".join(inc.relatorio(
        d.iloc[-1], f"{V(escolha)} · {L('último', 'latest')} "
        f"{i18n.data(pd.Timestamp(d.iloc[-1]['disparo']).date())}"))))
