"""
Base de conhecimento (RAG) dos agentes.

O que precisa ser verdade:
- todo domínio tem playbook, e todo trecho fala de métrica/dimensão que existe;
- a busca respeita domínio, direção e sinal (trecho de piora não aparece
  quando melhorou; o de efeito mix não aparece quando foi efeito taxa);
- a busca sem chave é determinística;
- o RAG nunca muda número: a resposta com e sem conhecimento traz os mesmos
  valores, e o trecho não carrega número de resultado.
"""

from __future__ import annotations

import re

import pytest

from vulcano import conhecimento as kb
from vulcano.dominios import listar, obter


DOMINIOS = [d.chave for d in listar()]


@pytest.mark.parametrize("chave", DOMINIOS)
def test_todo_dominio_tem_playbook(chave):
    assert len(kb.trechos(chave)) >= 5


@pytest.mark.parametrize("chave", DOMINIOS)
def test_metricas_e_dimensoes_existem(chave):
    dom = obter(chave)
    for t in kb.trechos(chave):
        for mk in t.metricas:
            assert mk in dom.metricas, f"{t.id}: métrica {mk} não existe"
        for dk in t.dimensoes:
            assert dk in dom.dimensoes, f"{t.id}: dimensão {dk} não existe"


def test_ids_unicos():
    ids = [t.id for c in DOMINIOS for t in kb.trechos(c)]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("chave", DOMINIOS)
def test_trecho_nao_carrega_numero_de_resultado(chave):
    """Percentual ou valor em reais no playbook seria número concorrendo com
    o motor. Regra de negócio (D+3, MOB3, 7 dias) pode."""
    proibido = re.compile(r"\d+([.,]\d+)?\s*%|R\$\s*\d")
    for t in kb.trechos(chave):
        assert not proibido.search(t.texto_pt), t.id
        assert not proibido.search(t.texto_en), t.id


def test_formato_invalido_quebra_na_hora(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("## Sem id | No id\n- quando: piora\n### pt\noi\n### en\nhi\n",
                 encoding="utf-8")
    with pytest.raises(ValueError):
        kb.ler_arquivo(p)
    p.write_text("## T | T\n- id: a\n- quando: talvez\n### pt\noi\n### en\nhi\n",
                 encoding="utf-8")
    with pytest.raises(ValueError):
        kb.ler_arquivo(p)


def test_busca_acha_o_playbook_da_metrica():
    sit = kb.Situacao(metrica="pct_seller_no_prazo", rotulo_metrica="Seller no prazo",
                      piorou=True)
    achados = kb.buscar("logistica", sit, k=1)
    assert achados and achados[0].trecho.id == "log-seller"


def test_direcao_filtra():
    piorou = kb.buscar("credito", kb.Situacao(metrica="taxa_aprovacao",
                                              piorou=True), k=5)
    melhorou = kb.buscar("credito", kb.Situacao(metrica="taxa_aprovacao",
                                                piorou=False), k=5)
    ids_p = {a.trecho.id for a in piorou}
    ids_m = {a.trecho.id for a in melhorou}
    assert "cred-aprovacao-caindo" in ids_p
    assert "cred-aprovacao-caindo" not in ids_m
    assert "cred-crescimento-marcar" in ids_m
    assert "cred-crescimento-marcar" not in ids_p


def test_sinal_filtra():
    taxa = kb.buscar("marketing", kb.Situacao(metrica="ticket_medio", piorou=True,
                                              sinais=("efeito_taxa",)), k=5)
    mix = kb.buscar("marketing", kb.Situacao(metrica="ticket_medio", piorou=True,
                                             sinais=("efeito_mix",)), k=5)
    assert "mkt-efeito-mix" not in {a.trecho.id for a in taxa}
    assert "mkt-efeito-mix" in {a.trecho.id for a in mix}


def test_dominio_nao_vaza():
    sit = kb.Situacao(metrica="ticket_medio", piorou=True,
                      sinais=("efeito_mix", "concentrado"))
    for a in kb.buscar("credito", sit, k=5):
        assert a.trecho.dominio == "credito"


def test_pergunta_em_ingles_acha_o_mesmo_trecho():
    pt = kb.buscar("people", kb.Situacao(pergunta="por que o eNPS caiu?",
                                         piorou=True), k=1)
    en = kb.buscar("people", kb.Situacao(pergunta="why did eNPS fall?",
                                         piorou=True), k=1)
    assert pt and en and pt[0].trecho.id == en[0].trecho.id == "ppl-enps"


def test_deterministico():
    sit = kb.Situacao(metrica="over30_mob3", piorou=True, dimensao="canal",
                      segmento="Parceiro", sinais=("concentrado",))
    a = [x.trecho.id for x in kb.buscar("credito", sit, k=3)]
    b = [x.trecho.id for x in kb.buscar("credito", sit, k=3)]
    assert a == b


def test_fora_de_assunto_nao_recomenda():
    sit = kb.Situacao(pergunta="qual a previsão do tempo amanhã?")
    assert kb.buscar("logistica", sit, k=2) == []


def test_linha_da_conversa_nao_traz_fonte():
    item = {"fonte": "playbook Abigail › Algo", "texto": "Faz isso.",
            "tipo": "playbook"}
    assert "playbook Abigail" not in kb.linha(item)


def test_direcao_desconhecida_so_traz_trecho_dos_dois_sentidos():
    for a in kb.buscar("credito", kb.Situacao(metrica="taxa_aprovacao"), k=5):
        assert a.trecho.quando == "ambos"
