"""
Analytics com agente — três domínios, um motor.

Ponto de entrada do Streamlit. Este arquivo cuida SÓ da tela: leitura de
estado, layout e chamada dos motores. Nenhuma conta acontece aqui — toda
métrica vem de `vulcano.dados`, que monta SQL a partir da camada semântica do
domínio. É o que garante que número de aba e número de chat sejam o mesmo
número.

A ordem das abas segue como a ferramenta é usada de verdade: ninguém abre um
painel para admirar o total do mês, abre para saber se tem algo errado hoje.
Alertas primeiro, agente logo depois — porque o alerta quase sempre gera uma
pergunta.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from vulcano import alertas as mod_alertas
from vulcano import analise as mod_analise
from vulcano import causa_raiz as mod_causa
from vulcano import graficos as g
from vulcano.agente import (PERGUNTA_ANALISE_GERAL, Contexto, chave_api,
                            perguntar, sugestoes)
from vulcano.dados import (Filtros, agregar, comparar, conectar,
                           periodo_disponivel, serie_diaria,
                           valores_da_dimensao)
from vulcano.dominios import listar, obter
from vulcano.estilo import (CSS, avatar_uri, cabecalho_comparacao,
                            cartao_alerta, cartao_metrica, descrever_janela,
                            md, nota, rosto, selo)
from vulcano.formatacao import julgar, numero, pct
from vulcano.graficos import JULGA_BOM, JULGA_RUIM, TINTA_MUDA
from vulcano.periodos import (NIVEIS_COMPARACAO, PRESETS, contra_dia,
                              contra_mes, contra_semana, descrever_dia,
                              montar_preset)
from vulcano.semantica import Dominio

# Nome da plataforma. PROVISÓRIO — cada domínio já tem seu próprio agente, com
# nome e rosto declarados no arquivo do domínio (vulcano/dominios/*.py). Falta
# só o nome do conjunto; trocar aqui muda a capa inteira.
MARCA = "Analytics com agente"
MARCA_ROSTO = "◆"

st.set_page_config(page_title=MARCA, page_icon="📊", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Conexão por domínio, em cache
# --------------------------------------------------------------------------- #

@st.cache_resource(show_spinner=False)
def _conexao(chave: str):
    dom = obter(chave)
    con = conectar(dom)
    return con, periodo_disponivel(con)


@st.cache_data(show_spinner=False)
def _valores(chave_dominio: str, chave_dim: str) -> list[str]:
    dom = obter(chave_dominio)
    con, _ = _conexao(chave_dominio)
    return valores_da_dimensao(con, dom, chave_dim, limite=200)


def _ir_para(chave: str | None) -> None:
    st.session_state["dominio"] = chave
    st.rerun()


# --------------------------------------------------------------------------- #
# Capa
# --------------------------------------------------------------------------- #

ARQUITETURA = [
    ("01", "Camada semântica",
     "Cada domínio declara suas métricas e dimensões em um único arquivo: o SQL "
     "de cada métrica, se ela é razão, se subir é bom, e sobre que entidade ela "
     "conta. Abas e agente leem daqui, então não existe caminho pelo qual o "
     "chat responda um número diferente do gráfico."),
    ("02", "Motor de cálculo",
     "DuckDB sobre Parquet, com o SQL montado a partir da declaração — nunca de "
     "texto livre. Numerador e denominador saem separados, que é o que permite "
     "decompor uma razão em efeito taxa e efeito mix depois."),
    ("03", "Agente",
     "O modelo planeja, o Python calcula. O LLM traduz a pergunta em um plano "
     "com chaves conhecidas, o motor executa, e o LLM só volta para narrar em "
     "cima de números já calculados. Ele nunca vê a base nem escreve SQL."),
    ("04", "Leitura, não só número",
     "Toda resposta sai em três camadas: o número, o que explica (segmento, "
     "efeito taxa vs mix, tendência) e o que fazer. As três são derivadas de "
     "regras sobre os números, então existem mesmo sem chave de API."),
]

DECISOES = [
    ("Por que não texto-para-SQL direto",
     "Deixar o modelo escrever SQL livre gera três problemas que só aparecem "
     "quando a ferramenta começa a ser usada de verdade: a mesma pergunta "
     "devolve dois números em dias diferentes, o erro de grão passa em "
     "silêncio, e não há o que validar. Restringindo a saída a um plano com "
     "chaves conhecidas, a pergunta impossível falha na validação e o agente "
     "diz o que não sabe — em vez de acertar a sintaxe e errar a conta."),
    ("Por que o alerta traz o provável motivo",
     "Um alerta que só diz 'a receita caiu' manda a pessoa abrir outra aba para "
     "descobrir onde. Aqui a decomposição roda junto. E ela procura o segmento "
     "DESPROPORCIONAL, não o maior: dizer que cartão de crédito carrega 82% do "
     "desvio é inútil quando cartão já é 80% da receita todo dia. O que informa "
     "é o segmento que pesa muito mais no desvio do que pesa no normal."),
    ("Por que a cascata expõe o resíduo",
     "Métrica de contagem distinta quebrada por dimensão de grão mais fino não "
     "fecha: o mesmo pedido entra em dois segmentos. O resíduo é calculado, "
     "mostrado e explicado, em vez de redistribuído entre as barras para o "
     "gráfico ficar bonito."),
    ("Por que efeito taxa e efeito mix andam separados",
     "Ticket médio cair porque cada segmento ficou mais barato e ticket médio "
     "cair porque mudou quem comprou são diagnósticos opostos: um pede ação no "
     "segmento, o outro em aquisição. A média simples não distingue os dois, e "
     "é por isso que a decomposição de razão abre em taxa, mix e interação."),
    ("Por que o alerta tem dois cortes",
     "Segmento pequeno estoura z-score o tempo todo — variação relativa em base "
     "pequena é enorme por construção. Sem o corte de relevância o painel "
     "dispara dezenas de alertas por dia, ninguém lê, e o produto morre. Todo "
     "alerta passa por duas provas: ser estranho E mover o total o bastante "
     "para valer a ligação."),
    ("Por que safra jovem aparece vazia, nunca zero",
     "Em crédito, inadimplência leva meses para aparecer. Preencher safra "
     "imatura com zero é o que faz um painel mostrar risco caindo justamente "
     "quando ele ainda não teve tempo de acontecer. A censura é por safra "
     "inteira: a safra só entra quando o seu último contrato completou o MOB."),
]


def render_capa() -> None:
    agentes = " · ".join(d.agente_nome for d in listar())
    st.markdown(
        f"""<div class="vulc-hero">
        <h1>{MARCA_ROSTO} {MARCA}</h1>
        <div class="sub">
          Três painéis, um motor: gráficos, comparação de períodos, causa raiz
          com cascata, alertas que já vêm com o provável motivo, e um agente que
          responde em linguagem natural — do analista júnior ao executivo.
          <br><br>
          Cada domínio tem o <b>seu</b> agente, com nome, rosto e vocabulário
          próprios: {agentes}. Quem responde sobre crédito não é quem responde
          sobre marketing, porque o vocabulário, as ressalvas e o que conta
          como resposta boa são outros. O motor por baixo é o mesmo.
        </div></div>""",
        unsafe_allow_html=True,
    )

    st.markdown("#### Escolha um domínio")
    cols = st.columns(3, gap="medium")
    for col, dom in zip(cols, listar()):
        with col:
            st.markdown(
                f"""<div class="vulc-dom">
                  <h3>{dom.nome}</h3>
                  <div class="sub">{dom.subtitulo}</div>
                  <div class="txt">{dom.descricao}</div>
                  <div class="vulc-agente" style="margin-top:12px">
                    {rosto(dom, "animada", 56)}
                    <div>
                      <div style="font-size:0.72rem;color:#7a8ba0;
                                  text-transform:uppercase;letter-spacing:.05em;
                                  font-weight:650">Agente</div>
                      <div style="font-size:1.02rem;font-weight:640;
                                  color:#0f1b2d">{dom.agente_nome}</div>
                    </div>
                  </div>
                  <div style="margin-top:12px">{selo(dom.simulado)}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.write("")
            if st.button(f"Abrir {dom.nome}", key=f"btn_{dom.chave}",
                         use_container_width=True, type="primary"):
                _ir_para(dom.chave)

    st.divider()

    st.markdown("#### O problema que este produto resolve")
    st.markdown(
        """
Em toda área que depende de dados existe a mesma fila: alguém precisa de um
número, abre um chamado para o time de analytics, e a decisão espera dois dias
por uma resposta que era uma consulta. Quem tem pressa decide sem o dado; quem
espera decide tarde.

Um dashboard tradicional resolve as perguntas que alguém previu no momento de
construí-lo. A pergunta seguinte — *por que* caiu, *onde* caiu, se já estava
caindo antes — volta para a fila.

O primeiro destes agentes, o Vulcano, nasceu na Petlove para fechar essa fila:
além dos gráficos, ele decompõe a variação, dispara alerta sozinho quando algo
foge do padrão e responde pergunta em linguagem natural, no mesmo lugar. Esta
versão pública reconstrói o produto sobre dados abertos e o estende a outros
dois domínios, para mostrar a arquitetura e as decisões técnicas por trás dele.
        """
    )

    st.markdown("#### Como é feito")
    cols = st.columns(4, gap="small")
    for col, (n, titulo, texto) in zip(cols, ARQUITETURA):
        with col:
            st.markdown(
                f"""<div class="vulc-arq"><div class="n">{n}</div>
                <h4>{titulo}</h4><p>{texto}</p></div>""",
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown("#### Decisões técnicas que valem discussão")
    for i in range(0, len(DECISOES), 2):
        cols = st.columns(2, gap="medium")
        for col, (titulo, texto) in zip(cols, DECISOES[i:i + 2]):
            with col:
                with st.expander(titulo, expanded=False):
                    st.write(texto)

    st.write("")
    st.markdown("#### Procedência dos dados")
    for dom in listar():
        st.markdown(f"**{dom.nome}** — {dom.fonte}")
    st.caption(
        "Stack: Python, DuckDB, pandas, Plotly, Streamlit e a biblioteca da "
        "OpenAI para o agente. Todo o código está no repositório."
    )


# --------------------------------------------------------------------------- #
# Barra lateral
# --------------------------------------------------------------------------- #

def barra_lateral(dom: Dominio, dmin: date, dmax: date):
    with st.sidebar:
        st.markdown(f"### {dom.nome}")
        if st.button("← Voltar para a capa", use_container_width=True):
            _ir_para(None)

        st.markdown("---")
        st.markdown("#### Período")
        modo = st.radio(
            "Modo", ["Últimos N dias", "Mês", "Intervalo livre"],
            key=f"modo_{dom.chave}", label_visibility="collapsed",
        )

        if modo == "Últimos N dias":
            n = st.slider("Quantos dias", 7, 180, 90, step=7,
                          key=f"ndias_{dom.chave}")
            ref = st.date_input("Até", value=dmax, min_value=dmin,
                                max_value=dmax, key=f"ref_{dom.chave}",
                                format="DD/MM/YYYY")
            ref = ref if isinstance(ref, date) else dmax
            inicio, fim = max(dmin, ref - timedelta(days=n - 1)), ref
        elif modo == "Mês":
            meses = pd.period_range(dmin, dmax, freq="M")
            rotulos = [p.strftime("%m/%Y") for p in meses]
            escolha = st.selectbox("Mês", rotulos, index=len(rotulos) - 1,
                                   key=f"mes_{dom.chave}")
            p = meses[rotulos.index(escolha)]
            inicio = max(dmin, p.start_time.date())
            fim = min(dmax, p.end_time.date())
        else:
            faixa = st.date_input(
                "Intervalo", value=(max(dmin, dmax - timedelta(days=89)), dmax),
                min_value=dmin, max_value=dmax, key=f"faixa_{dom.chave}",
                format="DD/MM/YYYY",
            )
            if isinstance(faixa, tuple) and len(faixa) == 2:
                inicio, fim = faixa
            else:
                inicio, fim = max(dmin, dmax - timedelta(days=89)), dmax

        st.caption(f"{descrever_dia(inicio)} até {descrever_dia(fim)} · "
                   f"{(fim - inicio).days + 1} dias")

        st.markdown("#### Comparar com")
        chaves = list(PRESETS.keys())
        preset = st.selectbox(
            "Comparação", chaves, index=chaves.index("mes_fechado"),
            format_func=lambda k: PRESETS[k], key=f"preset_{dom.chave}",
            label_visibility="collapsed",
        )

        st.markdown("#### Quebrar os gráficos por")
        opcoes_quebra = ["(sem quebra)"] + dom.dims_filtro
        quebra = st.selectbox(
            "Quebra", opcoes_quebra, index=0,
            format_func=lambda k: ("Sem quebra — só o total" if k == "(sem quebra)"
                                   else dom.dimensao(k).rotulo),
            key=f"quebra_{dom.chave}", label_visibility="collapsed",
        )
        quebra = None if quebra == "(sem quebra)" else quebra
        if quebra:
            st.caption("Cada gráfico passa a mostrar os 5 maiores segmentos "
                       "desta dimensão, em vez do total.")

        st.markdown("---")
        st.markdown("#### Filtros")
        valores: dict[str, list[str]] = {}

        def _campo(dk: str) -> None:
            d = dom.dimensao(dk)
            opcoes = _valores(dom.chave, dk)
            sel = st.multiselect(d.rotulo, opcoes, default=[],
                                 key=f"f_{dom.chave}_{dk}",
                                 placeholder=f"Todos ({len(opcoes)})",
                                 help=d.descricao or None)
            if sel:
                valores[dk] = sel

        # Os primeiros ficam à mão e o resto entra num expansor. Empilhar dez
        # multiselects abertos empurra o período para fora da tela, e o filtro
        # que se usa toda hora vira o mais difícil de achar. O contador no
        # rótulo existe para que um filtro ativo lá dentro nunca fique
        # escondido -- filtro invisível é como se lê um número errado sem saber.
        VISIVEIS = 5
        for dk in dom.dims_filtro[:VISIVEIS]:
            _campo(dk)

        extras = dom.dims_filtro[VISIVEIS:]
        if extras:
            ativos = sum(
                1 for dk in extras
                if st.session_state.get(f"f_{dom.chave}_{dk}"))
            rot = f"Mais filtros ({len(extras)})"
            if ativos:
                rot = f"Mais filtros — {ativos} ativo(s)"
            with st.expander(rot, expanded=bool(ativos)):
                for dk in extras:
                    _campo(dk)

        filtros = Filtros(valores)
        if filtros:
            st.caption(f"Filtro ativo: {filtros.resumo(dom)}")
            st.caption("Os filtros valem para todas as abas E para o agente.")

        st.markdown("---")
        if chave_api():
            st.caption("🔑 Chave de API detectada: o agente usa o modelo para "
                       "interpretar e narrar. O cálculo continua no Python.")
        else:
            st.caption("Sem chave de API: o agente roda com o interpretador "
                       "determinístico. Tudo funciona; a linguagem fica menos "
                       "flexível.")

    return inicio, fim, preset, filtros, quebra


# --------------------------------------------------------------------------- #
# Aba: Alertas
# --------------------------------------------------------------------------- #

def aba_alertas(con, dom, fim, filtros):
    # A cara de ALERTA, e nao a de conversa: e o mesmo bicho, com a expressao
    # atenta. Quem varre os alertas e o mesmo agente que responde no chat, e a
    # tela precisa dizer isso sem legenda.
    st.markdown(
        f"""<div class="vulc-agente">
          {rosto(dom, "alerta", 56)}
          <div>
            <div class="nome" style="font-size:1.16rem">{dom.agente_nome}
              <span style="font-weight:500;color:#46586e;font-size:0.92rem">
                está de olho</span></div>
            <div class="papel">Varro todas as métricas do painel contra o
              histórico e contra os limites combinados, segmento a segmento — e
              trago o provável motivo junto com o aviso.</div>
          </div>
        </div>""", unsafe_allow_html=True)
    st.write("")

    c1, c2, c3 = st.columns([2, 1.5, 1.5])
    with c1:
        # O dia analisado NAO e guardado na chave do proprio widget.
        #
        # O botao "Ver esse dia", mais abaixo, precisa mudar essa data. Escrever
        # em `st.session_state["al_d_..."]` depois que o date_input ja foi
        # criado nesta execucao levanta StreamlitWidgetAlreadyInstantiatedError
        # -- e como o botao so aparece nos dias sem alerta, o erro nao acontece
        # em teste nenhum que nao clique exatamente ali.
        #
        # Entao o valor mora numa chave nossa (`al_dia_*`) e o widget ganha um
        # sufixo que muda quando queremos forcar outra data. Chave nova = widget
        # novo = o `value` volta a valer, que e o unico jeito de reposicionar um
        # date_input sem escrever na chave dele.
        chave_dia = f"al_dia_{dom.chave}"
        chave_geracao = f"al_ger_{dom.chave}"
        st.session_state.setdefault(chave_geracao, 0)
        padrao = st.session_state.get(chave_dia) or fim
        ref = st.date_input(
            "Dia analisado", value=padrao, format="DD/MM/YYYY",
            key=f"al_d_{dom.chave}_{st.session_state[chave_geracao]}")
        ref = ref if isinstance(ref, date) else fim
    with c2:
        z = st.slider("Quão estranho precisa ser", 2.0, 5.0, 3.0, 0.25,
                      key=f"al_z_{dom.chave}",
                      help="Quantos desvios fora do normal o dia precisa estar "
                           "para virar alerta. O 'normal' é a mediana dos 56 "
                           "dias anteriores. Corte 3 = três desvios.")
    with c3:
        mat = st.slider("Quão relevante precisa ser", 0.0, 0.20, 0.03, 0.01,
                        format="%.2f", key=f"al_m_{dom.chave}",
                        help="Quanto o segmento precisa pesar no total do dia. "
                             "Corte 3% = só avisa se o segmento mover ao menos "
                             "3% da métrica.")

    al = mod_alertas.varrer(con, dom, ref, filtros, z_limite=z,
                            materialidade=mat)
    st.markdown(md(f"#### {mod_alertas.resumir(al, ref)}"))

    if not al:
        anterior = mod_alertas.ultimo_dia_com_alerta(con, dom, ref, filtros,
                                                     z_limite=z)
        if anterior and anterior != ref:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"O movimento mais recente antes desse dia foi em "
                            f"**{descrever_dia(anterior)}**.")
            with c2:
                if st.button("Ver esse dia", key=f"al_ir_{dom.chave}",
                             use_container_width=True):
                    st.session_state[chave_dia] = anterior
                    st.session_state[chave_geracao] += 1
                    st.rerun()
    else:
        # Os cartões ocupam a largura toda: cada um carrega o motivo provável,
        # que é texto corrido e não cabe em coluna estreita.
        for a in al[:10]:
            motivo = mod_alertas.motivo_provavel(con, dom, a, filtros)
            st.markdown(cartao_alerta(a.severidade, a.tipo, a.texto,
                                      a.acao, motivo),
                        unsafe_allow_html=True)

    # A explicação vem DEPOIS dos alertas: quem abre a aba quer o que aconteceu,
    # não a metodologia. Quem quiser entender os cortes rola até aqui.
    st.markdown("---")
    st.markdown("##### Como um alerta nasce")
    e1, e2 = st.columns(2, gap="large")
    with e1:
        st.markdown(
            "**Duas origens diferentes.** Um alerta pode nascer de *desvio do "
            "histórico* — o dia está fora do que essa métrica costuma ser — ou "
            "de *limite de negócio*, um patamar fixo combinado com a área, que "
            "dispara mesmo quando o histórico já se acostumou com o problema. "
            "Os dois aparecem misturados na lista, com a origem escrita no topo "
            "de cada cartão."
        )
    with e2:
        st.markdown(
            "**Dois cortes, não um.** *Quão estranho* mede o desvio contra a "
            "mediana e o MAD dos 56 dias anteriores — mediana em vez de média "
            "porque a média é puxada pelo próprio pico que se quer detectar. "
            "*Quão relevante* mede o peso do segmento no total: sem ele, uma "
            "categoria de 0,3% da receita estoura o corte toda semana. Baixe a "
            "relevância para zero e veja o painel encher de ruído — é a "
            "demonstração de por que o segundo corte existe."
        )

    # A tabela fecha a página. Os cartões acima são a leitura; isto aqui é a
    # conferência — quem quiser auditar o observado contra o esperado rola até
    # o fim e vê tudo, inclusive o que não coube nos dez primeiros cartões.
    if al:
        st.markdown("---")
        st.markdown("##### Todos os alertas do dia, para conferir")
        st.caption(
            "Os cartões acima mostram os dez primeiros, com o motivo provável. "
            "Aqui está a lista inteira, com o número observado, o esperado pelo "
            "histórico e o z robusto de cada linha."
        )
        st.dataframe(pd.DataFrame([{
            "Severidade": a.severidade,
            "Origem": ("desvio do histórico" if a.tipo == "anomalia"
                       else "limite de negócio"),
            "Métrica": dom.metrica(a.chave_metrica).rotulo,
            "Segmento": a.segmento or "— total —",
            "Observado": numero(a.observado, dom.metrica(a.chave_metrica)),
            "Esperado": numero(a.esperado, dom.metrica(a.chave_metrica)),
            "z robusto": f"{a.z:+.1f}" if a.tipo == "anomalia" else "—",
        } for a in al]), use_container_width=True, hide_index=True,
            height=min(600, 36 * len(al) + 40))


