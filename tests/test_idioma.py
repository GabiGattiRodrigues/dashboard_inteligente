"""
Testes da versão em inglês.

Mesmo espírito dos outros arquivos: cada teste é uma frase que a tela afirma.

- o número não muda de língua: a mesma pergunta em português e em inglês
  cai na mesma intenção, na mesma métrica e no mesmo valor;
- o roteiro "como conversar" de cada agente funciona nas duas línguas, na
  ordem em que a tela sugere;
- a resposta em inglês não vaza português;
- todo valor de dimensão que aparece na tela tem tradução;
- toda evidência de PLD gravada pelo job é reescrita em inglês;
- cada verbete de conceito tem o par em inglês.

Rodar:  python -m pytest tests/test_idioma.py -q
"""

from __future__ import annotations

import re
import sys
from datetime import timedelta
from pathlib import Path

import duckdb
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from vulcano import i18n  # noqa: E402
from vulcano.agente import Contexto, perguntar  # noqa: E402
from vulcano.conversa import CONCEITOS, explicar  # noqa: E402
from vulcano.conversa_en import CONCEITOS_EN  # noqa: E402
from vulcano.dados import Filtros, conectar, periodo_disponivel  # noqa: E402
from vulcano.dominios import DOMINIOS, obter  # noqa: E402
from vulcano.formatacao import numero  # noqa: E402
from vulcano.pld.en import evidencia  # noqa: E402

DOMS = list(DOMINIOS)


@pytest.fixture(autouse=True)
def _volta_para_portugues():
    yield
    i18n.definir("pt")


def _conversa(chave, idioma, perguntas):
    i18n.definir(idioma)
    dom = obter(chave)
    con = conectar(dom)
    dmin, dmax = periodo_disponivel(con)
    ctx = Contexto(dominio=dom, inicio=max(dmin, dmax - timedelta(days=89)),
                   fim=dmax, filtros=Filtros(),
                   preset_comparacao="ultimos_90" if chave == "pld"
                   else "mes_fechado")
    saida = []
    for p in perguntas:
        r = perguntar(con, p, ctx, usar_llm=False)
        ctx.ultimo_plano = r.plano
        saida.append(r)
    return saida


# --------------------------------------------------------------------------- #
# O roteiro de cada agente
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("chave", DOMS)
def test_roteiro_de_conversa_e_o_mesmo_nas_duas_linguas(chave):
    """O guia da tela, em sequência, cai nas mesmas intenções e métricas."""
    i18n.definir("pt")
    pt = [q for q, _ in obter(chave).guia_conversa]
    i18n.definir("en")
    en = [q for q, _ in obter(chave).guia_conversa]
    assert len(pt) == len(en) >= 4, chave

    r_pt = _conversa(chave, "pt", pt)
    r_en = _conversa(chave, "en", en)
    for q_pt, q_en, a, b in zip(pt, en, r_pt, r_en):
        assert a.plano["intencao"] == b.plano["intencao"], (q_pt, q_en)
        assert a.plano.get("metrica") == b.plano.get("metrica"), (q_pt, q_en)
        assert a.plano["intencao"] not in ("nao_entendi", "definicao",
                                           "catalogo"), (q_pt, q_en)


@pytest.mark.parametrize("chave", DOMS)
def test_exemplos_da_tela_nao_caem_em_nao_entendi(chave):
    for idioma in ("pt", "en"):
        i18n.definir(idioma)
        for q in obter(chave).perguntas_exemplo:
            r = _conversa(chave, idioma, [q])[0]
            assert r.plano["intencao"] not in ("nao_entendi", "catalogo"), q


def test_o_numero_nao_muda_de_lingua():
    """Mesmo valor por trás das duas respostas — só muda o separador."""
    a = _conversa("marketing", "pt", ["quanto foi a receita?"])[0]
    b = _conversa("marketing", "en", ["what was revenue?"])[0]
    assert a.plano["metrica"] == b.plano["metrica"] == "receita"
    i18n.definir("pt")
    v_pt = a.fatos["valor"]
    i18n.definir("en")
    v_en = b.fatos["valor"]
    # R$ 2,70 mi  ×  R$ 2.70M
    num = lambda s: float(re.sub(r"[^\d,\.]", "", s).replace(",", "."))  # noqa
    assert num(v_pt) == pytest.approx(float(re.sub(r"[^\d\.]", "", v_en)))


