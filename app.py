"""
Analytics com agente — quatro domínios, um motor.

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
from vulcano import i18n
from vulcano import analise as mod_analise
from vulcano import causa_raiz as mod_causa
from vulcano import graficos as g
from vulcano.agente import (Contexto, chave_api, pergunta_analise_geral,
                            perguntar, sugestoes)
from vulcano.dados import (Filtros, agregar, comparar, conectar,
                           periodo_disponivel, serie_diaria,
                           valores_da_dimensao)
from vulcano.dominios import listar, obter
from vulcano.estilo import (CSS, asset_uri, avatar_uri, cabecalho_comparacao,
                            cartao_alerta, cartao_metrica, descrever_janela,
                            md, nota, rosto, selo, selo_construcao)
from vulcano.formatacao import julgar, numero, pct
from vulcano.i18n import L, V
from vulcano.graficos import JULGA_BOM, JULGA_RUIM, TINTA_MUDA
from vulcano.periodos import (NIVEIS_COMPARACAO, PRESETS, contra_dia,
                              contra_mes, contra_semana, descrever_dia,
                              montar_preset, rotulo_preset)
from vulcano.semantica import Dominio

import telas_pld

# Nome da plataforma. PROVISÓRIO — cada domínio já tem seu próprio agente, com
# nome e rosto declarados no arquivo do domínio (vulcano/dominios/*.py). Falta
# só o nome do conjunto; trocar aqui muda a capa inteira.
MARCA = "Analytics com agente"
MARCA_EN = "Analytics with agents"
MARCA_ROSTO = "◆"


def marca() -> str:
    return L(MARCA, MARCA_EN)

# Domínios ainda em ajuste. Ficam publicados e navegáveis, com selo na capa e
# aviso no topo do painel: esconder até "ficar pronto" é o que faz um projeto
# de portfólio nunca sair do lugar. Tirar daqui é o passo único para dizer que
# terminou -- foi o que aconteceu com PLD e com People em set/2026.
EM_CONSTRUCAO: set[str] = set()

st.set_page_config(page_title=f"{MARCA} · {MARCA_EN}", page_icon="📊",
                   layout="wide")
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Língua
# --------------------------------------------------------------------------- #
#
# A língua mora no session_state e espelha na URL (?lang=en). O espelho é o
# que permite mandar para um recrutador de fora o link que já abre em inglês,
# sem pedir para ninguém achar o botão.

def _iniciar_idioma() -> None:
    if "idioma" not in st.session_state:
        pedido = str(st.query_params.get("lang", "pt")).lower()
        st.session_state["idioma"] = "en" if pedido.startswith("en") else "pt"
    i18n.definir(st.session_state["idioma"])


def _ao_trocar_idioma() -> None:
    novo = st.session_state.get("_seletor_idioma")
    # Clicar de novo na língua que já está ativa DESMARCA o controle (volta
    # None). Isso não é pedido de trocar de língua -- fica como estava.
    if novo in i18n.IDIOMAS:
        st.session_state["idioma"] = novo
        st.query_params["lang"] = novo


def seletor_idioma() -> None:
    """O botão PT/EN. Aparece na capa e na barra lateral dos painéis."""
    st.session_state["_seletor_idioma"] = st.session_state["idioma"]
    st.segmented_control(
        "Idioma · Language", options=["pt", "en"],
        format_func=lambda k: {"pt": "🇧🇷 Português", "en": "🇺🇸 English"}[k],
        key="_seletor_idioma", on_change=_ao_trocar_idioma,
        label_visibility="collapsed", selection_mode="single")


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

ARQUITETURA_EN = [
    ("01", "Semantic layer",
     "Each domain declares its metrics and dimensions in a single file: each "
     "metric's SQL, whether it's a ratio, whether up is good, and which "
     "entity it counts. Tabs and agent read from here, so there is no path by "
     "which the chat answers a number different from the chart."),
    ("02", "Calculation engine",
     "DuckDB over Parquet, with SQL built from the declaration — never from "
     "free text. Numerator and denominator come out separately, which is "
     "what later allows splitting a ratio into rate effect and mix effect."),
    ("03", "Agent",
     "The model plans, Python calculates. The LLM turns the question into a "
     "plan with known keys, the engine runs it, and the LLM only comes back to "
     "narrate on top of numbers already calculated. It never sees the "
     "database or writes SQL."),
    ("04", "A reading, not just a number",
     "Every answer comes in three layers: the number, what explains it "
     "(segment, rate vs mix effect, trend) and what to do. All three are "
     "derived from rules over the numbers, so they exist even without an API "
     "key."),
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
    ("Por que falso positivo só conta alerta maduro",
     "Em PLD é o mesmo problema da safra com outra roupa: num alerta de ontem, "
     "só os casos fáceis já foram decididos — e caso fácil costuma ser "
     "descarte. Falso positivo, conversão e tempo de análise só contam alertas "
     "com 45 dias ou mais, o prazo máximo de análise da Circular 3.978. O que "
     "passou disso sem decisão não some: vira 'fora do prazo'."),
    ("Por que a fila de PLD tem prioridade explicável, e não modelo",
     "A analista precisa defender a ordem da fila na frente do auditor, e 'o "
     "modelo deu 0,83' não se defende. A prioridade é uma soma de fatores "
     "nomeados — gravidade da regra, valor, regras distintas no mesmo cliente, "
     "histórico, risco — e a conta aparece no dossiê. O prazo anda em coluna "
     "separada, para o caso médio que vence amanhã não sumir. E a decisão de "
     "comunicar nunca é do agente."),
    ("Por que turnover é sobre pessoa-dia, e não sobre o headcount do mês",
     "O \"desligados ÷ headcount do fim do mês\" de planilha muda de base com "
     "quem acabou de entrar e não compara meses de tamanhos diferentes. Com "
     "uma linha por pessoa por dia ativo, turnover vira desligamentos sobre "
     "a base exposta, anualizado — e o peso de cada área nessa base vira o "
     "efeito mix da cascata sem nenhuma conta especial. Headcount, pelo mesmo "
     "grão, é média dos dias: somar 30 dias contaria cada pessoa 30 vezes."),
    ("Por que a Tomoyo nunca fala de uma pessoa",
     "People Analytics que aponta quem vai sair vira vigilância, e no mês "
     "seguinte a pesquisa de clima para de ter resposta sincera — o que "
     "destrói o sinal que ela usa. Então o risco de saída é lido por grupo "
     "(área × nível), com uma soma de sinais nomeados que aparece na tela, e "
     "recorte com menos de 10 pessoas não aparece: com menos que isso, o "
     "salário médio do grupo é o salário de alguém."),
]


DECISOES_EN = [
    ("Why not text-to-SQL",
     "Letting the model write free SQL causes three problems that only show "
     "up once the tool is really used: the same question returns two numbers "
     "on different days, grain errors slip through silently, and there is "
     "nothing to validate. By restricting the output to a plan with known "
     "keys, an impossible question fails validation and the agent says what "
     "it doesn't know — instead of getting the syntax right and the math "
     "wrong."),
    ("Why the alert brings the likely cause",
     "An alert that only says 'revenue dropped' sends people to another tab "
     "to find out where. Here the decomposition runs along with it. And it "
     "looks for the DISPROPORTIONATE segment, not the largest: saying credit "
     "card carries 82% of the deviation is useless when credit card is "
     "already 80% of revenue every day. What informs is the segment that "
     "weighs much more in the deviation than it does normally."),
    ("Why the waterfall exposes the residual",
     "A distinct-count metric split by a finer-grained dimension doesn't "
     "close: the same order lands in two segments. The residual is computed, "
     "shown and explained, instead of being spread across the bars to make "
     "the chart look nice."),
    ("Why rate effect and mix effect are kept apart",
     "Average ticket falling because each segment got cheaper and average "
     "ticket falling because who bought changed are opposite diagnoses: one "
     "calls for action in the segment, the other in acquisition. A simple "
     "average can't tell them apart, which is why the ratio decomposition "
     "splits into rate, mix and interaction."),
    ("Why the alert has two cuts",
     "Small segments blow the z-score all the time — relative change on a "
     "small base is huge by construction. Without the relevance cut the "
     "dashboard fires dozens of alerts a day, nobody reads them, and the "
     "product dies. Every alert passes two tests: being unusual AND moving "
     "the total enough to be worth the call."),
    ("Why a young vintage shows up empty, never zero",
     "In credit, delinquency takes months to show up. Filling an immature "
     "vintage with zero is what makes a dashboard show risk falling exactly "
     "when it hasn't had time to happen. Censoring is by whole vintage: the "
     "vintage only counts once its last contract has completed the MOB."),
    ("Why false positive only counts mature alerts",
     "In AML it's the vintage problem in different clothes: for yesterday's "
     "alert, only the easy cases have been decided — and easy cases tend to "
     "be dismissals. False positive, conversion and review time only count "
     "alerts 45+ days old, Circular 3,978's maximum review deadline. What "
     "passed that without a decision doesn't disappear: it becomes "
     "'overdue'."),
    ("Why the AML queue has an explainable priority, not a model",
     "The analyst has to defend the queue's order in front of the auditor, "
     "and 'the model said 0.83' can't be defended. Priority is a sum of named "
     "factors — rule severity, amount, distinct rules on the same client, "
     "history, risk — and the math shows up in the case file. The deadline "
     "runs in a separate column, so the medium case due tomorrow doesn't "
     "disappear. And the decision to report is never the agent's."),
    ("Why turnover is over person-days, not the month's headcount",
     "The spreadsheet's \"leavers ÷ end-of-month headcount\" changes base with "
     "whoever just joined and doesn't compare months of different lengths. "
     "With one row per person per active day, turnover becomes terminations "
     "over the exposed base, annualized — and each area's weight in that base "
     "becomes the waterfall's mix effect with no special math. Headcount, on "
     "the same grain, is the average of the days: summing 30 days would count "
     "each person 30 times."),
    ("Why Tomoyo never talks about a person",
     "People Analytics that points at who will leave becomes surveillance, "
     "and the next month the engagement survey stops getting honest answers "
     "— which destroys the signal it uses. So flight risk is read by group "
     "(area × level), with a sum of named signals shown on screen, and slices "
     "with fewer than 10 people don't show up: with fewer than that, the "
     "group's average salary is someone's salary."),
]


def render_capa() -> None:
    # Um respiro antes do seletor: sem ele, o cabeçalho fixo do Streamlit
    # come a borda de cima do botão.
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    _, c_idioma = st.columns([5, 1.3])
    with c_idioma:
        seletor_idioma()

    agentes = " · ".join(d.agente_nome for d in listar())
    n = len(listar())
    quantos = L({3: "Três", 4: "Quatro", 5: "Cinco"}.get(n, str(n)),
                {3: "Three", 4: "Four", 5: "Five"}.get(n, str(n)))
    # O elenco e opcional de proposito: sem o arquivo, o cabecalho volta a ser
    # so o texto, em vez de mostrar imagem quebrada.
    uri_elenco = asset_uri("elenco.webp")
    alt = L(f"Os agentes do painel: {agentes}",
            f"The dashboard's agents: {agentes}")
    elenco = (f'<div class="elenco"><img src="{uri_elenco}" alt="{alt}"></div>'
              if uri_elenco else "")
    sub = L(
        f"""{quantos} painéis, um motor: gráficos, comparação de períodos, causa raiz
          com cascata, alertas que já vêm com o provável motivo, e um agente que
          responde em linguagem natural — do analista júnior ao executivo.
          <br><br>
          Cada domínio tem o <b>seu</b> agente, com nome, rosto e vocabulário
          próprios: {agentes}. Quem responde sobre crédito não é quem responde
          sobre marketing, porque o vocabulário, as ressalvas e o que conta
          como resposta boa são outros. O motor por baixo é o mesmo.""",
        f"""{quantos} dashboards, one engine: charts, period comparison, root
          cause with a waterfall, alerts that already come with the likely
          cause, and an agent that answers in natural language — from junior
          analyst to executive.
          <br><br>
          Each domain has <b>its own</b> agent, with its own name, face and
          vocabulary: {agentes}. Whoever answers about credit is not whoever
          answers about marketing, because the vocabulary, the caveats and
          what counts as a good answer are different. The engine underneath
          is the same.""")
    st.markdown(
        f"""<div class="vulc-hero">
        <div class="texto">
        <h1>{MARCA_ROSTO} {marca()}</h1>
        <div class="sub">
          {sub}
        </div></div>{elenco}</div>""",
        unsafe_allow_html=True,
    )

    st.markdown(L("#### Escolha um domínio", "#### Pick a domain"))
    cols = st.columns(len(listar()), gap="small")
    for col, dom in zip(cols, listar()):
        with col:
            # Os selos entram numa string só. Se o selo de obra virasse uma
            # linha própria, o domínio sem obra deixaria uma linha em branco no
            # meio do HTML, e o markdown do Streamlit trataria o que vem depois
            # como bloco de código -- os </div> apareceriam escritos na tela.
            selos = selo(dom.simulado) + (
                selo_construcao() if dom.chave in EM_CONSTRUCAO else "")
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
                                  font-weight:650">{L("Agente", "Agent")}</div>
                      <div style="font-size:1.02rem;font-weight:640;
                                  color:#0f1b2d">{dom.agente_nome}</div>
                    </div>
                  </div>
                  <div style="margin-top:12px">{selos}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.write("")
            if dom.chave in EM_CONSTRUCAO:
                rotulo = L(f"Abrir {dom.nome} (em construção)",
                           f"Open {dom.nome} (under construction)")
            else:
                rotulo = L(f"Abrir {dom.nome}", f"Open {dom.nome}")
            if st.button(rotulo, key=f"btn_{dom.chave}",
                         use_container_width=True, type="primary"):
                _ir_para(dom.chave)

    st.divider()

    st.markdown(L("#### O problema que este produto resolve",
                  "#### The problem this product solves"))
    st.markdown(L(
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
domínios, para mostrar a arquitetura e as decisões técnicas por trás dele.

O quarto, **Compliance e PLD**, leva o mesmo motor para onde a pergunta muda
de natureza: além de "quantos alertas e quanto vira falso positivo", a analista
precisa saber **quem**, especificamente, se enquadra em qual situação da Carta
Circular 4.001 e em quanto tempo vence o prazo de análise. A Ravena responde
as duas — o agregado pelo motor, o cliente a cliente pela fila e pelo dossiê.

O quinto, **People Analytics**, leva o motor para gente — onde a regra muda de
novo, só que ao contrário: a Tomoyo **nunca** desce ao indivíduo. Ela lê
turnover, clima, contratação e remuneração por grupo, separa o gap salarial de
cargo do gap de composição e procura o sinal que vem antes da saída — o clima
que caiu, a promoção que não saiu — porque depois do pedido de demissão já é
tarde.
        """,
        """
Every area that depends on data has the same queue: someone needs a number,
opens a ticket with the analytics team, and the decision waits two days for an
answer that was a query. Whoever is in a hurry decides without the data;
whoever waits decides late.

A traditional dashboard answers the questions someone foresaw when building
it. The next question — *why* it dropped, *where* it dropped, whether it was
already dropping before — goes back to the queue.

The first of these agents, Vulcano, was born at Petlove to close that queue:
besides the charts, it breaks down the change, fires an alert on its own when
something breaks pattern and answers questions in natural language, all in the
same place. This public version rebuilds the product on open data and extends
it to other domains, to show the architecture and the technical decisions
behind it.

The fourth, **Compliance & AML**, takes the same engine to where the question
changes nature: beyond "how many alerts and how many become false positives",
the analyst needs to know **who**, specifically, falls under which situation of
Brazil's Central Bank Circular Letter 4,001 and when the review deadline
expires. Ravena answers both — the aggregate through the engine, client by
client through the queue and the case file.

The fifth, **People Analytics**, takes the engine to people — where the rule
changes again, only the other way around: Tomoyo **never** goes down to the
individual. She reads turnover, engagement, hiring and pay by group, separates
the same-job pay gap from the composition gap and looks for the signal that
comes before an exit — the engagement that dropped, the promotion that didn't
happen — because after the resignation letter it's too late.
        """))

    st.markdown(L("#### Como é feito", "#### How it's built"))
    cols = st.columns(4, gap="small")
    for col, (n, titulo, texto) in zip(cols, L(ARQUITETURA, ARQUITETURA_EN)):
        with col:
            st.markdown(
                f"""<div class="vulc-arq"><div class="n">{n}</div>
                <h4>{titulo}</h4><p>{texto}</p></div>""",
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown(L("#### Decisões técnicas que valem discussão",
                  "#### Technical decisions worth discussing"))
    decisoes = L(DECISOES, DECISOES_EN)
    for i in range(0, len(decisoes), 2):
        cols = st.columns(2, gap="medium")
        for col, (titulo, texto) in zip(cols, decisoes[i:i + 2]):
            with col:
                with st.expander(titulo, expanded=False):
                    st.write(texto)

    st.write("")
    st.markdown(L("#### Procedência dos dados", "#### Where the data comes from"))
    for dom in listar():
        st.markdown(md(f"**{dom.nome}** — {dom.fonte}"))
    st.caption(L(
        "Stack: Python, DuckDB, pandas, Plotly, Streamlit e a biblioteca da "
        "OpenAI para o agente. Todo o código está no repositório.",
        "Stack: Python, DuckDB, pandas, Plotly, Streamlit and the OpenAI "
        "library for the agent. All the code is in the repository."))


# --------------------------------------------------------------------------- #
# Barra lateral
# --------------------------------------------------------------------------- #

def barra_lateral(dom: Dominio, dmin: date, dmax: date):
    with st.sidebar:
        seletor_idioma()
        st.markdown(f"### {dom.nome}")
        if st.button(L("← Voltar para a capa", "← Back to the home page"),
                     use_container_width=True):
            _ir_para(None)

        st.markdown("---")
        st.markdown(L("#### Período", "#### Period"))
        # As opções são chaves, e o texto vem do format_func: trocar de
        # língua não pode trocar o VALOR guardado no widget, senão o modo
        # escolhido se perde no meio da conversa.
        modos = {"ultimos": L("Últimos N dias", "Last N days"),
                 "mes": L("Mês", "Month"),
                 "livre": L("Intervalo livre", "Custom range")}
        modo = st.radio(
            L("Modo", "Mode"), list(modos), format_func=modos.get,
            key=f"modo_{dom.chave}_k", label_visibility="collapsed",
        )
        fmt = i18n.formato_data_widget()

        if modo == "ultimos":
            n = st.slider(L("Quantos dias", "How many days"), 7, 180, 90,
                          step=7, key=f"ndias_{dom.chave}")
            ref = st.date_input(L("Até", "Up to"), value=dmax, min_value=dmin,
                                max_value=dmax, key=f"ref_{dom.chave}",
                                format=fmt)
            ref = ref if isinstance(ref, date) else dmax
            inicio, fim = max(dmin, ref - timedelta(days=n - 1)), ref
        elif modo == "mes":
            meses = [str(p) for p in pd.period_range(dmin, dmax, freq="M")]
            escolha = st.selectbox(
                L("Mês", "Month"), meses, index=len(meses) - 1,
                format_func=lambda k: i18n.mes(pd.Period(k).start_time.date()),
                key=f"mes_{dom.chave}_k")
            p = pd.Period(escolha)
            inicio = max(dmin, p.start_time.date())
            fim = min(dmax, p.end_time.date())
        else:
            faixa = st.date_input(
                L("Intervalo", "Range"),
                value=(max(dmin, dmax - timedelta(days=89)), dmax),
                min_value=dmin, max_value=dmax, key=f"faixa_{dom.chave}",
                format=fmt,
            )
            if isinstance(faixa, tuple) and len(faixa) == 2:
                inicio, fim = faixa
            else:
                inicio, fim = max(dmin, dmax - timedelta(days=89)), dmax

        st.caption(L(f"{descrever_dia(inicio)} até {descrever_dia(fim)} · "
                     f"{(fim - inicio).days + 1} dias",
                     f"{descrever_dia(inicio)} to {descrever_dia(fim)} · "
                     f"{(fim - inicio).days + 1} days"))

        st.markdown(L("#### Comparar com", "#### Compare with"))
        chaves = list(PRESETS.keys())
        # Em Compliance o mês corrente ainda não tem taxa de decisão (alerta
        # recente não amadureceu), e abrir o painel com quatro cartões vazios
        # é a pior primeira impressão. 90 dias alcança alertas maduros.
        padrao = "ultimos_90" if dom.chave == "pld" else "mes_fechado"
        preset = st.selectbox(
            L("Comparação", "Comparison"), chaves, index=chaves.index(padrao),
            format_func=rotulo_preset, key=f"preset_{dom.chave}",
            label_visibility="collapsed",
        )

        st.markdown(L("#### Quebrar os gráficos por", "#### Split the charts by"))
        opcoes_quebra = ["(sem quebra)"] + dom.dims_filtro
        quebra = st.selectbox(
            L("Quebra", "Split"), opcoes_quebra, index=0,
            format_func=lambda k: (L("Sem quebra — só o total",
                                     "No split — total only")
                                   if k == "(sem quebra)"
                                   else dom.dimensao(k).rotulo),
            key=f"quebra_{dom.chave}", label_visibility="collapsed",
        )
        quebra = None if quebra == "(sem quebra)" else quebra
        if quebra:
            st.caption(L("Cada gráfico passa a mostrar os 5 maiores segmentos "
                         "desta dimensão, em vez do total.",
                         "Each chart now shows this dimension's 5 largest "
                         "segments instead of the total."))

        st.markdown("---")
        st.markdown(L("#### Filtros", "#### Filters"))
        valores: dict[str, list[str]] = {}

        def _campo(dk: str) -> None:
            d = dom.dimensao(dk)
            opcoes = _valores(dom.chave, dk)
            # O valor guardado é o do dado (em português); o que muda com a
            # língua é só o texto mostrado.
            sel = st.multiselect(d.rotulo, opcoes, default=[],
                                 format_func=V,
                                 key=f"f_{dom.chave}_{dk}",
                                 placeholder=L(f"Todos ({len(opcoes)})",
                                               f"All ({len(opcoes)})"),
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
            rot = L(f"Mais filtros ({len(extras)})",
                    f"More filters ({len(extras)})")
            if ativos:
                rot = L(f"Mais filtros — {ativos} ativo(s)",
                        f"More filters — {ativos} active")
            with st.expander(rot, expanded=bool(ativos)):
                for dk in extras:
                    _campo(dk)

        filtros = Filtros(valores)
        if filtros:
            st.caption(L(f"Filtro ativo: {filtros.resumo(dom)}",
                         f"Active filter: {filtros.resumo(dom)}"))
            st.caption(L("Os filtros valem para todas as abas E para o agente.",
                         "Filters apply to every tab AND to the agent."))

        st.markdown("---")
        if chave_api():
            st.caption(L("🔑 Chave de API detectada: o agente usa o modelo para "
                         "interpretar e narrar. O cálculo continua no Python.",
                         "🔑 API key detected: the agent uses the model to "
                         "interpret and narrate. The math stays in Python."))
        else:
            st.caption(L("Sem chave de API: o agente roda com o interpretador "
                         "determinístico. Tudo funciona; a linguagem fica menos "
                         "flexível.",
                         "No API key: the agent runs on the deterministic "
                         "interpreter. Everything works; the language is less "
                         "flexible."))

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
                {L("está de olho", "is keeping watch")}</span></div>
            <div class="papel">{L(
                "Varro todas as métricas do painel contra o histórico e contra "
                "os limites combinados, segmento a segmento — e trago o "
                "provável motivo junto com o aviso.",
                "I sweep every metric on the dashboard against history and "
                "against the agreed limits, segment by segment — and bring the "
                "likely cause along with the warning.")}</div>
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
            L("Dia analisado", "Day analyzed"), value=padrao,
            format=i18n.formato_data_widget(),
            key=f"al_d_{dom.chave}_{st.session_state[chave_geracao]}")
        ref = ref if isinstance(ref, date) else fim
    with c2:
        z = st.slider(L("Quão estranho precisa ser", "How unusual it must be"),
                      2.0, 5.0, 3.0, 0.25,
                      key=f"al_z_{dom.chave}",
                      help=L("Quantos desvios fora do normal o dia precisa estar "
                             "para virar alerta. O 'normal' é a mediana dos 56 "
                             "dias anteriores. Corte 3 = três desvios.",
                             "How many deviations from normal the day must be "
                             "to become an alert. 'Normal' is the median of the "
                             "previous 56 days. Cut 3 = three deviations."))
    with c3:
        mat = st.slider(L("Quão relevante precisa ser", "How relevant it must be"),
                        0.0, 0.20, 0.03, 0.01,
                        format="%.2f", key=f"al_m_{dom.chave}",
                        help=L("Quanto o segmento precisa pesar no total do dia. "
                               "Corte 3% = só avisa se o segmento mover ao menos "
                               "3% da métrica.",
                               "How much the segment must weigh in the day's "
                               "total. Cut 3% = only warns if the segment moves "
                               "at least 3% of the metric."))

    al = mod_alertas.varrer(con, dom, ref, filtros, z_limite=z,
                            materialidade=mat)
    st.markdown(md(f"#### {mod_alertas.resumir(al, ref)}"))

    if not al:
        anterior = mod_alertas.ultimo_dia_com_alerta(con, dom, ref, filtros,
                                                     z_limite=z)
        if anterior and anterior != ref:
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(L(f"O movimento mais recente antes desse dia foi em "
                              f"**{descrever_dia(anterior)}**.",
                              f"The most recent movement before that day was on "
                              f"**{descrever_dia(anterior)}**."))
            with c2:
                if st.button(L("Ver esse dia", "See that day"),
                             key=f"al_ir_{dom.chave}",
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

    # Em Compliance, o alerta da operação ("o volume da R02 subiu") não serve
    # sozinho: a pergunta seguinte é sempre "de quem?". Os clientes do dia
    # entram logo abaixo dos cartões, com o caminho para o dossiê.
    if dom.chave == "pld":
        telas_pld.bloco_alertas(con, dom, ref, filtros)

    # A explicação vem DEPOIS dos alertas: quem abre a aba quer o que aconteceu,
    # não a metodologia. Quem quiser entender os cortes rola até aqui.
    st.markdown("---")
    st.markdown(L("##### Como um alerta nasce", "##### How an alert is born"))
    e1, e2 = st.columns(2, gap="large")
    with e1:
        st.markdown(L(
            "**Duas origens diferentes.** Um alerta pode nascer de *desvio do "
            "histórico* — o dia está fora do que essa métrica costuma ser — ou "
            "de *limite de negócio*, um patamar fixo combinado com a área, que "
            "dispara mesmo quando o histórico já se acostumou com o problema. "
            "Os dois aparecem misturados na lista, com a origem escrita no topo "
            "de cada cartão.",
            "**Two different origins.** An alert can be born from a *deviation "
            "from history* — the day is outside what this metric usually is — "
            "or from a *business limit*, a fixed threshold agreed with the "
            "team, which fires even when history has gotten used to the "
            "problem. Both appear mixed in the list, with the origin written at "
            "the top of each card."
        ))
    with e2:
        st.markdown(L(
            "**Dois cortes, não um.** *Quão estranho* mede o desvio contra a "
            "mediana e o MAD dos 56 dias anteriores — mediana em vez de média "
            "porque a média é puxada pelo próprio pico que se quer detectar. "
            "*Quão relevante* mede o peso do segmento no total: sem ele, uma "
            "categoria de 0,3% da receita estoura o corte toda semana. Baixe a "
            "relevância para zero e veja o painel encher de ruído — é a "
            "demonstração de por que o segundo corte existe.",
            "**Two cuts, not one.** *How unusual* measures the deviation "
            "against the median and MAD of the previous 56 days — median "
            "instead of mean because the mean is pulled by the very peak we "
            "want to detect. *How relevant* measures the segment's weight in "
            "the total: without it, a category that is 0.3% of revenue blows "
            "the cut every week. Drop relevance to zero and watch the "
            "dashboard fill with noise — that's the demonstration of why the "
            "second cut exists."
        ))

    # A tabela fecha a página. Os cartões acima são a leitura; isto aqui é a
    # conferência — quem quiser auditar o observado contra o esperado rola até
    # o fim e vê tudo, inclusive o que não coube nos dez primeiros cartões.
    if al:
        st.markdown("---")
        st.markdown(L("##### Todos os alertas do dia, para conferir",
                      "##### All of the day's alerts, for checking"))
        st.caption(L(
            "Os cartões acima mostram os dez primeiros, com o motivo provável. "
            "Aqui está a lista inteira, com o número observado, o esperado pelo "
            "histórico e o z robusto de cada linha.",
            "The cards above show the first ten, with the likely cause. Here "
            "is the full list, with the observed number, the one expected from "
            "history and each row's robust z."
        ))
        st.dataframe(pd.DataFrame([{
            L("Severidade", "Severity"): mod_alertas.nome_severidade(a.severidade),
            L("Origem", "Origin"): (
                L("desvio do histórico", "deviation from history")
                if a.tipo == "anomalia"
                else L("limite de negócio", "business limit")),
            L("Métrica", "Metric"): dom.metrica(a.chave_metrica).rotulo,
            L("Segmento", "Segment"): V(a.segmento) if a.segmento else "— total —",
            L("Observado", "Observed"): numero(a.observado,
                                               dom.metrica(a.chave_metrica)),
            L("Esperado", "Expected"): numero(a.esperado,
                                              dom.metrica(a.chave_metrica)),
            L("z robusto", "robust z"): (f"{a.z:+.1f}" if a.tipo == "anomalia"
                                         else "—"),
        } for a in al]), use_container_width=True, hide_index=True,
            height=min(600, 36 * len(al) + 40))


# --------------------------------------------------------------------------- #
# Aba: agente
# --------------------------------------------------------------------------- #

def _guia_conversa(dom) -> str:
    """O "como conversar" do agente deste domínio, na língua ativa.

    O roteiro de exemplo sai do arquivo do domínio (`guia_conversa`), e não de
    uma tabela única: cada agente ensina a perguntar o que ELE sabe responder.
    """
    # O pronome vem do domínio: escrever "ele" na mão aqui faria a Abigail
    # ser tratada no masculino no painel dela mesma.
    p_ = dom.agente_pronome
    p_en = "she" if dom.agente_genero == "f" else "he"
    linhas = "\n".join(f"| `{q}` | {o} |" for q, o in dom.guia_conversa)
    dica = f"\n\n{dom.dica_conversa}" if dom.dica_conversa else ""
    return L(f"""
**Fale normal.** Um "oi" recebe um "oi" de volta, não um número que você não
pediu. E dá para perguntar sobre o próprio produto — o que é z robusto, por que
a cascata tem resíduo, de onde vem o dado.

**A conversa tem memória.** O que você não repetir, {p_} mantém: métrica,
quebra e período. É por isso que, logo depois de uma pergunta de número, só
`e por quê?` já funciona.

| Você pergunta | O que {p_} faz |
|---|---|
{linhas}
{dica}

**Toda resposta de dado vem em três camadas:** o número, o que explica
(segmento, efeito taxa vs mix, tendência) e o que fazer. Quando a métrica tem
conta por trás, a fórmula aparece com os números do período.

**Três coisas que {p_} não faz, de propósito:** não inventa número (todo valor
sai do mesmo motor das abas), não responde fora do catálogo (prefere dizer que
não sabe a chutar) e não ignora os filtros da barra lateral.

*{dom.agente_nome} entende perguntas em português e em inglês; a resposta
sai na língua escolhida no botão PT/EN.*
""", f"""
**Talk normally.** A "hi" gets a "hi" back, not a number you didn't ask for.
And you can ask about the product itself — what a robust z is, why the
waterfall has a residual, where the data comes from.

**The conversation has memory.** Whatever you don't repeat, {p_en} keeps:
metric, split and period. That's why, right after a number question, just
`and why?` already works.

| You ask | What {p_en} does |
|---|---|
{linhas}
{dica}

**Every data answer comes in three layers:** the number, what explains it
(segment, rate vs mix effect, trend) and what to do. When the metric has math
behind it, the formula shows up with the period's numbers.

**Three things {p_en} doesn't do, on purpose:** make up numbers (every value
comes from the same engine as the tabs), answer outside the catalog (would
rather say it doesn't know than guess) or ignore the sidebar filters.

*{dom.agente_nome} understands both English and Portuguese; the answer comes
in the language picked on the PT/EN button.*
""")


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
    st.markdown(md(L(
        f"Perguntando no período **{i18n.data(inicio)} a {i18n.data(fim)}**, "
        f"com filtro **{filtros.resumo(dom)}**. "
        f"{dom.agente_nome} usa exatamente o mesmo motor das abas — se o número "
        f"divergir do gráfico, é bug, não interpretação.",
        f"Asking about **{i18n.data(inicio)} to {i18n.data(fim)}**, "
        + (f"with filter **{filtros.resumo(dom)}**. " if filtros
           else "with **no filter**. ")
        + f"{dom.agente_nome} uses exactly the "
        f"same engine as the tabs — if the number differs from the chart, "
        f"it's a bug, not an interpretation."
    )))

    with st.expander(L(f"Como conversar com {dom.agente_nome}",
                       f"How to talk to {dom.agente_nome}"), expanded=False):
        st.markdown(md(_guia_conversa(dom)))

    escolhida = None
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button(L("📋 Análise geral da situação",
                       "📋 Overall analysis of the situation"), type="primary",
                     use_container_width=True, key=f"ag_geral_{dom.chave}"):
            escolhida = pergunta_analise_geral()
    with c2:
        st.caption(L("Um raio-x do domínio: o que piorou, o que melhorou, o que "
                     "está em alerta, o que a tendência diz e o que fazer "
                     "primeiro.",
                     "An x-ray of the domain: what got worse, what improved, "
                     "what's on alert, what the trend says and what to do "
                     "first."))

    st.markdown(L("##### Ou comece por uma destas", "##### Or start with one of these"))
    exemplos = sugestoes(dom)
    cols = st.columns(4, gap="small")
    for i, q in enumerate(exemplos[:8]):
        with cols[i % 4]:
            if st.button(q, key=f"ex_{dom.chave}_{i}", use_container_width=True):
                escolhida = q

    if st.session_state[chave]:
        if st.button(L("Limpar conversa", "Clear conversation"),
                     key=f"limpar_{dom.chave}"):
            st.session_state[chave] = []
            st.session_state[chave_plano] = None
            st.rerun()

    pergunta = st.chat_input(L(f"Pergunte qualquer coisa para {dom.agente_nome}",
                               f"Ask {dom.agente_nome} anything"))
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
        with st.spinner(L(f"{dom.agente_nome} consultando...",
                          f"{dom.agente_nome} is looking it up...")):
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
            with st.expander(L("Números usados na resposta",
                               "Numbers used in the answer"), expanded=True):
                st.dataframe(r.tabela, use_container_width=True,
                             hide_index=True)

        # A fórmula só aparece quando existe conta. Métrica que é uma soma pura
        # não ganha bloco -- "Receita = soma da receita" não ensina nada.
        formula = r.fatos.get("formula_com_numeros")
        if formula:
            with st.expander(L("A conta por trás do número",
                               "The math behind the number"), expanded=False):
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


def aba_visao_geral(con, dom, inicio, fim, comp, filtros, quebra, dmax=None):
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
    if dom.funil:
        st.markdown("---")
        st.markdown(L("##### A jornada do pedido, ponta a ponta",
                      "##### The order journey, end to end"))
        passos = []
        base = None
        for coluna, rotulo, taxa_mk in dom.funil:
            n = con.execute(
                f"SELECT COUNT(DISTINCT CASE WHEN {coluna} = 1 THEN order_id END) "
                f"FROM fato WHERE data BETWEEN DATE '{inicio}' AND DATE '{fim}'"
                + ("" if not filtros else
                   "".join(" AND " + c for c in filtros.clausulas(dom)))
            ).fetchone()[0] or 0
            base = base or n or 1
            fatia = i18n.num(n / base * 100, 1)
            txt = i18n.num(n) + L(f"  ·  {fatia}% do início",
                                  f"  ·  {fatia}% of the start")
            passos.append((rotulo, float(n), txt))
        st.plotly_chart(g.funil(passos), use_container_width=True,
                        key=f"vg_funil_{dom.chave}")
        st.caption(L("Cada barra é o número de pedidos que alcançou aquela "
                     "etapa. A queda entre barras é onde a jornada trava.",
                     "Each bar is the number of orders that reached that "
                     "stage. The drop between bars is where the journey gets "
                     "stuck."))

    if dom.chave == "pld" and dmax is not None:
        telas_pld.bloco_visao_geral(con, dom, dmax, fim, filtros)

    st.markdown("---")
    if quebra:
        st.markdown(L(f"##### As métricas por dia, quebradas por "
                      f"{dom.dimensao(quebra).rotulo.lower()}",
                      f"##### The metrics by day, split by "
                      f"{dom.dimensao(quebra).rotulo.lower()}"))
    else:
        st.markdown(L("##### As métricas por dia", "##### The metrics by day"))

    for i in range(0, len(metricas), 2):
        cols = st.columns(2, gap="medium")
        for col, mk in zip(cols, metricas[i:i + 2]):
            m = dom.metrica(mk)
            with col:
                s, quebrado = _series_da_metrica(con, dom, mk, inicio, fim,
                                                 filtros, quebra)
                if s.empty or s[mk].notna().sum() < 2:
                    st.caption(L(f"{m.rotulo}: sem pontos suficientes no período.",
                                 f"{m.rotulo}: not enough points in the period."))
                    continue
                if quebrado:
                    coluna_dim, segmentos = quebrado
                    fig = g.linhas_por_segmento(s, coluna_dim, mk, m, segmentos,
                                                titulo=m.rotulo, altura=230)
                else:
                    fig = g.mini_serie(s, mk, m, titulo=m.rotulo)
                st.plotly_chart(fig, use_container_width=True,
                                key=f"vg_{mk}_{dom.chave}")

    st.caption(L("A quebra dos gráficos é escolhida na barra lateral e vale "
                 "para todos eles de uma vez. O teto de 5 segmentos não é "
                 "estético: a paleta só garante separação para daltonismo até "
                 "esse ponto.",
                 "The chart split is picked in the sidebar and applies to all "
                 "of them at once. The 5-segment cap isn't aesthetic: the "
                 "palette only guarantees color-blind separation up to that "
                 "point."))

    # Em Compliance, indicador acompanhado não é só o que virou alerta: o que
    # está em investigação e o comportamento do indicador ANTES do corte são
    # parte do monitoramento.
    if dom.chave == "pld" and dmax is not None:
        telas_pld.bloco_investigacao(con, dom, dmax, fim, filtros)
        telas_pld.bloco_indicadores(con, dom)


# --------------------------------------------------------------------------- #
# Aba: Comparação de períodos
# --------------------------------------------------------------------------- #

def aba_comparacao(con, dom, fim, filtros):
    st.markdown(L(f"##### Referência: **{descrever_dia(fim)}**",
                  f"##### Reference: **{descrever_dia(fim)}**"))
    st.caption(L("Todas as métricas do painel, nos quatro níveis de comparação "
                 "ao mesmo tempo. Cada coluna diz contra qual data está medindo.",
                 "Every metric on the dashboard, at the four comparison levels "
                 "at once. Each column says which date it's measuring "
                 "against."))

    comps = {n: montar_preset(n, fim) for n in NIVEIS_COMPARACAO}

    # As datas na cara, antes da tabela: sem elas, "-8%" não quer dizer nada.
    # Rotulo curto e proprio de cada nivel. Cortar o preset no " vs " daria
    # "Dia" em tres das quatro colunas -- os niveis ficariam indistinguiveis
    # justamente no lugar em que a coluna precisa se identificar.
    ROTULOS = {"dia_d1": L("Contra ontem", "Vs yesterday"),
               "dia_d7": L("Contra D-7", "Vs D-7"),
               "mtd": L("Mês acumulado", "Month-to-date"),
               "dia_media3": L("Contra 3 dias iguais", "Vs 3 same weekdays")}
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
               "mtd": L("vs mês ant.", "vs prev. month"),
               "dia_media3": L("vs média 3 iguais", "vs avg of 3 same")}
    COLS_VAR = [ROT_COL[n] for n in NIVEIS_COMPARACAO]

    linhas, cores = [], []
    for mk in dom.metricas_painel:
        m = dom.metrica(mk)
        c_met, c_val = L("Métrica", "Metric"), L("Valor no dia", "Value on the day")
        linha = {c_met: m.rotulo,
                 c_val: numero(
                     resultados[NIVEIS_COMPARACAO[0]][mk]["atual"], m)}
        cor = {c_met: "", c_val: ""}
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
    st.caption(L("A seta é a direção; a cor é o julgamento. Verde é movimento a "
                 "favor do negócio e vermelho é contra — por isso cancelamento "
                 "caindo aparece ▼ verde e prazo de entrega subindo, ▲ vermelho.",
                 "The arrow is the direction; the color is the judgment. Green "
                 "is a move in favor of the business and red is against — "
                 "that's why falling cancellation shows ▼ green and rising "
                 "delivery time shows ▲ red."))

    st.markdown(
        nota(L("Um mesmo dia pode parecer catástrofe contra ontem e normalidade "
               "contra a média dos mesmos dias da semana. É por isso que os "
               "quatro níveis aparecem juntos: a escolha da base muda a "
               "conclusão mais do que o dado muda.",
               "The same day can look like a disaster against yesterday and "
               "perfectly normal against the average of the same weekdays. "
               "That's why the four levels appear together: the choice of "
               "baseline changes the conclusion more than the data does.")),
        unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Aba: Causa raiz
# --------------------------------------------------------------------------- #

def aba_causa_raiz(con, dom, dmin, dmax, fim, filtros):
    fmt = i18n.formato_data_widget()
    c1, c2 = st.columns([2, 3])
    with c1:
        mk = st.selectbox(L("Métrica", "Metric"), list(dom.metricas.keys()),
                          format_func=lambda k: dom.metrica(k).rotulo,
                          key=f"cr_m_{dom.chave}")
        dk = st.selectbox(L("Decompor por", "Break down by"),
                          list(dom.dimensoes.keys()),
                          format_func=lambda k: dom.dimensao(k).rotulo,
                          key=f"cr_d_{dom.chave}")
    with c2:
        modos = {"dia": L("Dia vs dia anterior", "Day vs previous day"),
                 "semana": L("Semana acumulada vs outra semana",
                             "Week-to-date vs another week"),
                 "mes": L("Mês acumulado vs outro mês",
                          "Month-to-date vs another month")}
        modo = st.radio(L("Comparar", "Compare"), list(modos),
                        format_func=modos.get, key=f"cr_modo_{dom.chave}_k")

        if modo == "dia":
            ref = st.date_input(L("Dia", "Day"), value=fim, min_value=dmin,
                                max_value=dmax, key=f"cr_dia_{dom.chave}",
                                format=fmt)
            ref = ref if isinstance(ref, date) else fim
            comp = contra_dia(ref, ref - timedelta(days=1))
        elif modo == "semana":
            ref = st.date_input(L("Semana atual (qualquer dia dela)",
                                  "Current week (any day in it)"), value=fim,
                                min_value=dmin, max_value=dmax,
                                key=f"cr_sem_ref_{dom.chave}", format=fmt)
            alvo = st.date_input(L("Comparar com a semana de",
                                   "Compare with the week of"),
                                 value=max(dmin, fim - timedelta(days=7)),
                                 min_value=dmin, max_value=dmax,
                                 key=f"cr_sem_alvo_{dom.chave}", format=fmt)
            ref = ref if isinstance(ref, date) else fim
            alvo = alvo if isinstance(alvo, date) else fim - timedelta(days=7)
            comp = contra_semana(ref, alvo)
        else:
            meses = [str(p) for p in pd.period_range(dmin, dmax, freq="M")]

            def _rot(k):
                return i18n.mes(pd.Period(k).start_time.date())

            ca, cb = st.columns(2)
            with ca:
                i_ref = st.selectbox(L("Mês atual", "Current month"), meses,
                                     index=len(meses) - 1, format_func=_rot,
                                     key=f"cr_mes_ref_{dom.chave}_k")
            with cb:
                i_alvo = st.selectbox(L("Comparar com", "Compare with"), meses,
                                      index=max(0, len(meses) - 2),
                                      format_func=_rot,
                                      key=f"cr_mes_alvo_{dom.chave}_k")
            p_ref, p_alvo = pd.Period(i_ref), pd.Period(i_alvo)
            ref = min(dmax, p_ref.end_time.date())
            comp = contra_mes(ref, p_alvo.start_time.date())

    st.markdown(cabecalho_comparacao(comp), unsafe_allow_html=True)

    m = dom.metrica(mk)
    dec = mod_causa.decompor(con, dom, mk, dk, comp, filtros, top_n=8)

    if dec.total_a != dec.total_a and dec.total_b != dec.total_b:
        st.info(L(
            f"Não há valor de {m.rotulo} em nenhum dos dois períodos."
            + (" Em crédito isso costuma ser safra ainda imatura: a métrica só "
               "existe depois do MOB exigido." if dom.simulado else ""),
            f"There is no value of {m.rotulo} in either period."
            + (" This is usually an immature vintage/cohort: the metric only "
               "exists after the required maturation." if dom.simulado else "")))
        return

    st.plotly_chart(
        g.cascata(mod_causa.dados_cascata(dec), m,
                  titulo=L(f"{m.rotulo}: de onde veio a variação",
                           f"{m.rotulo}: where the change came from")),
        use_container_width=True, key=f"cr_casc_{dom.chave}")

    st.markdown(L("##### A conta, em português", "##### The math, in plain words"))
    for linha in mod_causa.explicar(dec):
        st.markdown(md(f"- {linha}"))
    if dec.aviso:
        st.markdown(nota(dec.aviso), unsafe_allow_html=True)

    st.caption(md(L(
        f"Soma das contribuições: "
        f"{numero(float(dec.df['contribuicao'].sum()), m, sinal=True)} · "
        f"Variação total: {numero(dec.delta, m, sinal=True)} · "
        f"Resíduo: {numero(dec.residuo, m, sinal=True)}",
        f"Sum of contributions: "
        f"{numero(float(dec.df['contribuicao'].sum()), m, sinal=True)} · "
        f"Total change: {numero(dec.delta, m, sinal=True)} · "
        f"Residual: {numero(dec.residuo, m, sinal=True)}")))

    # Em Compliance falta uma decomposição que nenhuma dimensão dá: o volume
    # de alertas subiu porque mais gente se comportou assim, ou porque a régua
    # passou a pegar mais? As duas pedem ações opostas.
    if dom.chave == "pld":
        telas_pld.bloco_causa_raiz(con, dom)


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
                    f"{selo(dom.simulado)}"
                    f"{selo_construcao() if dom.chave in EM_CONSTRUCAO else ''}"
                    f"</div>", unsafe_allow_html=True)

    if dom.chave in EM_CONSTRUCAO:
        sem_rosto = not avatar_uri(dom.agente_imagem)
        st.markdown(nota(L(
            "<b>Domínio em construção.</b> As telas e "
            f"{dom.agente_artigo} {dom.agente_nome} já funcionam ponta a "
            "ponta, mas os textos e os gráficos ainda estão em ajuste"
            + (f", e {dom.agente_artigo} {dom.agente_nome} ainda não tem rosto"
               if sem_rosto else "")
            + ". Fica publicado assim de propósito: prefiro mostrar em obra a "
            "esconder até ficar perfeito.",
            "<b>Domain under construction.</b> The screens and "
            f"{dom.agente_nome} already work end to end, but the texts and "
            "charts are still being tuned"
            + (f", and {dom.agente_nome} doesn't have a face yet"
               if sem_rosto else "")
            + ". It's published like this on purpose: I'd rather show work in "
            "progress than hide it until it's perfect.")),
            unsafe_allow_html=True)
    if dom.simulado:
        st.markdown(nota(L(f"<b>Este domínio usa dado simulado.</b> {dom.fonte}",
                           f"<b>This domain uses simulated data.</b> "
                           f"{dom.fonte}")),
                    unsafe_allow_html=True)

    # Compliance ganha duas abas que nenhum outro domínio tem. A fila entra
    # logo depois do agente: em PLD a pergunta da manhã não é "quanto", é
    # "quem" -- e ela precisa estar à mão, não no fim da barra de abas.
    #
    # As abas são indexadas por CHAVE, e o nome vem da língua ativa: indexar
    # pelo texto faria o painel quebrar no primeiro clique no botão EN.
    nomes = {
        "alertas": L("Alertas", "Alerts"),
        "agente": L(f"Pergunte {dom.agente_ao} {dom.agente_nome}",
                    f"Ask {dom.agente_nome}"),
        "clientes": L("Clientes em atenção", "Clients to review"),
        "visao": L("Visão geral", "Overview"),
        "regras": L("Regras e calibração", "Rules & calibration"),
        "comparacao": L("Comparação de períodos", "Period comparison"),
        "causa": L("Causa raiz", "Root cause"),
        "sobre": L("Sobre os dados", "About the data"),
    }
    ordem = ["alertas", "agente"]
    if dom.chave == "pld":
        ordem += ["clientes"]
    ordem += ["visao"]
    if dom.chave == "pld":
        ordem += ["regras"]
    ordem += ["comparacao", "causa", "sobre"]
    abas = dict(zip(ordem, st.tabs([nomes[k] for k in ordem])))

    with abas["alertas"]:
        aba_alertas(con, dom, fim, filtros)
    with abas["agente"]:
        aba_agente(con, dom, inicio, fim, preset, filtros, quebra)
    if dom.chave == "pld":
        with abas["clientes"]:
            telas_pld.aba_clientes(con, dom, dmax, fim, filtros)
    with abas["visao"]:
        aba_visao_geral(con, dom, inicio, fim, comp, filtros, quebra, dmax)
    if dom.chave == "pld":
        with abas["regras"]:
            telas_pld.aba_regras(con, dom, inicio, fim, filtros)
    with abas["comparacao"]:
        aba_comparacao(con, dom, fim, filtros)
    with abas["causa"]:
        aba_causa_raiz(con, dom, dmin, dmax, fim, filtros)
    with abas["sobre"]:
        st.markdown(L("#### Procedência", "#### Provenance"))
        st.markdown(md(dom.fonte))
        if dom.notas:
            st.markdown(L("#### Ressalvas metodológicas",
                          "#### Methodological caveats"))
            for n in dom.notas:
                st.markdown(md(f"- {n}"))
        st.markdown(L("#### Catálogo de métricas", "#### Metric catalog"))
        st.dataframe(pd.DataFrame([{
            L("Métrica", "Metric"): m.rotulo, L("Chave", "Key"): k,
            L("Conta", "Math"): m.formula or L("soma direta", "direct sum"),
            L("Melhora", "Improves when"): (L("subindo", "rising")
                                            if m.bom_quando_sobe
                                            else L("descendo", "falling")),
            L("Definição", "Definition"): m.descricao,
        } for k, m in dom.metricas.items()]), use_container_width=True,
            hide_index=True)
        st.markdown(L("#### Catálogo de dimensões", "#### Dimension catalog"))
        from vulcano.causa_raiz import ENTIDADES_EN
        st.dataframe(pd.DataFrame([{
            L("Dimensão", "Dimension"): d.rotulo, L("Chave", "Key"): k,
            L("Única por", "Unique per"): ", ".join(
                (ENTIDADES_EN.get(x, x) if i18n.en() else x)
                for x in d.unica_por) or "—",
            L("Definição", "Definition"): d.descricao,
        } for k, d in dom.dimensoes.items()]), use_container_width=True,
            hide_index=True)
        st.caption(L(f"Dados de {i18n.data(dmin)} a {i18n.data(dmax)}.",
                     f"Data from {i18n.data(dmin)} to {i18n.data(dmax)}."))
        if dom.chave == "pld":
            telas_pld.sobre_pld()


# --------------------------------------------------------------------------- #

def main() -> None:
    _iniciar_idioma()
    st.session_state.setdefault("dominio", None)
    atual = st.session_state["dominio"]
    if atual is None:
        render_capa()
    else:
        render_dashboard(atual)


if __name__ == "__main__":
    main()
