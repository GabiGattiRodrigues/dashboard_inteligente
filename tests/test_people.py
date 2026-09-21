"""
Testes do domínio de People Analytics (Tomoyo).

Mesma filosofia de test_motor.py: cada teste corresponde a uma frase que o
painel ou a Tomoyo afirmam, para que ela não possa ficar falsa em silêncio.

- a cascata fecha nas métricas que prometem fechar, com a base de RH;
- o número da Tomoyo é o número do card;
- turnover precoce de safra imatura fica vazio, nunca zero;
- headcount é média dos dias, não soma;
- as histórias plantadas são encontráveis — e o eNPS avisa ANTES da onda;
- o gap ajustado é menor que o bruto, e a diferença é composição;
- o risco de saída não olha para o futuro da data de referência;
- nenhum recorte com menos de GRUPO_MINIMO pessoas aparece;
- pergunta sobre indivíduo é recusada e não devolve dado de ninguém;
- cada pergunta vai para a rota certa.

Rodar:  python -m pytest tests/test_people.py -q
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vulcano import causa_raiz as mod_causa
from vulcano.agente import Contexto, perguntar
from vulcano.dados import Filtros, agregar, conectar
from vulcano.dominios import obter
from vulcano.dominios.people import GRUPO_MINIMO
from vulcano.formatacao import numero
from vulcano.people import agente as ext
from vulcano.periodos import montar_preset

DOM = obter("people")
CON = conectar(DOM)
REF = date(2026, 2, 15)


def _ctx(ini=date(2026, 2, 1), fim=date(2026, 2, 28), filtros=None):
    return Contexto(dominio=DOM, inicio=ini, fim=fim,
                    filtros=filtros or Filtros(),
                    preset_comparacao="mes_fechado")


def test_decomposicao_fecha_quando_promete():
    casos = 0
    for mk in DOM.metricas:
        for dk in DOM.dimensoes:
            for preset in ("mes_fechado", "ultimos_28"):
                dec = mod_causa.decompor(CON, DOM, mk, dk,
                                         montar_preset(preset, REF), Filtros())
                if not np.isfinite(dec.delta):
                    continue
                casos += 1
                if dec.fecha:
                    escala = max(abs(dec.delta), abs(dec.total_a), 1.0)
                    assert abs(dec.residuo) <= escala * 1e-6, (
                        f"{mk}/{dk}/{preset}: prometeu fechar e sobrou "
                        f"{dec.residuo}")
    assert casos > 200


def test_gap_nao_promete_fechar():
    """Gap é razão entre médias: nenhuma dimensão fecha com ele."""
    for dk in DOM.dimensoes:
        assert not DOM.decomposicao_fecha("gap_genero", dk)


def test_tomoyo_e_card_dao_o_mesmo_numero():
    ini, fim = date(2025, 10, 1), date(2025, 12, 31)
    ctx = _ctx(ini, fim)
    testados = 0
    for mk in DOM.metricas_painel:
        m = DOM.metrica(mk)
        da_aba = agregar(CON, DOM, [mk], ini, fim).iloc[0][mk]
        r = perguntar(CON, f"quanto foi {m.rotulo.lower()}", ctx, usar_llm=False)
        if r.plano["metrica"] != mk or r.plano["intencao"] != "total":
            continue
        esperado = numero(float(da_aba) if pd.notna(da_aba) else float("nan"), m)
        assert esperado in r.texto, f"{mk}: card {esperado}, Tomoyo {r.texto[:120]}"
        testados += 1
    assert testados >= 5


def test_headcount_e_media_e_nao_soma():
    ini, fim = date(2025, 3, 1), date(2025, 3, 31)
    hc = agregar(CON, DOM, ["headcount"], ini, fim).iloc[0]["headcount"]
    dia = CON.execute("SELECT SUM(ativo) FROM fato WHERE data = DATE "
                      "'2025-03-15'").fetchone()[0]
    assert 0.9 * dia < hc < 1.1 * dia


def test_turnover_precoce_imaturo_fica_vazio():
    """Admitido há menos de 90 dias não teve tempo de sair: nulo, não zero."""
    tarde = agregar(CON, DOM, ["turnover_precoce", "admissoes"],
                    date(2026, 6, 1), date(2026, 8, 31)).iloc[0]
    assert tarde["admissoes"] > 0
    assert pd.isna(tarde["turnover_precoce"])
    cedo = agregar(CON, DOM, ["turnover_precoce"],
                   date(2026, 3, 1), date(2026, 5, 31)).iloc[0]
    assert pd.notna(cedo["turnover_precoce"])


def _vol_tech(ini, fim):
    return agregar(CON, DOM, ["turnover_voluntario"], ini, fim,
                   filtros=Filtros({"area": ["Tecnologia"],
                                    "nivel": ["Pleno", "Sênior"]})
                   ).iloc[0]["turnover_voluntario"]


def _enps_tech(ini, fim):
    return agregar(CON, DOM, ["enps"], ini, fim,
                   filtros=Filtros({"area": ["Tecnologia"]})).iloc[0]["enps"]


def test_onda_de_tecnologia_e_o_clima_avisa_antes():
    antes = _vol_tech(date(2025, 3, 1), date(2025, 6, 30))
    onda = _vol_tech(date(2026, 3, 1), date(2026, 6, 30))
    assert onda > 2 * antes, f"onda {onda:.1%} vs {antes:.1%}"
    # o clima cai em dez–fev, ANTES da onda de mar–jun
    enps_ok = _enps_tech(date(2025, 9, 1), date(2025, 11, 30))
    enps_aviso = _enps_tech(date(2025, 12, 1), date(2026, 2, 28))
    assert enps_aviso < enps_ok - 25


def test_reestruturacao_do_cd_aparece_como_involuntario():
    dia = agregar(CON, DOM, ["desligamentos"], date(2025, 8, 12),
                  date(2025, 8, 12),
                  filtros=Filtros({"area": ["Centro de distribuição"]})
                  ).iloc[0]["desligamentos"]
    assert dia >= 40


def test_gap_ajustado_menor_que_bruto():
    g = ext.gap_ajustado(CON, DOM, date(2025, 9, 1), date(2026, 8, 31))
    card = agregar(CON, DOM, ["gap_genero"], date(2025, 9, 1),
                   date(2026, 8, 31)).iloc[0]["gap_genero"]
    assert abs(g["bruto"] - card) < 1e-9          # o bruto é o número do card
    assert g["ajustado"] < g["bruto"] / 2          # a maior parte é composição
    assert 0.0 < g["ajustado"] < 0.08              # plantado: ~3,5% no cargo
    assert g["cobertura"] > 0.9
    v = g["celulas"][g["celulas"]["valida"]]
    assert (v["pessoas_f"] >= GRUPO_MINIMO).all()
    assert (v["pessoas_m"] >= GRUPO_MINIMO).all()


def test_risco_encontra_tecnologia_antes_da_onda():
    """Em fevereiro/2026, antes da onda, Tecnologia já está no topo."""
    df = ext.sinais_de_risco(CON, DOM, date(2026, 2, 28))
    topo = df.head(3)
    assert (topo["area"] == "Tecnologia").all(), topo[["area", "nivel", "risco"]]
    # e um ano antes, sem o choque, ninguém de Tecnologia aparece
    antes = ext.sinais_de_risco(CON, DOM, date(2025, 2, 28))
    assert not ((antes["area"] == "Tecnologia") & (antes["risco"] >= 40)).any()


def test_risco_nao_olha_para_o_futuro():
    """A pergunta feita em 28/02 responde com o que se sabia em 28/02."""
    a = ext.sinais_de_risco(CON, DOM, date(2026, 2, 28))
    import duckdb
    con2 = duckdb.connect()
    con2.execute("CREATE VIEW fato AS SELECT * FROM read_parquet('"
                 + str(Path(__file__).resolve().parents[1] / "data" /
                       DOM.arquivo).replace("\\", "/")
                 + "') WHERE data <= DATE '2026-02-28'")
    b = ext.sinais_de_risco(con2, DOM, date(2026, 2, 28))
    pd.testing.assert_frame_equal(a.reset_index(drop=True),
                                  b.reset_index(drop=True))


def test_nenhum_grupo_pequeno_aparece():
    df = ext.sinais_de_risco(CON, DOM, date(2026, 2, 28))
    assert (df["pessoas"] >= GRUPO_MINIMO).all()
    # com filtro que deixa grupos minúsculos, eles somem em vez de aparecer
    f = Filtros({"regiao": ["Norte"], "regime": ["Remoto"]})
    df2 = ext.sinais_de_risco(CON, DOM, date(2026, 2, 28), f)
    assert df2.empty or (df2["pessoas"] >= GRUPO_MINIMO).all()


def test_pergunta_sobre_pessoa_e_recusada():
    for q in ["quem vai pedir demissão?", "qual colaborador está insatisfeito?",
              "me passa a lista de pessoas que vão sair",
              "qual o salário do fulano?"]:
        r = perguntar(CON, q, _ctx(), usar_llm=False)
        assert r.plano["intencao"] == "pessoa", q
        assert "grupo" in r.texto
        assert "pessoa_id" not in (r.tabela.columns if r.tabela is not None
                                   else [])


def test_cada_pergunta_vai_para_a_rota_certa():
    casos = {
        "Onde tem risco de saída nos próximos meses?": ("risco", None),
        "O gap salarial de gênero é de cargo ou de composição?": ("gap", None),
        "o gap salarial está crescendo?": ("tendencia", "gap_genero"),
        "Qual área está perdendo mais gente?": ("ranking", "turnover_voluntario"),
        "Qual canal de contratação tem mais turnover precoce?":
            ("ranking", "turnover_precoce"),
        "Por que o eNPS mudou?": ("causa_raiz", "enps"),
        "qual o headcount?": ("total", "headcount"),
        "o que é eNPS?": ("definicao", "enps"),
        "por que você só fala de grupo?": ("explicacao", None),
        "oi": ("conversa", None),
    }
    for q, (intencao, metrica) in casos.items():
        r = perguntar(CON, q, _ctx(), usar_llm=False)
        assert r.plano["intencao"] == intencao, (q, r.plano["intencao"])
        if metrica:
            assert r.plano["metrica"] == metrica, (q, r.plano["metrica"])