# --------------------------------------------------------------------------- #
# Aba: agente
# --------------------------------------------------------------------------- #

def aba_agente(con, dom, inicio, fim, preset, filtros, quebra):
    chave = f"hist_{dom.chave}"
    chave_plano = f"plano_{dom.chave}"
    st.session_state.setdefault(chave, [])
    st.session_state.setdefault(chave_plano, None)

    ctx = Contexto(dominio=dom, inicio=inicio, fim=fim, filtros=filtros,
                   preset_comparacao=preset,
                   ultimo_plano=st.session_state[chave_plano],
                   historico=st.session_state[chave])

    st.markdown(
        f"""<div class="vulc-agente">
          {rosto(dom, "animada", 68)}
          <div>
            <div class="nome">{dom.agente_nome}</div>
            <div class="papel">{dom.agente_papel}</div>
          </div>
        </div>""", unsafe_allow_html=True)
    st.markdown(md(
        f"Perguntando no período **{inicio.strftime('%d/%m/%Y')} a "
        f"{fim.strftime('%d/%m/%Y')}**, com filtro **{filtros.resumo(dom)}**. "
        f"{dom.agente_nome} usa exatamente o mesmo motor das abas — se o número "
        f"divergir do gráfico, é bug, não interpretação."
    ))

    # O pronome vem do domínio: escrever "ele" na mão aqui faria a Abigail
    # ser tratada no masculino no painel dela mesma.
    p_ = dom.agente_pronome
    with st.expander(f"Como conversar com {dom.agente_nome}", expanded=False):
        st.markdown(f"""
**Fale normal.** Um "oi" recebe um "oi" de volta, não o faturamento do mês. E
dá para perguntar sobre o próprio produto — o que é z robusto, por que a
cascata tem resíduo, de onde vem o dado.

**A conversa tem memória.** Pergunte `quanto foi a receita?` e depois só
`e por quê?` — {p_} entende que a pergunta continua sendo sobre receita. O que
você não repetir, {p_} mantém: métrica, quebra e período.

| Você pergunta | O que {p_} faz |
|---|---|
| `quanto foi a receita?` | dá o número do período selecionado |
| `e por quê?` | decompõe a variação e mostra a cascata |
| `e por região?` | refaz a mesma leitura quebrada por região |
| `e no mês passado?` | troca só o período, mantém a métrica |

**Toda resposta de dado vem em três camadas:** o número, o que explica
(segmento, efeito taxa vs mix, tendência) e o que fazer. Quando a métrica tem
conta por trás, a fórmula aparece com os números do período.

**Três coisas que {p_} não faz, de propósito:** não inventa número (todo valor
sai do mesmo motor das abas), não responde fora do catálogo (prefere dizer que
não sabe a chutar) e não ignora os filtros da barra lateral.
        """)

    escolhida = None
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("📋 Análise geral da situação", type="primary",
                     use_container_width=True, key=f"ag_geral_{dom.chave}"):
            escolhida = PERGUNTA_ANALISE_GERAL
    with c2:
        st.caption("Um raio-x do domínio: o que piorou, o que melhorou, o que "
                   "está em alerta, o que a tendência diz e o que fazer "
                   "primeiro.")

    st.markdown("##### Ou comece por uma destas")
    exemplos = sugestoes(dom)
    cols = st.columns(4, gap="small")
    for i, q in enumerate(exemplos[:8]):
        with cols[i % 4]:
            if st.button(q, key=f"ex_{dom.chave}_{i}", use_container_width=True):
                escolhida = q

    if st.session_state[chave]:
        if st.button("Limpar conversa", key=f"limpar_{dom.chave}"):
            st.session_state[chave] = []
            st.session_state[chave_plano] = None
            st.rerun()

    pergunta = st.chat_input(f"Pergunte qualquer coisa para {dom.agente_nome}")
    pergunta = pergunta or escolhida

    for item in st.session_state[chave]:
        avatar = (avatar_uri(dom.agente_imagem) or dom.agente_rosto
                  if item["papel"] == "assistant" else None)
        with st.chat_message(item["papel"], avatar=avatar):
            st.markdown(md(item["texto"]))

    if not pergunta:
        return

    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant",
                         avatar=avatar_uri(dom.agente_imagem) or dom.agente_rosto):
        with st.spinner(f"{dom.agente_nome} consultando..."):
            r = perguntar(con, pergunta, ctx, usar_llm=bool(chave_api()))
        st.markdown(md(r.texto))

        n = len(st.session_state[chave])
        if r.grafico is not None and not r.grafico.empty:
            m = dom.metrica(r.plano["metrica"])
            if r.plano["intencao"] == "causa_raiz":
                st.plotly_chart(g.cascata(r.grafico, m),
                                use_container_width=True,
                                key=f"ag_casc_{dom.chave}_{n}")
            elif r.plano["intencao"] == "tendencia":
                st.plotly_chart(g.linha_temporal(r.grafico, m, coluna="valor"),
                                use_container_width=True,
                                key=f"ag_lin_{dom.chave}_{n}")

        if r.tabela is not None and not r.tabela.empty:
            with st.expander("Números usados na resposta", expanded=True):
                st.dataframe(r.tabela, use_container_width=True,
                             hide_index=True)

        # A fórmula só aparece quando existe conta. Métrica que é uma soma pura
        # não ganha bloco -- "Receita = soma da receita" não ensina nada.
        formula = r.fatos.get("formula_com_numeros")
        if formula:
            with st.expander("A conta por trás do número", expanded=False):
                st.markdown(md(formula))
                m = dom.metrica(r.plano["metrica"])
                st.caption(f"{m.rotulo}: {m.descricao}")

    st.session_state[chave] += [
        {"papel": "user", "texto": pergunta},
        {"papel": "assistant", "texto": r.texto},
    ]
    st.session_state[chave_plano] = r.plano
    st.session_state[chave] = st.session_state[chave][-12:]


