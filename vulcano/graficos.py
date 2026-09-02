"""
Gráficos do Vulcano.

Regras seguidas aqui, e o motivo de cada uma:

- **Um eixo por gráfico.** Duas métricas de escalas diferentes viram dois
  gráficos ou vao para base 100. Eixo duplo deixa a relação entre as séries
  ser decidida pela escolha da escala, e não pelos dados.
- **Cor por papel, não por posição.** Séries categóricas usam a ordem fixa de
  slots; variação usa o par divergente azul/vermelho com cinza no meio;
  severidade usa a paleta de status, sempre acompanhada de rotulo -- cor
  nunca carrega significado sozinha.
- **Marca fina, grade recessiva, rotulo direto só onde ajuda a ler.**
- **Toda tela tem a tabela do lado.** Além da acessibilidade, é o que permite
  conferir o número -- num produto que responde em linguagem natural, poder
  auditar a conta é requisito, não enfeite.

Paleta validada pelos seis checks (banda de luminosidade, piso de croma,
separação para daltonismo, piso de visao normal e contraste) na superfície
clara #fcfcfb.
"""

from __future__ import annotations

from typing import Optional, Sequence

import pandas as pd
import plotly.graph_objects as go

from .formatacao import numero, pct
from .semantica import Metrica

# --------------------------------------------------------------------------- #
# Paleta
# --------------------------------------------------------------------------- #

SURFACE = "#ffffff"
PLANO = "#f5f8fc"
TINTA = "#0f1b2d"
TINTA_2 = "#46586e"
TINTA_MUDA = "#7a8ba0"
GRADE = "#e3eaf3"
EIXO = "#c3cfdd"

# Paleta em tons de azul, com o teal como segundo tom.
#
# Um detalhe que a validação de acessibilidade impõe: gráfico com duas séries
# NÃO pode ser todo azul. Dois tons do mesmo azul estouram a banda de
# luminosidade, e azul contra violeta fica indistinguível até para quem enxerga
# todas as cores (ΔE 12,4, abaixo do piso de 15). O teal `#0d9488` é o tom mais
# próximo do azul que ainda separa: ΔE 22,6 na visão normal e 20,7 em
# deuteranopia, e é o único candidato testado que passa sem nenhum aviso de
# contraste sobre esta superfície.
SERIE = ["#2563eb", "#0d9488", "#7c3aed", "#c2410c",
         "#0369a1", "#4d7c0f", "#a21caf", "#b91c1c"]

POSITIVO = "#2563eb"   # polo frio do par divergente
NEGATIVO = "#d13c3c"   # polo quente
NEUTRO = "#b8c4d2"

# Julgamento em texto (setas, cartões, tabelas) é outra coisa do que série de
# gráfico. Aqui verde/vermelho é a convenção que todo mundo já lê sem legenda,
# e usar o azul da marca para "bom" custaria uma explicação em toda tela. O
# azul continua sendo a cor do produto; verde e vermelho são estado, não marca.
JULGA_BOM = "#0a7d3c"
JULGA_RUIM = "#c0392b"

STATUS = {"alta": "#c0392b", "media": "#1d4ed8", "baixa": "#5b7a9e",
          "bom": "#0a7d3c"}
ICONE_STATUS = {"alta": "▲", "media": "◆", "baixa": "●", "bom": "✓"}

FONTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def _base(fig: go.Figure, altura: int = 340, titulo: str = "") -> go.Figure:
    # Titulo ausente precisa ser OMITIDO, e nao passado como None: o Plotly
    # serializa o None e o navegador desenha a string "undefined" no topo.
    if titulo:
        fig.update_layout(title=dict(
            text=titulo, font=dict(size=14, color=TINTA, family=FONTE),
            x=0, xanchor="left", y=0.97))
    fig.update_layout(
        height=altura,
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family=FONTE, size=12, color=TINTA_2),
        margin=dict(l=8, r=8, t=42 if titulo else 16, b=8),
        hoverlabel=dict(bgcolor="white", bordercolor=EIXO,
                        font=dict(family=FONTE, size=12, color=TINTA)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left",
                    x=0, font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, linecolor=EIXO, ticks="outside",
                     tickcolor=EIXO, tickfont=dict(size=11, color=TINTA_MUDA))
    fig.update_yaxes(showgrid=True, gridcolor=GRADE, gridwidth=1,
                     zeroline=False, linecolor="rgba(0,0,0,0)",
                     tickfont=dict(size=11, color=TINTA_MUDA))
    return fig


# --------------------------------------------------------------------------- #
# Serie temporal
# --------------------------------------------------------------------------- #

