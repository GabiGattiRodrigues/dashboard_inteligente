"""
As telas que só existem no domínio de Logística.

Mesma regra do app.py e do telas_pld.py: aqui só tem tela. A fila, a curva do
ponto de não retorno e o gráfico de controle são calculados em
`vulcano/logistica/dados.py`, e o texto de leitura é o mesmo que o Vulcão usa
no chat -- então a aba e a conversa dizem a mesma coisa com os mesmos números.

    Pedidos travados       a fila na data de referência, por faixa da régua,
                           e se a régua D+3/D+7 se sustenta neste dado
    Controle por origem    p-chart semanal da taxa fora do prazo, por origem
    (bloco extra)          o resumo da fila e do controle na aba Alertas
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from vulcano import graficos as g
from vulcano import i18n
from vulcano.dados import Filtros, periodo_disponivel
from vulcano.estilo import md, nota
from vulcano.formatacao import moeda, pct
from vulcano.graficos import (EIXO, GRADE, JULGA_BOM, JULGA_RUIM, SERIE,
                              SURFACE, TINTA, TINTA_2, TINTA_MUDA)
from vulcano.i18n import L, V
from vulcano.logistica import agente as la
from vulcano.logistica import dados as ld

CSS_LOG = f"""
<style>
  .log-kpi {{ border: 1px solid {GRADE}; border-radius: 12px;
             background: {SURFACE}; padding: 12px 14px; height: 100%; }}
  .log-kpi .rot {{ color: {TINTA_MUDA}; font-size: 0.66rem; font-weight: 650;
                  text-transform: uppercase; letter-spacing: .055em; }}
  .log-kpi .val {{ color: {TINTA}; font-size: 1.45rem; font-weight: 650;
                  margin-top: 2px; font-variant-numeric: tabular-nums; }}
  .log-kpi .det {{ color: {TINTA_MUDA}; font-size: 0.72rem; margin-top: 2px; }}
  .log-kpi.quente {{ border-left: 4px solid {JULGA_RUIM}; }}
  .log-kpi.morno {{ border-left: 4px solid #d97706; }}
  .log-kpi.frio {{ border-left: 4px solid {SERIE[0]}; }}
  .log-kpi.cinza {{ border-left: 4px solid {EIXO}; }}
</style>
"""

# Cores das faixas da régua: vencido (acompanhar), D+3 (cobrar), D+7 (falar
# com o cliente), esquecido (baixa). Do frio ao quente, e o esquecido em
# cinza -- ele já passou da hora de qualquer régua.
COR_FAIXA = {"vencido": SERIE[0], "d3": "#d97706", "d7": JULGA_RUIM,
             "esquecido": "#8a99ab"}


def _rot_faixa() -> dict:
    return {"vencido": L("Vencido há 1–2 dias", "Overdue 1–2 days"),
            "d3": L("D+3 a D+6 · cobrar", "D+3 to D+6 · chase"),
            "d7": L("D+7 a D+30 · falar com o cliente",
                    "D+7 to D+30 · contact customer"),
            "esquecido": L("Esquecidos (> 30 dias)", "Forgotten (> 30 days)")}


def _kpi(rotulo: str, valor: str, detalhe: str = "", tom: str = "") -> str:
    return (f'<div class="log-kpi {tom}"><div class="rot">{rotulo}</div>'
            f'<div class="val">{valor}</div><div class="det">{detalhe}</div>'
            f'</div>')


def _d(x) -> date:
    return x.date() if hasattr(x, "date") else x


def _num(n) -> str:
    return i18n.num(n, 0)


# --------------------------------------------------------------------------- #
# Aba: Pedidos travados
# --------------------------------------------------------------------------- #

def aba_travados(con, dom, dmin: date, dmax: date, fim: date,
                 filtros: Filtros) -> None:
    st.markdown(CSS_LOG, unsafe_allow_html=True)
    ref = min(fim, dmax)
    f = ld.fila(con, dom, ref, filtros)
    r = ld.resumo_fila(f)
    ativa = r["vencido"] + r["d3"] + r["d7"]

    st.markdown(md(L(
        f"#### Fila em {i18n.data(ref)}\n"
        f"Pedidos com **prazo vencido e sem entrega** nesse dia, como se "
        f"sabia nesse dia — o fim do período da barra lateral. Filtro: "
        f"**{filtros.resumo(dom)}**.",
        f"#### Queue on {i18n.data(ref)}\n"
        f"Orders **past their promised date and not delivered** on that day, "
        f"as known that day — the end of the sidebar period. Filter: "
        f"**{filtros.resumo(dom)}**.")))

    esq_valor = (f.loc[f["faixa"] == "esquecido", "valor"].sum()
                 if not f.empty else 0.0)
    c = st.columns(5, gap="small")
    hoje = L("entraram hoje", "entered today")
    with c[0]:
        st.markdown(_kpi(L("Fila ativa", "Active queue"), _num(ativa),
                         L("venceram há até 30 dias", "due up to 30 days ago"),
                         "frio"), unsafe_allow_html=True)
    with c[1]:
        st.markdown(_kpi(L("D+7 · falar com o cliente",
                           "D+7 · contact customer"), _num(r["d7"]),
                         f"{r['hoje_d7']} {hoje}", "quente"),
                    unsafe_allow_html=True)
    with c[2]:
        st.markdown(_kpi(L("D+3 · cobrar", "D+3 · chase"), _num(r["d3"]),
                         f"{r['hoje_d3']} {hoje}", "morno"),
                    unsafe_allow_html=True)
    with c[3]:
        st.markdown(_kpi(L("Vencidos há 1–2 dias", "Overdue 1–2 days"),
                         _num(r["vencido"]), L("só acompanhar", "just monitor"),
                         "frio"), unsafe_allow_html=True)
    with c[4]:
        st.markdown(_kpi(L("Esquecidos", "Forgotten"), _num(r["esquecido"]),
                         L(f"> 30 dias · {moeda(esq_valor, 0)}",
                           f"> 30 days · {moeda(esq_valor, 0)}"), "cinza"),
                    unsafe_allow_html=True)
    st.write("")

    # --- a fila ao longo do tempo ------------------------------------------ #
    ini = max(dmin, ref - timedelta(days=120))
    fd = ld.fila_diaria(con, dom, ini, ref, filtros)
    if not fd.empty:
        rot = _rot_faixa()
        mostrar_esq = st.toggle(L("Incluir os esquecidos no gráfico",
                                  "Include forgotten orders in the chart"),
                                value=False, key="log_esq")
        fig = go.Figure()
        faixas = ["d7", "d3", "vencido"] + (["esquecido"] if mostrar_esq
                                            else [])
        for k in faixas:
            fig.add_trace(go.Scatter(
                x=fd["ref"], y=fd[k], name=rot[k], mode="lines",
                stackgroup="fila", line=dict(width=0.6, color=COR_FAIXA[k]),
                hovertemplate="%{x|" + i18n.formato_data_plotly()
                              + "}<br><b>%{y:,.0f}</b><extra>" + rot[k]
                              + "</extra>"))
        g._base(fig, 300, L("Tamanho da fila em cada dia, por faixa da régua",
                            "Queue size each day, by rule band"))
        fig.update_layout(showlegend=True, hovermode="x unified",
                          legend=dict(y=-0.18, yanchor="top"),
                          margin=dict(b=40))
        st.plotly_chart(fig, use_container_width=True, key="log_fila_dia")
        st.caption(L(
            "Os últimos 120 dias até a data de referência. Fila que sobe na "
            "faixa do D+7 é cobrança do D+3 que não resolveu.",
            "The last 120 days up to the reference date. A queue rising in "
            "the D+7 band is D+3 chasing that didn't work."))

    # --- a fila em si --------------------------------------------------------#
    st.markdown(L("##### Quem acionar", "##### Who to act on"))
    if f.empty:
        st.info(L("Nenhum pedido vencido sem entrega nesse dia, com esse "
                  "filtro.", "No overdue undelivered order on that day, with "
                  "this filter."))
    else:
        fa = f[f["faixa"] != "esquecido"]
        rot = _rot_faixa()
        c1, c2 = st.columns([2, 1])
        with c1:
            escolha = st.multiselect(
                L("Faixa da régua", "Rule band"),
                options=["d7", "d3", "vencido"], default=["d7", "d3"],
                format_func=lambda k: rot[k], key="log_faixas")
        with c2:
            quem = st.selectbox(
                L("Com quem está", "Who has it"),
                options=["todos", "transportadora", "seller"],
                format_func=lambda k: {
                    "todos": L("Todos", "All"),
                    "transportadora": L("Transportadora (já postado)",
                                        "Carrier (already shipped)"),
                    "seller": L("Seller (não postou)",
                                "Seller (not shipped)")}[k],
                key="log_quem")
        sel = fa[fa["faixa"].isin(escolha or ["d7", "d3", "vencido"])]
        if quem == "transportadora":
            sel = sel[sel["quem"] == "transportadora"]
        elif quem == "seller":
            sel = sel[sel["quem"] != "transportadora"]
        st.dataframe(la.tabela_fila(sel), use_container_width=True,
                     hide_index=True, height=min(420, 38 + 35 * len(sel)))
        st.caption(L(
            f"{_num(len(sel))} pedidos, {moeda(sel['valor'].sum(), 0)}. "
            "Ordenados do mais vencido para o menos. Para ver a linha do "
            "tempo de um pedido, pergunte ao Vulcão pelo código.",
            f"{_num(len(sel))} orders, {moeda(sel['valor'].sum(), 0)}. Sorted "
            "from most to least overdue. To see an order's timeline, ask "
            "Vulcão for its code."))

        esq = f[f["faixa"] == "esquecido"]
        if not esq.empty:
            with st.expander(L(
                    f"Esquecidos: {_num(len(esq))} pedidos vencidos há mais "
                    f"de 30 dias", f"Forgotten: {_num(len(esq))} orders "
                    f"overdue for more than 30 days"), expanded=False):
                st.markdown(md(L(
                    "A régua não salva mais esses pedidos — é decidir baixa e "
                    "estorno de uma vez. Cada um é um D+7 que ninguém fez. Por "
                    "mês de vencimento:",
                    "The rule can't save these orders anymore — it's time to "
                    "decide write-off and refund in one go. Each one is a D+7 "
                    "nobody did. By month due:")))
                m = (esq.assign(mes=pd.to_datetime(esq["prometida"])
                                .dt.to_period("M").astype(str))
                     .groupby("mes").agg(n=("pedido", "count"),
                                         valor=("valor", "sum"))
                     .reset_index())
                st.dataframe(pd.DataFrame({
                    L("Mês do vencimento", "Month due"): m["mes"].map(
                        i18n.mes_ano),
                    L("Pedidos", "Orders"): m["n"],
                    L("Valor", "Value"): [moeda(v, 0) for v in m["valor"]],
                }), use_container_width=True, hide_index=True)

    st.markdown("---")
    _bloco_regua(con, dom, dmin, ref, filtros)


def _bloco_regua(con, dom, dmin: date, ref: date, filtros: Filtros) -> None:
    st.markdown(L("#### A régua D+3/D+7 se sustenta?",
                  "#### Does the D+3/D+7 rule hold?"))
    st.markdown(md(L(
        "Para cada dia depois do prometido: dos pedidos que **ainda não "
        "tinham chegado**, quantos chegaram depois. Enquanto a chance é alta, "
        "cobrar e esperar; quando cai, falar com o cliente. A faixa em volta "
        "da linha é o intervalo de Wilson (95%).",
        "For each day after the promise: of the orders that **still hadn't "
        "arrived**, how many arrived later. While the odds are high, chase "
        "and wait; when they drop, contact the customer. The band around the "
        "line is the Wilson interval (95%).")))
    ini = max(dmin, ref - timedelta(days=364))
    c1, c2 = st.columns([1, 2])
    with c1:
        por = st.selectbox(L("Abrir por", "Split by"),
                           options=["", "origem", "rota", "regiao_destino",
                                    "faixa_promessa"],
                           format_func=lambda k: (L("Sem quebra (malha)",
                                                    "No split (network)")
                                                  if not k else
                                                  dom.dimensao(k).rotulo),
                           key="log_regua_por")
    with c2:
        st.caption(L(
            f"Pedidos vencidos de {i18n.data(ini)} a {i18n.data(ref)} — "
            "doze meses, para a curva ter volume mesmo com filtro.",
            f"Orders due from {i18n.data(ini)} to {i18n.data(ref)} — twelve "
            "months, so the curve has volume even with a filter."))

    total = ld.ponto_sem_volta(con, dom, ini, ref, filtros)
    if total.empty or total["pendentes"].max() < 30:
        st.info(L("Pendentes de menos para ler a curva com esse filtro.",
                  "Too few pending orders to read the curve with this "
                  "filter."))
        return

    fig = go.Figure()
    series = [("", total)]
    if por:
        seg = ld.ponto_sem_volta(con, dom, ini, ref, filtros, por=por)
        grandes = (seg[seg["k"] == 7].sort_values("pendentes", ascending=False)
                   .query("pendentes >= 30")["segmento"].head(6).tolist())
        series = [(s, seg[seg["segmento"] == s]) for s in grandes]
    for i, (nome, d) in enumerate(series):
        cor = SERIE[i % len(SERIE)]
        rot = V(nome) if nome else L("Malha toda", "Whole network")
        if not por:
            fig.add_trace(go.Scatter(
                x=list(d["k"]) + list(d["k"])[::-1],
                y=list(d["ic_sup"]) + list(d["ic_inf"])[::-1],
                fill="toself", fillcolor="rgba(37,99,235,0.13)",
                line=dict(width=0), hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=d["k"], y=d["taxa"], name=rot, mode="lines+markers",
            line=dict(color=cor, width=2.2), marker=dict(size=4),
            customdata=list(zip([pct(a, 0, False) for a in d["ic_inf"]],
                                [pct(b, 0, False) for b in d["ic_sup"]],
                                d["pendentes"].astype(int))),
            hovertemplate="D+%{x}: <b>%{y:.0%}</b> (%{customdata[0]}–"
                          "%{customdata[1]})<br>%{customdata[2]} "
                          + L("pendentes", "pending") + "<extra>" + rot
                          + "</extra>"))
    for k, cor in ((3, "#d97706"), (7, JULGA_RUIM)):
        fig.add_vline(x=k, line=dict(color=cor, width=1.2, dash="dot"),
                      annotation_text=f"D+{k}", annotation_position="top",
                      annotation_font=dict(color=cor, size=11))
    fig.add_hline(y=0.5, line=dict(color=EIXO, width=1, dash="dash"))
    g._base(fig, 340, L("Dos pendentes em cada dia, quantos ainda chegam",
                        "Of those pending each day, how many still arrive"))
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    fig.update_xaxes(title=dict(text=L("dias depois do prometido",
                                       "days after the promise"),
                                font=dict(size=11, color=TINTA_MUDA)),
                     dtick=3)
    fig.update_layout(showlegend=bool(por), hovermode="closest")
    st.plotly_chart(fig, use_container_width=True, key="log_regua")

    # A leitura é a mesma que o Vulcão dá no chat.
    from vulcano.agente import Contexto
    ctx = Contexto(dominio=dom, inicio=ini, fim=ref, filtros=filtros)
    fatos, linhas = {}, []
    la._executar_regua(con, dom, ctx, {"por": None}, fatos, linhas)
    st.markdown(md("\n\n".join(linhas)))


# --------------------------------------------------------------------------- #
# Aba: Controle por origem
# --------------------------------------------------------------------------- #

def aba_controle(con, dom, dmin: date, dmax: date, fim: date,
                 filtros: Filtros) -> None:
    ref = ld.ultimo_domingo(min(fim, dmax))
    ini, _ = ld.janela_controle(ref, dmin)

    # O aviso da segunda-feira vem primeiro: a última semana fechada saiu
    # do controle? quem puxou?
    st.markdown(L("#### A última semana fechada",
                  "#### The last closed week"))
    sem = ld.semana_da_malha(con, dom, ref, filtros, dmin)
    if sem:
        c1, c2 = st.columns([1.1, 1], gap="large")
        with c1:
            st.markdown(md("\n\n".join(la.ler_semana(sem))))
        with c2:
            cb = sem["contribuicoes"]
            if not cb.empty:
                cb = cb.sort_values("excesso")
                fig = go.Figure(go.Bar(
                    y=[V(x) for x in cb["segmento"]], x=cb["excesso"],
                    orientation="h",
                    marker_color=[JULGA_RUIM if a else EIXO
                                  for a in cb["acima"]],
                    customdata=list(zip([pct(p, 1, False) for p in cb["p"]],
                                        [pct(p, 1, False) for p in cb["p_bar"]])),
                    hovertemplate="%{y}<br>%{customdata[0]} "
                                  + L("fora do prazo, normal ",
                                      "late, normal ")
                                  + "%{customdata[1]}<extra></extra>"))
                fig.add_vline(x=0, line=dict(color=EIXO, width=1))
                g._base(fig, 70 + 40 * len(cb),
                        L("Atraso a mais da semana, por região de destino",
                          "Extra delay in the week, by destination region"))
                fig.update_xaxes(tickformat="+.1%", showgrid=True)
                st.plotly_chart(fig, use_container_width=True,
                                key="log_semana_reg")
                st.caption(L(
                    "Pedidos fora do prazo acima do normal de cada região, "
                    "sobre o total da semana. Vermelho: a região saiu do "
                    "próprio limite de controle.",
                    "Late orders above each region's normal, over the "
                    "week's total. Red: the region broke its own control "
                    "limit."))
    st.markdown(md(L(
        f"#### Gráfico de controle da taxa fora do prazo\n"
        f"Semanas de {i18n.data(ini)} a {i18n.data(ref)}, pela data prometida. "
        f"Cada origem tem a própria média (p̄) e limites que dependem do volume "
        f"da semana: `p̄ ± 3·√(p̄(1−p̄)/n)`. Dentro do limite é ruído; fora, "
        f"a semana foi anormal.",
        f"#### Control chart of the late rate\n"
        f"Weeks from {i18n.data(ini)} to {i18n.data(ref)}, by promised date. "
        f"Each origin has its own average (p̄) and limits that depend on the "
        f"week's volume: `p̄ ± 3·√(p̄(1−p̄)/n)`. Within the limit it's noise; "
        f"outside it, the week was abnormal.")))

    por = st.radio(L("Abrir por", "Split by"),
                   options=["origem", "regiao_destino"], horizontal=True,
                   format_func=lambda k: dom.dimensao(k).rotulo,
                   key="log_ctrl_por")
    c = ld.controle(con, dom, ini, ref, filtros, por=por)
    malha = ld.controle(con, dom, ini, ref, filtros, por=None)
    if c.empty:
        st.info(L("Sem dado com esse filtro.", "No data with this filter."))
        return
    s = ld.resumo_controle(c)
    s = s[s["pedidos"] >= 200]

    # --- mapa: semana × origem --------------------------------------------- #
    st.markdown(L("##### Quem estourou, e quando",
                  "##### Who broke out, and when"))
    origens = s.sort_values("pedidos", ascending=False)["segmento"].tolist()
    cc = c[c["segmento"].isin(origens)].copy()
    cc["estado"] = 0
    cc.loc[cc["abaixo"], "estado"] = -1
    cc.loc[cc["acima"], "estado"] = 1
    piv = cc.pivot(index="segmento", columns="semana", values="estado"
                   ).reindex(origens)
    pp = cc.pivot(index="segmento", columns="semana", values="p"
                  ).reindex(origens)
    fig = go.Figure(go.Heatmap(
        z=piv.values, x=piv.columns, y=[V(o) for o in piv.index],
        zmin=-1, zmax=1, showscale=False, xgap=2, ygap=2,
        colorscale=[[0, "#bfdbfe"], [0.5, "#eef2f7"], [1, JULGA_RUIM]],
        customdata=pp.values,
        hovertemplate="%{y} · " + L("semana de ", "week of ")
                      + "%{x|" + i18n.formato_data_plotly() + "}"
                      "<br><b>%{customdata:.1%}</b> "
                      + L("fora do prazo", "late") + "<extra></extra>"))
    g._base(fig, 60 + 34 * len(origens))
    fig.update_yaxes(showgrid=False, autorange="reversed")
    st.plotly_chart(fig, use_container_width=True, key="log_mapa")
    st.caption(L(
        "Vermelho: semana acima do limite de controle. Azul: abaixo do limite "
        "inferior (melhor que o normal — ou promessa folgada demais). Coluna "
        "inteira vermelha é causa da malha, não de uma origem.",
        "Red: week above the control limit. Blue: below the lower limit "
        "(better than normal — or a promise that's too loose). A whole red "
        "column is a network-wide cause, not one origin's."))

    # --- o p-chart de uma origem ------------------------------------------- #
    st.markdown(L("##### O p-chart de um segmento",
                  "##### One segment's p-chart"))
    opcoes = ["__malha__"] + origens
    padrao = origens[0] if origens else "__malha__"
    if not s.empty and s["semanas_acima"].max() > 0:
        padrao = s.sort_values("semanas_acima", ascending=False
                               ).iloc[0]["segmento"]
    escolha = st.selectbox(
        dom.dimensao(por).rotulo, options=opcoes, index=opcoes.index(padrao),
        format_func=lambda k: (L("Malha toda", "Whole network")
                               if k == "__malha__" else V(k)),
        key="log_pchart_origem")
    d = malha if escolha == "__malha__" else c[c["segmento"] == escolha]
    st.plotly_chart(p_chart(d, L("Malha toda", "Whole network")
                            if escolha == "__malha__" else V(escolha)),
                    use_container_width=True, key="log_pchart")

    # --- a leitura, igual à do chat ----------------------------------------- #
    from vulcano.agente import Contexto
    ctx = Contexto(dominio=dom, inicio=ini, fim=ref, filtros=filtros)
    fatos, linhas = {}, []
    tabela, _ = la._executar_controle(con, dom, ctx, fatos, linhas,
                                      com_semana=False)
    st.markdown(md("\n\n".join(linhas)))
    if tabela is not None:
        st.dataframe(tabela, use_container_width=True, hide_index=True)


def p_chart(d: pd.DataFrame, titulo: str, altura: int = 340) -> go.Figure:
    d = d.sort_values("semana")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=d["semana"], y=d["lsc"], name=L("Limite superior", "Upper limit"),
        mode="lines", line=dict(color=JULGA_RUIM, width=1, dash="dot",
                                shape="hv"),
        hovertemplate="%{y:.1%}<extra>" + L("limite", "limit") + "</extra>"))
    fig.add_trace(go.Scatter(
        x=d["semana"], y=d["lic"], name=L("Limite inferior", "Lower limit"),
        mode="lines", line=dict(color=SERIE[0], width=1, dash="dot",
                                shape="hv"), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=d["semana"], y=d["p_bar"], name="p̄", mode="lines",
        line=dict(color=TINTA_MUDA, width=1.2), hoverinfo="skip"))
    cores = [JULGA_RUIM if a else (SERIE[0] if b else TINTA_2)
             for a, b in zip(d["acima"], d["abaixo"])]
    fig.add_trace(go.Scatter(
        x=d["semana"], y=d["p"], name=L("Fora do prazo", "Late"),
        mode="lines+markers", line=dict(color=TINTA_2, width=1.4),
        marker=dict(color=cores, size=[9 if a else 6 for a in d["acima"]]),
        customdata=d["n"],
        hovertemplate=L("semana de ", "week of ") + "%{x|"
                      + i18n.formato_data_plotly() + "}<br><b>%{y:.1%}</b> "
                      + L("fora do prazo", "late") + " · %{customdata:,} "
                      + L("pedidos", "orders") + "<extra></extra>"))
    g._base(fig, altura, titulo)
    fig.update_yaxes(tickformat=".0%", rangemode="tozero")
    fig.update_layout(showlegend=True, hovermode="x unified")
    return fig


def curva_regua(curva: pd.DataFrame) -> go.Figure:
    """A curva do ponto de não retorno, para a resposta do chat."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(curva["k"]) + list(curva["k"])[::-1],
        y=list(curva["ic_sup"]) + list(curva["ic_inf"])[::-1],
        fill="toself", fillcolor="rgba(37,99,235,0.13)", line=dict(width=0),
        hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=curva["k"], y=curva["taxa"],
                             mode="lines+markers",
                             line=dict(color=SERIE[0], width=2.2),
                             marker=dict(size=4),
                             hovertemplate="D+%{x}: <b>%{y:.0%}</b>"
                                           "<extra></extra>"))
    for k, cor in ((3, "#d97706"), (7, JULGA_RUIM)):
        fig.add_vline(x=k, line=dict(color=cor, width=1.2, dash="dot"),
                      annotation_text=f"D+{k}", annotation_position="top",
                      annotation_font=dict(color=cor, size=11))
    fig.add_hline(y=0.5, line=dict(color=EIXO, width=1, dash="dash"))
    g._base(fig, 300)
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    fig.update_xaxes(dtick=3)
    return fig


