"""CSS e componentes visuais reutilizados pelo app."""

from __future__ import annotations

import base64
import functools
import pathlib
from typing import Optional

from .formatacao import julgar, numero, pct
from .graficos import (EIXO, GRADE, JULGA_BOM, JULGA_RUIM, NEGATIVO, NEUTRO,
                       PLANO, POSITIVO, SERIE,
                       STATUS, SURFACE, TINTA, TINTA_2, TINTA_MUDA)
from .semantica import Metrica

CSS = f"""
<style>
  .stApp {{ background: {PLANO}; }}
  .block-container {{ padding-top: 2.2rem; max-width: 1400px; }}
  h1, h2, h3, h4 {{ color: {TINTA}; letter-spacing: -0.01em; }}

  .vulc-hero {{
    border: 1px solid {GRADE}; border-radius: 14px; background: {SURFACE};
    padding: 30px 32px; margin-bottom: 22px;
  }}
  .vulc-hero h1 {{ margin: 0 0 6px 0; font-size: 2.1rem; }}
  .vulc-hero .sub {{ color: {TINTA_2}; font-size: 1.02rem; line-height: 1.55;
                     max-width: 62ch; }}

  .vulc-card {{
    border: 1px solid {GRADE}; border-radius: 12px; background: {SURFACE};
    padding: 16px 18px; height: 100%;
  }}
  .vulc-card {{ padding: 12px 13px; }}
  .vulc-card .rot {{ color: {TINTA_MUDA}; font-size: 0.66rem; font-weight: 650;
                     text-transform: uppercase; letter-spacing: 0.055em;
                     line-height: 1.25; min-height: 2.4em; }}
  .vulc-card .val {{ color: {TINTA}; font-size: 1.16rem; font-weight: 640;
                     margin: 3px 0 1px 0; line-height: 1.15;
                     font-variant-numeric: tabular-nums; }}
  .vulc-card .delta {{ font-size: 0.74rem; font-weight: 620;
                       font-variant-numeric: tabular-nums; }}
  .vulc-card .ante {{ color: {TINTA_MUDA}; font-size: 0.665rem; margin-top: 2px;
                      font-variant-numeric: tabular-nums; }}

  .vulc-nota {{
    border-left: 3px solid {EIXO}; background: {SURFACE}; padding: 10px 14px;
    color: {TINTA_2}; font-size: 0.86rem; border-radius: 0 8px 8px 0;
    margin: 8px 0; line-height: 1.5;
  }}
  .vulc-sim {{
    display: inline-block; background: #e8eef8; color: #1e3a63;
    border: 1px solid #b7c8e0; border-radius: 999px; padding: 3px 11px;
    font-size: 0.74rem; font-weight: 640; letter-spacing: 0.02em;
  }}
  .vulc-real {{
    display: inline-block; background: #e8f4ee; color: #14532d;
    border: 1px solid #b0d8c1; border-radius: 999px; padding: 3px 11px;
    font-size: 0.74rem; font-weight: 640; letter-spacing: 0.02em;
  }}

  .vulc-alerta {{
    border: 1px solid {GRADE}; border-left-width: 4px; border-radius: 0 10px 10px 0;
    background: {SURFACE}; padding: 12px 16px; margin-bottom: 10px;
  }}
  .vulc-alerta .cab {{ font-size: 0.74rem; font-weight: 660; letter-spacing: 0.04em;
                       text-transform: uppercase; margin-bottom: 5px; }}
  .vulc-alerta .txt {{ color: {TINTA}; font-size: 0.92rem; line-height: 1.5; }}
  .vulc-alerta .aca {{ color: {TINTA_2}; font-size: 0.83rem; margin-top: 6px;
                       line-height: 1.45; }}
  .vulc-alerta .motivo {{
    margin-top: 9px; padding: 9px 12px; background: {PLANO};
    border-radius: 8px; font-size: 0.85rem; line-height: 1.5;
    color: {TINTA}; border-left: 2px solid {SERIE[0]};
  }}

  .vulc-nivel {{
    border: 1px solid {GRADE}; border-radius: 10px; background: {SURFACE};
    padding: 10px 12px; height: 100%;
  }}
  .vulc-nivel .rot {{ color: {TINTA_MUDA}; font-size: 0.66rem; font-weight: 650;
                      text-transform: uppercase; letter-spacing: 0.05em; }}
  .vulc-nivel .tit {{ color: {TINTA}; font-size: 0.82rem; font-weight: 600;
                      margin-top: 3px; line-height: 1.35;
                      font-variant-numeric: tabular-nums; }}

  .vulc-dom {{
    border: 1px solid {GRADE}; border-radius: 12px; background: {SURFACE};
    padding: 20px 22px; height: 100%;
  }}
  .vulc-dom h3 {{ margin: 0 0 4px 0; font-size: 1.16rem; }}
  .vulc-dom .sub {{ color: {TINTA_MUDA}; font-size: 0.82rem; margin-bottom: 10px; }}
  .vulc-dom .txt {{ color: {TINTA_2}; font-size: 0.88rem; line-height: 1.55;
                    min-height: 92px; }}

  .vulc-arq {{
    border: 1px solid {GRADE}; border-radius: 10px; background: {SURFACE};
    padding: 14px 16px; height: 100%;
  }}
  .vulc-arq .n {{ color: {SERIE[0]}; font-weight: 700; font-size: 0.78rem;
                  letter-spacing: 0.06em; }}
  .vulc-arq h4 {{ margin: 4px 0 6px 0; font-size: 0.97rem; }}
  .vulc-arq p {{ color: {TINTA_2}; font-size: 0.84rem; line-height: 1.5; margin: 0; }}

  .vulc-resp {{
    border: 1px solid {GRADE}; border-radius: 12px; background: {SURFACE};
    padding: 18px 22px; line-height: 1.62; color: {TINTA}; font-size: 0.96rem;
  }}
  .vulc-motor {{ color: {TINTA_MUDA}; font-size: 0.74rem; margin-top: 10px; }}

  .vulc-comp {{
    display: flex; align-items: stretch; gap: 0; margin: 4px 0 18px 0;
    border: 1px solid {GRADE}; border-radius: 12px; background: {SURFACE};
    overflow: hidden; flex-wrap: wrap;
  }}
  .vulc-comp-bloco {{ padding: 14px 20px; min-width: 210px; }}
  .vulc-comp-bloco.alt {{ background: #eef3fa; }}
  .vulc-comp-bloco .rot, .vulc-comp-regra .rot {{
    color: {TINTA_MUDA}; font-size: 0.72rem; font-weight: 660;
    text-transform: uppercase; letter-spacing: 0.05em;
  }}
  .vulc-comp-bloco .dat {{ color: {TINTA}; font-size: 1.02rem; font-weight: 600;
                           margin-top: 4px; }}
  .vulc-comp-bloco .det {{ color: {TINTA_2}; font-size: 0.8rem; margin-top: 2px; }}
  .vulc-comp-seta {{
    display: flex; align-items: center; padding: 0 14px; color: {TINTA_MUDA};
    font-size: 0.82rem; font-weight: 700; background: {SURFACE};
  }}
  .vulc-comp-regra {{
    padding: 14px 20px; border-left: 1px solid {GRADE}; flex: 1; min-width: 240px;
  }}
  .vulc-comp-regra .txt {{ color: {TINTA_2}; font-size: 0.86rem; margin-top: 4px;
                           line-height: 1.45; }}

  .vulc-ajuda {{
    border: 1px solid {GRADE}; border-radius: 12px; background: {SURFACE};
    padding: 16px 20px; margin-bottom: 14px;
  }}
  .vulc-ajuda h5 {{ margin: 0 0 8px 0; font-size: 0.94rem; color: {TINTA}; }}
  .vulc-ajuda p {{ color: {TINTA_2}; font-size: 0.87rem; line-height: 1.55;
                   margin: 0 0 8px 0; }}
  .vulc-ajuda code {{ background: #f0efec; border-radius: 4px; padding: 1px 6px;
                      font-size: 0.85rem; color: {TINTA}; }}

  /* O avatar e PNG com fundo transparente: nao leva borda nem recorte
     circular, senao a orelha some. Ele assenta direto sobre o fundo. */
  .vulc-rosto {{ object-fit: contain; display: block; flex: 0 0 auto; }}
  .vulc-rosto-emoji {{ line-height: 1; display: block; flex: 0 0 auto; }}

  .vulc-agente {{
    display: flex; align-items: center; gap: 14px; margin-bottom: 2px;
  }}
  .vulc-agente .nome {{ color: {TINTA}; font-size: 1.5rem; font-weight: 660;
                        letter-spacing: -0.01em; line-height: 1.15; }}
  .vulc-agente .papel {{ color: {TINTA_2}; font-size: 0.88rem; line-height: 1.45;
                         margin-top: 2px; max-width: 70ch; }}

  div[data-testid="stMetricValue"] {{ font-size: 1.5rem; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 2px; }}
  .stTabs [data-baseweb="tab"] {{ font-size: 0.92rem; }}
</style>
"""