def linha_temporal(
    df: pd.DataFrame, m: Metrica, coluna: Optional[str] = None,
    media_movel: Optional[str] = "media_movel", titulo: str = "",
    altura: int = 320,
) -> go.Figure:
    """Série diária com média movel. Duas séries => legenda presente."""
    col = coluna or m.chave
    d = df.dropna(subset=[col])
    rotulos = [numero(v, m) for v in d[col]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=d["data"], y=d[col], name="Diario", mode="lines",
        line=dict(color=SERIE[0], width=1.4),
        customdata=rotulos,
        hovertemplate="%{x|%d/%m/%Y}<br><b>%{customdata}</b><extra>Diario</extra>",
    ))
    tem_mm = media_movel and media_movel in d.columns and d[media_movel].notna().any()
    if tem_mm:
        fig.add_trace(go.Scatter(
            x=d["data"], y=d[media_movel], name="Média movel 7 dias", mode="lines",
            line=dict(color=SERIE[1], width=2),
            customdata=[numero(v, m) for v in d[media_movel]],
            hovertemplate="%{x|%d/%m/%Y}<br><b>%{customdata}</b>"
                          "<extra>Média movel</extra>",
        ))

    fig = _base(fig, altura, titulo)
    fig.update_layout(hovermode="x unified", showlegend=bool(tem_mm))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1,
                     spikedash="dot", spikecolor=EIXO)
    return fig


# --------------------------------------------------------------------------- #
# Ranking de segmentos
# --------------------------------------------------------------------------- #

def barras_segmentos(
    df: pd.DataFrame, coluna_rotulo: str, coluna_valor: str,
    m: Metrica, titulo: str = "", altura: int = 340,
    destaque: Optional[str] = None,
) -> go.Figure:
    """Barras horizontais, uma cor só: identidade esta no eixo, não na cor."""
    d = df.dropna(subset=[coluna_valor]).copy()
    d = d.iloc[::-1]  # maior no topo
    rotulos = [numero(v, m) for v in d[coluna_valor]]
    cores = [SERIE[1] if (destaque and str(r) == destaque) else SERIE[0]
             for r in d[coluna_rotulo]]

    fig = go.Figure(go.Bar(
        y=d[coluna_rotulo].astype(str), x=d[coluna_valor], orientation="h",
        marker=dict(color=cores, line=dict(color=SURFACE, width=2)),
        text=rotulos, textposition="outside",
        textfont=dict(size=11, color=TINTA_2, family=FONTE),
        customdata=rotulos,
        hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
    ))
    fig = _base(fig, altura, titulo)
    # O rotulo direto fica FORA da barra, entao o eixo precisa de folga: sem
    # esticar o alcance, o texto da maior barra e cortado pela borda -- e a
    # maior barra e justamente a que mais interessa ler.
    maximo = float(d[coluna_valor].max()) if len(d) else 0.0
    minimo = min(0.0, float(d[coluna_valor].min()) if len(d) else 0.0)
    if maximo > 0:
        fig.update_xaxes(range=[minimo, maximo * 1.22])
    fig.update_traces(cliponaxis=False)
    fig.update_xaxes(showgrid=True, gridcolor=GRADE, showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=TINTA_2))
    fig.update_layout(margin=dict(l=8, r=24, t=42 if titulo else 16, b=8),
                      bargap=0.34)
    return fig


# --------------------------------------------------------------------------- #
# Cascata de causa raiz
# --------------------------------------------------------------------------- #

def cascata(df: pd.DataFrame, m: Metrica, titulo: str = "",
            altura: int = 420) -> go.Figure:
    """
    Cascata do período anterior ao atual.

    Azul sobe, vermelho desce, cinza para os dois totais: o par divergente
    marca o SINAL da contribuição, que é a única coisa que a cor precisa dizer
    aqui. O valor vai no rotulo direto, sobre a barra.
    """
    medidas = ["absolute" if t == "total" else "relative" for t in df["tipo"]]
    textos = [numero(v, m, sinal=(t != "total"))
              for v, t in zip(df["valor"], df["tipo"])]

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=medidas,
        x=df["rotulo"],
        y=df["valor"],
        text=textos,
        textposition="outside",
        textfont=dict(size=10, color=TINTA_2, family=FONTE),
        connector=dict(line=dict(color=EIXO, width=1, dash="dot")),
        increasing=dict(marker=dict(color=POSITIVO,
                                    line=dict(color=SURFACE, width=2))),
        decreasing=dict(marker=dict(color=NEGATIVO,
                                    line=dict(color=SURFACE, width=2))),
        totals=dict(marker=dict(color=NEUTRO, line=dict(color=SURFACE, width=2))),
        hovertemplate="<b>%{x}</b><br>%{text}<extra></extra>",
    ))
    fig = _base(fig, altura, titulo)
    fig.update_xaxes(tickangle=-32, tickfont=dict(size=10, color=TINTA_2))
    fig.update_layout(margin=dict(l=8, r=8, t=52 if titulo else 24, b=110))
    return fig


