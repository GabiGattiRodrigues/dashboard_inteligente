"""
Testes do domínio de Logística (Vulcão).

Cada teste corresponde a uma frase que o painel ou o Vulcão afirmam:

- todo pedido do período já venceu, e quem nunca chegou conta como atraso;
- a fila numa data só usa o que se sabia naquela data;
- as faixas da régua somam a fila inteira;
- a curva do ponto de não retorno só cai, e o intervalo de Wilson contém a
  taxa;
- a taxa do D+3 e do D+7 na curva é a mesma do card;
- o gráfico de controle marca as semanas de pico conhecidas;
- o número do Vulcão é o número do card;
- cada pergunta vai para a rota certa.

Rodar:  python -m pytest tests/test_logistica.py -q
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vulcano.agente import Contexto, perguntar
from vulcano.dados import Filtros, agregar, conectar
from vulcano.dominios import obter
from vulcano.logistica import agente as ext
from vulcano.logistica import dados as ld

DOM = obter("logistica")
CON = conectar(DOM)
INI, FIM = date(2017, 9, 1), date(2018, 8, 31)


def _ctx(ini=date(2018, 8, 1), fim=date(2018, 8, 31), plano=None):
    return Contexto(dominio=DOM, inicio=ini, fim=fim, filtros=Filtros(),
                    preset_comparacao="mes_fechado", ultimo_plano=plano)


def test_nunca_entregue_conta_como_atraso():
    df = CON.execute("""SELECT SUM(no_prazo) a, SUM(nao_entregue) b,
                               SUM(atrasou) c, COUNT(*) total FROM fato""").df()
    r = df.iloc[0]
    assert r["a"] + r["b"] + r["c"] == r["total"]
    v = agregar(CON, DOM, ["pct_no_prazo", "pct_fora_prazo"], INI, FIM)
    assert abs(v.iloc[0]["pct_no_prazo"] + v.iloc[0]["pct_fora_prazo"] - 1) < 1e-12


def test_fila_nao_olha_o_futuro():
    ref = date(2018, 4, 10)
    f = ld.fila(CON, DOM, ref)
    assert not f.empty
    assert (pd.to_datetime(f["prometida"]) < pd.Timestamp(ref)).all()
    assert (pd.to_datetime(f["ultimo_evento"]) <= pd.Timestamp(ref)).all()
    # um pedido entregue DEPOIS da referência estava na fila naquele dia
    depois = CON.execute(f"""
        SELECT order_id FROM fato
         WHERE CAST(data AS DATE) < DATE '{ref}'
           AND CAST(dt_entrega AS DATE) > DATE '{ref}' LIMIT 1""").fetchone()[0]
    assert depois in set(f["order_id"])


def test_faixas_somam_a_fila():
    r = ld.resumo_fila(ld.fila(CON, DOM, FIM))
    assert r["vencido"] + r["d3"] + r["d7"] + r["esquecido"] == r["total"]
    assert r["transportadora"] + r["seller"] == r["total"]


def test_curva_cai_e_o_intervalo_contem_a_taxa():
    c = ld.ponto_sem_volta(CON, DOM, INI, FIM)
    assert (c["pendentes"].diff().dropna() <= 0).all()
    assert ((c["ic_inf"] <= c["taxa"]) & (c["taxa"] <= c["ic_sup"])).all()


def test_d3_e_d7_da_curva_batem_com_o_card():
    c = ld.ponto_sem_volta(CON, DOM, INI, FIM).set_index("k")
    v = agregar(CON, DOM, ["chegam_d3", "chegam_d7"], INI, FIM).iloc[0]
    assert abs(c.loc[3, "taxa"] - v["chegam_d3"]) < 1e-12
    assert abs(c.loc[7, "taxa"] - v["chegam_d7"]) < 1e-12


def test_wilson_fica_em_zero_um():
    for x, n in [(0, 5), (5, 5), (1, 3), (300, 500)]:
        a, b = ld.wilson(x, n)
        assert 0 <= a <= x / n <= b <= 1


def test_controle_pega_os_picos_conhecidos():
    c = ld.controle(CON, DOM, INI, FIM, por="origem")
    sp = c[(c["segmento"] == "SP") & c["acima"]]["semana"]
    # Natal de 2017 e o pico de mar–abr/2018
    assert ((sp >= "2017-12-11") & (sp <= "2018-01-08")).any()
    assert ((sp >= "2018-03-12") & (sp <= "2018-04-16")).any()


def test_numero_do_vulcao_e_o_do_card():
    ctx = _ctx()
    r = perguntar(CON, "qual o no prazo?", ctx, usar_llm=False)
    v = agregar(CON, DOM, ["pct_no_prazo"], ctx.inicio, ctx.fim).iloc[0]
    from vulcano.formatacao import numero
    assert numero(v["pct_no_prazo"], DOM.metrica("pct_no_prazo")) in r.texto


def test_rotas():
    casos = {
        "quais pedidos estão travados?": "travados",
        "qual origem está fora de controle?": "controle",
        "a régua D+3/D+7 faz sentido?": "regua",
        "me mostra o pedido d730d8d0": "pedido",
        "which orders are stuck?": "travados",
        "is any origin out of control?": "controle",
    }
    for q, esperado in casos.items():
        p = ext.interpretar(q, _ctx())
        assert p and p["intencao"] == esperado, (q, p)
    # pergunta de conceito e pergunta agregada seguem para o motor genérico
    assert ext.interpretar("o que é p-chart?", _ctx()) is None
    assert ext.interpretar("por que o no prazo caiu?", _ctx()) is None
    # continuação da régua abre por origem
    p = ext.interpretar("e por origem?", _ctx(plano={"intencao": "regua"}))
    assert p["intencao"] == "regua" and p["por"] == "origem"


def test_semana_fora_de_controle_diz_quem_puxou():
    # Semana de 26/03/2018: a malha inteira estourou; de 04/06/2018: só o
    # Sudeste.
    r = ld.semana_da_malha(CON, DOM, date(2018, 4, 3))
    assert r["acima"] and r["puxou"]
    assert abs(r["contribuicoes"]["excesso"].sum()
               - (r["p"] - (r["contribuicoes"]["n"] * r["contribuicoes"]["p_bar"]).sum() / r["n"])) < 1e-9
    r2 = ld.semana_da_malha(CON, DOM, date(2018, 6, 12))
    assert r2["acima"] and r2["puxou"]["segmento"] == "Sudeste"
    txt = " ".join(ext.ler_semana(r2))
    assert "Sudeste" in txt and "saiu do controle" in txt


def test_recomendacao_e_do_assunto_do_agente():
    from vulcano.playbooks import P
    from vulcano.dominios import DOMINIOS
    for chave, mets in P.items():
        dom = DOMINIOS[chave]
        for mk in mets:
            assert mk in dom.metricas, (chave, mk)
