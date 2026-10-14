"""
Constrói o fato de Marketing e CRM: os pedidos reais do Olist com a campanha
que trouxe cada um, mais as linhas de investimento e de disparo que o Olist
não publica.

Por que simular, e por que assim
--------------------------------
O Olist publica pedido, item, cliente e pagamento -- mas não diz de onde o
pedido veio, quanto custou trazê-lo nem quantos e-mails foram mandados. Sem
isso não existe ROAS, CAC, taxa de abertura ou lift de CRM, que são o pão com
manteiga de quem cuida de campanha.

A camada simulada é AMARRADA aos pedidos reais, e não sorteada ao lado deles:

- cada pedido real recebe um canal e uma campanha (atribuição last-click),
  com probabilidade que depende do que o pedido é de verdade: primeira compra
  ou recompra, categoria, dia da semana e data (Black Friday de 2017, Natal,
  Dia das Mães, Copa de 2018);
- o investimento de mídia nasce dos pedidos que a campanha trouxe, pelo
  caminho que a plataforma de mídia faz: pedidos ÷ conversão = cliques,
  cliques × CPC = investimento, cliques ÷ CTR = impressões;
- os disparos de CRM nascem da base real: a newsletter vai para quem já
  comprou até aquele dia (mais uma base de leads), a reativação vai para quem
  fez a última compra há exatos 90 dias, o WhatsApp de recompra vai para quem
  comprou há 18 dias;
- todo disparo de CRM separa 10% de grupo controle, que não recebe nada.
  Comparar a conversão de quem recebeu com a de quem não recebeu é o que
  separa "o CRM vendeu" de "o CRM estava lá quando a pessoa ia comprar de
  qualquer jeito".

A receita, os pedidos, os clientes, as categorias e os estados continuam
sendo os do Olist, sem nenhuma alteração. Só o que é de campanha é simulado.

Eventos plantados (para o painel ter o que achar, e documentados na aba
Sobre os dados):

1. Black Friday 2017: mídia social e e-mail concentram o pico de novembro, e
   o CPC sobe 25% no leilão.
2. Jun/2018 em diante: o CPC de "Social • Prospecção" sobe 35% e o CTR cai
   20% (fadiga de criativo + leilão da Copa) -- o ROAS do social cai.
3. WhatsApp de recompra entra em mar/2018 com o maior lift do CRM.
4. Nos dois últimos dias da base, o orçamento de "Social • Prospecção" sai
   2,6x maior por erro de configuração, sem pedido acompanhando -- é o que a
   aba de Alertas deve encontrar.

Grão do resultado
-----------------
- linhas de pedido: as mesmas do fato do Olist (item de pedido), com
  `canal`, `campanha` e `tipo_campanha`;
- linhas de campanha: data × campanha × estado, com investimento,
  impressões, cliques, envios, aberturas, cliques de CRM, opt-outs e grupo
  controle. Nessas linhas as colunas de pedido ficam vazias -- por isso cada
  métrica declara em quais dimensões existe (ver `semantica.Metrica.dims`).

Saída: data/fato_marketing.parquet
"""

from pathlib import Path

import numpy as np
import pandas as pd

PASTA = Path(__file__).resolve().parents[1] / "data"
ENTRADA = PASTA / "fato_olist.parquet"
SAIDA = PASTA / "fato_marketing.parquet"

SEMENTE = 20260810
rng = np.random.default_rng(SEMENTE)

D = pd.Timestamp
BF = (D("2017-11-13"), D("2017-11-27"))       # janela de Black Friday (mídia)
BF_EMAIL = [D("2017-11-20"), D("2017-11-22"), D("2017-11-24"), D("2017-11-27")]
FADIGA = D("2018-06-01")                       # CPC do social sobe
APP = D("2017-07-01")                          # app lançado: push existe daqui
WHATSAPP = D("2018-03-01")
REATIVACAO = D("2017-06-01")

MIDIA, CRM, ORG = "Mídia paga", "CRM", "Orgânico e direto"

