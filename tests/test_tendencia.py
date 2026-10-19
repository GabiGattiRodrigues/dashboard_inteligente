"""
Tendência em todos os agentes.

Todo agente tem que responder "qual a tendência de X?" para qualquer métrica
do painel dele -- inclusive métrica de maturação (over30 no MOB3, falso
positivo de alerta maduro, turnover precoce), que não tem leitura diária no
mês selecionado e cai para a série mensal.
"""

from __future__ import annotations

import pytest

from vulcano.agente import Contexto, perguntar
from vulcano.dados import Filtros, conectar, periodo_disponivel
from vulcano.dominios import listar

DOMS = {d.chave: d for d in listar()}
CONS = {}


def _ctx(dom):
    if dom.chave not in CONS:
        CONS[dom.chave] = conectar(dom)
    con = CONS[dom.chave]
    ini, fim = periodo_disponivel(con)
    return con, Contexto(dominio=dom, inicio=max(ini, fim.replace(day=1)),
                         fim=fim, filtros=Filtros(),
                         preset_comparacao="mes_fechado")


@pytest.mark.parametrize("chave", list(DOMS))
def test_toda_metrica_do_painel_tem_tendencia(chave):
    dom = DOMS[chave]
    con, ctx = _ctx(dom)
    for mk in dom.metricas_painel:
        m = dom.metrica(mk)
        r = perguntar(con, f"qual a tendência de {m.rotulo.lower()}?", ctx,
                      usar_llm=False)
        assert r.plano["intencao"] == "tendencia", mk
        assert "direcao" in r.fatos, f"{chave}/{mk}: {r.texto[:120]}"


@pytest.mark.parametrize("chave,mk", [
    ("credito", "over30_mob3"), ("credito", "default_mob12"),
    ("pld", "taxa_falso_positivo"), ("people", "turnover_precoce"),
])
def test_metrica_de_maturacao_cai_para_serie_mensal(chave, mk):
    dom = DOMS[chave]
    con, ctx = _ctx(dom)
    r = perguntar(con, f"qual a tendência de {dom.metrica(mk).rotulo.lower()}?",
                  ctx, usar_llm=False)
    assert r.fatos.get("granularidade") == "mes"
    assert "mensal" in r.texto


@pytest.mark.parametrize("q", ["vai piorar?", "para onde está indo?",
                               "faz uma previsão", "what's the outlook?"])
def test_pergunta_de_futuro_vira_tendencia(q):
    dom = DOMS["marketing"]
    con, ctx = _ctx(dom)
    r = perguntar(con, q, ctx, usar_llm=False)
    assert r.plano["intencao"] == "tendencia"


def test_projecao_nao_bate_no_limite():
    """Reta prolongada que chega a zero (ou 100%) não dimensiona nada."""
    dom = DOMS["marketing"]
    con, ctx = _ctx(dom)
    r = perguntar(con, "qual a tendência da receita?", ctx, usar_llm=False)
    assert "R$ 0,00" not in r.texto