# --------------------------------------------------------------------------- #
# Avatares dos agentes
# --------------------------------------------------------------------------- #

PASTA_ASSETS = pathlib.Path(__file__).resolve().parents[1] / "assets"


@functools.lru_cache(maxsize=32)
def avatar_uri(prefixo: str, variante: str = "animada") -> Optional[str]:
    """
    O PNG do agente como data URI.

    Vira data URI, e nao caminho de arquivo, porque o avatar aparece dentro de
    blocos de HTML que o Streamlit injeta -- e ali um caminho local do servidor
    nao resolve. Em cache porque sao 6 arquivos lidos em toda reexecucao do
    script, e o Streamlit reexecuta o script inteiro a cada clique.
    """
    if not prefixo:
        return None
    caminho = PASTA_ASSETS / f"{prefixo}-{variante}.png"
    if not caminho.exists():
        return None
    dados = base64.b64encode(caminho.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{dados}"


def rosto(dom, variante: str = "animada", tamanho: int = 44) -> str:
    """<img> do agente, com o emoji como reserva se o PNG nao existir."""
    uri = avatar_uri(getattr(dom, "agente_imagem", ""), variante)
    if not uri:
        return (f'<span class="vulc-rosto-emoji" '
                f'style="font-size:{tamanho * 0.62:.0f}px">'
                f'{dom.agente_rosto}</span>')
    return (f'<img class="vulc-rosto" src="{uri}" alt="{dom.agente_nome}" '
            f'style="width:{tamanho}px;height:{tamanho}px">')


def md(texto: str) -> str:
    """
    Escapa o cifrao antes de entregar texto ao markdown do Streamlit.

    O Streamlit interpreta $...$ como formula LaTeX. Sem isto, "R$ 608,9 mil
    para R$ 815,8 mil" faz o trecho entre os dois cifroes virar matemática --
    o número some e sobra itálico. Como toda moeda deste app e em reais, o
    escape tem de ser sistemático, e não caso a caso.
    """
    return texto.replace("$", r"\$")


def html_moeda(texto: str) -> str:
    """Mesma proteção dentro de blocos HTML, onde a entidade e mais segura."""
    return texto.replace("$", "&#36;")


def cartao_metrica(
    rotulo: str, valor: float, m: Metrica,
    anterior: Optional[float] = None, delta_pct: Optional[float] = None,
    rotulo_anterior: str = "período anterior",
) -> str:
    """
    Cartão de KPI.

    A seta diz a direção e a cor diz o julgamento: uma queda de cancelamento
    aparece ▼ em verde e uma alta de prazo ▲ em vermelho. Um painel que pinta
    tudo pelo sinal engana quem bate o olho.
    """
    corpo = f"""<div class="vulc-card">
      <div class="rot">{rotulo}</div>
      <div class="val">{html_moeda(numero(valor, m))}</div>"""

    if delta_pct is not None and delta_pct == delta_pct:
        bom = julgar(delta_pct, m.bom_quando_sobe)
        if bom is None:                       # variação some no arredondamento
            cor, seta = TINTA_MUDA, "▪"
        else:
            cor = JULGA_BOM if bom else JULGA_RUIM
            seta = "▲" if delta_pct > 0 else "▼"
        corpo += (f'<div class="delta" style="color:{cor}">{seta} '
                  f'{pct(delta_pct, 1, sinal=False)}</div>')
        if anterior is not None and anterior == anterior:
            corpo += (f'<div class="ante">{html_moeda(numero(anterior, m))} no '
                      f'{rotulo_anterior}</div>')
    else:
        corpo += f'<div class="delta" style="color:{TINTA_MUDA}">—</div>'
        corpo += '<div class="ante">sem base de comparação</div>'

    return corpo + "</div>"


def _negrito(t: str) -> str:
    """
    Converte **negrito** e *itálico* em HTML.

    O cartão de alerta é HTML puro, e os motores emitem markdown. Sem esta
    tradução os asteriscos aparecem crus na tela — o texto sai certo e a
    formatação sai literal.
    """
    import re
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", t)


def cartao_alerta(severidade: str, tipo: str, texto: str, acao: str,
                  motivo: Optional[str] = None) -> str:
    texto, acao = html_moeda(texto), html_moeda(acao)
    motivo = html_moeda(motivo) if motivo else None
    cor = STATUS.get(severidade, TINTA_MUDA)
    icone = {"alta": "▲", "media": "◆", "baixa": "●"}.get(severidade, "●")
    nome = {"alta": "Severidade alta", "media": "Severidade média",
            "baixa": "Severidade baixa"}.get(severidade, severidade)
    origem = "limite de negócio" if tipo == "limite" else "desvio do histórico"
    return f"""<div class="vulc-alerta" style="border-left-color:{cor}">
      <div class="cab" style="color:{cor}">{icone} {nome} · {origem}</div>
      <div class="txt">{_negrito(texto)}</div>
      <div class="aca">{_negrito(acao)}</div>
      {f'<div class="motivo">{_negrito(motivo)}</div>' if motivo else ''}
    </div>"""


DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez"]


def descrever_janela(j) -> tuple[str, str]:
    """Devolve (datas, detalhe) de uma janela, por extenso.

    Um dia solto mostra o dia da semana, porque e a informacao que falta para
    a comparacao fazer sentido: ninguem consegue julgar "18/08 contra 11/08"
    sem saber que os dois sao domingo.
    """
    ini, fim = j.inicio, j.fim
    if ini == fim:
        return (ini.strftime("%d/%m/%Y"), DIAS_SEMANA[ini.weekday()])
    datas = f"{ini.strftime('%d/%m/%Y')} — {fim.strftime('%d/%m/%Y')}"
    return (datas, f"{j.dias} dias")


def cabecalho_comparacao(comp) -> str:
    """
    Diz, sem ambiguidade, o que esta na tela e contra o que esta sendo lido.

    E a informacao que mais falta em painel: a pessoa ve "-8%" e nao sabe se e
    contra ontem, contra a semana passada ou contra o mes. Aqui as duas datas
    aparecem inteiras, lado a lado, com a regra da comparacao escrita.
    """
    a_datas, a_det = descrever_janela(comp.atual)
    if comp.composta:
        # Base composta nao e uma janela: e a media de varias. Mostrar so a
        # primeira daria a impressao de comparacao simples, que e outra conta.
        b_datas = comp.rotulo_base()
        b_det = f"média de {len(comp.anteriores)} dias iguais"
    else:
        b_datas, b_det = descrever_janela(comp.anterior)
    return f"""<div class="vulc-comp">
      <div class="vulc-comp-bloco">
        <div class="rot">Período selecionado</div>
        <div class="dat">{a_datas}</div>
        <div class="det">{a_det}</div>
      </div>
      <div class="vulc-comp-seta">vs</div>
      <div class="vulc-comp-bloco alt">
        <div class="rot">Comparado com</div>
        <div class="dat">{b_datas}</div>
        <div class="det">{b_det}</div>
      </div>
      <div class="vulc-comp-regra">
        <div class="rot">Regra da comparação</div>
        <div class="txt">{comp.descricao}</div>
      </div>
    </div>"""


def nota(texto: str) -> str:
    return f'<div class="vulc-nota">{texto}</div>'


def selo(simulado: bool) -> str:
    if simulado:
        return '<span class="vulc-sim">DADO SIMULADO</span>'
    return '<span class="vulc-real">DADO PÚBLICO REAL</span>'