# --------------------------------------------------------------------------- #
# Aba: Visão geral
# --------------------------------------------------------------------------- #

def _series_da_metrica(con, dom, mk, inicio, fim, filtros, quebra):
    """Série do total, ou uma série por segmento quando há quebra."""
    if not quebra:
        s = serie_diaria(con, dom, [mk], inicio, fim, filtros)
        return s, None
    d = dom.dimensao(quebra)
    topo = agregar(con, dom, [mk], inicio, fim, dims=[quebra], filtros=filtros,
                   ordenar_por=mk, limite=5).dropna(subset=[mk])
    segmentos = [str(x) for x in topo[d.coluna]] if not topo.empty else []
    if not segmentos:
        return serie_diaria(con, dom, [mk], inicio, fim, filtros), None
    s = agregar(con, dom, [mk], inicio, fim, dims=[quebra], filtros=filtros,
                por_dia=True)
    s["data"] = pd.to_datetime(s["data"])
    s[d.coluna] = s[d.coluna].astype(str)
    return s, (d.coluna, segmentos)


def aba_visao_geral(con, dom, inicio, fim, comp, filtros, quebra):
    st.markdown(cabecalho_comparacao(comp), unsafe_allow_html=True)
    rot_ant, _ = descrever_janela(comp.anterior) if not comp.composta else \
        (comp.rotulo_base(), "")

    valores = comparar(con, dom, dom.metricas_painel, comp, filtros)
    metricas = dom.metricas_painel

    for i in range(0, len(metricas), 4):
        cols = st.columns(4, gap="small")
        for col, mk in zip(cols, metricas[i:i + 4]):
            m = dom.metrica(mk)
            v = valores[mk]
            with col:
                st.markdown(
                    cartao_metrica(m.rotulo, v["atual"], m,
                                   anterior=v["base"],
                                   delta_pct=v["delta_pct"],
                                   rotulo_anterior=rot_ant),
                    unsafe_allow_html=True,
                )

    # Funil da jornada, quando o domínio tem um.
    if dom.chave == "produto":
        st.markdown("---")
        st.markdown("##### A jornada do pedido, ponta a ponta")
        from vulcano.dominios.produto import FUNIL
        passos = []
        base = None
        for coluna, rotulo, taxa_mk in FUNIL:
            n = con.execute(
                f"SELECT COUNT(DISTINCT CASE WHEN {coluna} = 1 THEN order_id END) "
                f"FROM fato WHERE data BETWEEN DATE '{inicio}' AND DATE '{fim}'"
                + ("" if not filtros else
                   "".join(" AND " + c for c in filtros.clausulas(dom)))
            ).fetchone()[0] or 0
            base = base or n or 1
            fatia = f"{n / base * 100:.1f}".replace(".", ",")
            txt = f"{n:,}".replace(",", ".") + f"  ·  {fatia}% do início"
            passos.append((rotulo, float(n), txt))
        st.plotly_chart(g.funil(passos), use_container_width=True,
                        key=f"vg_funil_{dom.chave}")
        st.caption("Cada barra é o número de pedidos que alcançou aquela etapa. "
                   "A queda entre barras é onde a jornada trava.")

    st.markdown("---")
    if quebra:
        st.markdown(f"##### As métricas por dia, quebradas por "
                    f"{dom.dimensao(quebra).rotulo.lower()}")
    else:
        st.markdown("##### As métricas por dia")

    for i in range(0, len(metricas), 2):
        cols = st.columns(2, gap="medium")
        for col, mk in zip(cols, metricas[i:i + 2]):
            m = dom.metrica(mk)
            with col:
                s, quebrado = _series_da_metrica(con, dom, mk, inicio, fim,
                                                 filtros, quebra)
                if s.empty or s[mk].notna().sum() < 2:
                    st.caption(f"{m.rotulo}: sem pontos suficientes no período.")
                    continue
                if quebrado:
                    coluna_dim, segmentos = quebrado
                    fig = g.linhas_por_segmento(s, coluna_dim, mk, m, segmentos,
                                                titulo=m.rotulo, altura=230)
                else:
                    fig = g.mini_serie(s, mk, m, titulo=m.rotulo)
                st.plotly_chart(fig, use_container_width=True,
                                key=f"vg_{mk}_{dom.chave}")

    st.caption("A quebra dos gráficos é escolhida na barra lateral e vale para "
               "todos eles de uma vez. O teto de 5 segmentos não é estético: a "
               "paleta só garante separação para daltonismo até esse ponto.")


