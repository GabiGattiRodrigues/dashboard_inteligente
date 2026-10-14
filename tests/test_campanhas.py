"""
Invariantes da camada de campanha de Marketing e CRM.

Cada teste corresponde a uma frase que a aba Campanhas ou a Abigail diz:

- os pedidos e a receita continuam os do Olist (a simulação não mexe neles);
- o ROAS por canal reconstrói o ROAS total (soma ÷ soma, sem pedido perdido);
- métrica de campanha não existe por meio de pagamento -- e o agente diz isso
  em vez de devolver um número sem sentido;
- o número da Abigail é o número da aba;
- o erro de orçamento plantado no fim da base vira alerta;
- o lift vem com intervalo, e o intervalo contém o lift.

Rodar:  python -m pytest tests/test_campanhas.py -q
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vulcano import alertas as mod_alertas
from vulcano import incrementalidade as inc
from vulcano.agente import Contexto, perguntar
from vulcano.dados import Filtros, agregar, conectar, periodo_disponivel
from vulcano.dominios import obter
from vulcano.formatacao import numero

DOM = obter("marketing")
CON = conectar(DOM)
DMIN, DMAX = periodo_disponivel(CON)
INI, FIM = date(2018, 3, 1), DMAX
RAIZ = Path(__file__).resolve().parents[1]


def _ctx(ini=INI, fim=FIM):
    return Contexto(dominio=DOM, inicio=ini, fim=fim, filtros=Filtros(),
                    preset_comparacao="mes_fechado")


def test_pedidos_e_receita_sao_os_do_olist():
    olist = CON.execute(f"""
        SELECT COUNT(DISTINCT order_id), SUM(receita)
          FROM read_parquet('{RAIZ / "data" / "fato_olist.parquet"}')
         WHERE data BETWEEN DATE '{DMIN}' AND DATE '{DMAX}'""").fetchone()
    v = agregar(CON, DOM, ["pedidos", "receita"], DMIN, DMAX).iloc[0]
    assert int(v["pedidos"]) == olist[0]
    assert abs(v["receita"] - olist[1]) < 1e-6 * olist[1]


def test_roas_por_canal_reconstroi_o_total():
    t = agregar(CON, DOM, ["roas"], INI, FIM).iloc[0]
    c = agregar(CON, DOM, ["roas"], INI, FIM, dims=["canal"])
    assert abs(c["roas__num"].sum() - t["roas__num"]) < 1e-6
    assert abs(c["roas__den"].sum() - t["roas__den"]) < 1e-6


def test_campanha_nao_existe_por_meio_de_pagamento():
    assert not DOM.dim_vale("roas", "meio_pagamento")
    r = perguntar(CON, "qual o ROAS por meio de pagamento?", _ctx(),
                  usar_llm=False)
    assert r.plano["dimensao"] != "meio_pagamento"
    assert "não existe por meio de pagamento" in r.texto


def test_numero_da_abigail_e_o_da_aba():
    for mk, q in [("roas", "qual o ROAS?"), ("cac", "qual o CAC?")]:
        r = perguntar(CON, q, _ctx(), usar_llm=False)
        v = agregar(CON, DOM, [mk], INI, FIM).iloc[0][mk]
        assert numero(v, DOM.metrica(mk)) in r.texto, (q, r.texto[:300])


def test_erro_de_orcamento_vira_alerta():
    al = mod_alertas.varrer(CON, DOM, DMAX, Filtros())
    assert any(a.chave_metrica in ("investimento", "roas", "cpc", "cac")
               for a in al), [a.chave_metrica for a in al]


def test_lift_tem_intervalo_que_contem_o_lift():
    lc = inc.por_campanha(CON, DOM, INI, FIM)
    v = lc.dropna(subset=["lift"])
    assert not v.empty
    assert ((v["ic_inf"] <= v["lift"]) & (v["lift"] <= v["ic_sup"])).all()
    r = perguntar(CON, "qual o lift do CRM?", _ctx(), usar_llm=False)
    assert "Cuidado com o volume" in r.texto


def test_janela_de_7_dias_incompleta_fica_vazia():
    ult = CON.execute("""
        SELECT COUNT(*) FROM fato
         WHERE tipo_campanha = 'CRM' AND janela_7d = 0
           AND resp_abriu IS NOT NULL""").fetchone()[0]
    assert ult == 0
    fim = CON.execute("""SELECT MIN(data) FROM fato
                          WHERE tipo_campanha = 'CRM' AND janela_7d = 0"""
                      ).fetchone()[0]
    assert (DMAX - fim.date()).days <= 6


def test_quem_abriu_superestima_o_lift():
    # A leitura clássica (abriu × controle) mistura efeito com perfil de
    # quem abre; o lift de quem recebeu, que compara grupos sorteados, é
    # sempre menor -- é a frase que a aba e a Abigail repetem.
    lc = inc.por_campanha(CON, DOM, INI, FIM).dropna(subset=["lift"])
    assert (lc["lift_aparente"] > lc["lift"]).all()


def test_mensuracao_da_abigail_bate_com_a_tabela():
    r = perguntar(CON, "Como foi a campanha de carrinho abandonado?", _ctx(),
                  usar_llm=False)
    assert r.plano["intencao"] == "mensuracao"
    lc = inc.por_campanha(CON, DOM, INI, FIM).set_index("campanha")
    v = lc.loc["E-mail • Carrinho abandonado"]
    from vulcano.formatacao import pct
    assert pct(v["r_abriu"], 2, False) in r.texto
    assert pct(v["lift"], 0) in r.texto