# --------------------------------------------------------------------------- #
# Variacao entre periodos
# --------------------------------------------------------------------------- #

def barras_variacao(
    itens: Sequence[tuple[str, float, bool]], titulo: str = "", altura: int = 320,
) -> go.Figure:
    """
    Variação percentual por métrica. Recebe (rotulo, variação, melhorou).

    A cor codifica se o movimento foi bom ou ruim -- não se foi para cima. Uma
    queda de cancelamento e azul; uma alta de prazo de entrega e vermelha.
    Sem isso, um painel cheio de barras azuis para cima pode estar todo errado.
    """
    d = list(itens)[::-1]
    rot = [x[0] for x in d]
    val = [x[1] for x in d]
    bom = [x[2] for x in d]
    cores = [POSITIVO if b else NEGATIVO for b in bom]
    textos = [pct(v) for v in val]

    fig = go.Figure(go.Bar(
        y=rot, x=val, orientation="h",
        marker=dict(color=cores, line=dict(color=SURFACE, width=2)),
        text=textos, textposition="outside",
        textfont=dict(size=11, color=TINTA_2, family=FONTE),
        hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
    ))
    fig = _base(fig, altura, titulo)
    fig.add_vline(x=0, line=dict(color=EIXO, width=1))
    fig.update_xaxes(showgrid=True, gridcolor=GRADE, showticklabels=False,
                     tickformat=".0%")
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=TINTA_2))
    fig.update_layout(margin=dict(l=8, r=64, t=42 if titulo else 16, b=8),
                      bargap=0.34)
    return fig


# --------------------------------------------------------------------------- #
# Perfil por dia da semana
# --------------------------------------------------------------------------- #

def perfil_semanal(df: pd.DataFrame, m: Metrica, titulo: str = "",
                   altura: int = 260) -> go.Figure:
    d = df.dropna(subset=["indice"])
    textos = [pct(v - 1) for v in d["indice"]]
    cores = [POSITIVO if v >= 1 else NEGATIVO for v in d["indice"]]

    fig = go.Figure(go.Bar(
        x=d["dia"], y=d["indice"] - 1,
        marker=dict(color=cores, line=dict(color=SURFACE, width=2)),
        text=textos, textposition="outside",
        textfont=dict(size=10, color=TINTA_2, family=FONTE),
        customdata=[numero(v, m) for v in d["valor"]],
        hovertemplate="<b>%{x}</b><br>%{customdata} (%{text} vs média)<extra></extra>",
    ))
    fig = _base(fig, altura, titulo)
    fig.add_hline(y=0, line=dict(color=EIXO, width=1))
    fig.update_yaxes(tickformat=".0%", showgrid=True, gridcolor=GRADE)
    fig.update_layout(bargap=0.4)
    return fig


# --------------------------------------------------------------------------- #
# Comparacao de duas janelas na mesma serie
# --------------------------------------------------------------------------- #

def duas_janelas(
    atual: pd.DataFrame, anterior: pd.DataFrame, m: Metrica,
    rotulo_atual: str, rotulo_anterior: str, titulo: str = "", altura: int = 320,
) -> go.Figure:
    """
    Os dois períodos sobrepostos por dia relativo (dia 1, dia 2, ...), não por
    data. Sobrepor por data colocaria as curvas lado a lado em vez de uma sobre
    a outra, que é justamente a comparação que se quer ver.
    """
    fig = go.Figure()
    for d, nome, cor, largura in (
        (anterior, rotulo_anterior, SERIE[1], 1.6),
        (atual, rotulo_atual, SERIE[0], 2.2),
    ):
        dd = d.dropna(subset=[m.chave]).reset_index(drop=True)
        if dd.empty:
            continue
        fig.add_trace(go.Scatter(
            x=list(range(1, len(dd) + 1)), y=dd[m.chave], name=nome,
            mode="lines", line=dict(color=cor, width=largura),
            customdata=[[numero(v, m), dt.strftime("%d/%m/%Y")]
                        for v, dt in zip(dd[m.chave], dd["data"])],
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}"
                          f"<extra>{nome}</extra>",
        ))
    fig = _base(fig, altura, titulo)
    fig.update_layout(hovermode="x unified", showlegend=True)
    fig.update_xaxes(title=dict(text="Dia dentro do período",
                                font=dict(size=11, color=TINTA_MUDA)))
    return fig


