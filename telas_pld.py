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
from vulcano.dados import Filtros, agregar
from vulcano.estilo import html_moeda, md, nota, rosto
from vulcano.formatacao import numero, pct
from vulcano.graficos import (EIXO, GRADE, JULGA_BOM, JULGA_RUIM, SERIE,
                              STATUS, SURFACE, TINTA, TINTA_2, TINTA_MUDA)
from vulcano.pld import dados as pld_dados
from vulcano.pld import fila as mod_fila
from vulcano.pld import parecer as mod_parecer
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
    return "R$ " + f"{v:,.0f}".replace(",", ".")


MESES_BR = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]


def _mes_br(mes: str) -> str:
    ano, m = mes.split("-")
    return f"{MESES_BR[int(m) - 1]}/{ano}"


def _prazo_txt(dias: int) -> str:
    if dias < 0:
        return f"vencido há {-dias} d"
    if dias == 0:
        return "vence hoje"
    return f"{dias} dias"


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
                separou quem precisa de atenção</span></div>
            <div class="papel">Cada cliente abaixo se enquadra em ao menos uma
              situação da Carta Circular 4.001 e está na fila de análise. A
              ordem é por prioridade; o prazo de 45 dias anda em coluna
              separada. Os filtros da barra lateral valem aqui.</div>
          </div>
        </div>""", unsafe_allow_html=True)
    st.write("")

    c1, c2, c3 = st.columns([1.2, 1.6, 1.4])
    with c1:
        # A chave carrega a data padrão: mudar o período na barra lateral
        # reposiciona a fila, em vez de o widget guardar a data antiga.
        ref = st.date_input("Posição da fila em", value=padrao,
                            min_value=date(2025, 9, 1), max_value=base,
                            format="DD/MM/YYYY", key=f"cl_ref_{padrao}")
        ref = ref if isinstance(ref, date) else padrao
    with c2:
        busca = st.text_input("Buscar cliente pelo código",
                              placeholder="T-01160, L-41167, E-0132",
                              key="cl_busca")
    with c3:
        mostrar = st.selectbox(
            "Mostrar", ["Todos", "Prioridade crítica e alta",
                        "Vencidos ou vencendo em 7 dias",
                        "Com mais de uma regra aberta"], key="cl_mostrar")

    fl = mod_fila.posicao(con, dom, ref, filtros)
    res = mod_fila.resumir(fl)

    cols = st.columns(5, gap="small")
    cartoes = [
        ("Clientes na fila", f"{res.clientes}", f"{res.alertas} alertas abertos",
         TINTA),
        ("Prioridade crítica", f"{res.criticos}", "70 pontos ou mais",
         STATUS["alta"] if res.criticos else TINTA),
        ("Vencem em até 7 dias", f"{res.vencem_7d}", "art. 43, § 1º",
         STATUS["media"] if res.vencem_7d else TINTA),
        ("Fora do prazo", f"{res.vencidos}", "mais de 45 dias sem decisão",
         JULGA_RUIM if res.vencidos else JULGA_BOM),
        ("Valor envolvido na fila", numero(res.valor, dom.metrica("valor_envolvido")),
         "soma das janelas dos alertas", TINTA),
    ]
    for col, (r, v, d, cor) in zip(cols, cartoes):
        with col:
            st.markdown(_kpi(r, v, d, cor), unsafe_allow_html=True)
    st.write("")

    if fl.empty:
        st.info(f"A fila está vazia em {ref.strftime('%d/%m/%Y')} com o filtro "
                f"{filtros.resumo(dom)}.")
        return

    vista = fl.copy()
    if mostrar == "Prioridade crítica e alta":
        vista = vista[vista["faixa"].isin(["Crítica", "Alta"])]
    elif mostrar == "Vencidos ou vencendo em 7 dias":
        vista = vista[vista["dias_para_prazo"] <= 7].sort_values(
            "dias_para_prazo")
    elif mostrar == "Com mais de uma regra aberta":
        vista = vista[vista["regras"].str.contains(",")]
    vista = vista.reset_index(drop=True)

    tabela = pd.DataFrame({
        "Prioridade": vista["prioridade"],
        "Faixa": vista["faixa"],
        "Cliente": vista["codigo"],
        "Tipo": vista["tipo_cliente"],
        "Regras abertas": vista["regras"],
        "Carta Circular 4.001": vista["enquadramento"],
        "Valor envolvido": [_brl(v) for v in vista["valor_envolvido"]],
        "Prazo": [_prazo_txt(int(x)) for x in vista["dias_para_prazo"]],
        "Risco": vista["faixa_risco"],
        "Já comunicado": ["sim" if x else "" for x in vista["reincidente"]],
        "UF": vista["uf"],
    })
    st.caption(f"{len(vista)} de {len(fl)} clientes · clique numa linha para "
               f"abrir o dossiê.")
    evento = st.dataframe(
        tabela, hide_index=True, use_container_width=True,
        height=min(420, 36 * len(tabela) + 40),
        on_select="rerun", selection_mode="single-row", key="cl_tabela",
        column_config={
            "Prioridade": st.column_config.ProgressColumn(
                "Prioridade", min_value=0, max_value=100, format="%.0f",
                help="Soma de pontos com fatores nomeados — a conta aparece "
                     "no dossiê."),
            "Prazo": st.column_config.TextColumn(
                "Prazo", help="Dias até o fim do prazo de análise do alerta "
                              "mais antigo aberto (45 dias corridos)."),
        })

    codigo = None
    if busca.strip():
        cid = mod_parecer.cliente_por_codigo(con, busca)
        if cid is None:
            st.warning(f"Não encontrei {busca.strip().upper()} entre os "
                       f"clientes com alerta.")
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
        st.info("Esse cliente não tem alerta até a data escolhida.")
        return

    st.markdown(f"### Dossiê · {d.codigo}")
    st.caption("Rascunho montado pela Ravena a partir dos alertas, das "
               "movimentações e das contrapartes. Dado simulado; documento "
               "mascarado.")
    st.markdown('<div class="pld-cab">' + "".join(
        f'<div><div class="r">{k}</div><div class="v">{v}</div></div>'
        for k, v in d.cabecalho.items()) + "</div>", unsafe_allow_html=True)

    esq, dir_ = st.columns([3, 2], gap="large")
    with esq:
        st.markdown("##### O que disparou")
        if d.abertos.empty:
            st.caption("Nenhum alerta aberto nesta data.")
        for a in d.abertos.itertuples():
            r = REGRAS[a.regra_id]
            limite = a.data + pd.Timedelta(days=PRAZO_ANALISE_DIAS)
            st.markdown(
                f"""<div class="vulc-alerta" style="border-left-color:{SERIE[0]}">
                  <div class="cab" style="color:{SERIE[0]}">{r.rotulo} ·
                    selecionado em {a.data.strftime('%d/%m/%Y')}</div>
                  <div class="txt">{html_moeda(a.evidencia)}</div>
                  <div class="aca">Enquadramento: {citar(list(r.enquadramento))}
                    · base: {citar(list(r.base_3978))} · análise até
                    {limite.strftime('%d/%m/%Y')}</div>
                </div>""", unsafe_allow_html=True)

    with dir_:
        st.markdown(f"##### Por que a prioridade é {d.prioridade:.0f}")
        topo = max([p for _, p in d.fatores] + [1.0])
        st.markdown("".join(
            f'<div class="pld-fator"><div>{nome}'
            f'<div class="pld-barra" style="width:{p / topo * 100:.0f}%"></div>'
            f'</div><div class="pts">+{p:.0f}</div></div>'
            for nome, p in d.fatores) + (
            f'<div class="pld-fator" style="border-top:1px solid {GRADE};'
            f'padding-top:6px"><div><b>Prioridade</b> (teto de 100)</div>'
            f'<div class="pts">{d.prioridade:.0f}</div></div>'),
            unsafe_allow_html=True)
        if d.prazo_final:
            vencido = d.dias_para_prazo < 0
            cor_fundo = "#fdecea" if vencido else "#eef3fa"
            cor_txt = JULGA_RUIM if vencido else TINTA
            st.markdown(
                f"""<div class="pld-prazo" style="background:{cor_fundo};
                    color:{cor_txt}">
                  <b>Análise até {d.prazo_final.strftime('%d/%m/%Y')}</b> —
                  {'vencida há ' + str(-d.dias_para_prazo) + ' dia(s)'
                   if vencido else 'faltam ' + str(d.dias_para_prazo) + ' dia(s)'}
                  (Circular 3.978, art. 43, § 1º). Se decidir comunicar hoje, o
                  envio vai até {proximo_dia_util(ref).strftime('%d/%m/%Y')}
                  (art. 48, § 2º).
                </div>""", unsafe_allow_html=True)

    # --- movimentação ---------------------------------------------------- #
    if not d.serie.empty:
        st.markdown("##### Movimentação")
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
                x=list(x.index), y=x.values, name=nome, mode="lines",
                line=dict(color=SERIE[i], width=1.6),
                customdata=[_brl(v) for v in x.values],
                hovertemplate="%{x|%d/%m/%Y}<br><b>%{customdata}</b>"
                              f"<extra>{nome}</extra>"))
        for a in d.abertos.itertuples():
            fig.add_vline(x=a.data.isoformat(),
                          line=dict(color=STATUS["alta"], width=1, dash="dot"))
        fig = g._base(fig, 280, "")
        fig.update_layout(showlegend=len(principais) > 1, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True,
                        key=f"pld_serie_{cliente_id}")
        st.caption("Linhas pontilhadas: datas de seleção dos alertas abertos. "
                   "Valores diários.")
        if cliente_id[0] == "L":
            noite = d.serie[d.serie["serie"] == "Transações entre 23h e 5h"]
            total = d.serie[d.serie["serie"] == "Transações"]
            if not total.empty:
                ult = ref - pd.Timedelta(days=30)
                n_noite = noite[noite["data"] > ult]["valor"].sum()
                n_total = total[total["data"] > ult]["valor"].sum()
                if n_total:
                    st.caption(f"Nos últimos 30 dias: {n_noite:.0f} de "
                               f"{n_total:.0f} transações entre 23h e 5h "
                               f"({n_noite / n_total * 100:.0f}%).")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("##### Contrapartes")
        if d.contrapartes.empty:
            st.caption("Sem contraparte registrada.")
        else:
            st.dataframe(pd.DataFrame({
                "Sentido": d.contrapartes["sentido"],
                "Contraparte": d.contrapartes["contraparte"],
                "Operações": d.contrapartes["qtd"].astype(int),
                "Valor": [_brl(v) for v in d.contrapartes["valor"]],
                "Em outros clientes com alerta": [
                    f"{int(x)}" if x > 0 else "" for x in
                    d.contrapartes["compartilhada"]],
            }).head(12), hide_index=True, use_container_width=True)
            st.caption("Contraparte que aparece em outros clientes com alerta é "
                       "o fio que liga contas de passagem entre si.")
    with c2:
        st.markdown("##### Histórico de análise")
        if d.historico.empty:
            st.caption("Primeira seleção deste cliente.")
        else:
            h = d.historico.sort_values("data", ascending=False)
            st.dataframe(pd.DataFrame({
                "Seleção": [x.strftime("%d/%m/%Y") for x in h["data"]],
                "Regra": h["regra_id"],
                "Decisão": h["decisao"],
                "Decidido em": [x.strftime("%d/%m/%Y") if pd.notna(x) else ""
                                for x in h["data_decisao"]],
            }), hide_index=True, use_container_width=True,
                height=min(260, 36 * len(h) + 40))

    with st.expander("Rascunho de parecer da Ravena", expanded=True):
        st.markdown(md(d.texto))
        st.download_button("Baixar o dossiê (.md)", d.texto.encode("utf-8"),
                           file_name=f"dossie_{d.codigo}.md",
                           mime="text/markdown", key=f"dl_{cliente_id}")

    # --- decisão --------------------------------------------------------- #
    st.markdown("##### Decisão da analista")
    registro = st.session_state.setdefault("pld_decisoes", {})
    anterior = registro.get(cliente_id)
    if anterior:
        st.success(f"Registrado nesta sessão: **{anterior['decisao']}** em "
                   f"{anterior['em']}. {anterior['nota']}")
    with st.form(f"form_{cliente_id}", clear_on_submit=False):
        decisao = st.radio("Decisão", ["Descartar", "Monitoramento reforçado",
                                       "Comunicar ao Coaf"], horizontal=True)
        justificativa = st.text_area(
            "Justificativa (vai para o dossiê — art. 43, § 2º)",
            placeholder="Ex.: origem comprovada por nota fiscal de venda do "
                        "veículo; movimentação compatível após atualização de "
                        "renda.")
        enviar = st.form_submit_button("Registrar decisão", type="primary")
    if enviar:
        if len(justificativa.strip()) < 15:
            st.error("A justificativa é obrigatória, inclusive no descarte: "
                     "sem ela o dossiê não se sustenta numa auditoria.")
        else:
            nota_txt = ""
            if decisao == "Comunicar ao Coaf":
                nota_txt = (f"Envio ao Coaf até "
                            f"{proximo_dia_util(ref).strftime('%d/%m/%Y')}, "
                            f"sem dar ciência ao cliente (Lei 9.613/1998, "
                            f"art. 11).")
            registro[cliente_id] = {"decisao": decisao,
                                    "em": ref.strftime("%d/%m/%Y"),
                                    "nota": nota_txt,
                                    "justificativa": justificativa.strip()}
            st.rerun()
    st.caption("Na demonstração a decisão fica só nesta sessão do navegador. "
               "Na operação, ela iria para a planilha da fila pelo Apps Script "
               "descrito em Sobre os dados — sem depender de squad de "
               "engenharia.")


# =========================================================================== #
# Aba: Regras e calibração
# =========================================================================== #

def aba_regras(con, dom, inicio: date, fim: date, filtros: Filtros) -> None:
    st.markdown(CSS_PLD, unsafe_allow_html=True)
    st.markdown("##### As dez regras e onde cada uma se apoia")
    st.caption("Cada regra traduz uma situação da Carta Circular 4.001 em um "
               "indicador, um corte e condições fixas. Um parâmetro só por "
               "regra — é o que torna a calibração discutível com a área.")
    st.dataframe(pd.DataFrame([{
        "ID": r.id, "Regra": r.nome, "Tipo": r.tipo,
        "Frequência": r.frequencia, "Indicador": r.indicador,
        "Corte vigente": r.parametro.formatar(),
        "Condições fixas": "; ".join(r.condicoes),
        "Carta Circular 4.001": " e ".join(
            TRECHOS[k].rotulo for k in r.enquadramento),
        "Circular 3.978": citar(list(r.base_3978)).replace("Circular 3.978, ", ""),
        "Gravidade": r.gravidade,
    } for r in REGRAS.values()]), hide_index=True, use_container_width=True,
        height=36 * len(REGRAS) + 40)
    with st.expander("O racional de cada regra"):
        for r in REGRAS.values():
            st.markdown(md(f"**{r.rotulo}.** {r.racional}"))

    # --- desempenho ------------------------------------------------------ #
    st.markdown("---")
    st.markdown("##### Desempenho por regra no período")
    st.caption(f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}, "
               f"com o filtro da barra lateral ({filtros.resumo(dom)}). Mesmos "
               f"números da aba de causa raiz; taxas só de alertas maduros.")
    mks = ["alertas", "clientes_alertados", "taxa_falso_positivo",
           "taxa_comunicacao", "dias_analise", "fora_do_prazo"]
    df = agregar(con, dom, mks, inicio, fim, dims=["regra"], filtros=filtros,
                 ordenar_por="alertas")
    if df.empty:
        st.info("Nenhum alerta no período com esse filtro.")
    else:
        st.dataframe(pd.DataFrame({
            "Regra": df["regra"],
            **{dom.metrica(k).rotulo: [numero(float(v) if pd.notna(v) else float("nan"),
                                              dom.metrica(k)) for v in df[k]]
               for k in mks},
        }), hide_index=True, use_container_width=True)

    # --- calibração ------------------------------------------------------ #
    st.markdown("---")
    st.markdown("##### Calibração: o que acontece se eu mudar o corte")
    calibraveis = [r for r in REGRAS.values() if r.calibravel]
    c1, c2 = st.columns([1.3, 2])
    with c1:
        rid = st.selectbox("Regra", [r.id for r in calibraveis],
                           format_func=lambda k: REGRAS[k].rotulo,
                           key="cal_regra")
    r = REGRAS[rid]
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

    motor = agregar(con, dom, ["alertas"], vigencia, pld_dados.data_base(),
                    filtros=Filtros({"regra": [r.rotulo]}))
    n_motor = int(motor.iloc[0]["alertas"]) if not motor.empty else 0

    cols = st.columns(4, gap="small")
    delta = len(novo_sel) - len(atual_sel)
    variacao = (delta / len(atual_sel)) if len(atual_sel) else None
    cartoes = [
        (f"Alertas desde {vigencia.strftime('%m/%Y')}", f"{len(novo_sel)}",
         f"hoje {len(atual_sel)} · {pct(variacao) if variacao is not None else '—'}",
         TINTA),
        ("Comunicações que se perderiam", f"{len(perdidos)}",
         f"de {len(comunicados)} comunicadas pela regra",
         JULGA_RUIM if len(perdidos) else TINTA),
        ("Falso positivo dos decididos",
         pct(fp_novo, 1, sinal=False) if fp_novo == fp_novo else "—",
         f"hoje {pct(fp_atual, 1, sinal=False) if fp_atual == fp_atual else '—'}",
         TINTA),
        ("Alertas novos sem histórico", f"{sem_analise}",
         "abaixo do corte atual, nunca analisados", TINTA),
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
    for col, ys, titulo, cor in ((g1, vol, "Alertas no corte", SERIE[0]),
                                 (g2, cap, "Comunicações mantidas", SERIE[1])):
        with col:
            fig = go.Figure(go.Scatter(
                x=grade, y=ys, mode="lines+markers", line=dict(color=cor, width=2),
                marker=dict(size=5),
                hovertemplate="corte %{x}<br><b>%{y}</b><extra></extra>"))
            fig.add_vline(x=p.valor, line=dict(color=EIXO, width=1, dash="dot"),
                          annotation_text="vigente", annotation_position="top")
            if novo != p.valor:
                fig.add_vline(x=novo, line=dict(color=STATUS["alta"], width=1.5),
                              annotation_text="escolhido",
                              annotation_position="bottom right")
            fig = g._base(fig, 240, titulo)
            fig.update_xaxes(title=dict(text=p.nome, font=dict(size=11,
                                                             color=TINTA_MUDA)))
            st.plotly_chart(fig, use_container_width=True,
                            key=f"cal_{titulo}_{rid}")

    if novo > p.valor:
        frase = (f"Subir o corte de **{p.formatar()}** para "
                 f"**{p.formatar(novo)}** tira {len(atual_sel) - len(novo_sel)} "
                 f"alertas da fila ({pct(variacao, 0, sinal=False) if variacao else '0%'}"
                 f" a menos) e deixaria de selecionar **{len(perdidos)} "
                 f"comunicação(ões)** que a análise sustentou.")
    elif novo < p.valor:
        frase = (f"Baixar o corte para **{p.formatar(novo)}** coloca "
                 f"{sem_analise} alertas novos na fila. Eles estão abaixo do "
                 f"corte atual, nunca foram analisados — então não dá para "
                 f"saber quantos virariam comunicação sem rodar em paralelo "
                 f"(modo sombra) por um ciclo.")
    else:
        frase = (f"No corte vigente, {len(atual_sel)} alertas desde "
                 f"{vigencia.strftime('%m/%Y')} — "
                 f"o mesmo número que o motor conta para a regra "
                 f"({n_motor}). Mova o corte para ver o custo de cada lado.")
    st.markdown(md(frase))
    st.markdown(nota(
        "A conta é exata, não estimativa: com um parâmetro só e supressão "
        "mensal, a regra dispara no mês se, e só se, o máximo mensal do "
        "indicador passar do corte. Mudança de corte é decisão de política — "
        "vai para a avaliação interna de risco (Circular 3.978, art. 10) com "
        "data de vigência, como a R01 em 01/03/2026. Os filtros da barra "
        "lateral não se aplicam à calibração."), unsafe_allow_html=True)

    # --- ciclo mensal ------------------------------------------------------ #
    st.markdown("---")
    st.markdown("##### Ciclo mensal de checagem de CPFs")
    ci = pld_dados.ciclo()
    ci = ci.assign(mes=[d.strftime("%Y-%m") for d in ci["data"]])
    # "no dia previsto": o reprocessamento fecha o mês, mas atrasado. Somar o
    # que foi checado depois esconderia justamente o buraco que importa.
    ci["no_dia"] = ci[["checados", "previstos"]].min(axis=1)
    por_mes = ci.groupby("mes")[["previstos", "no_dia"]].sum().reset_index()
    por_mes["cobertura"] = por_mes["no_dia"] / por_mes["previstos"]
    fig = go.Figure(go.Bar(
        x=por_mes["mes"], y=por_mes["cobertura"],
        marker=dict(color=[JULGA_RUIM if c < 0.999 else SERIE[0]
                           for c in por_mes["cobertura"]]),
        text=[pct(c, 1, sinal=False) for c in por_mes["cobertura"]],
        textposition="outside",
        hovertemplate="%{x}<br><b>%{text}</b> dos lotes previstos no dia "
                      "certo<extra></extra>"))
    fig = g._base(fig, 240, "Lotes checados no dia previsto")
    fig.update_yaxes(tickformat=".0%", range=[0.75, 1.06])
    st.plotly_chart(fig, use_container_width=True, key="pld_ciclo")
    falhas = ci[ci["situacao"].isin(["Falha do job", "Reprocessamento"])]
    if not falhas.empty:
        st.markdown(md(
            "**Buraco de cobertura:** " + "; ".join(
                f"{r.data.strftime('%d/%m/%Y')} — {r.situacao.lower()} "
                f"({r.checados} CPFs checados de {r.previstos} previstos)"
                for r in falhas.itertuples())
            + ". O reprocessamento fechou a cobertura do mês, mas os lotes "
              "atrasaram quatro a seis dias — e as regras de ciclo mensal "
              "desses lotes selecionaram com o mesmo atraso."))


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
    st.markdown(f"##### Quem entrou na fila em {ref.strftime('%d/%m/%Y')}")

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

    if novos.empty:
        st.caption("Nenhum cliente foi selecionado neste dia — o movimento do "
                   "painel veio de decisões, não de seleção nova.")
    else:
        novos["prioridade"] = (novos["cliente_id"].map(prio)
                               if prio is not None else float("nan"))
        novos = novos.sort_values("prioridade", ascending=False,
                                  na_position="last")
        st.caption(f"{len(novos)} cliente(s) selecionado(s) no dia. A "
                   f"prioridade considera todos os alertas abertos do cliente, "
                   f"não só os de hoje.")
        st.dataframe(pd.DataFrame({
            "Prioridade": novos["prioridade"].fillna(0),
            "Cliente": novos["codigo"],
            "Tipo": novos["tipo_cliente"],
            "Regras do dia": novos["regras"],
            "Carta Circular 4.001": novos["enquadramento"],
            "Valor envolvido": [_brl(v) for v in novos["valor"]],
            "Analisar até": [(ref + pd.Timedelta(days=PRAZO_ANALISE_DIAS)
                              ).strftime("%d/%m/%Y")] * len(novos),
            "Risco": novos["faixa_risco"],
            "UF": novos["uf"],
        }).head(12), hide_index=True, use_container_width=True,
            column_config={"Prioridade": st.column_config.ProgressColumn(
                "Prioridade", min_value=0, max_value=100, format="%.0f")})

    # o que vence antes vem depois: é a informação que manda no dia
    vencendo = (fila[fila["dias_para_prazo"] <= 3].sort_values("dias_para_prazo")
                if not fila.empty else fila)
    if not vencendo.empty:
        vencidos = int((vencendo["dias_para_prazo"] < 0).sum())
        st.markdown(f"##### Prazo estourando")
        st.caption(
            f"{len(vencendo)} cliente(s) com três dias ou menos até o fim do "
            f"prazo de análise" + (f", {vencidos} já vencido(s)" if vencidos
                                   else "") + " — Circular 3.978, art. 43, § 1º.")
        st.dataframe(pd.DataFrame({
            "Prazo": [_prazo_txt(int(x)) for x in vencendo["dias_para_prazo"]],
            "Cliente": vencendo["codigo"],
            "Tipo": vencendo["tipo_cliente"],
            "Prioridade": vencendo["prioridade"].round(0).astype(int),
            "Regras abertas": vencendo["regras"],
            "Valor envolvido": [_brl(v) for v in vencendo["valor_envolvido"]],
        }).head(10), hide_index=True, use_container_width=True)

    st.markdown(nota(
        "O dossiê de cada um destes clientes — evidência em número, "
        "contrapartes, verificações e rascunho de parecer — está na aba "
        "<b>Clientes em atenção</b>: cole o código na busca, ou mude a "
        "<i>posição da fila</i> para esta data e clique na linha."),
        unsafe_allow_html=True)


# =========================================================================== #
# Blocos extras
# =========================================================================== #

def bloco_visao_geral(con, dom, dmax: date, fim: date, filtros: Filtros) -> None:
    ref = pld_dados.referencia(fim, dmax)
    al = mod_fila.alertas_abertos(con, dom, ref, filtros)
    idade = mod_fila.idade_da_fila(al)
    st.caption("Falso positivo, conversão, comunicações e tempo de análise só "
               "contam alertas com 45 dias ou mais em 31/08/2026. Em período "
               "recente esses cartões aparecem vazios de propósito — o alerta "
               "ainda não teve tempo de ser decidido.")
    st.markdown("---")
    st.markdown(f"##### A fila em {ref.strftime('%d/%m/%Y')}, pela régua do "
                f"prazo")
    cores = [SERIE[0], SERIE[0], STATUS["media"], JULGA_RUIM]
    fig = go.Figure(go.Bar(
        x=idade["alertas"], y=idade["faixa"], orientation="h",
        marker=dict(color=cores), text=idade["alertas"], textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x} alertas abertos<extra></extra>"))
    fig = g._base(fig, 220, "")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, max(idade["alertas"].max() * 1.25, 1)],
                     showticklabels=False)
    fig.update_traces(cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True, key="pld_idade")
    st.caption("Alertas abertos por idade desde a seleção. A barra vermelha é "
               "descumprimento da Circular 3.978, art. 43, § 1º. Os clientes, "
               "um a um, estão na aba Clientes em atenção.")


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
    st.markdown(f"##### Casos em investigação em {ref.strftime('%d/%m/%Y')}")

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

    with esq:
        fig = go.Figure()
        for col, nome, cor in (("entraram", "Alertas selecionados", SERIE[0]),
                               ("concluidos", "Análises concluídas", SERIE[1])):
            fig.add_trace(go.Scatter(
                x=fluxo["semana"], y=fluxo[col], name=nome, mode="lines+markers",
                line=dict(color=cor, width=2), marker=dict(size=5),
                hovertemplate="semana de %{x|%d/%m}<br><b>%{y}</b>"
                              f"<extra>{nome}</extra>"))
        fig = g._base(fig, 260, "Entradas e conclusões por semana")
        fig.update_layout(showlegend=True, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True, key="pld_fluxo")
        if len(fluxo) > 1:
            saldo = int((fluxo["entraram"] - fluxo["concluidos"]).sum())
            atrasadas = int((fluxo["entraram"] > fluxo["concluidos"]).sum())
            lado = (f"entraram {saldo} alertas a mais do que saíram"
                    if saldo > 0 else
                    f"saíram {-saldo} alertas a mais do que entraram"
                    if saldo < 0 else "entrou e saiu a mesma quantidade")
            st.caption(
                f"Nas últimas {len(fluxo)} semanas fechadas {lado}, com "
                f"{atrasadas} semana(s) em que a seleção passou a capacidade "
                f"de análise. É isso que empurra a fila para o prazo — não o "
                f"volume de um dia.")

    with dir_:
        if al.empty:
            st.caption("Nenhum alerta aberto nesta data.")
        else:
            por_regra = (al.groupby("regra_id").size().sort_values()
                         .rename("abertos").reset_index())
            fig = go.Figure(go.Bar(
                x=por_regra["abertos"], y=por_regra["regra_id"], orientation="h",
                marker=dict(color=SERIE[0]), text=por_regra["abertos"],
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>%{x} alertas abertos<extra></extra>"))
            fig = g._base(fig, 260, "Em análise, por regra")
            fig.update_xaxes(showticklabels=False,
                             range=[0, por_regra["abertos"].max() * 1.25])
            fig.update_traces(cliponaxis=False)
            st.plotly_chart(fig, use_container_width=True, key="pld_abertos_regra")

    if not al.empty:
        parados = (al.sort_values("idade", ascending=False)
                   .drop_duplicates("cliente_id").head(6))
        st.caption("Os que estão há mais tempo esperando:")
        st.dataframe(pd.DataFrame({
            "Cliente": parados["codigo"],
            "Tipo": parados["tipo_cliente"],
            "Regra": parados["regra_id"],
            "Selecionado em": [x.strftime("%d/%m/%Y") for x in parados["data"]],
            "Dias na fila": parados["idade"],
            "Prazo": [_prazo_txt(int(x)) for x in parados["dias_para_prazo"]],
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
    st.markdown("##### Por que o volume de alertas mudou")

    c1, c2, c3 = st.columns([1.6, 1, 1])
    with c1:
        rid = st.selectbox("Regra", sorted(perfil["regra_id"].unique()),
                           format_func=lambda k: REGRAS[k].rotulo,
                           key="cr_pld_regra")
    with c2:
        m_ant = st.selectbox("Mês base", meses, index=max(0, len(meses) - 2),
                             format_func=_mes_br, key="cr_pld_a")
    with c3:
        m_atual = st.selectbox("Mês atual", meses, index=len(meses) - 1,
                               format_func=_mes_br, key="cr_pld_b")

    r = REGRAS[rid]
    d = perfil[perfil["regra_id"] == rid].set_index("mes")
    if m_ant not in d.index or m_atual not in d.index:
        st.info("Sem avaliação da regra em um dos meses escolhidos.")
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
        {"rotulo": "Efeito população", "valor": float(ef_pop), "tipo": "delta"},
        {"rotulo": "Efeito seleção", "valor": float(ef_sel), "tipo": "delta"},
        {"rotulo": "Interação", "valor": float(ef_int), "tipo": "delta"},
        {"rotulo": _mes_br(m_atual), "valor": float(b_["acima_do_corte"]),
         "tipo": "total"},
    ])
    esq, dir_ = st.columns([3, 2], gap="large")
    with esq:
        fig = g.cascata(cascata, m_alertas,
                        titulo=f"{r.rotulo}: de onde veio a variação de alertas")
        # "2026-07" seria lido como data pelo Plotly e o eixo viraria uma linha
        # do tempo com os rótulos dos efeitos no lugar errado.
        fig.update_xaxes(type="category")
        st.plotly_chart(fig, use_container_width=True, key=f"cr_pld_casc_{rid}")
    with dir_:
        st.markdown("###### A conta, em português")
        st.markdown(md(
            f"- Alertas = **avaliados × taxa de seleção**. Em {_mes_br(m_ant)}: "
            f"{int(a_['avaliados'])} × {pct(taxa_a, 0, sinal=False)} = "
            f"{int(a_['acima_do_corte'])}. Em {_mes_br(m_atual)}: "
            f"{int(b_['avaliados'])} × {pct(taxa_b, 0, sinal=False)} = "
            f"{int(b_['acima_do_corte'])}."))
        st.markdown(md(
            f"- **Efeito população** ({ef_pop:+.0f}): mais (ou menos) clientes "
            f"passaram nas condições fixas da regra.\n"
            f"- **Efeito seleção** ({ef_sel:+.0f}): entre os avaliados, a "
            f"parcela acima do corte mudou — é aqui que aparece mudança de "
            f"comportamento **ou** de parâmetro.\n"
            f"- **Interação** ({ef_int:+.0f}): os dois ao mesmo tempo."))
        if a_["corte"] != b_["corte"]:
            st.markdown(nota(
                f"O corte mudou de {r.parametro.formatar(a_['corte'])} para "
                f"{r.parametro.formatar(b_['corte'])} entre os dois meses: o "
                f"efeito seleção aqui é <b>decisão de política</b>, não "
                f"comportamento do cliente."), unsafe_allow_html=True)
        st.caption(f"Soma dos efeitos: {ef_pop + ef_sel + ef_int:+.0f} · "
                   f"variação total: {delta:+.0f}")

    # --- sinais brutos ---------------------------------------------------- #
    st.markdown("###### Os sinais brutos do mês, antes de virar alerta")
    ca = comp[comp["mes"] == m_ant].set_index("indicador")
    cb = comp[comp["mes"] == m_atual].set_index("indicador")

    def _fmt(v, unidade):
        if unidade == "moeda":
            return _brl(v)
        if unidade == "media":
            return f"{v:.2f}".replace(".", ",")
        return f"{v:,.0f}".replace(",", ".")

    linhas = []
    for ind in cb.index:
        if ind not in ca.index:
            continue
        va, vb = float(ca.loc[ind, "valor"]), float(cb.loc[ind, "valor"])
        linhas.append({
            "Sinal": ind, _mes_br(m_ant): _fmt(va, ca.loc[ind, "unidade"]),
            _mes_br(m_atual): _fmt(vb, cb.loc[ind, "unidade"]),
            "Variação": pct((vb - va) / va) if va else "—",
            "ordem": abs((vb - va) / va) if va else 0,
        })
    sinais = pd.DataFrame(linhas).sort_values("ordem", ascending=False)
    st.dataframe(sinais.drop(columns="ordem"), hide_index=True,
                 use_container_width=True)
    st.caption(
        "Contadores da população inteira, sem filtro de alerta e sem os "
        "filtros da barra lateral: filtrar por quem já alertou responderia a "
        "pergunta com a própria resposta. Se o efeito seleção subiu e os "
        "sinais brutos acompanham, o movimento é dos clientes; se os sinais "
        "estão parados, a régua é que mudou.")


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
    st.markdown("##### O indicador de cada regra, antes do corte")
    c1, c2 = st.columns([1.4, 3])
    with c1:
        rid = st.selectbox("Regra", sorted(perfil["regra_id"].unique()),
                           format_func=lambda k: REGRAS[k].rotulo,
                           key="ind_regra")
    r = REGRAS[rid]
    d = perfil[perfil["regra_id"] == rid].sort_values("mes")
    with c2:
        st.caption(f"**{r.indicador}.** A população avaliada são os clientes "
                   f"que passaram nas condições fixas da regra ({'; '.join(r.condicoes)}), "
                   f"no lote do ciclo quando a regra é mensal. Este bloco não "
                   f"responde aos filtros da barra lateral.")

    e, dr = st.columns(2, gap="medium")
    with e:
        fig = go.Figure()
        for col, nome, cor, largura in (("p95", "p95", SERIE[2], 1.6),
                                        ("p75", "p75", SERIE[1], 1.6),
                                        ("p50", "mediana", SERIE[0], 2.2)):
            fig.add_trace(go.Scatter(
                x=d["mes"], y=d[col], name=nome, mode="lines+markers",
                line=dict(color=cor, width=largura), marker=dict(size=4),
                hovertemplate="%{x}<br><b>%{y:.2f}</b>" f"<extra>{nome}</extra>"))
        fig.add_trace(go.Scatter(
            x=d["mes"], y=d["corte"], name="corte vigente", mode="lines",
            line=dict(color=STATUS["alta"], width=2, dash="dash"),
            line_shape="hv",
            hovertemplate="%{x}<br><b>corte %{y:.2f}</b><extra></extra>"))
        fig = g._base(fig, 280, "Distribuição do indicador e o corte")
        fig.update_layout(showlegend=True, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True, key=f"ind_dist_{rid}")
    with dr:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=d["mes"], y=d["avaliados"], name="avaliados",
                             marker=dict(color=GRADE),
                             hovertemplate="%{x}<br><b>%{y}</b> avaliados"
                                           "<extra></extra>"))
        fig.add_trace(go.Bar(x=d["mes"], y=d["acima_do_corte"],
                             name="acima do corte", marker=dict(color=SERIE[0]),
                             hovertemplate="%{x}<br><b>%{y}</b> acima do corte"
                                           "<extra></extra>"))
        fig = g._base(fig, 280, "Avaliados e selecionados")
        fig.update_layout(barmode="overlay", showlegend=True)
        st.plotly_chart(fig, use_container_width=True, key=f"ind_vol_{rid}")

    st.markdown(md(_leitura_indicador(d, r)))


def _leitura_indicador(d: pd.DataFrame, r) -> str:
    """Uma frase dizendo quem se mexeu: o cliente, o corte ou a população."""
    if len(d) < 6:
        return "Histórico curto demais para comparar trimestres."
    ini, fim_ = d.head(3), d.tail(3)

    def var(col):
        a, b = ini[col].mean(), fim_[col].mean()
        return (b - a) / a if a else float("nan")

    p95, aval, corte_mudou = var("p95"), var("avaliados"),         ini["corte"].iloc[-1] != fim_["corte"].iloc[-1]
    partes = []
    if corte_mudou:
        partes.append(
            f"O corte mudou de {r.parametro.formatar(ini['corte'].iloc[-1])} "
            f"para {r.parametro.formatar(fim_['corte'].iloc[-1])} no período — "
            f"parte da variação de volume é decisão de política, não "
            f"comportamento.")
    if abs(p95) >= 0.15:
        partes.append(
            f"O p95 do indicador {'subiu' if p95 > 0 else 'caiu'} "
            f"{pct(abs(p95), 0, sinal=False)} do primeiro para o último "
            f"trimestre: a ponta da distribuição se moveu de verdade.")
    else:
        partes.append("O p95 do indicador está estável entre o primeiro e o "
                      "último trimestre — a régua mexeu mais que o "
                      "comportamento.")
    if abs(aval) >= 0.15:
        partes.append(
            f"A população avaliada {'cresceu' if aval > 0 else 'encolheu'} "
            f"{pct(abs(aval), 0, sinal=False)}, o que move o volume mesmo com "
            f"taxa de seleção parada.")
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


def sobre_pld() -> None:
    st.markdown("#### Mapa regulatório: onde cada exigência aparece")
    st.dataframe(pd.DataFrame(MAPA, columns=["Exigência", "Norma",
                                             "Onde está no painel"]),
                 hide_index=True, use_container_width=True)
    st.caption("Resumos para uso no painel. A referência é sempre o normativo "
               "publicado pelo Banco Central.")

    st.markdown("#### Automação de baixo custo da fila")
    st.markdown(
        "A fila deste painel também existe como planilha, sem squad de "
        "engenharia: `automacoes/apps_script/fila_pld.gs` é um Google Apps "
        "Script que roda todo dia útil às 8h, lê os alertas exportados pelo "
        "job, calcula prazo de análise e prazo de comunicação em dia útil, "
        "ordena por prioridade, protege as colunas de decisão contra edição "
        "fora do fluxo e manda o resumo do dia num canal do Slack — com os "
        "vencidos em primeiro lugar. O passo a passo está no README.")
