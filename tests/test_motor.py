"""
Testes das invariantes do motor.

Nao testam "o codigo roda" -- testam as afirmacoes que o produto faz na tela.
Cada teste aqui corresponde a uma frase que o dashboard exibe para o usuario,
e existe para que essa frase nao possa ficar falsa em silencio:

- a cascata soma exatamente a variacao, quando promete somar;
- quando NAO promete, o residuo aparece em vez de sumir;
- efeito taxa + efeito mix + interacao reconstroem a contribuicao;
- o numero do agente e o numero da aba, sempre;
- o filtro da barra lateral chega ao agente;
- safra imatura fica vazia, nunca zero;
- o corte de materialidade realmente corta;
- o baseline robusto nao se deixa arrastar por um outlier;
- "pior" respeita a direcao da metrica.

Rodar:  python -m pytest tests/ -q      (ou  python tests/test_motor.py)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vulcano import alertas as mod_alertas
from vulcano import causa_raiz as mod_causa
from vulcano import tendencia as mod_tendencia
from vulcano.agente import Contexto, perguntar
from vulcano.dados import Filtros, agregar, conectar, periodo_disponivel
from vulcano.dominios import listar, obter
from vulcano.formatacao import numero, pct
from vulcano.periodos import montar_preset

PRESETS_TESTE = ["mes_fechado", "ultimos_28", "semana"]
REF = date(2018, 5, 15)
TOL = 1e-6


def _con(chave):
    dom = obter(chave)
    return conectar(dom), dom


# --------------------------------------------------------------------------- #
# 1. A cascata fecha quando promete fechar
# --------------------------------------------------------------------------- #

def test_decomposicao_fecha_quando_promete():
    casos = 0
    for dom in listar():
        con = conectar(dom)
        for mk in dom.metricas:
            for dk in dom.dimensoes:
                for preset in PRESETS_TESTE:
                    comp = montar_preset(preset, REF)
                    dec = mod_causa.decompor(con, dom, mk, dk, comp, Filtros())
                    if not np.isfinite(dec.delta):
                        continue
                    casos += 1
                    if dec.fecha:
                        escala = max(abs(dec.delta), abs(dec.total_a), 1.0)
                        assert abs(dec.residuo) <= escala * 1e-6, (
                            f"{dom.chave}/{mk}/{dk}/{preset}: prometeu fechar "
                            f"mas sobrou residuo {dec.residuo}"
                        )
    assert casos > 300, f"cobertura baixa demais: {casos} casos"
    print(f"  ok — {casos} combinacoes de metrica x dimensao x periodo")


def test_soma_das_barras_bate_com_a_tabela():
    """O que a cascata desenha e o que a tabela lista sao a mesma conta."""
    for dom in listar():
        con = conectar(dom)
        for mk in list(dom.metricas)[:6]:
            dk = dom.dims_filtro[0]
            comp = montar_preset("mes_fechado", REF)
            dec = mod_causa.decompor(con, dom, mk, dk, comp, Filtros(), top_n=8)
            if not np.isfinite(dec.delta):
                continue
            casc = mod_causa.dados_cascata(dec)
            deltas = casc[casc["tipo"] == "delta"]["valor"].sum()
            escala = max(abs(dec.delta), 1.0)
            assert abs(deltas - dec.delta) <= escala * 1e-6, (
                f"{dom.chave}/{mk}: cascata soma {deltas}, delta e {dec.delta}"
            )


# --------------------------------------------------------------------------- #
# 2. Quando NAO fecha, o residuo aparece
# --------------------------------------------------------------------------- #

def test_residuo_e_exposto_quando_nao_fecha():
    """
    Metrica de contagem distinta por dimensao de grao fino tem de acusar o
    problema: flag `fecha` falso E aviso escrito na tela. Silenciar isso seria
    apresentar uma conta que nao fecha como se fechasse.
    """
    dom = obter("marketing")
    con = conectar(dom)
    dec = mod_causa.decompor(con, dom, "pedidos", "categoria",
                             montar_preset("mes_fechado", REF), Filtros())
    assert not dec.fecha
    import unicodedata
    plano = "".join(c for c in unicodedata.normalize("NFKD", dec.aviso.lower())
                    if not unicodedata.combining(c))
    assert "residuo" in plano, f"o aviso nao menciona o residuo: {dec.aviso[:120]}"
    soma = dec.df["contribuicao"].sum()
    assert abs(dec.residuo - (dec.delta - soma)) < TOL
    # e o total exibido e o total VERDADEIRO, nao a soma inflada dos segmentos
    real = agregar(con, dom, ["pedidos"], dec.comparacao.atual.inicio,
                   dec.comparacao.atual.fim).iloc[0]["pedidos"]
    assert abs(dec.total_b - float(real)) < TOL
    assert dec.total_b < soma + dec.total_a + 1e6  # sanidade
    print(f"  ok — residuo de {dec.residuo:+.0f} pedidos exposto, nao redistribuido")


def test_o_modelo_nao_e_conservador_demais():
    """
    Dizer "nao fecha" sobre tudo seria seguro e inutil.

    Este teste cobra a reciproca: os casos marcados como nao-fechaveis tem de
    ser justamente os que de fato nao fecham. Clientes por regiao e o caso
    sutil -- regiao parece dimensao segura, mas a entidade contada e a pessoa,
    e a mesma pessoa pode comprar para duas regioes.
    """
    dom = obter("marketing")
    con = conectar(dom)
    comp = montar_preset("mes_fechado", REF)

    assert not dom.decomposicao_fecha("clientes", "regiao")
    dec = mod_causa.decompor(con, dom, "clientes", "regiao", comp, Filtros())
    assert abs(dec.residuo) > 0, (
        "clientes por regiao foi marcado como nao-fechavel mas fechou; "
        "o modelo esta conservador demais"
    )

    # e o caso vizinho, que DEVE fechar, fecha
    assert dom.decomposicao_fecha("pedidos", "regiao")
    dec2 = mod_causa.decompor(con, dom, "pedidos", "regiao", comp, Filtros())
    assert abs(dec2.residuo) < 1e-6
    print(f"  ok — clientes x regiao acusa residuo {dec.residuo:+.0f}; "
          f"pedidos x regiao fecha em zero")


# --------------------------------------------------------------------------- #
# 3. Taxa + mix + interacao == contribuicao
# --------------------------------------------------------------------------- #

def test_efeitos_reconstroem_a_contribuicao():
    for dom in listar():
        con = conectar(dom)
        razoes = [k for k, m in dom.metricas.items() if m.eh_razao]
        for mk in razoes:
            for dk in dom.dims_filtro[:3]:
                dec = mod_causa.decompor(con, dom, mk, dk,
                                         montar_preset("mes_fechado", REF),
                                         Filtros())
                if not np.isfinite(dec.delta):
                    continue
                soma = (dec.df["efeito_taxa"] + dec.df["efeito_mix"]
                        + dec.df["interacao"])
                erro = (soma - dec.df["contribuicao"]).abs().max()
                assert erro < 1e-9, f"{dom.chave}/{mk}/{dk}: erro {erro}"


# --------------------------------------------------------------------------- #
# 4. O numero do agente e o numero da aba
# --------------------------------------------------------------------------- #

def test_agente_e_aba_dao_o_mesmo_numero():
    """
    A afirmacao mais forte do produto: 'se o numero divergir do grafico, e bug'.
    Aqui ela vira teste. O caminho da aba e o caminho do agente sao chamados
    com o mesmo periodo e comparados valor a valor.
    """
    for dom in listar():
        con = conectar(dom)
        ini, fim = date(2018, 3, 1), date(2018, 5, 31)
        ctx = Contexto(dominio=dom, inicio=ini, fim=fim, filtros=Filtros(),
                       preset_comparacao="mes_fechado")
        for mk in dom.metricas_painel:
            m = dom.metrica(mk)
            da_aba = agregar(con, dom, [mk], ini, fim).iloc[0][mk]
            r = perguntar(con, f"quanto foi {m.rotulo.lower()}", ctx,
                          usar_llm=False)
            if r.plano["metrica"] != mk or r.plano["intencao"] != "total":
                continue  # a pergunta caiu em outra rota; nao e o alvo do teste
            esperado = numero(float(da_aba) if pd.notna(da_aba) else float("nan"), m)
            assert esperado in r.texto, (
                f"{dom.chave}/{mk}: aba diz {esperado}, agente diz {r.texto[:120]}"
            )


def test_filtro_da_tela_chega_ao_agente():
    dom = obter("marketing")
    con = conectar(dom)
    ini, fim = date(2018, 3, 1), date(2018, 5, 31)
    filtros = Filtros({"regiao": ["Sudeste"]})

    total = float(agregar(con, dom, ["receita"], ini, fim).iloc[0]["receita"])
    filtrado = float(agregar(con, dom, ["receita"], ini, fim,
                             filtros=filtros).iloc[0]["receita"])
    assert filtrado < total, "o filtro nao reduziu nada; nao esta sendo aplicado"

    ctx = Contexto(dominio=dom, inicio=ini, fim=fim, filtros=filtros)
    r = perguntar(con, "quanto foi a receita", ctx, usar_llm=False)
    m = dom.metrica("receita")
    assert numero(filtrado, m) in r.texto
    assert numero(total, m) not in r.texto
    print(f"  ok — com filtro o agente responde {numero(filtrado, m)}, "
          f"nao {numero(total, m)}")


# --------------------------------------------------------------------------- #
# 5. Credito: censura a direita preservada
# --------------------------------------------------------------------------- #

def test_safra_imatura_fica_vazia_nunca_zero():
    dom = obter("credito")
    con = conectar(dom)
    _, dmax = periodo_disponivel(con)

    df = con.execute("""
        SELECT safra,
               COUNT(*) AS contratos,
               COUNT(over90_mob6) AS com_marcacao,
               MAX(data) AS ultima
          FROM fato WHERE aprovado = 1
         GROUP BY 1 ORDER BY 1
    """).fetchdf()

    for _, r in df.iterrows():
        idade = (pd.Timestamp(dmax) - pd.Timestamp(r["ultima"])).days
        if idade < 180:
            assert r["com_marcacao"] == 0, (
                f"safra {r['safra']} tem {idade} dias e ja traz marcacao de "
                f"over90 MOB6 — censura a direita foi violada"
            )

    # E a metrica agregada devolve NULL (nao 0) para um periodo so de safra nova
    v = agregar(con, dom, ["over90_mob6"], dmax - timedelta(days=20), dmax)
    assert pd.isna(v.iloc[0]["over90_mob6"]), (
        "safra imatura devolveu numero em vez de vazio"
    )
    print("  ok — safras jovens sem marcacao; metrica devolve vazio, nao zero")


def test_choque_de_safra_e_detectavel():
    """O choque plantado no gerador tem de ser encontravel pelo motor."""
    dom = obter("credito")
    con = conectar(dom)
    df = agregar(con, dom, ["over30_mob3"], date(2017, 1, 5), date(2018, 3, 31),
                 dims=["safra"]).dropna(subset=["over30_mob3"])
    piores = df.nlargest(3, "over30_mob3")["safra"].tolist()
    assert set(piores) <= {"2017-09", "2017-10", "2017-11"}, (
        f"o motor nao encontrou o choque plantado; achou {piores}"
    )
    print(f"  ok — piores safras encontradas: {piores}")


# --------------------------------------------------------------------------- #
# 6. Alertas: materialidade e baseline robusto
# --------------------------------------------------------------------------- #

def test_materialidade_realmente_corta():
    dom = obter("marketing")
    con = conectar(dom)
    dia = date(2018, 5, 15)
    solto = mod_alertas.varrer(con, dom, dia, Filtros(), materialidade=0.0)
    apertado = mod_alertas.varrer(con, dom, dia, Filtros(), materialidade=0.10)
    assert len(solto) > len(apertado), (
        "o corte de materialidade nao esta filtrando nada"
    )
    print(f"  ok — materialidade 0% => {len(solto)} alertas; "
          f"10% => {len(apertado)}")


def test_baseline_resiste_a_outlier():
    """
    Mediana e MAD tem de ignorar um pico; media e desvio nao ignoram.

    O teste compara os dois na mesma serie: um unico outlier gigante infla o
    desvio padrao a ponto de esconder um desvio real seguinte. E exatamente o
    caso da Black Friday.
    """
    rng = np.random.default_rng(7)
    hist = np.concatenate([rng.normal(100, 5, 40), [1000.0]])  # 40 dias + pico

    z_rob, esperado = mod_alertas._z_robusto(130.0, hist)
    assert abs(esperado - 100.0) < 6, "a mediana foi arrastada pelo pico"
    assert abs(z_rob) > 3, f"z robusto perdeu o desvio real (z={z_rob:.2f})"

    z_ingenuo = (130.0 - hist.mean()) / hist.std()
    assert abs(z_ingenuo) < 1, (
        "o teste ficou sem sentido: a versao ingenua tambem detectaria"
    )
    print(f"  ok — z robusto {z_rob:+.1f} detecta; z por media/desvio "
          f"{z_ingenuo:+.2f} nao detectaria")


def test_serie_constante_nao_engole_o_desvio():
    """MAD zero nao pode virar 'nada aconteceu'."""
    z, esp = mod_alertas._z_robusto(130.0, np.array([100.0] * 40))
    assert abs(esp - 100.0) < 1e-9
    assert abs(z) > 3, f"serie constante engoliu um desvio obvio (z={z})"
    z0, _ = mod_alertas._z_robusto(100.0, np.array([100.0] * 40))
    assert z0 == 0.0, "serie constante sem desvio nao pode alertar"


def test_alerta_de_limite_nao_depende_de_historico():
    dom = obter("produto")
    con = conectar(dom)
    dia = date(2017, 11, 24)   # Black Friday: prazo estourado
    al = mod_alertas.varrer(con, dom, dia, Filtros())
    limites = [a for a in al if a.tipo == "limite"]
    assert limites, "nenhum limite de negocio disparou num dia claramente ruim"
    for a in limites:
        assert a.z == 0.0, "alerta de limite nao deveria usar z"


# --------------------------------------------------------------------------- #
# 7. "Pior" respeita a direcao da metrica
# --------------------------------------------------------------------------- #

def test_pior_nao_e_sinonimo_de_menor():
    dom = obter("produto")
    con = conectar(dom)
    ctx = Contexto(dominio=dom, inicio=date(2018, 3, 1), fim=date(2018, 5, 31),
                   filtros=Filtros())

    ruim = perguntar(con, "quais os piores estados em prazo de entrega", ctx,
                     usar_llm=False)
    bom = perguntar(con, "quais os melhores estados em prazo de entrega", ctx,
                    usar_llm=False)

    def primeiro(resp):
        return resp.tabela.iloc[0][resp.tabela.columns[1]]

    assert primeiro(ruim) > primeiro(bom), (
        f"prazo: 'pior' devolveu {primeiro(ruim)} e 'melhor' {primeiro(bom)} — "
        f"invertido, porque nesta metrica menor e melhor"
    )

    ctx2 = Contexto(dominio=obter("marketing"), inicio=ctx.inicio, fim=ctx.fim,
                    filtros=Filtros())
    con2 = conectar(obter("marketing"))
    ruim2 = perguntar(con2, "quais as piores categorias em receita", ctx2,
                      usar_llm=False)
    bom2 = perguntar(con2, "quais as melhores categorias em receita", ctx2,
                     usar_llm=False)
    assert primeiro(ruim2) < primeiro(bom2), "receita: 'pior' deveria ser menor"
    print("  ok — pior prazo = maior; pior receita = menor")


# --------------------------------------------------------------------------- #
# 8. Tendencia so afirma direcao quando ha evidencia
# --------------------------------------------------------------------------- #

def test_ruido_puro_nao_vira_tendencia():
    dom = obter("marketing")
    con = conectar(dom)
    t = mod_tendencia.analisar(con, dom, "receita", date(2018, 3, 1),
                               date(2018, 5, 31), Filtros())
    assert t is not None
    if not t.significante:
        assert t.direcao == "estavel"
    if t.direcao != "estavel":
        assert t.p_valor < 0.05


def test_qualidade_corta_a_cauda_de_extracao():
    """Os ultimos dias do Olist sao artefato de exportacao, nao queda de vendas."""
    dom = obter("marketing")
    con = conectar(dom)
    _, dmax = periodo_disponivel(con)
    s = agregar(con, dom, ["pedidos"], dmax - timedelta(days=13), dmax,
                por_dia=True)
    mediana = s["pedidos"].median()
    assert s["pedidos"].iloc[-1] > mediana * 0.4, (
        "o ultimo dia da base ainda parece cauda de extracao"
    )


# --------------------------------------------------------------------------- #
# Conversa: o agente tem de saber quando NAO responder com numero
# --------------------------------------------------------------------------- #

def test_conversa_nao_devolve_numero():
    """
    "oi" nao pode virar faturamento.

    O modo de falhar aqui e silencioso e caro: a pessoa cumprimenta, o agente
    responde com a receita do mes, e ela conclui que o produto e um formulario
    com cara de chat. O mesmo vale para pergunta que o agente nao entendeu --
    chutar uma metrica e pior do que admitir, porque o numero chutado vira
    slide de reuniao.
    """
    dom = obter("marketing")
    con = conectar(dom)
    ctx = Contexto(dominio=dom, inicio=date(2017, 11, 1), fim=date(2017, 11, 30),
                   filtros=Filtros())

    sociais = ["oi", "bom dia", "obrigada!", "tchau", "tudo bem?"]
    for q in sociais:
        r = perguntar(con, q, ctx, usar_llm=False)
        assert r.plano["intencao"] == "conversa", f"{q!r} virou {r.plano['intencao']}"
        assert "R$" not in r.texto, f"{q!r} devolveu moeda: {r.texto[:90]}"

    fora_de_escopo = ["você gosta de café?", "qual o sentido da vida"]
    for q in fora_de_escopo:
        r = perguntar(con, q, ctx, usar_llm=False)
        assert r.plano["intencao"] == "nao_entendi", \
            f"{q!r} virou {r.plano['intencao']} em vez de admitir"
        assert "R$" not in r.texto

    # E o contrario: educacao na frente de uma pergunta de dado nao pode
    # sequestrar a resposta. "Bom dia, quanto foi a receita?" quer o numero.
    r = perguntar(con, "bom dia! quanto foi a receita?", ctx, usar_llm=False)
    assert r.plano["intencao"] == "total"
    assert "R$" in r.texto
    print(f"  ok — {len(sociais)} saudacoes sem numero; "
          f"{len(fora_de_escopo)} perguntas fora de escopo admitidas")


def test_conceito_nao_sequestra_consulta():
    """
    "o que e um alerta" explica; "tem alerta hoje?" lista.

    Os dois usam a mesma palavra. Sem separar duvida de consulta, o painel
    perderia a resposta mais usada da ferramenta para uma aula sobre ela.
    """
    dom = obter("marketing")
    con = conectar(dom)
    ctx = Contexto(dominio=dom, inicio=date(2017, 11, 1), fim=date(2017, 11, 30),
                   filtros=Filtros())

    casos = {
        "o que é z robusto?": "explicacao",
        "me explica a cascata": "explicacao",
        "de onde vem esse dado?": "explicacao",
        "como você calcula o ticket médio?": "definicao",
        "tem alerta hoje?": "alertas",
        "a receita está crescendo?": "tendencia",
        "quais as maiores categorias?": "ranking",
    }
    for q, esperado in casos.items():
        r = perguntar(con, q, ctx, usar_llm=False)
        assert r.plano["intencao"] == esperado, \
            f"{q!r} => {r.plano['intencao']}, esperado {esperado}"
        assert r.texto.strip(), f"{q!r} devolveu resposta vazia"
    print(f"  ok — {len(casos)} perguntas roteadas para a intencao certa")


def test_funil_aponta_a_queda_e_nao_o_nivel():
    """
    "Onde a jornada trava?" nao pode responder "na etapa final, com 100%".

    Ordenar a taxa por etapa devolve a ultima etapa com 100% -- verdadeiro,
    tautologico e inutil. A pergunta e sobre a QUEDA entre duas etapas.
    """
    dom = obter("produto")
    con = conectar(dom)
    ctx = Contexto(dominio=dom, inicio=date(2017, 11, 1), fim=date(2017, 11, 30),
                   filtros=Filtros())
    r = perguntar(con, "onde a jornada trava?", ctx, usar_llm=False)
    assert r.plano["intencao"] == "funil"
    queda = r.fatos.get("maior_queda")
    assert queda and queda["perdidos"] > 0, "nenhuma queda encontrada no funil"
    assert queda["de"] != queda["para"]
    # A etapa apontada tem de ser uma transicao real declarada no dominio.
    rotulos = [rot for _, rot, _ in dom.funil]
    assert queda["de"] in rotulos and queda["para"] in rotulos
    print(f"  ok — maior queda entre {queda['de']} e {queda['para']}: "
          f"{queda['perdidos']} pedidos")


# --------------------------------------------------------------------------- #

def main() -> int:
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    falhas = 0
    for t in testes:
        nome = t.__name__.replace("test_", "").replace("_", " ")
        try:
            t()
            print(f"PASSOU  {nome}")
        except AssertionError as e:
            falhas += 1
            print(f"FALHOU  {nome}\n        {e}")
        except Exception as e:  # noqa: BLE001
            falhas += 1
            print(f"ERRO    {nome}\n        {type(e).__name__}: {e}")
    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