# --------------------------------------------------------------------------- #
# Série quebrada por dimensão
# --------------------------------------------------------------------------- #

def linhas_por_segmento(
    df: pd.DataFrame, coluna_dim: str, coluna_valor: str, m: Metrica,
    segmentos: Sequence[str], titulo: str = "", altura: int = 260,
) -> go.Figure:
    """
    Uma linha por segmento, no máximo cinco.

    O teto de cinco não é estético: a paleta só garante separação para
    daltonismo até esse ponto. Um sexto segmento entraria com cor que alguém
    não distingue da anterior, e o gráfico passaria a mentir para uma parte dos
    leitores. Acima disso, o resto vai para "Outros" ou vira um gráfico por
    segmento.
    """
    fig = go.Figure()
    for i, seg in enumerate(segmentos[:5]):
        d = df[df[coluna_dim].astype(str) == str(seg)].dropna(subset=[coluna_valor])
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["data"], y=d[coluna_valor], name=str(seg), mode="lines",
            line=dict(color=SERIE[i % len(SERIE)], width=1.8),
            customdata=[numero(v, m) for v in d[coluna_valor]],
            hovertemplate="%{x|%d/%m/%Y}<br><b>%{customdata}</b>"
                          f"<extra>{seg}</extra>",
        ))
    fig = _base(fig, altura, titulo)
    fig.update_layout(hovermode="x unified", showlegend=True,
                      legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10)))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1,
                     spikedash="dot", spikecolor=EIXO)
    return fig


def mini_serie(
    df: pd.DataFrame, coluna_valor: str, m: Metrica, titulo: str,
    altura: int = 170,
) -> go.Figure:
    """
    Série compacta com área, para a grade de métricas.

    O último ponto ganha marcador porque, num gráfico pequeno, é o valor que a
    pessoa procura primeiro -- e sem destaque ele some no fim da linha.
    """
    d = df.dropna(subset=[coluna_valor])
    fig = go.Figure()
    if not d.empty:
        fig.add_trace(go.Scatter(
            x=d["data"], y=d[coluna_valor], mode="lines",
            line=dict(color=SERIE[0], width=1.6),
            fill="tozeroy", fillcolor="rgba(37,99,235,0.10)",
            customdata=[numero(v, m) for v in d[coluna_valor]],
            hovertemplate="%{x|%d/%m/%Y}<br><b>%{customdata}</b><extra></extra>",
        ))
        ultimo = d.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[ultimo["data"]], y=[ultimo[coluna_valor]], mode="markers",
            marker=dict(color=SERIE[0], size=7,
                        line=dict(color=SURFACE, width=2)),
            hoverinfo="skip", showlegend=False,
        ))
    fig = _base(fig, altura, titulo)
    fig.update_layout(margin=dict(l=4, r=8, t=30 if titulo else 6, b=4),
                      showlegend=False)
    fig.update_yaxes(showticklabels=False, showgrid=True, gridcolor=GRADE)
    fig.update_xaxes(showticklabels=True, tickfont=dict(size=9, color=TINTA_MUDA),
                     nticks=4)
    return fig


def funil(passos: Sequence[tuple], altura: int = 300, titulo: str = "") -> go.Figure:
    """
    Funil da jornada. Cada passo traz o volume e a taxa de passagem.

    Desenhado como barras horizontais alinhadas à esquerda, e não como o
    trapézio clássico: o trapézio centraliza as barras e faz o olho comparar
    larguras a partir de dois pontos móveis, o que atrapalha justamente a
    leitura que importa -- quanto sobrou de um passo para o outro.
    """
    rotulos = [p[0] for p in passos]
    valores = [p[1] for p in passos]
    textos = [p[2] for p in passos]
    topo = max(valores) if valores else 1

    fig = go.Figure(go.Bar(
        y=rotulos[::-1], x=valores[::-1], orientation="h",
        marker=dict(color=[SERIE[0]] * len(valores),
                    line=dict(color=SURFACE, width=2)),
        text=textos[::-1], textposition="outside",
        textfont=dict(size=11, color=TINTA_2, family=FONTE),
        hovertemplate="<b>%{y}</b><br>%{text}<extra></extra>",
    ))
    fig = _base(fig, altura, titulo)
    fig.update_xaxes(range=[0, topo * 1.28], showticklabels=False,
                     showgrid=True, gridcolor=GRADE)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=11, color=TINTA_2))
    fig.update_traces(cliponaxis=False)
    fig.update_layout(bargap=0.32, margin=dict(l=8, r=20, t=42 if titulo else 12, b=8))
    return fig