# --------------------------------------------------------------------------- #
# Aba: Comparação de períodos
# --------------------------------------------------------------------------- #

def aba_comparacao(con, dom, fim, filtros):
    st.markdown(f"##### Referência: **{descrever_dia(fim)}**")
    st.caption("Todas as métricas do painel, nos quatro níveis de comparação "
               "ao mesmo tempo. Cada coluna diz contra qual data está medindo.")

    comps = {n: montar_preset(n, fim) for n in NIVEIS_COMPARACAO}

    # As datas na cara, antes da tabela: sem elas, "-8%" não quer dizer nada.
    # Rotulo curto e proprio de cada nivel. Cortar o preset no " vs " daria
    # "Dia" em tres das quatro colunas -- os niveis ficariam indistinguiveis
    # justamente no lugar em que a coluna precisa se identificar.
    ROTULOS = {"dia_d1": "Contra ontem", "dia_d7": "Contra D-7",
               "mtd": "Mês acumulado", "dia_media3": "Contra 3 dias iguais"}
    cols = st.columns(len(comps), gap="small")
    for col, (nivel, c) in zip(cols, comps.items()):
        with col:
            st.markdown(
                f"""<div class="vulc-nivel">
                  <div class="rot">{ROTULOS[nivel]}</div>
                  <div class="tit">vs {c.rotulo_base()}</div>
                </div>""", unsafe_allow_html=True)

    resultados = {n: comparar(con, dom, dom.metricas_painel, c, filtros)
                  for n, c in comps.items()}

    # A seta diz a DIREÇÃO (subiu ou desceu) e a cor diz o JULGAMENTO (a favor
    # ou contra o negócio). São duas informações diferentes e é por isso que
    # elas ficam em canais diferentes: cancelamento caindo é ▼ verde, prazo de
    # entrega subindo é ▲ vermelho. Com isso a tabela sozinha responde o que o
    # gráfico de barras respondia, e o gráfico sai.
    ROT_COL = {"dia_d1": "vs D-1", "dia_d7": "vs D-7",
               "mtd": "vs mês ant.", "dia_media3": "vs média 3 iguais"}
    COLS_VAR = [ROT_COL[n] for n in NIVEIS_COMPARACAO]

    linhas, cores = [], []
    for mk in dom.metricas_painel:
        m = dom.metrica(mk)
        linha = {"Métrica": m.rotulo,
                 "Valor no dia": numero(
                     resultados[NIVEIS_COMPARACAO[0]][mk]["atual"], m)}
        cor = {"Métrica": "", "Valor no dia": ""}
        for nivel in NIVEIS_COMPARACAO:
            dp = resultados[nivel][mk]["delta_pct"]
            rot = ROT_COL[nivel]
            bom = julgar(dp, m.bom_quando_sobe)
            if dp is None:
                linha[rot], cor[rot] = "—", f"color: {TINTA_MUDA}"
            elif bom is None:                 # some no arredondamento
                linha[rot] = f"▪ {pct(dp)}"
                cor[rot] = f"color: {TINTA_MUDA}"
            else:
                seta = "▲" if dp > 0 else "▼"
                linha[rot] = f"{seta} {pct(dp)}"
                cor[rot] = (f"color: {JULGA_BOM}; font-weight: 600" if bom
                            else f"color: {JULGA_RUIM}; font-weight: 600")
        linhas.append(linha)
        cores.append(cor)

    tabela = pd.DataFrame(linhas)
    estilos = pd.DataFrame(cores)[tabela.columns]
    st.dataframe(tabela.style.apply(lambda _: estilos, axis=None),
                 use_container_width=True, hide_index=True,
                 height=min(600, 36 * len(tabela) + 44))
    st.caption("A seta é a direção; a cor é o julgamento. Verde é movimento a "
               "favor do negócio e vermelho é contra — por isso cancelamento "
               "caindo aparece ▼ verde e prazo de entrega subindo, ▲ vermelho.")

    st.markdown(
        nota("Um mesmo dia pode parecer catástrofe contra ontem e normalidade "
             "contra a média dos mesmos dias da semana. É por isso que os "
             "quatro níveis aparecem juntos: a escolha da base muda a conclusão "
             "mais do que o dado muda."),
        unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Aba: Causa raiz
# --------------------------------------------------------------------------- #

def aba_causa_raiz(con, dom, dmin, dmax, fim, filtros):
    c1, c2 = st.columns([2, 3])
    with c1:
        mk = st.selectbox("Métrica", list(dom.metricas.keys()),
                          format_func=lambda k: dom.metrica(k).rotulo,
                          key=f"cr_m_{dom.chave}")
        dk = st.selectbox("Decompor por", list(dom.dimensoes.keys()),
                          format_func=lambda k: dom.dimensao(k).rotulo,
                          key=f"cr_d_{dom.chave}")
    with c2:
        modo = st.radio(
            "Comparar",
            ["Dia vs dia anterior", "Semana acumulada vs outra semana",
             "Mês acumulado vs outro mês"],
            key=f"cr_modo_{dom.chave}")

        if modo == "Dia vs dia anterior":
            ref = st.date_input("Dia", value=fim, min_value=dmin,
                                max_value=dmax, key=f"cr_dia_{dom.chave}",
                                format="DD/MM/YYYY")
            ref = ref if isinstance(ref, date) else fim
            comp = contra_dia(ref, ref - timedelta(days=1))
        elif modo == "Semana acumulada vs outra semana":
            ref = st.date_input("Semana atual (qualquer dia dela)", value=fim,
                                min_value=dmin, max_value=dmax,
                                key=f"cr_sem_ref_{dom.chave}",
                                format="DD/MM/YYYY")
            alvo = st.date_input("Comparar com a semana de",
                                 value=max(dmin, fim - timedelta(days=7)),
                                 min_value=dmin, max_value=dmax,
                                 key=f"cr_sem_alvo_{dom.chave}",
                                 format="DD/MM/YYYY")
            ref = ref if isinstance(ref, date) else fim
            alvo = alvo if isinstance(alvo, date) else fim - timedelta(days=7)
            comp = contra_semana(ref, alvo)
        else:
            meses = pd.period_range(dmin, dmax, freq="M")
            rots = [p.strftime("%m/%Y") for p in meses]
            ca, cb = st.columns(2)
            with ca:
                i_ref = st.selectbox("Mês atual", rots, index=len(rots) - 1,
                                     key=f"cr_mes_ref_{dom.chave}")
            with cb:
                i_alvo = st.selectbox("Comparar com", rots,
                                      index=max(0, len(rots) - 2),
                                      key=f"cr_mes_alvo_{dom.chave}")
            p_ref = meses[rots.index(i_ref)]
            p_alvo = meses[rots.index(i_alvo)]
            ref = min(dmax, p_ref.end_time.date())
            comp = contra_mes(ref, p_alvo.start_time.date())

    st.markdown(cabecalho_comparacao(comp), unsafe_allow_html=True)

    m = dom.metrica(mk)
    dec = mod_causa.decompor(con, dom, mk, dk, comp, filtros, top_n=8)

    if dec.total_a != dec.total_a and dec.total_b != dec.total_b:
        st.info(
            f"Não há valor de {m.rotulo} em nenhum dos dois períodos."
            + (" Em crédito isso costuma ser safra ainda imatura: a métrica só "
               "existe depois do MOB exigido." if dom.simulado else ""))
        return

    st.plotly_chart(
        g.cascata(mod_causa.dados_cascata(dec), m,
                  titulo=f"{m.rotulo}: de onde veio a variação"),
        use_container_width=True, key=f"cr_casc_{dom.chave}")

    st.markdown("##### A conta, em português")
    for linha in mod_causa.explicar(dec):
        st.markdown(md(f"- {linha}"))
    if dec.aviso:
        st.markdown(nota(dec.aviso), unsafe_allow_html=True)

    st.caption(md(
        f"Soma das contribuições: "
        f"{numero(float(dec.df['contribuicao'].sum()), m, sinal=True)} · "
        f"Variação total: {numero(dec.delta, m, sinal=True)} · "
        f"Resíduo: {numero(dec.residuo, m, sinal=True)}"))


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

def render_dashboard(chave: str) -> None:
    dom = obter(chave)
    con, (dmin, dmax) = _conexao(chave)

    inicio, fim, preset, filtros, quebra = barra_lateral(dom, dmin, dmax)
    comp = montar_preset(preset, fim)

    esq, dir_ = st.columns([5, 1])
    with esq:
        st.markdown(f"## {dom.nome}")
        st.caption(dom.subtitulo)
    with dir_:
        st.markdown(f"<div style='text-align:right;padding-top:18px'>"
                    f"{selo(dom.simulado)}</div>", unsafe_allow_html=True)

    if dom.simulado:
        st.markdown(nota(f"<b>Este domínio usa dado simulado.</b> {dom.fonte}"),
                    unsafe_allow_html=True)

    abas = st.tabs(["Alertas",
                    f"Pergunte {dom.agente_ao} {dom.agente_nome}",
                    "Visão geral",
                    "Comparação de períodos", "Causa raiz", "Sobre os dados"])

    with abas[0]:
        aba_alertas(con, dom, fim, filtros)
    with abas[1]:
        aba_agente(con, dom, inicio, fim, preset, filtros, quebra)
    with abas[2]:
        aba_visao_geral(con, dom, inicio, fim, comp, filtros, quebra)
    with abas[3]:
        aba_comparacao(con, dom, fim, filtros)
    with abas[4]:
        aba_causa_raiz(con, dom, dmin, dmax, fim, filtros)
    with abas[5]:
        st.markdown("#### Procedência")
        st.markdown(dom.fonte)
        if dom.notas:
            st.markdown("#### Ressalvas metodológicas")
            for n in dom.notas:
                st.markdown(f"- {n}")
        st.markdown("#### Catálogo de métricas")
        st.dataframe(pd.DataFrame([{
            "Métrica": m.rotulo, "Chave": k,
            "Conta": m.formula or "soma direta",
            "Melhora": "subindo" if m.bom_quando_sobe else "descendo",
            "Definição": m.descricao,
        } for k, m in dom.metricas.items()]), use_container_width=True,
            hide_index=True)
        st.markdown("#### Catálogo de dimensões")
        st.dataframe(pd.DataFrame([{
            "Dimensão": d.rotulo, "Chave": k,
            "Única por": ", ".join(d.unica_por) or "—",
            "Definição": d.descricao,
        } for k, d in dom.dimensoes.items()]), use_container_width=True,
            hide_index=True)
        st.caption(f"Dados de {dmin.strftime('%d/%m/%Y')} a "
                   f"{dmax.strftime('%d/%m/%Y')}.")


# --------------------------------------------------------------------------- #

def main() -> None:
    st.session_state.setdefault("dominio", None)
    atual = st.session_state["dominio"]
    if atual is None:
        render_capa()
    else:
        render_dashboard(atual)


if __name__ == "__main__":
    main()
