"""
As telas que só existem no domínio de Compliance e PLD.

Mesma regra do app.py: aqui só tem tela. A fila, a prioridade, o dossiê e a
calibração são calculados em `vulcano/pld`, e os números agregados vêm do
mesmo motor das outras abas.

    Clientes em atenção    a fila de análise, cliente a cliente, e o dossiê
    Regras e calibração    catálogo, desempenho por regra, corte e ciclo
    (blocos extras)        idade da fila na Visão geral; mapa regulatório e
                           automação na aba Sobre os dados
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from vulcano import graficos as g
from vulcano import i18n
from vulcano.dados import Filtros, agregar
from vulcano.estilo import html_moeda, md, nota, rosto
from vulcano.formatacao import numero, pct
from vulcano.i18n import L, V
from vulcano.graficos import (EIXO, GRADE, JULGA_BOM, JULGA_RUIM, SERIE,
                              STATUS, SURFACE, TINTA, TINTA_2, TINTA_MUDA)
from vulcano.pld import dados as pld_dados
from vulcano.pld import fila as mod_fila
from vulcano.pld import parecer as mod_parecer
from vulcano.pld.en import evidencia as ev_local
from vulcano.pld.calendario import (PRAZO_ANALISE_DIAS, eh_dia_util,
                                    proximo_dia_util)
from vulcano.pld.normas import TRECHOS, citar
from vulcano.pld.regras import REGRAS

CSS_PLD = f"""
<style>
  .pld-kpi {{ border: 1px solid {GRADE}; border-radius: 12px;
             background: {SURFACE}; padding: 12px 14px; height: 100%; }}
  .pld-kpi .rot {{ color: {TINTA_MUDA}; font-size: 0.66rem; font-weight: 650;
                  text-transform: uppercase; letter-spacing: .055em; }}
  .pld-kpi .val {{ color: {TINTA}; font-size: 1.35rem; font-weight: 650;
                  margin-top: 2px; font-variant-numeric: tabular-nums; }}
  .pld-kpi .det {{ color: {TINTA_MUDA}; font-size: 0.7rem; margin-top: 1px; }}
  .pld-cab {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
             gap: 8px 18px; border: 1px solid {GRADE}; border-radius: 12px;
             background: {SURFACE}; padding: 14px 18px; margin: 6px 0 14px; }}
  .pld-cab .r {{ color: {TINTA_MUDA}; font-size: 0.66rem; font-weight: 650;
                text-transform: uppercase; letter-spacing: .05em; }}
  .pld-cab .v {{ color: {TINTA}; font-size: 0.92rem; font-weight: 600; }}
  .pld-fator {{ display: grid; grid-template-columns: 1fr 44px; gap: 8px;
               align-items: center; margin: 5px 0; font-size: 0.84rem;
               color: {TINTA_2}; }}
  .pld-barra {{ height: 6px; border-radius: 3px; background: {SERIE[0]};
               margin-top: 3px; }}
  .pld-fator .pts {{ text-align: right; font-weight: 650; color: {TINTA};
                    font-variant-numeric: tabular-nums; }}
  .pld-prazo {{ border-radius: 10px; padding: 10px 14px; margin-top: 12px;
               font-size: 0.86rem; line-height: 1.5; }}
  @media (max-width: 900px) {{
    .pld-cab {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  }}
</style>
"""


def _kpi(rotulo: str, valor: str, detalhe: str = "", cor: str = TINTA) -> str:
    return (f'<div class="pld-kpi"><div class="rot">{rotulo}</div>'
            f'<div class="val" style="color:{cor}">{html_moeda(valor)}</div>'
            f'<div class="det">{detalhe}</div></div>')


def _brl(v: float) -> str:
    return i18n.brl(v)


MESES_BR = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


def _mes_br(mes: str) -> str:
    return i18n.mes_ano(mes)


def _prazo_txt(dias: int) -> str:
    if dias < 0:
        return L(f"vencido há {-dias} d", f"overdue by {-dias} d")
    if dias == 0:
        return L("vence hoje", "due today")
    return L(f"{dias} dias", f"{dias} days")


def _d(x) -> str:
    return i18n.data(x)


# =========================================================================== #
# Aba: Clientes em atenção
# =========================================================================== #

def aba_clientes(con, dom, dmax: date, fim: date, filtros: Filtros) -> None:
    st.markdown(CSS_PLD, unsafe_allow_html=True)
    base = pld_dados.data_base()
    padrao = pld_dados.referencia(fim, dmax)

    st.markdown(
        f"""<div class="vulc-agente">
          {rosto(dom, "alerta", 56)}
          <div>
            <div class="nome" style="font-size:1.16rem">{dom.agente_nome}
              <span style="font-weight:500;color:#46586e;font-size:0.92rem">
                {L("separou quem precisa de atenção",
                   "set aside who needs attention")}</span></div>
            <div class="papel">{L(
                "Cada cliente abaixo se enquadra em ao menos uma situação da "
                "Carta Circular 4.001 e está na fila de análise. A ordem é por "
                "prioridade; o prazo de 45 dias anda em coluna separada. Os "
                "filtros da barra lateral valem aqui.",
                "Each client below falls under at least one situation of "
                "Circular Letter 4,001 and is in the review queue. The order "
                "is by priority; the 45-day deadline runs in a separate "
                "column. The sidebar filters apply here.")}</div>
          </div>
        </div>""", unsafe_allow_html=True)
    st.write("")

    c1, c2, c3 = st.columns([1.2, 1.6, 1.4])
    with c1:
        # A chave carrega a data padrão: mudar o período na barra lateral
        # reposiciona a fila, em vez de o widget guardar a data antiga.
        ref = st.date_input(L("Posição da fila em", "Queue position on"),
                            value=padrao,
                            min_value=date(2025, 9, 1), max_value=base,
                            format=i18n.formato_data_widget(),
                            key=f"cl_ref_{padrao}")
        ref = ref if isinstance(ref, date) else padrao
    with c2:
        busca = st.text_input(L("Buscar cliente pelo código",
                                "Search client by code"),
                              placeholder="T-01160, L-41167, E-0132",
                              key="cl_busca")
    with c3:
        vistas = {"todos": L("Todos", "All"),
                  "critica": L("Prioridade crítica e alta",
                               "Critical and high priority"),
                  "prazo": L("Vencidos ou vencendo em 7 dias",
                             "Overdue or due within 7 days"),
                  "multi": L("Com mais de uma regra aberta",
                             "More than one open rule")}
        mostrar = st.selectbox(L("Mostrar", "Show"), list(vistas),
                               format_func=vistas.get, key="cl_mostrar_k")

    fl = mod_fila.posicao(con, dom, ref, filtros)
    res = mod_fila.resumir(fl)

    cols = st.columns(5, gap="small")
    cartoes = [
        (L("Clientes na fila", "Clients in the queue"), f"{res.clientes}",
         L(f"{res.alertas} alertas abertos", f"{res.alertas} open alerts"),
         TINTA),
        (L("Prioridade crítica", "Critical priority"), f"{res.criticos}",
         L("70 pontos ou mais", "70 points or more"),
         STATUS["alta"] if res.criticos else TINTA),
        (L("Vencem em até 7 dias", "Due within 7 days"), f"{res.vencem_7d}",
         L("art. 43, § 1º", "art. 43, § 1"),
         STATUS["media"] if res.vencem_7d else TINTA),
        (L("Fora do prazo", "Overdue"), f"{res.vencidos}",
         L("mais de 45 dias sem decisão", "over 45 days without a decision"),
         JULGA_RUIM if res.vencidos else JULGA_BOM),
        (L("Valor envolvido na fila", "Amount involved in the queue"),
         numero(res.valor, dom.metrica("valor_envolvido")),
         L("soma das janelas dos alertas", "sum of the alerts' windows"),
         TINTA),
    ]
    for col, (r, v, d, cor) in zip(cols, cartoes):
        with col:
            st.markdown(_kpi(r, v, d, cor), unsafe_allow_html=True)
    st.write("")

    if fl.empty:
        st.info(L(f"A fila está vazia em {_d(ref)} com o filtro "
                  f"{filtros.resumo(dom)}.",
                  f"The queue is empty on {_d(ref)} with the filter "
                  f"{filtros.resumo(dom)}."))
        return

    vista = fl.copy()
    if mostrar == "critica":
        vista = vista[vista["faixa"].isin(["Crítica", "Alta"])]
    elif mostrar == "prazo":
        vista = vista[vista["dias_para_prazo"] <= 7].sort_values(
            "dias_para_prazo")
    elif mostrar == "multi":
        vista = vista[vista["regras"].str.contains(",")]
    vista = vista.reset_index(drop=True)

    c_prio, c_prazo = L("Prioridade", "Priority"), L("Prazo", "Deadline")
    tabela = pd.DataFrame({
        c_prio: vista["prioridade"],
        L("Faixa", "Band"): vista["faixa"].map(V),
        L("Cliente", "Client"): vista["codigo"],
        L("Tipo", "Type"): vista["tipo_cliente"].map(V),
        L("Regras abertas", "Open rules"): vista["regras"],
        L("Carta Circular 4.001", "Circular Letter 4,001"): vista["enquadramento"],
        L("Valor envolvido", "Amount involved"): [_brl(v) for v in vista["valor_envolvido"]],
        c_prazo: [_prazo_txt(int(x)) for x in vista["dias_para_prazo"]],
        L("Risco", "Risk"): vista["faixa_risco"].map(V),
        L("Já comunicado", "Previously reported"): [L("sim", "yes") if x else ""
                                                    for x in vista["reincidente"]],
        L("UF", "State"): vista["uf"],
    })
    st.caption(L(f"{len(vista)} de {len(fl)} clientes · clique numa linha para "
                 f"abrir o dossiê.",
                 f"{len(vista)} of {len(fl)} clients · click a row to open the "
                 f"case file."))
    evento = st.dataframe(
        tabela, hide_index=True, use_container_width=True,
        height=min(420, 36 * len(tabela) + 40),
        on_select="rerun", selection_mode="single-row", key="cl_tabela",
        column_config={
            c_prio: st.column_config.ProgressColumn(
                c_prio, min_value=0, max_value=100, format="%.0f",
                help=L("Soma de pontos com fatores nomeados — a conta aparece "
                       "no dossiê.",
                       "Sum of points with named factors — the math shows up "
                       "in the case file.")),
            c_prazo: st.column_config.TextColumn(
                c_prazo, help=L("Dias até o fim do prazo de análise do alerta "
                                "mais antigo aberto (45 dias corridos).",
                                "Days until the review deadline of the oldest "
                                "open alert (45 calendar days).")),
        })

    codigo = None
    if busca.strip():
        cid = mod_parecer.cliente_por_codigo(con, busca)
        if cid is None:
            st.warning(L(f"Não encontrei {busca.strip().upper()} entre os "
                         f"clientes com alerta.",
                         f"I couldn't find {busca.strip().upper()} among "
                         f"clients with alerts."))
        else:
            codigo = cid
    if codigo is None:
        linhas = (evento.selection.rows if evento and evento.selection else [])
        if linhas and linhas[0] < len(vista):
            codigo = vista.iloc[linhas[0]]["cliente_id"]
        elif not vista.empty:
            codigo = vista.iloc[0]["cliente_id"]
    if codigo:
        st.markdown("---")
        _dossie(con, dom, codigo, ref)


def _dossie(con, dom, cliente_id: str, ref: date) -> None:
    d = mod_parecer.montar(con, dom, cliente_id, ref)
    if d is None:
        st.info(L("Esse cliente não tem alerta até a data escolhida.",
                  "This client has no alert up to the chosen date."))
        return

    st.markdown(L(f"### Dossiê · {d.codigo}", f"### Case file · {d.codigo}"))
    st.caption(L("Rascunho montado pela Ravena a partir dos alertas, das "
                 "movimentações e das contrapartes. Dado simulado; documento "
                 "mascarado.",
                 "Draft put together by Ravena from the alerts, the account "
                 "activity and the counterparties. Simulated data; masked "
                 "document."))
    st.markdown('<div class="pld-cab">' + "".join(
        f'<div><div class="r">{k}</div><div class="v">{v}</div></div>'
        for k, v in mod_parecer.rotulos_cabecalho(d.cabecalho).items())
        + "</div>", unsafe_allow_html=True)

    esq, dir_ = st.columns([3, 2], gap="large")
    with esq:
        st.markdown(L("##### O que disparou", "##### What fired"))
        if d.abertos.empty:
            st.caption(L("Nenhum alerta aberto nesta data.",
                         "No open alert on this date."))
        for a in d.abertos.itertuples():
            r = REGRAS[a.regra_id].local
            limite = a.data + pd.Timedelta(days=PRAZO_ANALISE_DIAS)
            st.markdown(
                f"""<div class="vulc-alerta" style="border-left-color:{SERIE[0]}">
                  <div class="cab" style="color:{SERIE[0]}">{r.rotulo} ·
                    {L("selecionado em", "selected on")} {_d(a.data)}</div>
                  <div class="txt">{html_moeda(ev_local(a.evidencia))}</div>
                  <div class="aca">{L("Enquadramento", "Fits")}:
                    {citar(list(r.enquadramento))}
                    · {L("base", "grounded in")}: {citar(list(r.base_3978))}
                    · {L("análise até", "review due by")} {_d(limite)}</div>
                </div>""", unsafe_allow_html=True)

    with dir_:
        st.markdown(L(f"##### Por que a prioridade é {d.prioridade:.0f}",
                      f"##### Why the priority is {d.prioridade:.0f}"))
        topo = max([p for _, p in d.fatores] + [1.0])
        st.markdown("".join(
            f'<div class="pld-fator"><div>{nome}'
            f'<div class="pld-barra" style="width:{p / topo * 100:.0f}%"></div>'
            f'</div><div class="pts">+{p:.0f}</div></div>'
            for nome, p in d.fatores) + (
            f'<div class="pld-fator" style="border-top:1px solid {GRADE};'
            f'padding-top:6px"><div><b>{L("Prioridade", "Priority")}</b> '
            f'{L("(teto de 100)", "(capped at 100)")}</div>'
            f'<div class="pts">{d.prioridade:.0f}</div></div>'),
            unsafe_allow_html=True)
        if d.prazo_final:
            vencido = d.dias_para_prazo < 0
            cor_fundo = "#fdecea" if vencido else "#eef3fa"
            cor_txt = JULGA_RUIM if vencido else TINTA
            n = d.dias_para_prazo
            situacao = (L(f"vencida há {-n} dia(s)", f"overdue by {-n} day(s)")
                        if vencido else
                        L(f"faltam {n} dia(s)", f"{n} day(s) left"))
            st.markdown(
                f"""<div class="pld-prazo" style="background:{cor_fundo};
                    color:{cor_txt}">{L(
                  f"<b>Análise até {_d(d.prazo_final)}</b> — {situacao} "
                  f"(Circular 3.978, art. 43, § 1º). Se decidir comunicar hoje, "
                  f"o envio vai até {_d(proximo_dia_util(ref))} "
                  f"(art. 48, § 2º).",
                  f"<b>Review due by {_d(d.prazo_final)}</b> — {situacao} "
                  f"(Circular 3,978, art. 43, § 1). If you decide to report "
                  f"today, the filing is due by {_d(proximo_dia_util(ref))} "
                  f"(art. 48, § 2).")}
                </div>""", unsafe_allow_html=True)

    # --- movimentação ---------------------------------------------------- #
    if not d.serie.empty:
        st.markdown(L("##### Movimentação", "##### Account activity"))
        principais = {"T": ["Pix recebidos", "Pix enviados"],
                      "L": ["Recebido no POS"],
                      "E": ["Recarga de benefício"]}[cliente_id[0]]
        s = d.serie[d.serie["serie"].isin(principais)]
        fig = go.Figure()
        todas_datas = pd.date_range(min(d.serie["data"]), ref)
        for i, nome in enumerate(principais):
            x = (s[s["serie"] == nome].set_index("data")["valor"]
                 .reindex(todas_datas.date, fill_value=0.0))
            fig.add_trace(go.Scatter(
                x=list(x.index), y=x.values, name=V(nome), mode="lines",
                line=dict(color=SERIE[i], width=1.6),
                customdata=[_brl(v) for v in x.values],
                hovertemplate="%{x|" + i18n.formato_data_plotly()
                              + "}<br><b>%{customdata}</b>"
                              f"<extra>{V(nome)}</extra>"))
        for a in d.abertos.itertuples():
            fig.add_vline(x=a.data.isoformat(),
                          line=dict(color=STATUS["alta"], width=1, dash="dot"))
        fig = g._base(fig, 280, "")
        fig.update_layout(showlegend=len(principais) > 1, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True,
                        key=f"pld_serie_{cliente_id}")
        st.caption(L("Linhas pontilhadas: datas de seleção dos alertas abertos. "
                     "Valores diários.",
                     "Dotted lines: selection dates of the open alerts. Daily "
                     "values."))
        if cliente_id[0] == "L":
            noite = d.serie[d.serie["serie"] == "Transações entre 23h e 5h"]
            total = d.serie[d.serie["serie"] == "Transações"]
            if not total.empty:
                ult = ref - pd.Timedelta(days=30)
                n_noite = noite[noite["data"] > ult]["valor"].sum()
                n_total = total[total["data"] > ult]["valor"].sum()
                if n_total:
                    st.caption(L(
                        f"Nos últimos 30 dias: {n_noite:.0f} de "
                        f"{n_total:.0f} transações entre 23h e 5h "
                        f"({n_noite / n_total * 100:.0f}%).",
                        f"In the last 30 days: {n_noite:.0f} of "
                        f"{n_total:.0f} transactions between 11pm and 5am "
                        f"({n_noite / n_total * 100:.0f}%)."))

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(L("##### Contrapartes", "##### Counterparties"))
        if d.contrapartes.empty:
            st.caption(L("Sem contraparte registrada.",
                         "No counterparty recorded."))
        else:
            st.dataframe(pd.DataFrame({
                L("Sentido", "Direction"): d.contrapartes["sentido"].map(V),
                L("Contraparte", "Counterparty"): d.contrapartes["contraparte"].map(V),
                L("Operações", "Transactions"): d.contrapartes["qtd"].astype(int),
                L("Valor", "Amount"): [_brl(v) for v in d.contrapartes["valor"]],
                L("Em outros clientes com alerta",
                  "In other clients with alerts"): [
                    f"{int(x)}" if x > 0 else "" for x in
                    d.contrapartes["compartilhada"]],
            }).head(12), hide_index=True, use_container_width=True)
            st.caption(L("Contraparte que aparece em outros clientes com alerta "
                         "é o fio que liga contas de passagem entre si.",
                         "A counterparty that shows up in other clients with "
                         "alerts is the thread that ties pass-through accounts "
                         "together."))
    with c2:
        st.markdown(L("##### Histórico de análise", "##### Review history"))
        if d.historico.empty:
            st.caption(L("Primeira seleção deste cliente.",
                         "First selection of this client."))
        else:
            h = d.historico.sort_values("data", ascending=False)
            st.dataframe(pd.DataFrame({
                L("Seleção", "Selected"): [_d(x) for x in h["data"]],
                L("Regra", "Rule"): h["regra_id"],
                L("Decisão", "Decision"): h["decisao"].map(V),
                L("Decidido em", "Decided on"): [_d(x) if pd.notna(x) else ""
                                                 for x in h["data_decisao"]],
            }), hide_index=True, use_container_width=True,
                height=min(260, 36 * len(h) + 40))

    with st.expander(L("Rascunho de parecer da Ravena",
                       "Ravena's draft opinion"), expanded=True):
        st.markdown(md(d.texto))
        st.download_button(L("Baixar o dossiê (.md)",
                             "Download the case file (.md)"),
                           d.texto.encode("utf-8"),
                           file_name=L(f"dossie_{d.codigo}.md",
                                       f"case_file_{d.codigo}.md"),
                           mime="text/markdown", key=f"dl_{cliente_id}")

    # --- decisão --------------------------------------------------------- #
    st.markdown(L("##### Decisão da analista", "##### Analyst's decision"))
    registro = st.session_state.setdefault("pld_decisoes", {})
    anterior = registro.get(cliente_id)
    decisoes = {"descartar": L("Descartar", "Dismiss"),
                "reforcado": L("Monitoramento reforçado", "Enhanced monitoring"),
                "comunicar": L("Comunicar ao Coaf", "Report to COAF")}
    if anterior:
        st.success(L(f"Registrado nesta sessão: **{decisoes[anterior['decisao']]}** "
                     f"em {_d(anterior['em'])}. {anterior['nota']}",
                     f"Recorded in this session: "
                     f"**{decisoes[anterior['decisao']]}** on "
                     f"{_d(anterior['em'])}. {anterior['nota']}"))
    with st.form(f"form_{cliente_id}", clear_on_submit=False):
        decisao = st.radio(L("Decisão", "Decision"), list(decisoes),
                           format_func=decisoes.get, horizontal=True)
        justificativa = st.text_area(
            L("Justificativa (vai para o dossiê — art. 43, § 2º)",
              "Justification (goes into the case file — art. 43, § 2)"),
            placeholder=L("Ex.: origem comprovada por nota fiscal de venda do "
                          "veículo; movimentação compatível após atualização de "
                          "renda.",
                          "E.g.: source proven by the vehicle sale invoice; "
                          "activity consistent after the income update."))
        enviar = st.form_submit_button(L("Registrar decisão", "Record decision"),
                                       type="primary")
    if enviar:
        if len(justificativa.strip()) < 15:
            st.error(L("A justificativa é obrigatória, inclusive no descarte: "
                       "sem ela o dossiê não se sustenta numa auditoria.",
                       "The justification is mandatory, including for a "
                       "dismissal: without it the case file doesn't hold up "
                       "in an audit."))
        else:
            nota_txt = ""
            if decisao == "comunicar":
                nota_txt = L(f"Envio ao Coaf até {_d(proximo_dia_util(ref))}, "
                             f"sem dar ciência ao cliente (Lei 9.613/1998, "
                             f"art. 11).",
                             f"Filing to COAF by {_d(proximo_dia_util(ref))}, "
                             f"without informing the client (Law 9,613/1998, "
                             f"art. 11).")
            registro[cliente_id] = {"decisao": decisao, "em": ref,
                                    "nota": nota_txt,
                                    "justificativa": justificativa.strip()}
            st.rerun()
    st.caption(L("Na demonstração a decisão fica só nesta sessão do navegador. "
                 "Na operação, ela iria para a planilha da fila pelo Apps "
                 "Script descrito em Sobre os dados — sem depender de squad de "
                 "engenharia.",
                 "In the demo the decision stays only in this browser session. "
                 "In operation, it would go to the queue spreadsheet through "
                 "the Apps Script described in About the data — without "
                 "depending on an engineering squad."))


# =========================================================================== #
# Aba: Regras e calibração
# =========================================================================== #

def aba_regras(con, dom, inicio: date, fim: date, filtros: Filtros) -> None:
    st.markdown(CSS_PLD, unsafe_allow_html=True)
    st.markdown(L("##### As dez regras e onde cada uma se apoia",
                  "##### The ten rules and what each one rests on"))
    st.caption(L("Cada regra traduz uma situação da Carta Circular 4.001 em um "
                 "indicador, um corte e condições fixas. Um parâmetro só por "
                 "regra — é o que torna a calibração discutível com a área.",
                 "Each rule translates a situation from Circular Letter 4,001 "
                 "into an indicator, a threshold and fixed conditions. A "
                 "single parameter per rule — that's what makes calibration "
                 "something you can discuss with the business."))
    locais = [r.local for r in REGRAS.values()]
    st.dataframe(pd.DataFrame([{
        "ID": r.id, L("Regra", "Rule"): r.nome, L("Tipo", "Type"): r.tipo,
        L("Frequência", "Frequency"): r.frequencia,
        L("Indicador", "Indicator"): r.indicador,
        L("Corte vigente", "Current threshold"): r.parametro.formatar(),
        L("Condições fixas", "Fixed conditions"): "; ".join(r.condicoes),
        L("Carta Circular 4.001", "Circular Letter 4,001"): L(" e ", " and ").join(
            V(TRECHOS[k].rotulo) for k in r.enquadramento),
        L("Circular 3.978", "Circular 3,978"): citar(list(r.base_3978)).replace(
            L("Circular 3.978, ", "Circular 3,978, "), ""),
        L("Gravidade", "Severity"): r.gravidade,
    } for r in locais]), hide_index=True, use_container_width=True,
        height=36 * len(REGRAS) + 40)
    with st.expander(L("O racional de cada regra", "The rationale of each rule")):
        for r in locais:
            st.markdown(md(f"**{r.rotulo}.** {r.racional}"))

    # --- desempenho ------------------------------------------------------ #
    st.markdown("---")
    st.markdown(L("##### Desempenho por regra no período",
                  "##### Performance by rule in the period"))
    st.caption(L(f"{_d(inicio)} a {_d(fim)}, com o filtro da barra lateral "
                 f"({filtros.resumo(dom)}). Mesmos números da aba de causa "
                 f"raiz; taxas só de alertas maduros.",
                 f"{_d(inicio)} to {_d(fim)}, with the sidebar filter "
                 f"({filtros.resumo(dom)}). Same numbers as the root cause "
                 f"tab; rates from mature alerts only."))
    mks = ["alertas", "clientes_alertados", "taxa_falso_positivo",
           "taxa_comunicacao", "dias_analise", "fora_do_prazo"]
    df = agregar(con, dom, mks, inicio, fim, dims=["regra"], filtros=filtros,
                 ordenar_por="alertas")
    if df.empty:
        st.info(L("Nenhum alerta no período com esse filtro.",
                  "No alerts in the period with this filter."))
    else:
        st.dataframe(pd.DataFrame({
            L("Regra", "Rule"): df["regra"].map(V),
            **{dom.metrica(k).rotulo: [numero(float(v) if pd.notna(v) else float("nan"),
                                              dom.metrica(k)) for v in df[k]]
               for k in mks},
        }), hide_index=True, use_container_width=True)

    # --- calibração ------------------------------------------------------ #
    st.markdown("---")
    st.markdown(L("##### Calibração: o que acontece se eu mudar o corte",
                  "##### Calibration: what happens if I change the threshold"))
    calibraveis = [r for r in REGRAS.values() if r.calibravel]
    c1, c2 = st.columns([1.3, 2])
    with c1:
        rid = st.selectbox(L("Regra", "Rule"), [r.id for r in calibraveis],
                           format_func=lambda k: REGRAS[k].local.rotulo,
                           key="cal_regra")
    r_pt = REGRAS[rid]
    r = r_pt.local
    p = r.parametro
    with c2:
        # A chave inclui a regra: trocar de regra precisa trazer o corte
        # vigente DELA, e não o número que estava no slider da anterior.
        if p.unidade == "%":
            novo = st.slider(p.nome, float(p.minimo), float(p.maximo),
                             float(p.valor), float(p.passo), format="%.2f",
                             key=f"cal_{rid}")
        else:
            novo = st.slider(p.nome, float(p.minimo), float(p.maximo),
                             float(p.valor), float(p.passo), key=f"cal_{rid}")

    # Só os meses em que o corte ATUAL estava valendo: misturar meses com
    # parâmetro antigo compararia duas regras diferentes com o mesmo nome.
    vigencia = (r.parametro.historico[-1][0] if r.parametro.historico
                else date(2025, 9, 1))
    cal = pld_dados.calibracao()
    cal = cal[(cal["regra_id"] == rid) & (cal["mes"] >= vigencia.strftime("%Y-%m"))]
    atual_sel = cal[cal["indicador"] >= p.valor]
    novo_sel = cal[cal["indicador"] >= novo]
    decididos = atual_sel[atual_sel["decisao"].notna()
                          & (atual_sel["decisao"] != "Em análise")]
    comunicados = decididos[decididos["decisao"] == "Comunicado ao COAF"]
    perdidos = comunicados[comunicados["indicador"] < novo]
    fp_atual = (decididos["decisao"] == "Descartado").mean() if len(decididos) else float("nan")
    dec_novo = decididos[decididos["indicador"] >= novo]
    fp_novo = (dec_novo["decisao"] == "Descartado").mean() if len(dec_novo) else float("nan")
    sem_analise = len(novo_sel) - len(novo_sel[novo_sel["indicador"] >= p.valor]) \
        if novo < p.valor else 0

    # O filtro compara contra o rótulo gravado no dado (português).
    motor = agregar(con, dom, ["alertas"], vigencia, pld_dados.data_base(),
                    filtros=Filtros({"regra": [r_pt.rotulo]}))
    n_motor = int(motor.iloc[0]["alertas"]) if not motor.empty else 0

    cols = st.columns(4, gap="small")
    delta = len(novo_sel) - len(atual_sel)
    variacao = (delta / len(atual_sel)) if len(atual_sel) else None
    var_txt = pct(variacao) if variacao is not None else '—'
    fp_at_txt = pct(fp_atual, 1, sinal=False) if fp_atual == fp_atual else '—'
    cartoes = [
        (L(f"Alertas desde {i18n.mes(vigencia)}",
           f"Alerts since {i18n.mes(vigencia)}"), f"{len(novo_sel)}",
         L(f"hoje {len(atual_sel)} · {var_txt}",
           f"today {len(atual_sel)} · {var_txt}"),
         TINTA),
        (L("Comunicações que se perderiam", "Reports that would be lost"),
         f"{len(perdidos)}",
         L(f"de {len(comunicados)} comunicadas pela regra",
           f"of {len(comunicados)} reported by the rule"),
         JULGA_RUIM if len(perdidos) else TINTA),
        (L("Falso positivo dos decididos", "False positive of decided"),
         pct(fp_novo, 1, sinal=False) if fp_novo == fp_novo else "—",
         L(f"hoje {fp_at_txt}", f"today {fp_at_txt}"),
         TINTA),
        (L("Alertas novos sem histórico", "New alerts with no history"),
         f"{sem_analise}",
         L("abaixo do corte atual, nunca analisados",
           "below the current threshold, never reviewed"), TINTA),
    ]
    for col, (rot, val, det, cor) in zip(cols, cartoes):
        with col:
            st.markdown(_kpi(rot, val, det, cor), unsafe_allow_html=True)

    # curva: volume e comunicações capturadas em cada corte
    grade = [x for x in _grade(p)]
    vol = [int((cal["indicador"] >= x).sum()) for x in grade]
    cap = [int((comunicados["indicador"] >= x).sum()) if x >= p.valor
           else len(comunicados) for x in grade]
    g1, g2 = st.columns(2, gap="medium")
    for chave_g, col, ys, titulo, cor in (
            ("vol", g1, vol, L("Alertas no corte", "Alerts at the threshold"),
             SERIE[0]),
            ("cap", g2, cap, L("Comunicações mantidas", "Reports kept"),
             SERIE[1])):
        with col:
            fig = go.Figure(go.Scatter(
                x=grade, y=ys, mode="lines+markers", line=dict(color=cor, width=2),
                marker=dict(size=5),
                hovertemplate=L("corte", "threshold")
                              + " %{x}<br><b>%{y}</b><extra></extra>"))
            fig.add_vline(x=p.valor, line=dict(color=EIXO, width=1, dash="dot"),
                          annotation_text=L("vigente", "current"),
                          annotation_position="top")
            if novo != p.valor:
                fig.add_vline(x=novo, line=dict(color=STATUS["alta"], width=1.5),
                              annotation_text=L("escolhido", "chosen"),
                              annotation_position="bottom right")
            fig = g._base(fig, 240, titulo)
            fig.update_xaxes(title=dict(text=p.nome, font=dict(size=11,
                                                             color=TINTA_MUDA)))
            st.plotly_chart(fig, use_container_width=True,
                            key=f"cal_{chave_g}_{rid}")

    if novo > p.valor:
        menos = pct(variacao, 0, sinal=False) if variacao else '0%'
        frase = L(f"Subir o corte de **{p.formatar()}** para "
                  f"**{p.formatar(novo)}** tira {len(atual_sel) - len(novo_sel)} "
                  f"alertas da fila ({menos} a menos) e deixaria de selecionar "
                  f"**{len(perdidos)} comunicação(ões)** que a análise "
                  f"sustentou.",
                  f"Raising the threshold from **{p.formatar()}** to "
                  f"**{p.formatar(novo)}** takes "
                  f"{len(atual_sel) - len(novo_sel)} alerts off the queue "
                  f"({menos} fewer) and would stop selecting **{len(perdidos)} "
                  f"report(s)** that the analysis supported.")
    elif novo < p.valor:
        frase = L(f"Baixar o corte para **{p.formatar(novo)}** coloca "
                  f"{sem_analise} alertas novos na fila. Eles estão abaixo do "
                  f"corte atual, nunca foram analisados — então não dá para "
                  f"saber quantos virariam comunicação sem rodar em paralelo "
                  f"(modo sombra) por um ciclo.",
                  f"Lowering the threshold to **{p.formatar(novo)}** puts "
                  f"{sem_analise} new alerts in the queue. They are below the "
                  f"current threshold and were never reviewed — so there's no "
                  f"way to know how many would become reports without running "
                  f"in parallel (shadow mode) for a cycle.")
    else:
        frase = L(f"No corte vigente, {len(atual_sel)} alertas desde "
                  f"{i18n.mes(vigencia)} — o mesmo número que o motor conta "
                  f"para a regra ({n_motor}). Mova o corte para ver o custo de "
                  f"cada lado.",
                  f"At the current threshold, {len(atual_sel)} alerts since "
                  f"{i18n.mes(vigencia)} — the same number the engine counts "
                  f"for the rule ({n_motor}). Move the threshold to see the "
                  f"cost on each side.")
    st.markdown(md(frase))
    st.markdown(nota(L(
        "A conta é exata, não estimativa: com um parâmetro só e supressão "
        "mensal, a regra dispara no mês se, e só se, o máximo mensal do "
        "indicador passar do corte. Mudança de corte é decisão de política — "
        "vai para a avaliação interna de risco (Circular 3.978, art. 10) com "
        "data de vigência, como a R01 em 01/03/2026. Os filtros da barra "
        "lateral não se aplicam à calibração.",
        "The math is exact, not an estimate: with a single parameter and "
        "monthly suppression, the rule fires in a month if, and only if, the "
        "indicator's monthly maximum crosses the threshold. Changing a "
        "threshold is a policy decision — it goes into the internal risk "
        "assessment (Circular 3,978, art. 10) with an effective date, like "
        "R01 on Mar 1, 2026. The sidebar filters don't apply to "
        "calibration.")), unsafe_allow_html=True)

    # --- ciclo mensal ------------------------------------------------------ #
    st.markdown("---")
    st.markdown(L("##### Ciclo mensal de checagem de CPFs",
                  "##### Monthly CPF check cycle"))
    ci = pld_dados.ciclo()
    ci = ci.assign(mes=[d.strftime("%Y-%m") for d in ci["data"]])
    # "no dia previsto": o reprocessamento fecha o mês, mas atrasado. Somar o
    # que foi checado depois esconderia justamente o buraco que importa.
    ci["no_dia"] = ci[["checados", "previstos"]].min(axis=1)
    por_mes = ci.groupby("mes")[["previstos", "no_dia"]].sum().reset_index()
    por_mes["cobertura"] = por_mes["no_dia"] / por_mes["previstos"]
    fig = go.Figure(go.Bar(
        x=[_mes_br(m) for m in por_mes["mes"]], y=por_mes["cobertura"],
        marker=dict(color=[JULGA_RUIM if c < 0.999 else SERIE[0]
                           for c in por_mes["cobertura"]]),
        text=[pct(c, 1, sinal=False) for c in por_mes["cobertura"]],
        textposition="outside",
        hovertemplate="%{x}<br><b>%{text}</b> "
                      + L("dos lotes previstos no dia certo",
                          "of scheduled batches on the right day")
                      + "<extra></extra>"))
    fig = g._base(fig, 240, L("Lotes checados no dia previsto",
                              "Batches checked on the scheduled day"))
    fig.update_xaxes(type="category")
    fig.update_yaxes(tickformat=".0%", range=[0.75, 1.06])
    st.plotly_chart(fig, use_container_width=True, key="pld_ciclo")
    falhas = ci[ci["situacao"].isin(["Falha do job", "Reprocessamento"])]
    if not falhas.empty:
        itens = "; ".join(
            L(f"{_d(r.data)} — {r.situacao.lower()} "
              f"({r.checados} CPFs checados de {r.previstos} previstos)",
              f"{_d(r.data)} — {V(r.situacao).lower()} "
              f"({r.checados} CPFs checked out of {r.previstos} scheduled)")
            for r in falhas.itertuples())
        st.markdown(md(L(
            f"**Buraco de cobertura:** {itens}. O reprocessamento fechou a "
            f"cobertura do mês, mas os lotes atrasaram quatro a seis dias — e "
            f"as regras de ciclo mensal desses lotes selecionaram com o mesmo "
            f"atraso.",
            f"**Coverage gap:** {itens}. The reprocessing closed the month's "
            f"coverage, but the batches were four to six days late — and the "
            f"monthly-cycle rules for those batches selected with the same "
            f"delay.")))


def _grade(p) -> list[float]:
    passos = int(round((p.maximo - p.minimo) / p.passo))
    salto = max(1, passos // 24)
    return [round(p.minimo + i * p.passo, 4) for i in range(0, passos + 1, salto)]


# =========================================================================== #
# Bloco na aba de Alertas: quem está por trás do movimento do dia
# =========================================================================== #

def bloco_alertas(con, dom, ref: date, filtros: Filtros) -> None:
    """
    O alerta da operação diz que algo saiu do padrão; este bloco diz QUEM.

    Sem ele a aba responde "o volume da R02 subiu" e a pessoa tem de trocar de
    aba, refazer o filtro e procurar o dia na fila para descobrir de quem se
    trata. São dois cliques que ninguém dá com pressa — e o alerta morre ali.
    Aqui os clientes vêm junto, com o prazo já contado, e o caminho para o
    dossiê escrito na tela.
    """
    st.markdown(CSS_PLD, unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(L(f"##### Quem entrou na fila em {_d(ref)}",
                  f"##### Who entered the queue on {_d(ref)}"))

    novos = con.execute(f"""
        SELECT cliente_id, codigo, tipo_cliente, faixa_risco, area, pep, uf,
               STRING_AGG(DISTINCT regra_id, ', ' ORDER BY regra_id) AS regras,
               STRING_AGG(DISTINCT situacao_4001, ' · ') AS enquadramento,
               SUM(valor_envolvido) AS valor, COUNT(*) AS alertas
          FROM fato
         WHERE data = DATE '{ref}'
           {''.join(' AND ' + c for c in (filtros.clausulas(dom) if filtros else []))}
         GROUP BY ALL
    """).fetchdf()

    fila = mod_fila.posicao(con, dom, ref, filtros)
    prio = fila.set_index("cliente_id")["prioridade"] if not fila.empty else None
    c_prio = L("Prioridade", "Priority")

    if novos.empty:
        st.caption(L("Nenhum cliente foi selecionado neste dia — o movimento do "
                     "painel veio de decisões, não de seleção nova.",
                     "No client was selected on this day — the dashboard's "
                     "movement came from decisions, not new selections."))
    else:
        novos["prioridade"] = (novos["cliente_id"].map(prio)
                               if prio is not None else float("nan"))
        novos = novos.sort_values("prioridade", ascending=False,
                                  na_position="last")
        st.caption(L(f"{len(novos)} cliente(s) selecionado(s) no dia. A "
                     f"prioridade considera todos os alertas abertos do "
                     f"cliente, não só os de hoje.",
                     f"{len(novos)} client(s) selected on the day. The "
                     f"priority considers all of the client's open alerts, "
                     f"not just today's."))
        enq = novos["enquadramento"].map(
            lambda x: " · ".join(V(p) for p in str(x).split(" · ")))
        st.dataframe(pd.DataFrame({
            c_prio: novos["prioridade"].fillna(0),
            L("Cliente", "Client"): novos["codigo"],
            L("Tipo", "Type"): novos["tipo_cliente"].map(V),
            L("Regras do dia", "Today's rules"): novos["regras"],
            L("Carta Circular 4.001", "Circular Letter 4,001"): enq,
            L("Valor envolvido", "Amount involved"): [_brl(v) for v in novos["valor"]],
            L("Analisar até", "Review by"): [
                _d(ref + pd.Timedelta(days=PRAZO_ANALISE_DIAS))] * len(novos),
            L("Risco", "Risk"): novos["faixa_risco"].map(V),
            L("UF", "State"): novos["uf"],
        }).head(12), hide_index=True, use_container_width=True,
            column_config={c_prio: st.column_config.ProgressColumn(
                c_prio, min_value=0, max_value=100, format="%.0f")})

    # o que vence antes vem depois: é a informação que manda no dia
    vencendo = (fila[fila["dias_para_prazo"] <= 3].sort_values("dias_para_prazo")
                if not fila.empty else fila)
    if not vencendo.empty:
        vencidos = int((vencendo["dias_para_prazo"] < 0).sum())
        st.markdown(L("##### Prazo estourando", "##### Deadlines about to blow"))
        st.caption(L(
            f"{len(vencendo)} cliente(s) com três dias ou menos até o fim do "
            f"prazo de análise" + (f", {vencidos} já vencido(s)" if vencidos
                                   else "") + " — Circular 3.978, art. 43, § 1º.",
            f"{len(vencendo)} client(s) with three days or less until the end "
            f"of the review deadline" + (f", {vencidos} already overdue"
                                         if vencidos else "")
            + " — Circular 3,978, art. 43, § 1."))
        st.dataframe(pd.DataFrame({
            L("Prazo", "Deadline"): [_prazo_txt(int(x))
                                     for x in vencendo["dias_para_prazo"]],
            L("Cliente", "Client"): vencendo["codigo"],
            L("Tipo", "Type"): vencendo["tipo_cliente"].map(V),
            c_prio: vencendo["prioridade"].round(0).astype(int),
            L("Regras abertas", "Open rules"): vencendo["regras"],
            L("Valor envolvido", "Amount involved"): [
                _brl(v) for v in vencendo["valor_envolvido"]],
        }).head(10), hide_index=True, use_container_width=True)

    st.markdown(nota(L(
        "O dossiê de cada um destes clientes — evidência em número, "
        "contrapartes, verificações e rascunho de parecer — está na aba "
        "<b>Clientes em atenção</b>: cole o código na busca, ou mude a "
        "<i>posição da fila</i> para esta data e clique na linha.",
        "The case file for each of these clients — evidence in numbers, "
        "counterparties, checks and a draft opinion — is in the "
        "<b>Clients to review</b> tab: paste the code into the search, or "
        "set the <i>queue position</i> to this date and click the row.")),
        unsafe_allow_html=True)


# =========================================================================== #
# Blocos extras
# =========================================================================== #

def bloco_visao_geral(con, dom, dmax: date, fim: date, filtros: Filtros) -> None:
    ref = pld_dados.referencia(fim, dmax)
    al = mod_fila.alertas_abertos(con, dom, ref, filtros)
    idade = mod_fila.idade_da_fila(al)
    st.caption(L(
        "Falso positivo, conversão, comunicações e tempo de análise só "
        "contam alertas com 45 dias ou mais em 31/08/2026. Em período "
        "recente esses cartões aparecem vazios de propósito — o alerta "
        "ainda não teve tempo de ser decidido.",
        "False positive, conversion, reports and review time only count "
        "alerts 45+ days old on Aug 31, 2026. In a recent period these cards "
        "show up empty on purpose — the alert hasn't had time to be "
        "decided."))
    st.markdown("---")
    st.markdown(L(f"##### A fila em {_d(ref)}, pela régua do prazo",
                  f"##### The queue on {_d(ref)}, by the deadline ruler"))
    cores = [SERIE[0], SERIE[0], STATUS["media"], JULGA_RUIM]
    fig = go.Figure(go.Bar(
        x=idade["alertas"], y=idade["faixa"].map(V), orientation="h",
        marker=dict(color=cores), text=idade["alertas"], textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x} "
                      + L("alertas abertos", "open alerts") + "<extra></extra>"))
    fig = g._base(fig, 220, "")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, max(idade["alertas"].max() * 1.25, 1)],
                     showticklabels=False)
    fig.update_traces(cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True, key="pld_idade")
    st.caption(L("Alertas abertos por idade desde a seleção. A barra vermelha é "
                 "descumprimento da Circular 3.978, art. 43, § 1º. Os clientes, "
                 "um a um, estão na aba Clientes em atenção.",
                 "Open alerts by age since selection. The red bar is "
                 "non-compliance with Circular 3,978, art. 43, § 1. The "
                 "clients, one by one, are in the Clients to review tab."))


def bloco_investigacao(con, dom, dmax: date, fim: date, filtros: Filtros) -> None:
    """
    O acompanhamento do que está em investigação.

    A fila não cresce porque chegou muito alerta nem porque a equipe rendeu
    pouco: cresce quando uma coisa passa a outra, semana após semana. Por isso
    entradas e conclusões aparecem juntas, e não em dois cartões distantes.
    """
    ref = pld_dados.referencia(fim, dmax)
    onde = "".join(" AND " + c for c in (filtros.clausulas(dom) if filtros else []))
    st.markdown("---")
    st.markdown(L(f"##### Casos em investigação em {_d(ref)}",
                  f"##### Cases under review on {_d(ref)}"))

    fluxo = con.execute(f"""
        WITH entradas AS (
          SELECT date_trunc('week', data) AS semana, COUNT(*) AS entraram
            FROM fato
           WHERE data BETWEEN DATE '{ref}' - 83 AND DATE '{ref}' {onde}
           GROUP BY 1),
        saidas AS (
          SELECT date_trunc('week', data_decisao) AS semana, COUNT(*) AS concluidos
            FROM fato
           WHERE data_decisao BETWEEN DATE '{ref}' - 83 AND DATE '{ref}' {onde}
           GROUP BY 1)
        SELECT COALESCE(e.semana, s.semana) AS semana,
               COALESCE(entraram, 0) AS entraram,
               COALESCE(concluidos, 0) AS concluidos
          FROM entradas e FULL OUTER JOIN saidas s USING (semana)
         ORDER BY 1
    """).fetchdf()

    # A semana corrente entra pela metade e desenharia um tombo que não
    # aconteceu: só semanas fechadas ficam no gráfico.
    if not fluxo.empty:
        fluxo = fluxo[fluxo["semana"].dt.date <= ref - timedelta(days=6)]

    al = mod_fila.alertas_abertos(con, dom, ref, filtros)
    esq, dir_ = st.columns([3, 2], gap="large")
    fmt_curto = "%b %d" if i18n.en() else "%d/%m"

    with esq:
        fig = go.Figure()
        for col, nome, cor in (("entraram", L("Alertas selecionados",
                                              "Alerts selected"), SERIE[0]),
                               ("concluidos", L("Análises concluídas",
                                                "Reviews completed"), SERIE[1])):
            fig.add_trace(go.Scatter(
                x=fluxo["semana"], y=fluxo[col], name=nome, mode="lines+markers",
                line=dict(color=cor, width=2), marker=dict(size=5),
                hovertemplate=L("semana de", "week of")
                              + " %{x|" + fmt_curto + "}<br><b>%{y}</b>"
                              f"<extra>{nome}</extra>"))
        fig = g._base(fig, 260, L("Entradas e conclusões por semana",
                                  "Inflow and completions by week"))
        fig.update_layout(showlegend=True, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True, key="pld_fluxo")
        if len(fluxo) > 1:
            saldo = int((fluxo["entraram"] - fluxo["concluidos"]).sum())
            atrasadas = int((fluxo["entraram"] > fluxo["concluidos"]).sum())
            if saldo > 0:
                lado = L(f"entraram {saldo} alertas a mais do que saíram",
                         f"{saldo} more alerts came in than went out")
            elif saldo < 0:
                lado = L(f"saíram {-saldo} alertas a mais do que entraram",
                         f"{-saldo} more alerts went out than came in")
            else:
                lado = L("entrou e saiu a mesma quantidade",
                         "the same number came in and went out")
            st.caption(L(
                f"Nas últimas {len(fluxo)} semanas fechadas {lado}, com "
                f"{atrasadas} semana(s) em que a seleção passou a capacidade "
                f"de análise. É isso que empurra a fila para o prazo — não o "
                f"volume de um dia.",
                f"Over the last {len(fluxo)} full weeks {lado}, with "
                f"{atrasadas} week(s) in which selection exceeded review "
                f"capacity. That's what pushes the queue toward the deadline — "
                f"not one day's volume."))

    with dir_:
        if al.empty:
            st.caption(L("Nenhum alerta aberto nesta data.",
                         "No open alert on this date."))
        else:
            por_regra = (al.groupby("regra_id").size().sort_values()
                         .rename("abertos").reset_index())
            fig = go.Figure(go.Bar(
                x=por_regra["abertos"], y=por_regra["regra_id"], orientation="h",
                marker=dict(color=SERIE[0]), text=por_regra["abertos"],
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>%{x} "
                              + L("alertas abertos", "open alerts")
                              + "<extra></extra>"))
            fig = g._base(fig, 260, L("Em análise, por regra",
                                      "Under review, by rule"))
            fig.update_xaxes(showticklabels=False,
                             range=[0, por_regra["abertos"].max() * 1.25])
            fig.update_traces(cliponaxis=False)
            st.plotly_chart(fig, use_container_width=True, key="pld_abertos_regra")

    if not al.empty:
        parados = (al.sort_values("idade", ascending=False)
                   .drop_duplicates("cliente_id").head(6))
        st.caption(L("Os que estão há mais tempo esperando:",
                     "The ones waiting the longest:"))
        st.dataframe(pd.DataFrame({
            L("Cliente", "Client"): parados["codigo"],
            L("Tipo", "Type"): parados["tipo_cliente"].map(V),
            L("Regra", "Rule"): parados["regra_id"],
            L("Selecionado em", "Selected on"): [_d(x) for x in parados["data"]],
            L("Dias na fila", "Days in queue"): parados["idade"],
            L("Prazo", "Deadline"): [_prazo_txt(int(x))
                                     for x in parados["dias_para_prazo"]],
        }), hide_index=True, use_container_width=True)


def bloco_causa_raiz(con, dom) -> None:
    """
    A causa raiz do VOLUME de alertas, que é outra pergunta.

    A cascata das abas decompõe a métrica por dimensão — por regra, por região.
    Ela não responde a pergunta que vem primeiro em monitoramento: o volume
    subiu porque mais gente passou a se comportar assim, ou porque a régua
    passou a pegar mais? São ações opostas: uma é investigar, a outra é
    recalibrar.

    Aqui o número de alertas é escrito como  avaliados × taxa de seleção  e a
    variação abre nos mesmos três termos das outras abas (efeito população,
    efeito seleção e interação), somando exatamente a diferença. Embaixo, os
    sinais brutos do mês — quantos Pix, quanto valor, quantos pagadores
    distintos — para conferir a conclusão contra o comportamento de verdade.
    """
    perfil = pld_dados.indicadores()
    comp = pld_dados.comportamento()
    meses = sorted(perfil["mes"].unique())
    st.markdown("---")
    st.markdown(L("##### Por que o volume de alertas mudou",
                  "##### Why the alert volume changed"))

    c1, c2, c3 = st.columns([1.6, 1, 1])
    with c1:
        rid = st.selectbox(L("Regra", "Rule"), sorted(perfil["regra_id"].unique()),
                           format_func=lambda k: REGRAS[k].local.rotulo,
                           key="cr_pld_regra")
    with c2:
        m_ant = st.selectbox(L("Mês base", "Base month"), meses,
                             index=max(0, len(meses) - 2),
                             format_func=_mes_br, key="cr_pld_a")
    with c3:
        m_atual = st.selectbox(L("Mês atual", "Current month"), meses,
                               index=len(meses) - 1,
                               format_func=_mes_br, key="cr_pld_b")

    r = REGRAS[rid].local
    d = perfil[perfil["regra_id"] == rid].set_index("mes")
    if m_ant not in d.index or m_atual not in d.index:
        st.info(L("Sem avaliação da regra em um dos meses escolhidos.",
                  "No evaluation of the rule in one of the chosen months."))
        return
    a_, b_ = d.loc[m_ant], d.loc[m_atual]

    taxa_a = a_["acima_do_corte"] / a_["avaliados"] if a_["avaliados"] else 0.0
    taxa_b = b_["acima_do_corte"] / b_["avaliados"] if b_["avaliados"] else 0.0
    d_aval = b_["avaliados"] - a_["avaliados"]
    d_taxa = taxa_b - taxa_a
    ef_pop = d_aval * taxa_a
    ef_sel = a_["avaliados"] * d_taxa
    ef_int = d_aval * d_taxa
    delta = b_["acima_do_corte"] - a_["acima_do_corte"]

    m_alertas = dom.metrica("alertas")
    cascata = pd.DataFrame([
        {"rotulo": _mes_br(m_ant), "valor": float(a_["acima_do_corte"]),
         "tipo": "total"},
        {"rotulo": L("Efeito população", "Population effect"),
         "valor": float(ef_pop), "tipo": "delta"},
        {"rotulo": L("Efeito seleção", "Selection effect"),
         "valor": float(ef_sel), "tipo": "delta"},
        {"rotulo": L("Interação", "Interaction"), "valor": float(ef_int),
         "tipo": "delta"},
        {"rotulo": _mes_br(m_atual), "valor": float(b_["acima_do_corte"]),
         "tipo": "total"},
    ])
    esq, dir_ = st.columns([3, 2], gap="large")
    with esq:
        fig = g.cascata(cascata, m_alertas,
                        titulo=L(f"{r.rotulo}: de onde veio a variação de alertas",
                                 f"{r.rotulo}: where the change in alerts "
                                 f"came from"))
        # "2026-07" seria lido como data pelo Plotly e o eixo viraria uma linha
        # do tempo com os rótulos dos efeitos no lugar errado.
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, use_container_width=True, key=f"cr_pld_casc_{rid}")
    with dir_:
        st.markdown(L("###### A conta, em português",
                      "###### The math, in plain words"))
        ma, mb = _mes_br(m_ant), _mes_br(m_atual)
        conta_a = (f"{int(a_['avaliados'])} × {pct(taxa_a, 0, sinal=False)} = "
                   f"{int(a_['acima_do_corte'])}")
        conta_b = (f"{int(b_['avaliados'])} × {pct(taxa_b, 0, sinal=False)} = "
                   f"{int(b_['acima_do_corte'])}")
        st.markdown(md(L(
            f"- Alertas = **avaliados × taxa de seleção**. Em {ma}: "
            f"{conta_a}. Em {mb}: {conta_b}.",
            f"- Alerts = **evaluated × selection rate**. In {ma}: "
            f"{conta_a}. In {mb}: {conta_b}.")))
        st.markdown(md(L(
            f"- **Efeito população** ({ef_pop:+.0f}): mais (ou menos) clientes "
            f"passaram nas condições fixas da regra.\n"
            f"- **Efeito seleção** ({ef_sel:+.0f}): entre os avaliados, a "
            f"parcela acima do corte mudou — é aqui que aparece mudança de "
            f"comportamento **ou** de parâmetro.\n"
            f"- **Interação** ({ef_int:+.0f}): os dois ao mesmo tempo.",
            f"- **Population effect** ({ef_pop:+.0f}): more (or fewer) clients "
            f"passed the rule's fixed conditions.\n"
            f"- **Selection effect** ({ef_sel:+.0f}): among those evaluated, "
            f"the share above the threshold changed — this is where a change "
            f"in behavior **or** in the parameter shows up.\n"
            f"- **Interaction** ({ef_int:+.0f}): both at once.")))
        if a_["corte"] != b_["corte"]:
            de, para = (r.parametro.formatar(a_['corte']),
                        r.parametro.formatar(b_['corte']))
            st.markdown(nota(L(
                f"O corte mudou de {de} para {para} entre os dois meses: o "
                f"efeito seleção aqui é <b>decisão de política</b>, não "
                f"comportamento do cliente.",
                f"The threshold changed from {de} to {para} between the two "
                f"months: the selection effect here is a <b>policy "
                f"decision</b>, not client behavior.")),
                unsafe_allow_html=True)
        st.caption(L(f"Soma dos efeitos: {ef_pop + ef_sel + ef_int:+.0f} · "
                     f"variação total: {delta:+.0f}",
                     f"Sum of effects: {ef_pop + ef_sel + ef_int:+.0f} · "
                     f"total change: {delta:+.0f}"))

    # --- sinais brutos ---------------------------------------------------- #
    st.markdown(L("###### Os sinais brutos do mês, antes de virar alerta",
                  "###### The month's raw signals, before becoming alerts"))
    ca = comp[comp["mes"] == m_ant].set_index("indicador")
    cb = comp[comp["mes"] == m_atual].set_index("indicador")

    def _fmt(v, unidade):
        if unidade == "moeda":
            return _brl(v)
        if unidade == "media":
            return i18n.num(v, 2)
        return i18n.num(v, 0)

    linhas = []
    for ind in cb.index:
        if ind not in ca.index:
            continue
        va, vb = float(ca.loc[ind, "valor"]), float(cb.loc[ind, "valor"])
        linhas.append({
            L("Sinal", "Signal"): V(ind),
            _mes_br(m_ant): _fmt(va, ca.loc[ind, "unidade"]),
            _mes_br(m_atual): _fmt(vb, cb.loc[ind, "unidade"]),
            L("Variação", "Change"): pct((vb - va) / va) if va else "—",
            "ordem": abs((vb - va) / va) if va else 0,
        })
    sinais = pd.DataFrame(linhas).sort_values("ordem", ascending=False)
    st.dataframe(sinais.drop(columns="ordem"), hide_index=True,
                 use_container_width=True)
    st.caption(L(
        "Contadores da população inteira, sem filtro de alerta e sem os "
        "filtros da barra lateral: filtrar por quem já alertou responderia a "
        "pergunta com a própria resposta. Se o efeito seleção subiu e os "
        "sinais brutos acompanham, o movimento é dos clientes; se os sinais "
        "estão parados, a régua é que mudou.",
        "Counters for the whole population, with no alert filter and without "
        "the sidebar filters: filtering by who already alerted would answer "
        "the question with its own answer. If the selection effect rose and "
        "the raw signals follow, the movement is the clients'; if the signals "
        "are flat, it's the ruler that changed."))


def bloco_indicadores(con, dom) -> None:
    """
    O indicador antes do alerta.

    Contar alerta mede a régua e o comportamento ao mesmo tempo. Quando o
    volume sobe, a primeira pergunta é qual dos dois se mexeu — e ela só tem
    resposta olhando a distribuição do indicador na população avaliada, com o
    corte desenhado por cima.
    """
    perfil = pld_dados.indicadores()
    st.markdown("---")
    st.markdown(L("##### O indicador de cada regra, antes do corte",
                  "##### Each rule's indicator, before the threshold"))
    c1, c2 = st.columns([1.4, 3])
    with c1:
        rid = st.selectbox(L("Regra", "Rule"), sorted(perfil["regra_id"].unique()),
                           format_func=lambda k: REGRAS[k].local.rotulo,
                           key="ind_regra")
    r = REGRAS[rid].local
    d = perfil[perfil["regra_id"] == rid].sort_values("mes")
    meses_rot = [_mes_br(m) for m in d["mes"]]
    with c2:
        st.caption(L(
            f"**{r.indicador}.** A população avaliada são os clientes "
            f"que passaram nas condições fixas da regra ({'; '.join(r.condicoes)}), "
            f"no lote do ciclo quando a regra é mensal. Este bloco não "
            f"responde aos filtros da barra lateral.",
            f"**{r.indicador}.** The evaluated population is the clients who "
            f"passed the rule's fixed conditions ({'; '.join(r.condicoes)}), "
            f"in the cycle's batch when the rule is monthly. This block doesn't "
            f"respond to the sidebar filters."))

    e, dr = st.columns(2, gap="medium")
    with e:
        fig = go.Figure()
        for col, nome, cor, largura in (("p95", "p95", SERIE[2], 1.6),
                                        ("p75", "p75", SERIE[1], 1.6),
                                        ("p50", L("mediana", "median"),
                                         SERIE[0], 2.2)):
            fig.add_trace(go.Scatter(
                x=meses_rot, y=d[col], name=nome, mode="lines+markers",
                line=dict(color=cor, width=largura), marker=dict(size=4),
                hovertemplate="%{x}<br><b>%{y:.2f}</b>" f"<extra>{nome}</extra>"))
        fig.add_trace(go.Scatter(
            x=meses_rot, y=d["corte"], name=L("corte vigente", "current threshold"),
            mode="lines",
            line=dict(color=STATUS["alta"], width=2, dash="dash"),
            line_shape="hv",
            hovertemplate="%{x}<br><b>" + L("corte", "threshold")
                          + " %{y:.2f}</b><extra></extra>"))
        fig = g._base(fig, 280, L("Distribuição do indicador e o corte",
                                  "Indicator distribution and the threshold"))
        fig.update_layout(showlegend=True, hovermode="x unified")
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, use_container_width=True, key=f"ind_dist_{rid}")
    with dr:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=meses_rot, y=d["avaliados"],
                             name=L("avaliados", "evaluated"),
                             marker=dict(color=GRADE),
                             hovertemplate="%{x}<br><b>%{y}</b> "
                                           + L("avaliados", "evaluated")
                                           + "<extra></extra>"))
        fig.add_trace(go.Bar(x=meses_rot, y=d["acima_do_corte"],
                             name=L("acima do corte", "above threshold"),
                             marker=dict(color=SERIE[0]),
                             hovertemplate="%{x}<br><b>%{y}</b> "
                                           + L("acima do corte", "above threshold")
                                           + "<extra></extra>"))
        fig = g._base(fig, 280, L("Avaliados e selecionados",
                                  "Evaluated and selected"))
        fig.update_layout(barmode="overlay", showlegend=True)
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, use_container_width=True, key=f"ind_vol_{rid}")

    st.markdown(md(_leitura_indicador(d, r)))


def _leitura_indicador(d: pd.DataFrame, r) -> str:
    """Uma frase dizendo quem se mexeu: o cliente, o corte ou a população."""
    if len(d) < 6:
        return L("Histórico curto demais para comparar trimestres.",
                 "History too short to compare quarters.")
    ini, fim_ = d.head(3), d.tail(3)

    def var(col):
        a, b = ini[col].mean(), fim_[col].mean()
        return (b - a) / a if a else float("nan")

    p95, aval = var("p95"), var("avaliados")
    corte_mudou = ini["corte"].iloc[-1] != fim_["corte"].iloc[-1]
    partes = []
    if corte_mudou:
        de = r.parametro.formatar(ini['corte'].iloc[-1])
        para = r.parametro.formatar(fim_['corte'].iloc[-1])
        partes.append(L(
            f"O corte mudou de {de} para {para} no período — parte da "
            f"variação de volume é decisão de política, não comportamento.",
            f"The threshold changed from {de} to {para} in the period — part "
            f"of the volume change is a policy decision, not behavior."))
    if abs(p95) >= 0.15:
        q = pct(abs(p95), 0, sinal=False)
        partes.append(L(
            f"O p95 do indicador {'subiu' if p95 > 0 else 'caiu'} {q} do "
            f"primeiro para o último trimestre: a ponta da distribuição se "
            f"moveu de verdade.",
            f"The indicator's p95 {'rose' if p95 > 0 else 'fell'} {q} from "
            f"the first to the last quarter: the tail of the distribution "
            f"really moved."))
    else:
        partes.append(L("O p95 do indicador está estável entre o primeiro e o "
                        "último trimestre — a régua mexeu mais que o "
                        "comportamento.",
                        "The indicator's p95 is stable between the first and "
                        "the last quarter — the ruler moved more than the "
                        "behavior."))
    if abs(aval) >= 0.15:
        q = pct(abs(aval), 0, sinal=False)
        partes.append(L(
            f"A população avaliada {'cresceu' if aval > 0 else 'encolheu'} "
            f"{q}, o que move o volume mesmo com taxa de seleção parada.",
            f"The evaluated population {'grew' if aval > 0 else 'shrank'} "
            f"{q}, which moves the volume even with a flat selection rate."))
    return " ".join(partes)


MAPA = [
    ("Monitoramento e seleção", "Circular 3.978, arts. 38 e 39",
     "Dez regras diárias e de ciclo mensal (aba Regras e calibração)"),
    ("Situações de suspeita", "Carta Circular 4.001, art. 1º",
     "Cada regra aponta para o inciso e a alínea que traduz"),
    ("Avaliação interna de risco", "Circular 3.978, art. 10",
     "Cortes com data de vigência; calibração com custo em comunicações"),
    ("Classificação de risco e PEP", "Circular 3.978, arts. 20 e 27",
     "Fatores da prioridade; regra R09"),
    ("Análise em até 45 dias", "Circular 3.978, art. 43, § 1º",
     "Prazo por cliente, idade da fila, métrica e limite no painel"),
    ("Dossiê da análise", "Circular 3.978, art. 43, § 2º",
     "Rascunho de parecer e justificativa obrigatória na decisão"),
    ("Comunicação até D+1 útil", "Circular 3.978, art. 48, § 2º",
     "Prazo calculado com calendário de dias úteis; métrica e limite"),
    ("Sigilo da comunicação", "Lei 9.613/1998, art. 11",
     "Lembrado no dossiê e no registro da decisão"),
]

MAPA_EN = [
    ("Monitoring and selection", "Circular 3,978, arts. 38 and 39",
     "Ten daily and monthly-cycle rules (Rules & calibration tab)"),
    ("Suspicious situations", "Circular Letter 4,001, art. 1",
     "Each rule points to the item and sub-item it translates"),
    ("Internal risk assessment", "Circular 3,978, art. 10",
     "Thresholds with effective dates; calibration with its cost in reports"),
    ("Risk classification and PEP", "Circular 3,978, arts. 20 and 27",
     "Priority factors; rule R09"),
    ("Review within 45 days", "Circular 3,978, art. 43, § 1",
     "Deadline per client, queue age, metric and limit on the dashboard"),
    ("Review case file", "Circular 3,978, art. 43, § 2",
     "Draft opinion and mandatory justification for the decision"),
    ("Report by next business day", "Circular 3,978, art. 48, § 2",
     "Deadline computed with a business-day calendar; metric and limit"),
    ("Confidentiality of the report", "Law 9,613/1998, art. 11",
     "Reminded in the case file and in the decision record"),
]


def sobre_pld() -> None:
    st.markdown(L("#### Mapa regulatório: onde cada exigência aparece",
                  "#### Regulatory map: where each requirement shows up"))
    st.dataframe(pd.DataFrame(L(MAPA, MAPA_EN),
                              columns=[L("Exigência", "Requirement"),
                                       L("Norma", "Regulation"),
                                       L("Onde está no painel",
                                         "Where it is on the dashboard")]),
                 hide_index=True, use_container_width=True)
    st.caption(L("Resumos para uso no painel. A referência é sempre o normativo "
                 "publicado pelo Banco Central.",
                 "Summaries for use in the dashboard. The reference is always "
                 "the regulation published by the Central Bank of Brazil."))

    st.markdown(L("#### Automação de baixo custo da fila",
                  "#### Low-cost automation of the queue"))
    st.markdown(L(
        "A fila deste painel também existe como planilha, sem squad de "
        "engenharia: `automacoes/apps_script/fila_pld.gs` é um Google Apps "
        "Script que roda todo dia útil às 8h, lê os alertas exportados pelo "
        "job, calcula prazo de análise e prazo de comunicação em dia útil, "
        "ordena por prioridade, protege as colunas de decisão contra edição "
        "fora do fluxo e manda o resumo do dia num canal do Slack — com os "
        "vencidos em primeiro lugar. O passo a passo está no README.",
        "This dashboard's queue also exists as a spreadsheet, with no "
        "engineering squad: `automacoes/apps_script/fila_pld.gs` is a Google "
        "Apps Script that runs every business day at 8am, reads the alerts "
        "exported by the job, computes the review deadline and the reporting "
        "deadline in business days, sorts by priority, protects the decision "
        "columns against out-of-flow edits and posts the day's summary in a "
        "Slack channel — overdue cases first. The step-by-step is in the "
        "README."))
