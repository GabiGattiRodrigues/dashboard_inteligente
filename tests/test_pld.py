"""
Testes do domínio de Compliance e PLD (Ravena).

Mesmo espírito de test_motor.py: cada teste é uma frase que a tela afirma e
que não pode ficar falsa em silêncio.

- as tipologias plantadas são encontradas pelas regras que dizem encontrá-las;
- a calibração conta exatamente os alertas que o motor conta;
- a fila da aba é o "em aberto" do motor;
- falso positivo não conta alerta imaturo;
- prazo de comunicação respeita dia útil e feriado;
- a prioridade é a soma dos fatores que a tela mostra;
- a supressão é mesmo de um alerta por cliente, regra e mês;
- o dossiê não inventa número e não decide;
- a Ravena manda cada pergunta para a rota certa.

Rodar:  python -m pytest tests/test_pld.py -q
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vulcano.agente import Contexto, perguntar  # noqa: E402
from vulcano.dados import Filtros, agregar, conectar  # noqa: E402
from vulcano.dominios import obter  # noqa: E402
from vulcano.pld import dados as pld_dados  # noqa: E402
from vulcano.pld import fila as mod_fila  # noqa: E402
from vulcano.pld import parecer as mod_parecer  # noqa: E402
from vulcano.pld.calendario import proximo_dia_util  # noqa: E402
from vulcano.pld.regras import REGRAS  # noqa: E402

PASTA = Path(__file__).resolve().parents[1] / "data"
DOM = obter("pld")
CON = conectar(DOM)
BASE = pld_dados.data_base()


def _fato() -> pd.DataFrame:
    f = pd.read_parquet(PASTA / "fato_pld.parquet")
    f["data"] = pd.to_datetime(f["data"])
    return f


# --------------------------------------------------------------------------- #
# 1. O gabarito é encontrado
# --------------------------------------------------------------------------- #

def test_tipologias_plantadas_sao_encontradas_pela_regra_certa():
    f = _fato()
    gab = pd.read_parquet(PASTA / "pld_gabarito.parquet")
    regras = f.groupby("cliente_id")["regra_id"].agg(set)
    esperado = {"passagem": "R02", "anel_troca": "R05", "fachada_empresa": "R07",
                "fracionamento": "R03", "pep_habitual": "R09",
                "obito_movimenta": "R10", "fachada_titular": "R08",
                "renda": "R01"}
    for tip, rid in esperado.items():
        ids = gab.loc[gab["tipologia"] == tip, "cliente_id"]
        achados = sum(1 for c in ids if rid in regras.get(c, set()))
        taxa = achados / len(ids)
        assert taxa >= 0.9, f"{tip}: {rid} achou só {taxa:.0%} dos {len(ids)}"
    # a troca de madrugada também tem de aparecer na regra de horário
    anel = gab.loc[gab["tipologia"] == "anel_troca", "cliente_id"]
    assert all("R06" in regras.get(c, set()) for c in anel)


def test_mudanca_de_politica_da_r01_aparece_no_volume():
    f = _fato()
    r01 = f[f["regra_id"] == "R01"]
    antes = r01[r01["data"] < "2026-03-01"].groupby(r01["data"].dt.to_period("M")).size().mean()
    depois = r01[r01["data"] >= "2026-03-01"].groupby(r01["data"].dt.to_period("M")).size().mean()
    assert depois > antes * 1.2, f"R01 antes {antes:.0f}/mês, depois {depois:.0f}/mês"


# --------------------------------------------------------------------------- #
# 2. Calibração e fila batem com o motor
# --------------------------------------------------------------------------- #

def test_calibracao_conta_exatamente_o_que_o_motor_conta():
    """A conta da aba de calibração, na janela de vigência do corte atual."""
    cal = pld_dados.calibracao()
    for r in REGRAS.values():
        if not r.calibravel:
            continue
        vigencia = (r.parametro.historico[-1][0] if r.parametro.historico
                    else date(2025, 9, 1))
        janela = cal[(cal["regra_id"] == r.id)
                     & (cal["mes"] >= vigencia.strftime("%Y-%m"))]
        pela_calibracao = int((janela["indicador"] >= r.parametro.valor).sum())
        df = agregar(CON, DOM, ["alertas"], vigencia, BASE,
                     filtros=Filtros({"regra": [r.rotulo]}))
        pelo_motor = int(df.iloc[0]["alertas"]) if not df.empty and pd.notna(df.iloc[0]["alertas"]) else 0
        assert pela_calibracao == pelo_motor, (
            f"{r.id}: calibração diz {pela_calibracao}, motor diz {pelo_motor}")


def test_fila_da_aba_e_o_em_aberto_do_motor():
    for filtros in (Filtros(), Filtros({"regra": [REGRAS["R02"].rotulo]}),
                    Filtros({"tipo_cliente": ["Estabelecimento (PJ)"]})):
        fila = mod_fila.posicao(CON, DOM, BASE, filtros)
        motor = agregar(CON, DOM, ["em_aberto"], date(2025, 9, 1), BASE,
                        filtros=filtros).iloc[0]["em_aberto"]
        assert int(fila["alertas"].sum()) == int(motor or 0), filtros.resumo(DOM)


def test_fila_reconstruida_numa_data_passada_nao_ve_o_futuro():
    ref = date(2026, 6, 30)
    al = mod_fila.alertas_abertos(CON, DOM, ref)
    assert (al["data"] <= ref).all()
    f = _fato()
    ids = set(al["alerta_id"])
    decididos_antes = f[(f["alerta_id"].isin(ids)) & f["data_decisao"].notna()
                        & (pd.to_datetime(f["data_decisao"]) <= pd.Timestamp(ref))]
    assert decididos_antes.empty


# --------------------------------------------------------------------------- #
# 3. Censura: alerta imaturo não entra em taxa de decisão
# --------------------------------------------------------------------------- #

def test_falso_positivo_nao_conta_alerta_imaturo():
    f = _fato()
    jovens = f[f["data"] > pd.Timestamp(BASE - timedelta(days=45))]
    assert jovens["descartado_m"].isna().all()
    assert jovens["dias_analise"].isna().all()
    assert jovens["comunicado_maduro"].isna().all()
    df = agregar(CON, DOM, ["taxa_falso_positivo", "comunicacoes"],
                 BASE - timedelta(days=30), BASE)
    assert pd.isna(df.iloc[0]["taxa_falso_positivo"])
    assert pd.isna(df.iloc[0]["comunicacoes"]), "mês imaturo apareceu como zero"


# --------------------------------------------------------------------------- #
# 4. Prazos
# --------------------------------------------------------------------------- #

def test_comunicacao_vai_no_dia_util_seguinte_pulando_feriado():
    assert proximo_dia_util(date(2026, 4, 2)) == date(2026, 4, 6)    # Sexta Santa
    assert proximo_dia_util(date(2026, 6, 3)) == date(2026, 6, 5)    # Corpus Christi
    assert proximo_dia_util(date(2026, 8, 28)) == date(2026, 8, 31)  # sexta -> segunda
    f = _fato()
    com = f[f["comunicado"] == 1]
    no_prazo = com["com_no_prazo"] == 1
    for r in com[no_prazo].head(200).itertuples():
        assert r.data_comunicacao <= proximo_dia_util(r.data_decisao)
    assert (~no_prazo).sum() > 0, "o painel precisa ter o que mostrar no limite D+1"


# --------------------------------------------------------------------------- #
# 5. Prioridade e supressão
# --------------------------------------------------------------------------- #

def test_prioridade_e_a_soma_dos_fatores_que_a_tela_mostra():
    fila = mod_fila.posicao(CON, DOM, BASE)
    for r in fila.head(40).itertuples():
        d = mod_parecer.montar(CON, DOM, r.cliente_id, BASE)
        soma = min(100.0, sum(p for _, p in d.fatores))
        assert abs(soma - r.prioridade) < 0.11, r.codigo
        assert abs(d.prioridade - r.prioridade) < 0.11, r.codigo
    um = mod_fila.prioridade(["R01"], 20_000, "Baixo", False, False)
    dois = mod_fila.prioridade(["R01", "R04"], 20_000, "Baixo", False, False)
    assert dois > um, "sinais independentes no mesmo cliente têm de somar"


def test_supressao_e_um_alerta_por_cliente_regra_e_mes():
    f = _fato()
    f["mes"] = f["data"].dt.to_period("M")
    dup = f[f["regra_id"] != "R10"].duplicated(["cliente_id", "regra_id", "mes"])
    assert not dup.any()
    assert not f[f["regra_id"] == "R10"].duplicated("cliente_id").any()


# --------------------------------------------------------------------------- #
# 6. Dossiê
# --------------------------------------------------------------------------- #

def test_dossie_nao_inventa_numero_e_nao_decide():
    fila = mod_fila.posicao(CON, DOM, BASE)
    amostra = pd.concat([fila.head(8), fila.tail(4)])
    for r in amostra.itertuples():
        d = mod_parecer.montar(CON, DOM, r.cliente_id, BASE)
        permitidos = " ".join(d.abertos["evidencia"]) + " " + " ".join(
            mod_parecer._brl(v) for v in d.contrapartes["valor"])
        for valor in re.findall(r"R\$ [\d.]+", d.texto):
            assert valor in permitidos, f"{d.codigo}: {valor} não está nos dados"
        baixo = d.texto.lower()
        for proibido in ("recomendo comunicar", "deve ser comunicado",
                         "recomendo descartar", "é lavagem", "lava dinheiro",
                         "criminoso"):
            assert proibido not in baixo, f"{d.codigo}: '{proibido}'"
        assert "a decisão é da analista" in baixo


# --------------------------------------------------------------------------- #
# 7. Rotas da Ravena
# --------------------------------------------------------------------------- #

def _ctx():
    return Contexto(dominio=DOM, inicio=BASE - timedelta(days=89), fim=BASE,
                    filtros=Filtros(), preset_comparacao="ultimos_90")


def test_cada_pergunta_vai_para_a_rota_certa():
    topo = mod_fila.posicao(CON, DOM, BASE).iloc[0]["codigo"]
    casos = {
        "Quais clientes precisam de atenção primeiro?": "fila",
        f"me mostra o dossiê do {topo}": "dossie",
        f"e o {topo.lower().replace('-', '')}?": "dossie",
        "o que é a R02?": "regra",
        "O que diz a Circular 3.978 sobre o prazo de análise?": "explicacao",
        "como a prioridade é calculada?": "explicacao",
        "tem alerta hoje?": "alertas",
        "oi": "conversa",
    }
    for q, rota in casos.items():
        r = perguntar(CON, q, _ctx(), usar_llm=False)
        assert r.plano["intencao"] == rota, f"'{q}' foi para {r.plano['intencao']}"

    # "alerta" é métrica em Compliance: "por que os alertas mudaram" é causa
    # raiz do volume, não a lista de anomalias do dia
    r = perguntar(CON, "por que os alertas caíram contra o mês passado?", _ctx(),
                  usar_llm=False)
    assert r.plano["intencao"] == "causa_raiz"
    assert r.plano["metrica"] == "alertas"


def test_fila_do_agente_e_a_fila_da_aba():
    for filtros in (Filtros(), Filtros({"regiao": ["Centro-Oeste"]})):
        ctx = _ctx()
        ctx.filtros = filtros
        r = perguntar(CON, "quais clientes precisam de atenção?", ctx,
                      usar_llm=False)
        fila = mod_fila.posicao(CON, DOM, BASE, filtros)
        assert f"**{len(fila)} clientes**" in r.texto, r.texto[:160]


def test_perfil_do_indicador_bate_com_os_alertas():
    """O "acima do corte" do perfil é o alerta que o motor conta no mês."""
    perfil = pld_dados.indicadores()
    f = _fato()
    f["mes"] = f["data"].dt.strftime("%Y-%m")
    contagem = f.groupby(["regra_id", "mes"]).size()
    for r in perfil.itertuples():
        esperado = int(contagem.get((r.regra_id, r.mes), 0))
        assert r.acima_do_corte == esperado, f"{r.regra_id}/{r.mes}"
        assert r.p50 <= r.p75 <= r.p90 <= r.p95 <= r.p99
        assert r.acima_do_corte <= r.avaliados


def test_decomposicao_do_volume_fecha():
    """Efeito população + efeito seleção + interação = variação de alertas."""
    perfil = pld_dados.indicadores()
    for rid, d in perfil.groupby("regra_id"):
        d = d.sort_values("mes").reset_index(drop=True)
        for i in range(1, len(d)):
            a, b = d.loc[i - 1], d.loc[i]
            ta = a["acima_do_corte"] / a["avaliados"]
            tb = b["acima_do_corte"] / b["avaliados"]
            d_aval, d_taxa = b["avaliados"] - a["avaliados"], tb - ta
            soma = d_aval * ta + a["avaliados"] * d_taxa + d_aval * d_taxa
            delta = b["acima_do_corte"] - a["acima_do_corte"]
            assert abs(soma - delta) < 1e-6, f"{rid} {a['mes']}->{b['mes']}"


def test_sinais_brutos_cobrem_o_periodo_e_veem_a_onda():
    comp = pld_dados.comportamento()
    meses = sorted(comp["mes"].unique())
    assert meses[0] == "2025-09" and meses[-1] == "2026-08"
    # a onda de contas de passagem tem de aparecer no sinal bruto, não só no
    # alerta: mais Pix recebidos e mais pagadores distintos por conta
    def valor(mes, ind):
        linha = comp[(comp["mes"] == mes) & (comp["indicador"] == ind)]
        return float(linha["valor"].iloc[0])
    for ind in ("Pix recebidos", "Pagadores distintos por conta (7 dias)"):
        assert valor("2026-07", ind) > valor("2026-05", ind) * 1.1, ind


def test_ciclo_mostra_a_falha_de_abril():
    ci = pld_dados.ciclo()
    abril = ci[[d.month == 4 and d.year == 2026 for d in ci["data"]]]
    no_dia = abril[["checados", "previstos"]].min(axis=1).sum()
    assert no_dia < abril["previstos"].sum()
    assert (abril["situacao"] == "Falha do job").sum() == 3


if __name__ == "__main__":
    import inspect
    for nome, fn in list(globals().items()):
        if nome.startswith("test_") and inspect.isfunction(fn):
            fn()
            print(f"ok  {nome}")
