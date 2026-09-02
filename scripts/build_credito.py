"""
Gera a carteira de credito SIMULADA do dominio de Credito.

Este dado nao e real e o app diz isso em toda tela. Ele existe porque nao ha
base publica de credito com data de originacao e marcacao de inadimplencia
disponivel, e sem ela nao da para mostrar a analise que importa em credito:
desempenho por safra.

O que foi simulado com intencao (e nao com ruido aleatorio)
-----------------------------------------------------------
1. **Curva de aprovacao por faixa de score.** Score melhor aprova mais.
2. **Curva de maturacao.** Inadimplencia nao acontece na originacao: over30
   aparece a partir do terceiro mes de vida (MOB3), over90 a partir do sexto.
   Ler inadimplencia pela data de originacao sem respeitar MOB e o erro
   classico -- a safra nova sempre parece otima porque ainda nao teve tempo de
   quebrar.
3. **Censura a direita, preservada de proposito.** Safra originada ha menos de
   3 (ou 6, ou 12) meses NAO tem a marcacao correspondente: fica nula, nao
   zero. Preencher com zero e o que faz um painel de credito mostrar
   inadimplencia caindo justamente quando ela nao pode ter acontecido ainda.
4. **Choque de safra.** As safras de set/2017 a nov/2017 tem risco elevado,
   simulando afrouxamento de politica. Existe para que a analise de causa raiz
   e os alertas tenham o que encontrar -- e para que se possa verificar se
   encontram.
5. **Efeito de canal.** Telemarketing origina pior que App com o mesmo score:
   e o caso em que o efeito mix e o efeito taxa contam historias diferentes.

Saida: data/fato_credito.parquet
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "fato_credito.parquet"

DATA_INICIO = pd.Timestamp("2017-01-05")
DATA_FIM = pd.Timestamp("2018-08-23")
SEMENTE = 20260901

FAIXAS_SCORE = ["A (900+)", "B (750-899)", "C (600-749)", "D (450-599)", "E (<450)"]
PESO_SCORE = [0.17, 0.27, 0.30, 0.17, 0.09]
APROVACAO = dict(zip(FAIXAS_SCORE, [0.93, 0.84, 0.66, 0.41, 0.16]))
RISCO_BASE = dict(zip(FAIXAS_SCORE, [0.011, 0.023, 0.047, 0.094, 0.168]))

CANAIS = ["App", "Site", "Loja parceira", "Telemarketing", "Correspondente"]
PESO_CANAL = [0.31, 0.24, 0.21, 0.13, 0.11]
RISCO_CANAL = dict(zip(CANAIS, [0.80, 0.92, 1.05, 1.42, 1.18]))
APROV_CANAL = dict(zip(CANAIS, [1.06, 1.02, 0.98, 0.88, 0.94]))

PRODUTOS = ["Crédito pessoal", "CDC veículo", "Cartão consignado",
            "Capital de giro"]
PESO_PRODUTO = [0.42, 0.21, 0.24, 0.13]
TICKET_PRODUTO = dict(zip(PRODUTOS, [3800, 26000, 2100, 41000]))
PRAZO_PRODUTO = dict(zip(PRODUTOS, [18, 42, 12, 24]))
RISCO_PRODUTO = dict(zip(PRODUTOS, [1.12, 0.72, 0.86, 1.30]))

FAIXAS_RENDA = ["Até 2 SM", "2 a 5 SM", "5 a 10 SM", "Acima de 10 SM"]
PESO_RENDA = [0.28, 0.36, 0.24, 0.12]
RISCO_RENDA = dict(zip(FAIXAS_RENDA, [1.34, 1.06, 0.83, 0.62]))

REGIOES = ["Sudeste", "Nordeste", "Sul", "Centro-Oeste", "Norte"]
PESO_REGIAO = [0.47, 0.22, 0.16, 0.09, 0.06]
RISCO_REGIAO = dict(zip(REGIOES, [0.94, 1.21, 0.88, 1.02, 1.16]))

UF_POR_REGIAO = {
    "Sudeste": ["SP", "RJ", "MG", "ES"],
    "Nordeste": ["BA", "PE", "CE", "MA", "PB", "RN", "AL", "PI", "SE"],
    "Sul": ["PR", "RS", "SC"],
    "Centro-Oeste": ["GO", "DF", "MT", "MS"],
    "Norte": ["PA", "AM", "RO", "TO", "AC", "AP", "RR"],
}

# Safras com politica afrouxada: multiplicador de risco por safra.
CHOQUE_SAFRA = {"2017-09": 1.55, "2017-10": 1.78, "2017-11": 1.62, "2017-12": 1.24}


def _volume_diario(datas: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """Volume de propostas: nivel com crescimento, sazonalidade semanal e ruido."""
    t = np.arange(len(datas))
    base = 240 * (1 + 0.00055 * t)                       # crescimento suave
    dow = datas.dayofweek.to_numpy()
    fator_dow = np.array([1.14, 1.12, 1.09, 1.06, 1.00, 0.62, 0.48])[dow]
    mes = datas.month.to_numpy()
    fator_mes = np.where(np.isin(mes, [1, 2]), 0.88,
                         np.where(np.isin(mes, [11, 12]), 1.15, 1.0))
    ruido = rng.normal(1.0, 0.09, len(datas))
    return np.clip(base * fator_dow * fator_mes * ruido, 20, None).astype(int)


def gerar() -> pd.DataFrame:
    rng = np.random.default_rng(SEMENTE)
    datas = pd.date_range(DATA_INICIO, DATA_FIM, freq="D")
    volumes = _volume_diario(datas, rng)
    n = int(volumes.sum())

    data = np.repeat(datas.to_numpy(), volumes)
    df = pd.DataFrame({"data": data})
    df["contrato_id"] = [f"C{i:07d}" for i in range(1, n + 1)]

    df["faixa_score"] = rng.choice(FAIXAS_SCORE, n, p=PESO_SCORE)
    df["canal"] = rng.choice(CANAIS, n, p=PESO_CANAL)
    df["produto"] = rng.choice(PRODUTOS, n, p=PESO_PRODUTO)
    df["faixa_renda"] = rng.choice(FAIXAS_RENDA, n, p=PESO_RENDA)
    df["regiao"] = rng.choice(REGIOES, n, p=PESO_REGIAO)
    df["estado"] = [rng.choice(UF_POR_REGIAO[r]) for r in df["regiao"]]
    df["safra"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m")

    # --- decisao de credito -------------------------------------------------
    p_aprov = (
        df["faixa_score"].map(APROVACAO).to_numpy()
        * df["canal"].map(APROV_CANAL).to_numpy()
    )
    # Aperto gradual de politica ao longo do tempo (resposta ao choque).
    idx_mes = (
        pd.to_datetime(df["data"]).dt.year * 12 + pd.to_datetime(df["data"]).dt.month
    ).to_numpy()
    aperto = np.where(idx_mes >= (2018 * 12 + 1), 0.93, 1.0)
    p_aprov = np.clip(p_aprov * aperto, 0.02, 0.985)
    df["aprovado"] = (rng.random(n) < p_aprov).astype(int)

    # --- valores ------------------------------------------------------------
    base_ticket = df["produto"].map(TICKET_PRODUTO).to_numpy(dtype=float)
    mult_renda = df["faixa_renda"].map(
        dict(zip(FAIXAS_RENDA, [0.55, 0.85, 1.25, 2.10]))
    ).to_numpy()
    df["valor_solicitado"] = np.round(
        base_ticket * mult_renda * rng.lognormal(0, 0.34, n), 2)
    df["valor_liberado"] = np.where(
        df["aprovado"] == 1,
        np.round(df["valor_solicitado"] * rng.uniform(0.72, 1.0, n), 2), 0.0)

    df["prazo_meses"] = np.where(
        df["aprovado"] == 1,
        df["produto"].map(PRAZO_PRODUTO).to_numpy()
        + rng.integers(-6, 13, n), 0).clip(0, 72)

    juros = (
        1.42
        + df["faixa_score"].map(dict(zip(FAIXAS_SCORE, [0.0, 0.55, 1.35, 2.40, 3.60])))
        .to_numpy()
        + rng.normal(0, 0.22, n)
    )
    df["taxa_juros_am"] = np.where(df["aprovado"] == 1, np.round(juros, 3), np.nan)

    # --- risco por contrato -------------------------------------------------
    risco = (
        df["faixa_score"].map(RISCO_BASE).to_numpy()
        * df["canal"].map(RISCO_CANAL).to_numpy()
        * df["produto"].map(RISCO_PRODUTO).to_numpy()
        * df["faixa_renda"].map(RISCO_RENDA).to_numpy()
        * df["regiao"].map(RISCO_REGIAO).to_numpy()
        * df["safra"].map(CHOQUE_SAFRA).fillna(1.0).to_numpy()
    )
    risco = np.clip(risco, 0.002, 0.75)

    aprovado = df["aprovado"].to_numpy() == 1
    u = rng.random(n)
    # Escada de severidade: quem entra em over90 passou por over30 antes.
    over30 = aprovado & (u < risco)
    over90 = over30 & (rng.random(n) < 0.58)
    default12 = over90 & (rng.random(n) < 0.71)

    df["over30_mob3"] = np.where(aprovado, over30.astype(float), np.nan)
    df["over90_mob6"] = np.where(aprovado, over90.astype(float), np.nan)
    df["default_mob12"] = np.where(aprovado, default12.astype(float), np.nan)

    # --- censura a direita, no nivel da SAFRA -------------------------------
    #
    # A censura tem de ser por safra inteira, e nao contrato a contrato.
    # Censurando por idade individual, a safra de fevereiro entraria na conta
    # com os contratos do dia 1 marcados e os do dia 28 nao -- e a taxa da
    # safra sairia calculada so sobre os contratos mais antigos dela. Isso
    # enviesa exatamente na direcao que mais engana em credito: contrato
    # originado no comeco do mes ja teve mais tempo de quebrar, entao a safra
    # parcial aparece PIOR do que e, e a leitura vira "a safra nova esta
    # horrivel" quando o que se esta vendo e um recorte.
    #
    # Regra: a safra so entra quando o SEU ULTIMO contrato completou o MOB.
    idade_dias = (DATA_FIM - pd.to_datetime(df["data"])).dt.days.to_numpy()
    df["_idade"] = idade_dias
    idade_minima_da_safra = df.groupby("safra")["_idade"].transform("min")

    df.loc[idade_minima_da_safra < 90, "over30_mob3"] = np.nan
    df.loc[idade_minima_da_safra < 180, "over90_mob6"] = np.nan
    df.loc[idade_minima_da_safra < 365, "default_mob12"] = np.nan
    df = df.drop(columns=["_idade"])

    # --- saldo em aberto ----------------------------------------------------
    meses_decorridos = np.clip(idade_dias / 30.44, 0, None)
    fracao_paga = np.clip(
        meses_decorridos / np.where(df["prazo_meses"] > 0, df["prazo_meses"], 1), 0, 1)
    df["saldo"] = np.round(
        np.where(aprovado, df["valor_liberado"] * (1 - fracao_paga), 0.0), 2)

    df["propostas"] = 1

    # --- dimensoes derivadas ------------------------------------------------
    #
    # Faixas em vez de numeros crus: ninguem filtra "prazo = 37 meses", filtra
    # "prazo longo". As faixas nascem aqui, como coluna, pelo mesmo motivo do
    # outro fato -- filtro, alerta, cascata e agente leem a mesma coluna.
    df["faixa_prazo"] = pd.cut(
        df["prazo_meses"], bins=[-1, 0, 12, 24, 36, 200],
        labels=["Não aprovado", "Até 12 meses", "13 a 24 meses",
                "25 a 36 meses", "Acima de 36 meses"]).astype(str)

    df["faixa_ticket"] = pd.cut(
        df["valor_liberado"], bins=[-1, 0, 2000, 5000, 15000, 1e12],
        labels=["Não aprovado", "Até R$ 2 mil", "R$ 2 a 5 mil",
                "R$ 5 a 15 mil", "Acima de R$ 15 mil"]).astype(str)

    df["faixa_taxa"] = pd.cut(
        df["taxa_juros_am"], bins=[-1, 1.8, 2.6, 3.6, 100],
        labels=["Até 1,8% a.m.", "1,8 a 2,6% a.m.", "2,6 a 3,6% a.m.",
                "Acima de 3,6% a.m."]).astype(str)
    df.loc[df["taxa_juros_am"].isna(), "faixa_taxa"] = "Não aprovado"

    df["decisao"] = np.where(df["aprovado"] == 1, "Aprovado", "Recusado")

    df["data"] = pd.to_datetime(df["data"])
    return df.sort_values(["data", "contrato_id"]).reset_index(drop=True)


if __name__ == "__main__":
    fato = gerar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fato.to_parquet(OUT, index=False, compression="zstd")

    ap = fato[fato["aprovado"] == 1]
    print(f"propostas: {len(fato):,} | aprovadas: {len(ap):,} "
          f"({len(ap)/len(fato):.1%})")
    print(f"periodo: {fato['data'].min().date()} a {fato['data'].max().date()}")
    print(f"originacao: R$ {ap['valor_liberado'].sum()/1e6:,.1f} mi")
    print(f"over30 MOB3 (safras maduras): {fato['over30_mob3'].mean():.2%}")
    print(f"safras sem marcacao MOB3: "
          f"{fato['over30_mob3'].isna().sum() - (fato['aprovado']==0).sum():,} contratos")
    print(f"arquivo: {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")
    print("\nover30 MOB3 por safra:")
    print((fato.groupby("safra")["over30_mob3"].mean() * 100).round(2).to_string())