# --------------------------------------------------------------------------- #
# Catálogo de campanhas
# --------------------------------------------------------------------------- #
# w_novo / w_rec: peso relativo na atribuição de primeira compra / recompra.
# janela: (início, fim) em que a campanha existe. afinidade: categorias que a
# campanha puxa mais (peso x3). Mídia: cvr (pedido por clique), cpc, ctr.
# CRM: abertura, clique, optout (por envio), custo por envio e lift sobre o
# grupo controle (quanto a conversão de quem recebeu supera a de quem não
# recebeu).

CAMPANHAS = [
    # ---- mídia paga ------------------------------------------------------- #
    dict(nome="Busca • Marca", canal="Busca paga", tipo=MIDIA,
         w_novo=.090, w_rec=.060, cvr=.045, cpc=.55, ctr=.090),
    dict(nome="Busca • Categorias", canal="Busca paga", tipo=MIDIA,
         w_novo=.085, w_rec=.030, cvr=.018, cpc=1.10, ctr=.035),
    dict(nome="Shopping • Catálogo", canal="Busca paga", tipo=MIDIA,
         w_novo=.065, w_rec=.020, cvr=.015, cpc=.70, ctr=.012),
    dict(nome="Social • Prospecção", canal="Social pago", tipo=MIDIA,
         w_novo=.075, w_rec=.020, cvr=.009, cpc=.65, ctr=.011, rampa=True),
    dict(nome="Social • Remarketing", canal="Social pago", tipo=MIDIA,
         w_novo=.045, w_rec=.050, cvr=.022, cpc=.80, ctr=.016, rampa=True),
    dict(nome="Social • Black Friday 2017", canal="Social pago", tipo=MIDIA,
         w_novo=.200, w_rec=.100, cvr=.014, cpc=.75, ctr=.015, janela=BF),
    dict(nome="Social • Natal 2017", canal="Social pago", tipo=MIDIA,
         w_novo=.050, w_rec=.030, cvr=.012, cpc=.75, ctr=.014,
         janela=(D("2017-12-01"), D("2017-12-24")),
         afinidade=["Brinquedos", "Relógios presentes", "Perfumaria",
                    "Consoles games"]),
    dict(nome="Social • Dia das Mães 2018", canal="Social pago", tipo=MIDIA,
         w_novo=.050, w_rec=.030, cvr=.013, cpc=.72, ctr=.015,
         janela=(D("2018-04-23"), D("2018-05-13")),
         afinidade=["Beleza saúde", "Perfumaria", "Relógios presentes",
                    "Fashion bolsas e acessórios", "Cama mesa banho"]),
    dict(nome="Social • Copa 2018", canal="Social pago", tipo=MIDIA,
         w_novo=.035, w_rec=.020, cvr=.011, cpc=.78, ctr=.013,
         janela=(D("2018-05-28"), D("2018-07-15")),
         afinidade=["Esporte lazer", "Eletrônicos", "Telefonia",
                    "Consoles games"]),
    dict(nome="Afiliados • Cashback", canal="Afiliados", tipo=MIDIA,
         w_novo=.050, w_rec=.020, cvr=.030, comissao=.09, ctr=.020),
    # ---- CRM -------------------------------------------------------------- #
    dict(nome="E-mail • Newsletter semanal", canal="E-mail", tipo=CRM,
         w_novo=.018, w_rec=.130, abertura=.17, clique=.021, optout=.0016,
         custo=.003, lift=.20, semanal=True,
         base7=.00136, engaj=2.4, efeito=.20, tk=1.00, tk_up=.03),
    dict(nome="E-mail • Carrinho abandonado", canal="E-mail", tipo=CRM,
         w_novo=.012, w_rec=.080, abertura=.41, clique=.085, optout=.0004,
         custo=.003, lift=1.10,
         base7=.0105, engaj=1.6, efeito=.90, tk=1.15, tk_up=.08),
    dict(nome="E-mail • Reativação 90 dias", canal="E-mail", tipo=CRM,
         w_novo=0.0, w_rec=.100, abertura=.13, clique=.011, optout=.0045,
         custo=.003, lift=.55, janela=(REATIVACAO, None),
         base7=.0165, engaj=2.5, efeito=.60, tk=.95, tk_up=-.05),
    dict(nome="E-mail • Black Friday 2017", canal="E-mail", tipo=CRM,
         w_novo=.060, w_rec=.150, abertura=.23, clique=.036, optout=.0025,
         custo=.003, lift=.30, janela=(D("2017-11-20"), D("2017-11-28")),
         base7=.00185, engaj=2.2, efeito=.40, tk=.90, tk_up=-.08),
    dict(nome="Push • Ofertas relâmpago", canal="Push", tipo=CRM,
         w_novo=.008, w_rec=.080, abertura=.055, clique=.016, optout=.0025,
         custo=.0004, lift=.12, janela=(APP, None),
         base7=.00199, engaj=3.0, efeito=.35, tk=.85, tk_up=-.05),
    dict(nome="WhatsApp • Recompra pós-entrega", canal="WhatsApp", tipo=CRM,
         w_novo=0.0, w_rec=.160, abertura=.83, clique=.15, optout=.011,
         custo=.085, lift=.75, janela=(WHATSAPP, None),
         base7=.01257, engaj=1.1, efeito=.70, tk=1.05, tk_up=.06),
    # ---- sem campanha ----------------------------------------------------- #
    dict(nome="Sem campanha (orgânico)", canal="Orgânico", tipo=ORG,
         w_novo=.260, w_rec=.100),
    dict(nome="Sem campanha (direto)", canal="Direto", tipo=ORG,
         w_novo=.170, w_rec=.120),
]
POR_NOME = {c["nome"]: c for c in CAMPANHAS}