PALAVRAS_PT = [" não ", " também ", " período", "variação", " está ", " são ",
               " contra ", " vezes ", " pedidos", " desvio", " maior ",
               "segmento ", " quebra"]


@pytest.mark.parametrize("chave", DOMS)
def test_resposta_em_ingles_nao_vaza_portugues(chave):
    i18n.definir("en")
    dom = obter(chave)
    perguntas = [q for q, _ in dom.guia_conversa] + list(dom.perguntas_exemplo)
    for q, r in zip(perguntas, _conversa(chave, "en", perguntas)):
        texto = " " + r.texto.lower() + " "
        vazou = [p for p in PALAVRAS_PT if p in texto]
        assert not vazou, (q, vazou, r.texto[:400])


# --------------------------------------------------------------------------- #
# O que a tela mostra do dado
# --------------------------------------------------------------------------- #

# Valores que passam como vieram: siglas, códigos, datas, nomes próprios e o
# status do Olist, que já é gravado em inglês.
PASSA = re.compile(r"^([A-Z]{2}|\d{4}-\d{2}|[A-E] \(.*\)|approved|canceled|"
                   r"created|delivered|invoiced|processing|shipped|"
                   r"unavailable|LinkedIn|App|PEP|Voucher|Cool stuff|Telemarketing|"
                   r"La cuisine|Pet shop|PCs)$")


@pytest.mark.parametrize("chave", DOMS)
def test_todo_valor_de_dimensao_tem_traducao(chave):
    i18n.definir("pt")
    dom = obter(chave)
    con = conectar(dom)
    i18n.definir("en")
    faltam = []
    for dk in dom.dims_filtro:
        col = dom.dimensao(dk).coluna
        for (v,) in con.execute(
                f"SELECT DISTINCT {col} FROM fato WHERE {col} IS NOT NULL"
        ).fetchall():
            v = str(v)
            if i18n.V(v) == v and not PASSA.match(v):
                faltam.append((dk, v))
    assert not faltam, faltam[:20]


def test_toda_evidencia_de_pld_e_reescrita():
    i18n.definir("en")
    linhas = duckdb.sql(
        f"SELECT DISTINCT evidencia FROM '{RAIZ / 'data' / 'fato_pld.parquet'}'"
    ).fetchall()
    sobrou = [e for (e,) in linhas if evidencia(e) == e]
    assert not sobrou, sobrou[:3]
    # e os números mudam de roupa: 43.438 vira 43,438
    assert all(not re.search(r"R\$ \d{1,3}\.\d{3}\b", evidencia(e))
               for (e,) in linhas)


def test_numero_em_ingles_usa_virgula_de_milhar():
    i18n.definir("en")
    m = obter("marketing").metrica("ticket_medio")
    assert numero(1234.5, m) == "R$ 1,234.50"
    i18n.definir("pt")
    m = obter("marketing").metrica("ticket_medio")
    assert numero(1234.5, m) == "R$ 1.234,50"


# --------------------------------------------------------------------------- #
# Conceitos
# --------------------------------------------------------------------------- #

def test_cada_conceito_tem_par_em_ingles():
    assert len(CONCEITOS) == len(CONCEITOS_EN)
    i18n.definir("en")
    for (gat_en, _, titulo_en, corpo_en) in CONCEITOS_EN:
        assert corpo_en.strip()
        achado = explicar(gat_en[0])
        assert achado is not None, gat_en[0]


def test_conceito_em_ingles_responde_na_lingua_ativa():
    i18n.definir("pt")
    assert explicar("what is a robust z?")[0] == "Z robusto"
    i18n.definir("en")
    assert explicar("o que é z robusto?")[0] == "Robust z"