def grafico_resposta(r) -> go.Figure | None:
    """O gráfico que acompanha a resposta do Vulcão no chat, quando há."""
    intencao = (r.plano or {}).get("intencao")
    d = r.grafico
    if d is None or getattr(d, "empty", True):
        return None
    if intencao == "regua":
        return curva_regua(d)
    if intencao == "controle":
        if "segmento" in d:
            pior = (d[d["acima"]].groupby("segmento").size()
                    .sort_values(ascending=False))
            seg = pior.index[0] if not pior.empty else d["segmento"].iloc[0]
            return p_chart(d[d["segmento"] == seg], V(seg), 300)
    return None


# --------------------------------------------------------------------------- #
# Bloco na aba de Alertas
# --------------------------------------------------------------------------- #

def bloco_alertas(con, dom, ref: date, filtros: Filtros) -> None:
    """O alerta do motor diz que o no prazo caiu; a pergunta seguinte é
    sempre 'e quem eu aciono hoje?'. A fila do dia entra logo abaixo."""
    st.markdown(CSS_LOG, unsafe_allow_html=True)
    f = ld.fila(con, dom, ref, filtros)
    r = ld.resumo_fila(f)
    dmin, _ = periodo_disponivel(con)
    sem = ld.semana_da_malha(con, dom, ref, filtros, dmin)

    st.markdown(L("##### Na régua hoje", "##### On the rule today"))
    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        st.markdown(_kpi(L("Cruzaram o D+7 hoje", "Crossed D+7 today"),
                         _num(r["hoje_d7"]),
                         L(f"{_num(r['d7'])} na faixa do D+7",
                           f"{_num(r['d7'])} in the D+7 band"), "quente"),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(_kpi(L("Cruzaram o D+3 hoje", "Crossed D+3 today"),
                         _num(r["hoje_d3"]),
                         L(f"{_num(r['d3'])} na faixa do D+3",
                           f"{_num(r['d3'])} in the D+3 band"), "morno"),
                    unsafe_allow_html=True)
    with c3:
        if sem:
            pux = sem.get("puxou")
            st.markdown(_kpi(
                L(f"Semana de {i18n.data_curta(sem['semana'])}",
                  f"Week of {i18n.data_curta(sem['semana'])}"),
                (L("Fora de controle", "Out of control") if sem["acima"]
                 else L("Sob controle", "In control")),
                (L(f"{pct(sem['p'], 1, False)} fora do prazo",
                   f"{pct(sem['p'], 1, False)} late")
                 + (L(f" · puxou: {V(pux['segmento'])}",
                      f" · driven by: {V(pux['segmento'])}")
                    if sem["acima"] and pux else "")),
                "quente" if sem["acima"] else "frio"),
                unsafe_allow_html=True)
    if sem and sem["acima"]:
        st.markdown(md("\n\n".join(la.ler_semana(sem))))
    st.caption(L("A fila completa e o gráfico de controle estão nas abas "
                 "Pedidos travados e Controle por origem.",
                 "The full queue and the control chart are in the Stuck "
                 "orders and Control by origin tabs."))