# Newsletter sai às terças; a compra que ela puxa se espalha pelos dias
# seguintes. Segunda=0 ... domingo=6.
MOD_NEWSLETTER = {0: .6, 1: 2.2, 2: 1.6, 3: 1.1, 4: .6, 5: .6, 6: .6}


def _arredonda(x) -> np.ndarray:
    """Arredondamento estocástico: 0,3 vira 1 em 30% das vezes. Arredondar
    para o inteiro mais próximo zeraria sistematicamente os estados pequenos
    e puxaria taxa de clique e grupo controle para baixo."""
    x = np.asarray(x, dtype=float)
    base = np.floor(x)
    return (base + (rng.random(len(x)) < (x - base))).astype("int64")


def _ativa(c: dict, datas: pd.Series) -> np.ndarray:
    ini, fim = c.get("janela", (None, None))
    ok = np.ones(len(datas), dtype=bool)
    if ini is not None:
        ok &= (datas >= ini).to_numpy()
    if fim is not None:
        ok &= (datas <= fim).to_numpy()
    return ok


def _rampa_social(datas: pd.Series) -> np.ndarray:
    """O social pago cresce ao longo de 2017: de 0,6x a 1,1x do peso."""
    t = ((datas - D("2017-01-01")).dt.days / 425).clip(0, 1).to_numpy()
    return 0.6 + 0.5 * t


# --------------------------------------------------------------------------- #
# 1. Atribuição: cada pedido real ganha uma campanha
# --------------------------------------------------------------------------- #

def atribuir(fato: pd.DataFrame) -> pd.DataFrame:
    # Categoria do pedido = a do item mais caro; é ela que a campanha sazonal
    # disputa.
    ped = (fato.sort_values("receita", ascending=False)
           .drop_duplicates("order_id")
           [["order_id", "data", "tipo_cliente", "categoria"]]
           .reset_index(drop=True))
    datas = ped["data"]
    novo = (ped["tipo_cliente"] == "Primeira compra").to_numpy()
    dow = datas.dt.dayofweek.to_numpy()

    pesos = np.zeros((len(ped), len(CAMPANHAS)))
    for j, c in enumerate(CAMPANHAS):
        w = np.where(novo, c["w_novo"], c["w_rec"]).astype(float)
        w *= _ativa(c, datas)
        if c.get("rampa"):
            w *= _rampa_social(datas)
        if c["nome"] == "Social • Prospecção":
            w *= np.where(datas >= FADIGA, 0.82, 1.0)
        if c.get("afinidade"):
            w *= np.where(ped["categoria"].isin(c["afinidade"]), 3.0, 1.0)
        if c.get("semanal"):
            w *= np.vectorize(MOD_NEWSLETTER.get)(dow)
        if c["canal"] == "Push":
            w *= np.where((datas >= BF[0]) & (datas <= BF[1]), 1.5, 1.0)
        pesos[:, j] = w

    pesos /= pesos.sum(axis=1, keepdims=True)
    acum = pesos.cumsum(axis=1)
    sorteio = rng.random(len(ped))[:, None]
    idx = (sorteio > acum).sum(axis=1)

    ped["campanha"] = [CAMPANHAS[i]["nome"] for i in idx]
    ped["canal"] = [CAMPANHAS[i]["canal"] for i in idx]
    ped["tipo_campanha"] = [CAMPANHAS[i]["tipo"] for i in idx]
    return fato.merge(ped[["order_id", "campanha", "canal", "tipo_campanha"]],
                      on="order_id", how="left")


# --------------------------------------------------------------------------- #
# 2. Mídia paga: investimento, impressões e cliques a partir dos pedidos
# --------------------------------------------------------------------------- #

def _mix_estado(fato: pd.DataFrame) -> pd.DataFrame:
    """Participação de cada estado nos pedidos de cada campanha em cada mês.
    É por ela que o investimento do dia é distribuído no mapa."""
    ped = fato.drop_duplicates("order_id").copy()
    ped["mes"] = ped["data"].dt.to_period("M")
    mix = (ped.groupby(["campanha", "mes", "estado"]).size()
           .rename("n").reset_index())
    mix["share"] = mix["n"] / mix.groupby(["campanha", "mes"])["n"].transform("sum")
    return mix[["campanha", "mes", "estado", "share"]]


def _mix_geral(fato: pd.DataFrame) -> pd.DataFrame:
    ped = fato.drop_duplicates("order_id").copy()
    ped["mes"] = ped["data"].dt.to_period("M")
    mix = ped.groupby(["mes", "estado"]).size().rename("n").reset_index()
    mix["share"] = mix["n"] / mix.groupby("mes")["n"].transform("sum")
    return mix[["mes", "estado", "share"]]


def _espalhar(diario: pd.DataFrame, nome: str, mix_c: pd.DataFrame,
              mix_g: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    """Distribui o total do dia de uma campanha pelos estados."""
    diario = diario.copy()
    diario["mes"] = diario["data"].dt.to_period("M")
    m = mix_c[mix_c["campanha"] == nome]
    if m.empty:
        m = mix_g.assign(campanha=nome)
    # Mês sem pedido da campanha usa o mix geral daquele mês.
    meses_c = set(m["mes"])
    falta = mix_g[~mix_g["mes"].isin(meses_c)].assign(campanha=nome)
    m = pd.concat([m, falta[m.columns]], ignore_index=True)
    out = diario.merge(m[["mes", "estado", "share"]], on="mes", how="inner")
    for c in colunas:
        out[c] = out[c] * out["share"]
    return out.drop(columns=["share", "mes"])


def midia(fato: pd.DataFrame, dias: pd.DatetimeIndex, mix_c, mix_g) -> pd.DataFrame:
    ped = fato.drop_duplicates("order_id")
    rec = fato.groupby(["campanha", "data"])["receita"].sum()
    blocos = []
    for c in CAMPANHAS:
        if c["tipo"] != MIDIA:
            continue
        nome = c["nome"]
        serie = (ped[ped["campanha"] == nome].groupby("data").size()
                 .reindex(dias, fill_value=0).astype(float))
        ativa = _ativa(c, pd.Series(dias))
        # O orçamento é suave: segue a média de 7 dias dos pedidos, não o
        # pedido do dia -- ninguém reconfigura campanha todo dia.
        esperado = serie.rolling(7, center=True, min_periods=1).mean()
        esperado = np.maximum(esperado.to_numpy(), 0.3) * ativa
        ruido = rng.lognormal(0, .10, len(dias))
        cliques = esperado / c["cvr"] * ruido

        bf = ((dias >= BF[0]) & (dias <= BF[1]))
        dez = (dias.month == 12)
        ctr = np.full(len(dias), c["ctr"])
        if "comissao" in c:
            r = (rec.xs(nome, level="campanha") if nome in rec.index.get_level_values(0)
                 else pd.Series(dtype=float))
            r = r.reindex(dias, fill_value=0).rolling(7, center=True,
                                                     min_periods=1).mean()
            invest = c["comissao"] * r.to_numpy() * ativa * rng.lognormal(0, .05, len(dias))
        else:
            cpc = np.full(len(dias), c["cpc"]) * np.where(bf, 1.25, 1.0) \
                * np.where(dez, 1.10, 1.0)
            if nome == "Social • Prospecção":
                cpc = cpc * np.where(dias >= FADIGA, 1.35, 1.0)
                ctr = ctr * np.where(dias >= FADIGA, 0.80, 1.0)
            invest = cliques * cpc * rng.lognormal(0, .04, len(dias))
        impressoes = cliques / ctr

        # Evento plantado: orçamento duplicado nos dois últimos dias.
        # A base é o ritmo das duas semanas anteriores, e não o próprio dia:
        # o último dia do Olist tem poucos pedidos (fim da extração), e um
        # erro proporcional ao dia sumiria justamente onde ele precisa
        # aparecer.
        if nome == "Social • Prospecção":
            erro = dias >= dias[-2]
            ritmo = pd.Series(invest, index=dias).shift(1).rolling(
                14, min_periods=7).median().to_numpy()
            imp_r = pd.Series(impressoes, index=dias).shift(1).rolling(
                14, min_periods=7).median().to_numpy()
            cli_r = pd.Series(cliques, index=dias).shift(1).rolling(
                14, min_periods=7).median().to_numpy()
            invest = np.where(erro, ritmo * 2.6, invest)
            cliques = np.where(erro, cli_r * 2.2, cliques)
            impressoes = np.where(erro, imp_r * 2.4, impressoes)

        d = pd.DataFrame({"data": dias, "investimento": invest,
                          "impressoes": impressoes, "cliques": cliques})
        d = d[ativa & (invest > 0)]
        d = _espalhar(d, nome, mix_c, mix_g,
                      ["investimento", "impressoes", "cliques"])
        d["campanha"], d["canal"], d["tipo_campanha"] = nome, c["canal"], MIDIA
        blocos.append(d)
    out = pd.concat(blocos, ignore_index=True)
    out["investimento"] = out["investimento"].round(2)
    out["impressoes"] = _arredonda(out["impressoes"])
    out["cliques"] = _arredonda(out["cliques"])
    return out


# --------------------------------------------------------------------------- #
# 3a. Resposta em 7 dias: como se mensura um disparo de CRM
# --------------------------------------------------------------------------- #
#
# É a régua de quem opera CRM: de quem recebeu, quem abriu (foi impactado),
# e quem fez a ação que a campanha queria -- uma compra -- em até 7 dias
# depois do disparo. Compara-se a taxa de resposta de quem abriu com a do
# grupo controle, e o ticket médio dos dois.
#
# A simulação separa três populações, porque é aí que mora a armadilha:
#
#   quem abriu       compra mais por natureza (engaj > 1: quem abre e-mail é
#                    quem já gosta da marca) E recebe o efeito do disparo;
#   quem não abriu   compra menos que a média e não recebe efeito nenhum;
#   controle         compra na média da audiência (base7), sem disparo.
#
# A média ponderada de quem abriu e de quem não abriu, sem efeito, é
# exatamente base7 -- o controle é a mesma audiência, sorteada. Por isso
# "quem abriu × controle" superestima o lift: mistura o efeito do disparo com
# a diferença de perfil de quem abre. O painel mostra as duas leituras.
#
# Disparo sem os 7 dias inteiros dentro da base (os últimos seis dias) fica
# com a resposta vazia: medir janela pela metade daria resposta menor e
# pareceria queda.

def _resposta_7d(d: pd.DataFrame, c: dict, ultimo_dia, ticket_base: float
                 ) -> pd.DataFrame:
    k = len(d)
    abriu = d["aberturas"].to_numpy(dtype=float)
    nao_abriu = (d["envios"] - d["aberturas"]).clip(lower=0).to_numpy(dtype=float)
    ctrl = d["grupo_controle"].to_numpy(dtype=float)
    o = abriu.sum() / max(d["envios"].sum(), 1)
    b, e, ef = c["base7"], c["engaj"], c["efeito"]
    r_abriu = b * e * (1 + ef)
    r_nao = b * max(1 - o * e, 0.05) / max(1 - o, 0.05)

    resp_abriu = rng.poisson(abriu * r_abriu)
    resp_nao = rng.poisson(nao_abriu * r_nao)
    resp_ctrl = rng.poisson(ctrl * b)

    tk_c = ticket_base * c["tk"]
    tk_a = tk_c * (1 + c["tk_up"])

    def _receita(n, tk):
        # Soma de n tickets: média tk, ruído que encolhe com o volume.
        n = np.asarray(n, dtype=float)
        ruido = rng.lognormal(0, 0.6 / np.sqrt(np.maximum(n, 1)), len(n))
        return np.round(n * tk * ruido, 2)

    d["janela_7d"] = (d["data"] + pd.Timedelta(days=6) <= ultimo_dia).astype(int)
    d["resp_abriu"] = resp_abriu
    d["receita_abriu"] = _receita(resp_abriu, tk_a)
    d["resp_recebeu"] = resp_abriu + resp_nao
    d["receita_recebeu"] = d["receita_abriu"] + _receita(resp_nao, tk_c)
    d["resp_controle"] = resp_ctrl
    d["receita_controle"] = _receita(resp_ctrl, tk_c)
    fora = d["janela_7d"] == 0
    for col in ["resp_abriu", "receita_abriu", "resp_recebeu",
                "receita_recebeu", "resp_controle", "receita_controle"]:
        d[col] = d[col].astype(float)
        d.loc[fora, col] = np.nan
    return d


# --------------------------------------------------------------------------- #
# 3. CRM: disparos a partir da base real, com grupo controle
# --------------------------------------------------------------------------- #

def crm(fato: pd.DataFrame, dias: pd.DatetimeIndex, mix_g) -> pd.DataFrame:
    ped = fato.drop_duplicates("order_id")
    pedidos_dia = ped.groupby("data").size().reindex(dias, fill_value=0)

    # Clientes acumulados até a véspera: é quem pode estar na base de e-mail.
    primeira = ped.groupby("cliente_id")["data"].min()
    novos_dia = primeira.value_counts().reindex(dias, fill_value=0)
    acumulados = novos_dia.cumsum().shift(1, fill_value=0)

    # Reativação: quem fez a ÚLTIMA compra há exatos 90 dias e não voltou.
    compras = ped[["cliente_id", "data"]].sort_values("data")
    compras["proxima"] = compras.groupby("cliente_id")["data"].shift(-1)
    inativos = compras.assign(alvo=compras["data"] + pd.Timedelta(days=90))
    inativos = inativos[inativos["proxima"].isna()
                        | (inativos["proxima"] > inativos["alvo"])]
    reativ_dia = inativos.groupby("alvo").size().reindex(dias, fill_value=0)

    # Base de e-mail: 55% de quem já comprou deu opt-in, mais uma base de
    # leads de newsletter que cresce sozinha. Opt-out sai da base.
    dias_desde = (dias - dias[0]).days.to_numpy()
    leads = 25000 + 60 * dias_desde

    n = len(dias)
    linhas = {c["nome"]: np.zeros(n) for c in CAMPANHAS if c["tipo"] == CRM}
    saidas_email = 0.0
    for i, dia in enumerate(dias):
        base_email = max(0.55 * acumulados.iloc[i] + leads[i] - saidas_email, 0)
        envios = {}
        if dia.dayofweek == 1:
            envios["E-mail • Newsletter semanal"] = base_email
        envios["E-mail • Carrinho abandonado"] = pedidos_dia.iloc[i] * 1.6
        if dia >= REATIVACAO:
            envios["E-mail • Reativação 90 dias"] = reativ_dia.iloc[i] * 0.55
        if dia in BF_EMAIL:
            envios["E-mail • Black Friday 2017"] = base_email * 0.95
        if dia >= APP:
            meses_app = min((dia - APP).days / 180, 1.0)
            envios["Push • Ofertas relâmpago"] = (0.30 * acumulados.iloc[i]
                                                  * meses_app * 0.5)
        if dia >= WHATSAPP and i >= 18:
            envios["WhatsApp • Recompra pós-entrega"] = pedidos_dia.iloc[i - 18] * 0.38
        for nome, v in envios.items():
            v = v * rng.lognormal(0, .05)
            linhas[nome][i] = v
            if nome.startswith("E-mail"):
                saidas_email += v * POR_NOME[nome]["optout"]

    # Ticket de referência: o ticket médio real do Olist no período.
    ticket_base = float(fato.groupby("order_id")["receita"].sum().mean())

    blocos = []
    for nome, envios in linhas.items():
        c = POR_NOME[nome]
        d = pd.DataFrame({"data": dias, "envios": envios})
        d = d[d["envios"] > 0]
        if d.empty:
            continue
        k = len(d)
        d["aberturas"] = d["envios"] * c["abertura"] * rng.lognormal(0, .06, k)
        d["cliques_crm"] = d["envios"] * c["clique"] * rng.lognormal(0, .08, k)
        d["optouts"] = d["envios"] * c["optout"] * rng.lognormal(0, .15, k)
        d["investimento"] = d["envios"] * c["custo"]
        # 10% da audiência fica de fora: 1 controle para cada 9 tratados.
        d["grupo_controle"] = d["envios"] / 9.0

        d = _espalhar(d, nome, pd.DataFrame(columns=["campanha", "mes", "estado",
                                                     "share"]),
                      mix_g, ["envios", "aberturas", "cliques_crm", "optouts",
                              "investimento", "grupo_controle"])
        for col in ["envios", "aberturas", "cliques_crm", "optouts",
                    "grupo_controle"]:
            d[col] = _arredonda(d[col])
        d = d[d["envios"] > 0].copy()
        d = _resposta_7d(d, c, dias[-1], ticket_base)
        d["campanha"], d["canal"], d["tipo_campanha"] = nome, c["canal"], CRM
        blocos.append(d)
    out = pd.concat(blocos, ignore_index=True)
    out["investimento"] = out["investimento"].round(2)
    out = out[out["envios"] > 0]
    return out


# --------------------------------------------------------------------------- #

def build() -> pd.DataFrame:
    base = pd.read_parquet(ENTRADA)
    manter = ["data", "order_id", "cliente_id", "categoria", "estado",
              "regiao", "meio_pagamento", "faixa_parcelas", "status",
              "cancelado", "receita", "frete", "itens", "dia_semana",
              "tipo_dia", "faixa_valor", "tipo_cliente"]
    fato = atribuir(base[manter].copy())

    dias = pd.date_range(fato["data"].min(), fato["data"].max(), freq="D")
    mix_c, mix_g = _mix_estado(fato), _mix_geral(fato)

    camp = pd.concat([midia(fato, dias, mix_c, mix_g),
                      crm(fato, dias, mix_g)], ignore_index=True)
    regiao = fato.drop_duplicates("estado").set_index("estado")["regiao"]
    camp["regiao"] = camp["estado"].map(regiao)
    dsem = dict(fato[["data", "dia_semana"]].drop_duplicates().values)
    camp["dia_semana"] = camp["data"].map(dsem)
    faltou = camp["dia_semana"].isna()
    if faltou.any():
        nomes = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado",
                 "Domingo"]
        camp.loc[faltou, "dia_semana"] = camp.loc[faltou, "data"].dt.dayofweek.map(
            dict(enumerate(nomes)))
    camp["tipo_dia"] = np.where(camp["data"].dt.dayofweek >= 5,
                                "Fim de semana", "Dia útil")

    out = pd.concat([fato, camp], ignore_index=True)
    inteiros = ["impressoes", "cliques", "envios", "aberturas", "cliques_crm",
                "optouts", "grupo_controle", "janela_7d", "resp_abriu",
                "resp_recebeu", "resp_controle"]
    for c in inteiros:
        out[c] = out[c].astype("Int64")
    out["linha"] = np.where(out["order_id"].notna(), "pedido", "campanha")
    return out.sort_values(["data", "linha"]).reset_index(drop=True)


if __name__ == "__main__":
    out = build()
    out.to_parquet(SAIDA, index=False, compression="zstd")
    print(f"linhas: {len(out):,} ({(out['linha'] == 'campanha').sum():,} de campanha)")
    print(f"período: {out['data'].min().date()} a {out['data'].max().date()}")
    print(f"arquivo: {SAIDA} ({SAIDA.stat().st_size / 1e6:.1f} MB)")
