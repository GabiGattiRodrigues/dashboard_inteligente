"""
Gera a base SIMULADA do domínio de Compliance (Ravena) e roda o monitoramento.

Nada aqui é dado real. A empresa é uma plataforma fictícia de benefícios
flexíveis com conta digital; os clientes, as empresas e os estabelecimentos são
inventados, e os documentos saem mascarados de propósito. Não existe base
pública de monitoramento PLD — nenhuma instituição publica os próprios alertas
— e é por isso que o domínio é simulado e diz isso em toda tela.

O que o script faz, na ordem de um job de verdade
-------------------------------------------------
1. **Cadastro.** Empresas clientes, titulares (colaboradores) e
   estabelecimentos credenciados, com renda, porte, risco, PEP, região e canal
   de abertura.
2. **Movimentação.** Pix recebidos e enviados na conta digital, recargas de
   benefício e recebimentos dos estabelecimentos, dia a dia, de mai/2025 a
   ago/2026. Os quatro meses iniciais são aquecimento: a regra de conta que
   acorda precisa de três meses de história antes de poder julgar.
3. **Monitoramento.** As regras de `vulcano/pld/regras.py` rodam sobre as
   janelas (7 e 30 dias), com as regras diárias todo dia e as de ciclo mensal
   no lote do dia. Supressão: um alerta por cliente, por regra, por mês.
4. **Análise.** Uma fila com capacidade fixa de analistas trabalha os alertas
   em dia útil — primeiro o que está perto de vencer o prazo de 45 dias,
   depois por prioridade — e decide: descartar, reforçar monitoramento ou
   comunicar ao Coaf (até o dia útil seguinte).

O que foi plantado com intenção, e serve de gabarito
----------------------------------------------------
- **Contas de passagem (jun–ago/2026).** 45 contas abertas em lote no mesmo
  celular, recebendo Pix de centenas de origens e esvaziando no mesmo dia para
  os mesmos destinos. É a onda que enche a fila em julho.
- **Troca de benefício na fronteira (abr–ago/2026).** Cinco empresas recém-
  cadastradas em MS e MT carregam cinco mil reais por colaborador; os
  titulares gastam o saldo inteiro, muitas vezes de madrugada, em quatro
  mercearias parceiras.
- **Incompatibilidade com renda e fracionamento**, espalhados no ano.
- **PEP com movimentação habitual** e **conta de titular falecido que continua
  movimentando**.
- **Mudança de política em mar/2026:** o corte da R01 cai de 4× para 3× a
  renda, e o volume de alertas (e de falso positivo) sobe junto.
- **Falha do job de checagem de CPF em 14–16/abr/2026**, reprocessada em 20/abr:
  aparece como buraco de cobertura no ciclo mensal.
- **Férias de duas analistas entre 15/jun e 10/jul/2026**, bem no pico da
  onda: a fila estoura o prazo de 45 dias pela primeira vez no ano.
- **Pré-triagem automática a partir de 06/jul/2026:** alerta só cadastral
  passa a custar um décimo do tempo e a capacidade sobe. O tempo de análise
  cai no mês.
- **Ruído legítimo** que vira falso positivo: venda de carro, vaquinha,
  inauguração de loja, PLR de dezembro, farmácia 24h cadastrada como comercial.

O gabarito das tipologias fica em `data/pld_gabarito.parquet`, que só os
testes leem. O app nunca olha para ele: a tela vê o que uma analista veria.

Saídas (data/):
    fato_pld.parquet          um alerta por linha — o fato do motor
    pld_evidencias.parquet    séries diárias dos clientes com alerta (dossiê)
    pld_contrapartes.parquet  principais contrapartes dos clientes com alerta
    pld_calibracao.parquet    máximo mensal do indicador, por regra (calibração)
    pld_indicadores.parquet   percentis do indicador na população avaliada, por mês
    pld_ciclo.parquet         cobertura diária do ciclo de checagem de CPF
    pld_comportamento.parquet sinais brutos por mês (Pix, POS, recargas, contas)
    pld_gabarito.parquet      tipologia plantada por cliente (só testes)
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from vulcano.pld.calendario import (PRAZO_ANALISE_DIAS, eh_dia_util,  # noqa: E402
                                    proximo_dia_util, somar_dias_uteis)
from vulcano.pld.fila import faixa_prioridade, prioridade  # noqa: E402
from vulcano.pld.regras import AVALIADORES, LIMITE_PIX, REGRAS  # noqa: E402

PASTA = RAIZ / "data"
SEMENTE = 20260911

INICIO = date(2025, 5, 1)
MON_INICIO = date(2025, 9, 1)
DATA_BASE = date(2026, 8, 31)
DIAS = [INICIO + timedelta(days=i) for i in range((DATA_BASE - INICIO).days + 1)]
ND = len(DIAS)
IDX = {d: i for i, d in enumerate(DIAS)}
I_MON = IDX[MON_INICIO]

FALHA_CICLO = {date(2026, 4, 14), date(2026, 4, 15), date(2026, 4, 16)}
REPROCESSO = date(2026, 4, 20)
AUTOMACAO = date(2026, 7, 6)
FERIAS = (date(2026, 6, 15), date(2026, 7, 10))

UF_REGIAO = {
    "SP": "Sudeste", "RJ": "Sudeste", "MG": "Sudeste", "ES": "Sudeste",
    "BA": "Nordeste", "PE": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "RN": "Nordeste", "AL": "Nordeste", "PI": "Nordeste",
    "SE": "Nordeste", "PR": "Sul", "RS": "Sul", "SC": "Sul",
    "GO": "Centro-Oeste", "DF": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste", "PA": "Norte", "AM": "Norte", "RO": "Norte",
    "TO": "Norte", "AC": "Norte", "AP": "Norte", "RR": "Norte",
}
PESO_UF = {"SP": 30, "RJ": 9, "MG": 10, "ES": 2, "BA": 6, "PE": 4, "CE": 4,
           "MA": 1.5, "PB": 1.2, "RN": 1.2, "AL": 0.8, "PI": 0.8, "SE": 0.6,
           "PR": 6, "RS": 5.5, "SC": 4.5, "GO": 3, "DF": 2.5, "MT": 1.8,
           "MS": 1.4, "PA": 1.8, "AM": 1.2, "RO": 0.6, "TO": 0.5, "AC": 0.3,
           "AP": 0.2, "RR": 0.2}
UFS_FRONTEIRA = {"MS", "MT", "PR", "RS", "SC", "RO", "AC", "AM", "RR", "PA",
                 "AP"}


def _uf(rng, n):
    ufs = list(PESO_UF)
    p = np.array([PESO_UF[u] for u in ufs], dtype=float)
    return rng.choice(ufs, n, p=p / p.sum())


def _area(rng, ufs):
    return np.where([u in UFS_FRONTEIRA for u in ufs],
                    np.where(rng.random(len(ufs)) < 0.14, "Fronteira",
                             "Demais áreas"), "Demais áreas")


def _codigos(rng, prefixo, n, digitos):
    nums = rng.choice(10 ** digitos, n, replace=False)
    return [f"{prefixo}-{x:0{digitos}d}" for x in nums]


def _doc_cpf(rng, n):
    a, b = rng.integers(0, 1000, n), rng.integers(0, 1000, n)
    return [f"***.{x:03d}.{y:03d}-**" for x, y in zip(a, b)]


def _doc_cnpj(rng, n):
    a, b = rng.integers(0, 1000, n), rng.integers(0, 1000, n)
    return [f"**.{x:03d}.{y:03d}/0001-**" for x, y in zip(a, b)]


def _roll(m: np.ndarray, k: int) -> np.ndarray:
    """Soma móvel de k dias terminando no dia, ao longo do eixo 1."""
    c = np.cumsum(np.pad(m, ((0, 0), (1, 0))), axis=1, dtype=np.float64)
    fim = np.arange(1, m.shape[1] + 1)
    ini = np.maximum(fim - k, 0)
    return c[:, fim] - c[:, ini]


def _mes(d: date) -> int:
    return d.year * 12 + d.month


# =========================================================================== #
# 1. Cadastro
# =========================================================================== #

def cadastro(rng):
    # ----------------------------- empresas -------------------------------- #
    NE_NORMAL, NE_NOVAS, NE_FACHADA = 380, 40, 5
    NE = NE_NORMAL + NE_NOVAS + NE_FACHADA
    portes = np.array(["MEI", "Pequena", "Média", "Grande"])
    porte = rng.choice(portes, NE, p=[0.08, 0.47, 0.30, 0.15])
    tamanho = {"MEI": 1.5, "Pequena": 12, "Média": 60, "Grande": 170}
    fat = {"MEI": (8e3, 30e3), "Pequena": (60e3, 400e3),
           "Média": (4e5, 4e6), "Grande": (4e6, 40e6)}
    emp = pd.DataFrame({
        "e": np.arange(NE),
        "porte": porte,
        "uf": _uf(rng, NE),
    })
    emp["tamanho"] = emp["porte"].map(tamanho) * rng.lognormal(0, 0.4, NE)
    emp["faturamento"] = [rng.uniform(*fat[p]) for p in emp["porte"]]
    emp["beneficio"] = rng.uniform(600, 1500, NE) * \
        np.where(emp["porte"] == "Grande", 1.15, 1.0)
    emp["dia_recarga"] = rng.integers(1, 6, NE)
    emp["risco"] = rng.choice(["Baixo", "Médio", "Alto"], NE,
                              p=[0.75, 0.22, 0.03])
    ini = rng.integers(0, (date(2025, 4, 1) - date(2019, 1, 1)).days, NE)
    emp["inicio"] = [date(2019, 1, 1) + timedelta(days=int(x)) for x in ini]
    emp["tipologia"] = "normal"

    novas = np.arange(NE_NORMAL, NE_NORMAL + NE_NOVAS)
    emp.loc[novas, "inicio"] = [
        MON_INICIO + timedelta(days=int(x))
        for x in rng.integers(0, (DATA_BASE - MON_INICIO).days - 30, NE_NOVAS)]

    fach = np.arange(NE_NORMAL + NE_NOVAS, NE)
    emp.loc[fach, "porte"] = "Pequena"
    emp.loc[fach, "uf"] = ["MS", "MS", "MS", "MT", "MT"]
    emp.loc[fach, "faturamento"] = rng.uniform(60e3, 120e3, NE_FACHADA)
    emp.loc[fach, "beneficio"] = rng.uniform(4200, 6400, NE_FACHADA)
    emp.loc[fach, "tamanho"] = 24
    emp.loc[fach, "risco"] = ["Médio", "Baixo", "Médio", "Baixo", "Baixo"]
    emp.loc[fach, "inicio"] = [date(2026, 3, 2), date(2026, 3, 9),
                               date(2026, 3, 23), date(2026, 4, 1),
                               date(2026, 4, 8)]
    emp.loc[fach, "tipologia"] = "fachada_empresa"
    emp["area"] = _area(rng, emp["uf"].tolist())
    emp.loc[fach[:3], "area"] = "Fronteira"
    emp["codigo"] = _codigos(rng, "E", NE, 4)
    emp["doc"] = _doc_cnpj(rng, NE)
    emp["lote"] = rng.integers(0, 28, NE)

    # ----------------------------- titulares ------------------------------- #
    NT = 9_000
    peso = emp.loc[: NE_NORMAL + NE_NOVAS - 1, "tamanho"].to_numpy()
    e_de = rng.choice(NE_NORMAL + NE_NOVAS, NT, p=peso / peso.sum())
    tit = pd.DataFrame({"t": np.arange(NT), "e": e_de})
    tit["tipologia"] = "normal"

    # fachada: 24 titulares por empresa
    n_f = NE_FACHADA * 24
    extra_f = pd.DataFrame({"t": np.arange(NT, NT + n_f),
                            "e": np.repeat(fach, 24),
                            "tipologia": "fachada_titular"})
    # passagem: 45 contas penduradas em empresas pequenas já existentes
    peq = emp.index[(emp["porte"] == "Pequena") & (emp.index < NE_NORMAL)]
    n_p = 45
    extra_p = pd.DataFrame({"t": np.arange(NT + n_f, NT + n_f + n_p),
                            "e": rng.choice(peq, n_p),
                            "tipologia": "passagem"})
    tit = pd.concat([tit, extra_f, extra_p], ignore_index=True)
    NTT = len(tit)

    e = emp.set_index("e")
    tit["porte"] = e.loc[tit["e"], "porte"].to_numpy()
    tit["uf"] = np.where(rng.random(NTT) < 0.85, e.loc[tit["e"], "uf"],
                         _uf(rng, NTT))
    tit.loc[tit["tipologia"] == "fachada_titular", "uf"] = \
        e.loc[tit.loc[tit["tipologia"] == "fachada_titular", "e"], "uf"].to_numpy()
    tit["area"] = _area(rng, tit["uf"].tolist())
    ff = tit["tipologia"] == "fachada_titular"
    tit.loc[ff, "area"] = e.loc[tit.loc[ff, "e"], "area"].to_numpy()
    mediana = tit["porte"].map({"MEI": 1800, "Pequena": 2600, "Média": 3500,
                                "Grande": 5500}).to_numpy()
    tit["renda"] = np.round(mediana * rng.lognormal(0, 0.45, NTT), -1)
    tit["risco"] = rng.choice(["Baixo", "Médio", "Alto"], NTT,
                              p=[0.72, 0.24, 0.04])
    tit["pep"] = False
    tit["canal"] = np.where(rng.random(NTT) < 0.85, "Portal RH", "App")
    tit["dispositivo_lote"] = 0
    tit["usa_conta"] = rng.random(NTT) < 0.6

    # abertura: base antiga antes do início; empresas novas depois da data
    ab = rng.integers(0, (date(2025, 4, 25) - date(2019, 3, 1)).days, NTT)
    tit["abertura"] = [date(2019, 3, 1) + timedelta(days=int(x)) for x in ab]
    for idx_e in novas:
        sel = tit.index[(tit["e"] == idx_e) & (tit["tipologia"] == "normal")]
        base = emp.loc[idx_e, "inicio"]
        tit.loc[sel, "abertura"] = [base + timedelta(days=int(x))
                                    for x in rng.integers(0, 25, len(sel))]
        tit.loc[sel, "canal"] = "Portal RH"

    # fachada: abertos pelo app, em lotes de 6 a 10 no mesmo celular
    for idx_e in fach:
        sel = list(tit.index[tit["e"] == idx_e])
        base = emp.loc[idx_e, "inicio"]
        pos = 0
        while pos < len(sel):
            tam = int(rng.integers(6, 11))
            grupo = sel[pos: pos + tam]
            dia_lote = base + timedelta(days=int(rng.integers(2, 20)))
            tit.loc[grupo, "abertura"] = dia_lote
            tit.loc[grupo, "canal"] = "App"
            tit.loc[grupo, "dispositivo_lote"] = len(grupo)
            pos += tam
    tit.loc[ff, "renda"] = np.round(rng.uniform(1600, 2500, ff.sum()), -1)
    tit.loc[ff, "usa_conta"] = False

    # passagem: 6 lotes no mesmo celular entre 18/mai e 12/jun/2026
    pp = list(tit.index[tit["tipologia"] == "passagem"])
    datas_lote = [date(2026, 5, 18), date(2026, 5, 23), date(2026, 5, 29),
                  date(2026, 6, 3), date(2026, 6, 8), date(2026, 6, 12)]
    for i, grupo in enumerate(np.array_split(pp, 6)):
        tit.loc[grupo, "abertura"] = datas_lote[i]
        tit.loc[grupo, "canal"] = "App"
        tit.loc[grupo, "dispositivo_lote"] = len(grupo)
        tit.loc[grupo, "lote_passagem"] = i
    pmask = tit["tipologia"] == "passagem"
    tit.loc[pmask, "renda"] = np.round(rng.uniform(1500, 2400, pmask.sum()), -1)
    tit.loc[pmask, "usa_conta"] = True
    tit.loc[pmask, "risco"] = "Baixo"

    # famílias no mesmo wi-fi / celular: lote pequeno e legítimo
    familias = rng.choice(tit.index[(tit["tipologia"] == "normal")
                                    & (tit["canal"] == "App")], 170,
                          replace=False)
    for f in familias:
        tam = int(rng.choice([3, 4, 5, 6], p=[0.45, 0.3, 0.17, 0.08]))
        vizinhos = tit.index[(tit["e"] == tit.loc[f, "e"])
                             & (tit["tipologia"] == "normal")][:tam]
        d_ab = tit.loc[f, "abertura"]
        if d_ab < MON_INICIO:
            d_ab = MON_INICIO + timedelta(days=int(rng.integers(0, 330)))
        tit.loc[vizinhos, "abertura"] = d_ab
        tit.loc[vizinhos, "canal"] = "App"
        tit.loc[vizinhos, "dispositivo_lote"] = len(vizinhos)

    # renda incompatível e fracionamento: titulares normais escolhidos
    livres = tit.index[(tit["tipologia"] == "normal")
                       & (tit["abertura"] < date(2025, 8, 1))]
    esc = rng.choice(livres, 30 + 18 + 32, replace=False)
    tit.loc[esc[:30], "tipologia"] = "renda"
    tit.loc[esc[30:48], "tipologia"] = "fracionamento"
    tit.loc[esc[:48], "usa_conta"] = True

    # PEP: 26 titulares, 6 com movimentação habitual
    peps = esc[48:74]
    tit.loc[peps, "pep"] = True
    tit.loc[peps, "risco"] = "Alto"
    tit.loc[peps, "renda"] = np.round(rng.uniform(12e3, 26e3, len(peps)), -1)
    tit.loc[peps, "usa_conta"] = True
    tit.loc[peps[:6], "tipologia"] = "pep_habitual"

    # CPF irregular: 3 falecidos que continuam movimentando + 34 irregulares
    obitos = esc[74:77]
    tit.loc[obitos, "tipologia"] = "obito_movimenta"
    tit.loc[obitos, "usa_conta"] = True
    tit["cpf_situacao"] = "Regular"
    tit["cpf_irregular_desde"] = pd.NaT
    irr = rng.choice(tit.index[(tit["tipologia"] == "normal")
                               & tit["usa_conta"]], 34, replace=False)
    for i in irr:
        tit.loc[i, "cpf_situacao"] = rng.choice(["Suspenso", "Cancelado",
                                                 "Titular falecido"],
                                                p=[0.62, 0.23, 0.15])
        tit.loc[i, "cpf_irregular_desde"] = pd.Timestamp(
            MON_INICIO + timedelta(days=int(rng.integers(-60, 300))))
    for i, d0 in zip(obitos, [date(2025, 11, 20), date(2026, 2, 7),
                              date(2026, 5, 12)]):
        tit.loc[i, "cpf_situacao"] = "Titular falecido"
        tit.loc[i, "cpf_irregular_desde"] = pd.Timestamp(d0)

    tit["codigo"] = _codigos(rng, "T", NTT, 5)
    tit["doc"] = _doc_cpf(rng, NTT)
    tit["lote"] = rng.integers(0, 28, NTT)

    # ------------------------- estabelecimentos ---------------------------- #
    NM = 1_200
    cats = ["Padaria e mercearia", "Supermercado", "Farmácia", "Restaurante",
            "Posto e mobilidade", "Outros"]
    categoria = rng.choice(cats, NM, p=[0.17, 0.24, 0.12, 0.30, 0.09, 0.08])
    rec_mediana = {"Padaria e mercearia": 22e3, "Supermercado": 160e3,
                   "Farmácia": 70e3, "Restaurante": 48e3,
                   "Posto e mobilidade": 110e3, "Outros": 30e3}
    ticket = {"Padaria e mercearia": 24, "Supermercado": 96, "Farmácia": 58,
              "Restaurante": 39, "Posto e mobilidade": 118, "Outros": 55}
    est = pd.DataFrame({"m": np.arange(NM), "categoria": categoria,
                        "uf": _uf(rng, NM)})
    est["receita_mensal"] = est["categoria"].map(rec_mediana) * \
        rng.lognormal(0, 0.55, NM)
    est["ticket"] = est["categoria"].map(ticket)
    est["horario_comercial"] = est["categoria"].isin(
        ["Padaria e mercearia", "Supermercado", "Farmácia"])
    est["noturno_base"] = np.where(est["horario_comercial"], 0.004, 0.05)
    # farmácias 24h cadastradas como comercial: o falso positivo recorrente
    f24 = rng.choice(est.index[est["categoria"] == "Farmácia"], 3, replace=False)
    est.loc[f24, "noturno_base"] = rng.uniform(0.27, 0.36, 3)
    est["tipologia"] = "normal"
    est["risco"] = rng.choice(["Baixo", "Médio", "Alto"], NM,
                              p=[0.78, 0.19, 0.03])
    anel = pd.DataFrame({
        "m": np.arange(NM, NM + 4), "categoria": "Padaria e mercearia",
        "uf": ["MS", "MS", "MS", "MT"],
        "receita_mensal": rng.uniform(20e3, 34e3, 4), "ticket": 24,
        "horario_comercial": True, "noturno_base": 0.004,
        "tipologia": "anel_troca", "risco": "Baixo"})
    est = pd.concat([est, anel], ignore_index=True)
    est["area"] = _area(rng, est["uf"].tolist())
    est.loc[est["tipologia"] == "anel_troca", "area"] = \
        ["Fronteira", "Fronteira", "Fronteira", "Demais áreas"]
    est["codigo"] = _codigos(rng, "L", len(est), 5)
    est["doc"] = _doc_cnpj(rng, len(est))
    est["inicio"] = [date(2020, 1, 1) + timedelta(days=int(x))
                     for x in rng.integers(0, 1900, len(est))]
    est.loc[est["tipologia"] == "anel_troca", "inicio"] = \
        [date(2025, 12, 1), date(2026, 1, 12), date(2026, 2, 3),
         date(2026, 2, 20)]
    return emp, tit, est


# =========================================================================== #
# 2. Movimentação
# =========================================================================== #

def movimentacao(rng, emp, tit, est):
    NT, NE, NM = len(tit), len(emp), len(est)
    dow = np.array([d.weekday() for d in DIAS])
    ab_idx = np.array([IDX.get(d, 0 if d < INICIO else ND) for d in tit["abertura"]])
    ativo = np.arange(ND)[None, :] >= ab_idx[:, None]          # T × D

    pix = []    # (t, dia, sentido, valor, contraparte)

    def add(t, d, sentido, valor, cp):
        pix.append(pd.DataFrame({"t": np.asarray(t, dtype=np.int32),
                                 "d": np.asarray(d, dtype=np.int32),
                                 "sentido": sentido,
                                 "valor": np.round(np.asarray(valor, dtype=float), 2),
                                 "cp": np.asarray(cp, dtype=np.int64)}))

    # ---- uso normal da conta ---------------------------------------------- #
    usa = tit["usa_conta"].to_numpy()
    fator_dow = np.array([1.05, 1.0, 1.0, 1.02, 1.18, 0.9, 0.7])[dow]
    renda = tit["renda"].to_numpy()
    escala = np.clip(renda / 3000, 0.5, 4.0)
    for sentido, lam, med in (("in", 0.07, 150), ("out", 0.10, 130)):
        L = (usa[:, None] & ativo) * lam * fator_dow[None, :]
        q = rng.poisson(L)
        t_i, d_i = np.nonzero(q)
        rep = q[t_i, d_i]
        t_i, d_i = np.repeat(t_i, rep), np.repeat(d_i, rep)
        n = len(t_i)
        v = np.minimum(med * escala[t_i] * rng.lognormal(0, 0.95, n),
                       LIMITE_PIX * 0.88)
        pool = rng.integers(0, 8, n)
        novo = rng.random(n) < 0.18
        cp = np.where(novo, 10_000_000 + rng.integers(0, 5_000_000, n),
                      t_i.astype(np.int64) * 16 + pool + (8 if sentido == "out" else 0))
        add(t_i, d_i, sentido, np.round(v, 2), cp)

    mes_de = np.array([_mes(d) for d in DIAS])
    meses = sorted(set(mes_de))

    def dias_do_mes(m):
        return np.nonzero(mes_de == m)[0]

    # ---- ruído legítimo: venda de carro, rescisão --------------------------- #
    normais = tit.index[(tit["tipologia"] == "normal") & usa].to_numpy()
    for m in meses:
        dd = dias_do_mes(m)
        quem = normais[rng.random(len(normais)) < 0.030]
        for t in quem:
            d0 = int(rng.choice(dd))
            if not ativo[t, d0]:
                continue
            v_in = float(rng.uniform(8e3, 45e3))
            add([t], [d0], "in", [v_in], [20_000_000 + int(rng.integers(1e6))])
            if rng.random() < 0.6:
                saida = v_in * rng.uniform(0.5, 1.0)
                partes = []
                while saida > 0:
                    x = min(saida, float(rng.uniform(1500, LIMITE_PIX - 1)))
                    partes.append(x)
                    saida -= x
                ds = np.minimum(d0 + rng.integers(1, 10, len(partes)), ND - 1)
                add([t] * len(partes), ds, "out", partes,
                    [21_000_000 + int(x) for x in rng.integers(0, 1e6, len(partes))])

    # ---- ruído legítimo: vaquinha ------------------------------------------ #
    for m in meses:
        dd = dias_do_mes(m)
        quem = normais[rng.random(len(normais)) < 0.005]
        for t in quem:
            d0 = int(rng.choice(dd[:-6])) if len(dd) > 6 else int(dd[0])
            k = int(rng.integers(12, 46))
            ds = d0 + rng.integers(0, 5, k)
            vs = rng.uniform(20, 150, k)
            add([t] * k, ds, "in", vs,
                30_000_000 + rng.integers(0, 5_000_000, k))
            if rng.random() < 0.45:
                add([t], [min(d0 + 5, ND - 1)], "out", [min(vs.sum() * 0.92, LIMITE_PIX - 1)],
                    [31_000_000 + int(rng.integers(1e6))])

    # ---- renda incompatível ------------------------------------------------ #
    for t in tit.index[tit["tipologia"] == "renda"]:
        meses_ativos = int(rng.integers(2, 5))
        m0 = int(rng.integers(_mes(MON_INICIO) - 1, _mes(DATA_BASE) - meses_ativos + 1))
        origens = 40_000_000 + t * 10 + np.arange(5)
        destinos = 41_000_000 + t * 10 + np.arange(3)
        mult = rng.uniform(4.5, 11)
        for m in range(m0, m0 + meses_ativos):
            dd = dias_do_mes(m)
            if len(dd) == 0:
                continue
            total = renda[t] * mult
            k = int(rng.integers(3, 8))
            ds = np.sort(rng.choice(dd, k))
            vs = rng.dirichlet(np.ones(k)) * total
            vs = np.minimum(vs, 60e3)
            add([t] * k, ds, "in", vs, rng.choice(origens, k))
            for d0, v in zip(ds, vs):
                resto = v * rng.uniform(0.85, 0.98)
                partes = []
                while resto > 1:
                    x = min(resto, float(rng.uniform(1200, LIMITE_PIX * 0.86)))
                    partes.append(x)
                    resto -= x
                add([t] * len(partes),
                    np.minimum(d0 + rng.integers(0, 3, len(partes)), ND - 1),
                    "out", partes, rng.choice(destinos, len(partes)))

    # ---- fracionamento ----------------------------------------------------- #
    for t in tit.index[tit["tipologia"] == "fracionamento"]:
        meses_ativos = int(rng.integers(1, 4))
        m0 = int(rng.integers(_mes(MON_INICIO), _mes(DATA_BASE) - meses_ativos + 1))
        destinos = 42_000_000 + t * 10 + np.arange(4)
        for m in range(m0, m0 + meses_ativos):
            dd = dias_do_mes(m)
            for _ in range(int(rng.integers(1, 3))):
                d0 = int(rng.choice(dd[:-5]))
                k = int(rng.integers(3, 6))
                vs = rng.uniform(4_600, 4_995, k)
                add([t], [d0], "in", [vs.sum() * rng.uniform(1.0, 1.1)],
                    [43_000_000 + int(rng.integers(0, 3))])
                add([t] * k, d0 + np.sort(rng.integers(0, 5, k)), "out", vs,
                    rng.choice(destinos, k))

    # ---- contas de passagem ------------------------------------------------ #
    destinos_lote = {i: 50_000_000 + i * 10 + np.arange(3) for i in range(6)}
    pico = IDX[date(2026, 7, 15)]
    for t in tit.index[tit["tipologia"] == "passagem"]:
        d_ini = IDX[tit.loc[t, "abertura"]] + int(rng.integers(8, 16))
        lote_p = int(tit.loc[t, "lote_passagem"])
        for d in range(d_ini, ND):
            rampa = np.exp(-((d - pico) / 28.0) ** 2) * 0.85 + 0.15
            k = rng.poisson(3.2 * rampa)
            if k == 0:
                continue
            vs = rng.uniform(80, 950, k)
            add([t] * k, [d] * k, "in", vs,
                60_000_000 + rng.integers(0, 3_000_000, k))
            resto = vs.sum() * rng.uniform(0.86, 0.98)
            partes = []
            while resto > 1:
                x = min(resto, LIMITE_PIX * 0.8)
                partes.append(x)
                resto -= x
            add([t] * len(partes), [d] * len(partes), "out", partes,
                rng.choice(destinos_lote[lote_p], len(partes)))

    # ---- PEP habitual ------------------------------------------------------ #
    for t in tit.index[tit["tipologia"] == "pep_habitual"]:
        origens = 70_000_000 + t * 10 + np.arange(3)
        for m in meses:
            dd = dias_do_mes(m)
            if rng.random() < 0.25:
                continue
            k = int(rng.integers(2, 5))
            ds = rng.choice(dd, k)
            vs = rng.uniform(4e3, 14e3, k)
            add([t] * k, ds, "in", vs, rng.choice(origens, k))
            add([t] * k, np.minimum(ds + 1, ND - 1), "out",
                np.minimum(vs * 0.9, LIMITE_PIX * 0.85),
                71_000_000 + t * 10 + rng.integers(0, 2, k))

    # ---- PEP comum: movimentação alta ocasional, legítima ------------------ #
    for t in tit.index[tit["pep"] & (tit["tipologia"] == "normal")]:
        for m in meses:
            if rng.random() < 0.3:
                d0 = int(rng.choice(dias_do_mes(m)))
                add([t], [d0], "in", [rng.uniform(6e3, 16e3)],
                    [72_000_000 + int(rng.integers(0, 4))])

    # ---- falecido que continua movimentando -------------------------------- #
    for t in tit.index[tit["tipologia"] == "obito_movimenta"]:
        d0 = IDX[pd.Timestamp(tit.loc[t, "cpf_irregular_desde"]).date()]
        for d in range(d0 + 3, ND, 6):
            add([t], [d], "out", [rng.uniform(900, 3200)],
                [73_000_000 + t])

    pix = pd.concat(pix, ignore_index=True)
    pix = pix[(pix["d"] >= 0) & (pix["d"] < ND)]
    pix = pix[ativo[pix["t"].to_numpy(), pix["d"].to_numpy()]]

    # ---- recargas de benefício --------------------------------------------- #
    inicio_emp = np.array([IDX.get(d, 0 if d < INICIO else ND) for d in emp["inicio"]])
    recarga_tit = np.zeros((NT, ND), dtype=np.float32)
    recarga_emp = np.zeros((NE, ND), dtype=np.float32)
    e_de = tit["e"].to_numpy()
    for m in meses:
        dd = dias_do_mes(m)
        primeiro = DIAS[dd[0]]
        for e_i in range(NE):
            dia_util = primeiro.replace(day=int(emp.loc[e_i, "dia_recarga"]))
            while not eh_dia_util(dia_util):
                dia_util += timedelta(days=1)
            d = IDX.get(dia_util)
            if d is None or d < inicio_emp[e_i]:
                continue
            quem = np.nonzero((e_de == e_i) & ativo[:, d])[0]
            if len(quem) == 0:
                continue
            valor = emp.loc[e_i, "beneficio"] * rng.uniform(0.96, 1.04, len(quem))
            recarga_tit[quem, d] += valor
            recarga_emp[e_i, d] += valor.sum()
        # PLR / 13º em dezembro: o falso positivo esperado da R07
        if primeiro.month == 12:
            for e_i in np.nonzero(rng.random(NE) < 0.09)[0]:
                if emp.loc[e_i, "tipologia"] != "normal":
                    continue
                d = IDX[date(primeiro.year, 12, int(rng.integers(15, 21)))]
                quem = np.nonzero((e_de == e_i) & ativo[:, d])[0]
                if len(quem) == 0:
                    continue
                valor = rng.uniform(1800, 4200) * np.ones(len(quem))
                recarga_tit[quem, d] += valor
                recarga_emp[e_i, d] += valor.sum()

    # ---- recebimentos dos estabelecimentos --------------------------------- #
    fdow = np.array([0.95, 0.92, 0.95, 1.0, 1.15, 1.2, 0.83])[dow]
    esperado_dia = est["receita_mensal"].to_numpy()[:, None] / 30.4 * fdow[None, :]
    rec_v = esperado_dia * rng.gamma(9, 1 / 9, (NM, ND))
    # eventos legítimos: inauguração, festa, promoção
    for m in meses:
        dd = dias_do_mes(m)
        for i in np.nonzero(rng.random(NM) < 0.03)[0]:
            if est.loc[i, "tipologia"] != "normal":
                continue
            d0 = int(rng.choice(dd))
            rec_v[i, d0: d0 + int(rng.integers(6, 11))] *= rng.uniform(2.6, 5.0)
    inicio_est = np.array([IDX.get(d, 0 if d < INICIO else ND) for d in est["inicio"]])
    rec_v[np.arange(ND)[None, :] < inicio_est[:, None]] = 0
    # a mercearia do anel quase não tem venda de balcão de verdade
    rec_v[(est["tipologia"] == "anel_troca").to_numpy()] *= 0.15
    ticket = est["ticket"].to_numpy()[:, None]
    rec_q = rng.poisson(rec_v / ticket).astype(np.float32)
    noturno = rng.binomial(rec_q.astype(np.int64),
                           np.clip(est["noturno_base"].to_numpy()[:, None], 0, 1)
                           ).astype(np.float32)
    top_emp_v = rec_v * rng.uniform(0.03, 0.2, (NM, 1))

    # troca de benefício: titulares da fachada gastam o saldo no anel
    aneis = est.index[est["tipologia"] == "anel_troca"].to_numpy()
    fach_t = tit.index[tit["tipologia"] == "fachada_titular"].to_numpy()
    anel_de = {t: int(rng.choice(aneis, p=[0.34, 0.26, 0.22, 0.18])) for t in fach_t}
    compras_anel = []
    for t in fach_t:
        dias_rec = np.nonzero(recarga_tit[t] > 0)[0]
        for d in dias_rec:
            saldo = float(recarga_tit[t, d]) * rng.uniform(0.85, 0.97)
            k = int(rng.integers(2, 7))
            for v, dd_ in zip(rng.dirichlet(np.ones(k)) * saldo,
                              d + rng.integers(0, 4, k)):
                if dd_ >= ND:
                    continue
                m_i = anel_de[t]
                noite = rng.random() < 0.7
                rec_v[m_i, dd_] += v
                rec_q[m_i, dd_] += 1
                noturno[m_i, dd_] += 1 if noite else 0
                top_emp_v[m_i, dd_] += v * 0.8
                compras_anel.append((t, int(dd_), m_i, v))
    compras_anel = pd.DataFrame(compras_anel, columns=["t", "d", "m", "valor"])

    return pix, recarga_tit, recarga_emp, rec_v, rec_q, noturno, top_emp_v, \
        ativo, compras_anel


# =========================================================================== #
# 3. Monitoramento
# =========================================================================== #

def janelas(pix, tit, emp, est, recarga_emp, rec_v, rec_q, noturno, top_emp_v,
            ativo):
    NT = len(tit)
    t_, d_ = pix["t"].to_numpy(), pix["d"].to_numpy()
    v_ = pix["valor"].to_numpy()
    ent = pix["sentido"].to_numpy() == "in"

    in_v = np.zeros((NT, ND)); out_v = np.zeros((NT, ND))
    np.add.at(in_v, (t_[ent], d_[ent]), v_[ent])
    np.add.at(out_v, (t_[~ent], d_[~ent]), v_[~ent])
    perto = (~ent) & (v_ >= 0.9 * LIMITE_PIX) & (v_ < LIMITE_PIX)
    perto_q = np.zeros((NT, ND)); perto_v = np.zeros((NT, ND))
    np.add.at(perto_q, (t_[perto], d_[perto]), 1)
    np.add.at(perto_v, (t_[perto], d_[perto]), v_[perto])

    # origens distintas em 7 dias: cada Pix recebido "vale" pelos 7 dias
    # seguintes, e a contagem é de pagadores únicos nessa janela
    rec = pix.loc[ent, ["t", "d", "cp"]]
    exp = pd.concat([rec.assign(d=rec["d"] + k) for k in range(7)])
    exp = exp[exp["d"] < ND].drop_duplicates()
    cont = exp.groupby(["t", "d"]).size()
    origens7 = np.zeros((NT, ND), dtype=np.float32)
    origens7[cont.index.get_level_values(0), cont.index.get_level_values(1)] = cont.to_numpy()

    in30, out30 = _roll(in_v, 30), _roll(out_v, 30)
    vol = in_v + out_v
    c = np.cumsum(np.pad(vol, ((0, 0), (1, 0))), axis=1)
    fim = np.clip(np.arange(ND) - 30 + 1, 0, ND)
    ini = np.clip(np.arange(ND) - 120 + 1, 0, ND)
    media_ant = (c[:, fim] - c[:, ini]) / 3.0

    ab = np.array([IDX.get(d, -1) for d in tit["abertura"]])
    lote_disp = np.zeros((NT, ND), dtype=np.float32)
    ok = (ab >= 0) & (tit["canal"].to_numpy() == "App")
    lote_disp[np.nonzero(ok)[0], ab[ok]] = tit["dispositivo_lote"].to_numpy()[ok]

    desde = tit["cpf_irregular_desde"]
    irregular = np.zeros((NT, ND), dtype=bool)
    for i in np.nonzero(desde.notna().to_numpy())[0]:
        d0 = IDX.get(pd.Timestamp(desde.iloc[i]).date(), 0)
        irregular[i, d0:] = True

    JT = {"in30": in30, "out30": out30, "in7": _roll(in_v, 7),
          "out7": _roll(out_v, 7), "origens7": origens7,
          "perto_limite7": _roll(perto_q, 7), "perto_limite_v7": _roll(perto_v, 7),
          "media_mensal_ant": media_ant, "renda": tit["renda"].to_numpy(),
          "pep": tit["pep"].to_numpy(), "lote_dispositivo": lote_disp,
          "cpf_irregular": irregular}

    JM = {"rec7": _roll(rec_v, 7), "qtd7": _roll(rec_q, 7),
          "noturno7": _roll(noturno, 7), "top7": _roll(top_emp_v, 7),
          "receita_semanal": est["receita_mensal"].to_numpy() / 4.33,
          "horario_comercial": est["horario_comercial"].to_numpy()}

    colab = np.zeros((len(emp), ND))
    e_de = tit["e"].to_numpy()
    np.add.at(colab, (e_de[ab >= 0], ab[ab >= 0]), 1)
    antigos = ab < 0
    colab[:, 0] += np.bincount(e_de[antigos], minlength=len(emp))
    colab = np.cumsum(colab, axis=1)
    JE = {"recarga30": _roll(recarga_emp, 30), "colaboradores": colab}
    series = {"in_v": in_v, "out_v": out_v}
    return JT, JM, JE, series


def slot_do_ciclo(d: date) -> set[int]:
    """Lotes checados no dia. Falha de 14–16/abr, reprocessada em 20/abr."""
    if d in FALHA_CICLO:
        return set()
    lotes = {d.day - 1} if d.day <= 28 else set()
    if d == REPROCESSO:
        lotes |= {x.day - 1 for x in FALHA_CICLO}
    return lotes


def monitorar(JT, JM, JE, tit, emp, est):
    lote_por_dia = [slot_do_ciclo(d) for d in DIAS]
    hits, sombra, perfil = [], [], []
    entidade = {"titular": (JT, tit), "estabelecimento": (JM, est),
                "empresa": (JE, emp)}
    mes_idx = np.array([_mes(d) for d in DIAS])

    for rid, regra in REGRAS.items():
        J, cad = entidade[regra.entidade]
        ind, cond = AVALIADORES[rid](J)
        ind = np.asarray(ind, dtype=float)
        cond = np.asarray(cond, dtype=bool)
        cond[:, :I_MON] = False
        if regra.frequencia == "Ciclo mensal":
            lotes = cad["lote"].to_numpy() if "lote" in cad else np.zeros(len(cad), int)
            mask = np.zeros_like(cond)
            for d, ls in enumerate(lote_por_dia):
                if ls:
                    mask[:, d] = np.isin(lotes, list(ls))
            cond &= mask
        param = np.array([regra.parametro.vigente_em(d) for d in DIAS])
        hit = cond & (ind >= param[None, :])

        e_i, d_i = np.nonzero(hit)
        df = pd.DataFrame({"ent": e_i, "d": d_i, "regra_id": rid,
                           "indicador": ind[e_i, d_i]})
        if rid == "R10":
            df = df.sort_values("d").drop_duplicates("ent")
        else:
            df["mes"] = mes_idx[df["d"]]
            df = df.sort_values("d").drop_duplicates(["ent", "mes"]).drop(columns="mes")
        hits.append(df)

        # Calibração: o máximo do indicador no mês, onde as condições fixas
        # valem. Guarda o período inteiro; quem decide a janela é a leitura,
        # porque a janela útil é a da VIGÊNCIA do parâmetro atual — misturar
        # meses com corte antigo compararia duas regras diferentes.
        if regra.calibravel:
            e_c, d_c = np.nonzero(cond & (ind >= regra.parametro.minimo))
            sb = pd.DataFrame({"ent": e_c, "mes": mes_idx[d_c],
                               "indicador": ind[e_c, d_c]})
            sb = sb.groupby(["ent", "mes"], as_index=False)["indicador"].max()
            sb["regra_id"] = rid
            sombra.append(sb)

        # Comportamento do indicador na população avaliada, mês a mês. É o que
        # separa "os clientes mudaram" de "o corte mudou": se o p95 do
        # indicador está parado e o volume de alertas dobrou, quem se mexeu foi
        # o parâmetro. O máximo mensal por entidade é a unidade certa, porque é
        # ele que decide o alerta (supressão mensal).
        # A R10 fica de fora: o indicador dela é binário (o CPF está irregular
        # ou não), a distribuição seria uma linha reta em 1 e a supressão dela
        # não é mensal — o "acima do corte" não corresponderia ao alerta.
        e_t, d_t = np.nonzero(cond) if regra.calibravel else (np.array([]), np.array([]))
        if len(e_t):
            todos = pd.DataFrame({"ent": e_t, "mes": mes_idx[d_t],
                                  "indicador": ind[e_t, d_t]})
            todos = todos.groupby(["ent", "mes"], as_index=False)["indicador"].max()
            for mes, g in todos.groupby("mes"):
                corte = regra.parametro.vigente_em(
                    date((mes - 1) // 12, (mes - 1) % 12 + 1, 15))
                perfil.append({
                    "regra_id": rid, "mes": mes,
                    "avaliados": len(g),
                    "acima_do_corte": int((g["indicador"] >= corte).sum()),
                    "corte": float(corte),
                    "p50": float(g["indicador"].quantile(0.50)),
                    "p75": float(g["indicador"].quantile(0.75)),
                    "p90": float(g["indicador"].quantile(0.90)),
                    "p95": float(g["indicador"].quantile(0.95)),
                    "p99": float(g["indicador"].quantile(0.99)),
                })

    return (pd.concat(hits, ignore_index=True),
            pd.concat(sombra, ignore_index=True),
            pd.DataFrame(perfil))


def _brl(v):
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def enriquecer(hits, JT, JM, JE, tit, emp, est):
    """Cliente, atributos denormalizados, valor envolvido e a evidência."""
    linhas = []
    for r in hits.itertuples(index=False):
        regra = REGRAS[r.regra_id]
        e, d = int(r.ent), int(r.d)
        dia = DIAS[d]
        if regra.entidade == "titular":
            c = tit.loc[e]
            in30, out30 = JT["in30"][e, d], JT["out30"][e, d]
            base = dict(cliente_id=f"T{e}", codigo=c["codigo"], doc_mascarado=c["doc"],
                        tipo_cliente="Titular (PF)", uf=c["uf"], area=c["area"],
                        faixa_risco=c["risco"], pep="PEP" if c["pep"] else "Não PEP",
                        segmento=f"Colaborador · empresa {c['porte'].lower()}")
            if r.regra_id == "R01":
                valor = in30 + out30
                ev = (f"{_brl(in30)} recebidos e {_brl(out30)} enviados por Pix em 30 "
                      f"dias — {str(round(r.indicador, 1)).replace('.', ',')}× a renda "
                      f"mensal declarada de {_brl(c['renda'])}.")
            elif r.regra_id == "R02":
                in7, out7 = JT["in7"][e, d], JT["out7"][e, d]
                valor = in7
                ev = (f"{int(r.indicador)} pagadores distintos mandaram {_brl(in7)} em 7 "
                      f"dias; {_brl(out7)} ({out7 / in7 * 100:.0f}% do recebido) saiu "
                      f"da conta na mesma janela.")
            elif r.regra_id == "R03":
                valor = JT["perto_limite_v7"][e, d]
                ev = (f"{int(r.indicador)} Pix enviados entre R$ 4.500 e R$ 5.000 em 7 "
                      f"dias, somando {_brl(valor)} — o limite por transação é "
                      f"R$ 5.000.")
            elif r.regra_id == "R04":
                valor = in30 + out30
                media = max(JT["media_mensal_ant"][e, d], 0)
                ev = (f"{_brl(valor)} movimentados em 30 dias, contra média mensal de "
                      f"{_brl(media)} nos 3 meses anteriores "
                      f"({r.indicador:.0f}× a média, com piso de R$ 200).")
            elif r.regra_id == "R08":
                valor = 0.0
                ev = (f"Conta aberta pelo app em {dia.strftime('%d/%m/%Y')}, junto com "
                      f"outras {int(r.indicador) - 1} contas no mesmo dispositivo e no "
                      f"mesmo dia.")
            elif r.regra_id == "R09":
                valor = in30 + out30
                ev = (f"Titular PEP movimentou {_brl(valor)} em 30 dias "
                      f"({_brl(in30)} recebidos, {_brl(out30)} enviados); renda mensal "
                      f"declarada de {_brl(c['renda'])}.")
            else:  # R10
                valor = in30 + out30
                desde = pd.Timestamp(c["cpf_irregular_desde"]).strftime("%d/%m/%Y")
                ev = (f"Checagem mensal (lote {int(c['lote']) + 1} de 28) encontrou o CPF "
                      f"com situação \"{c['cpf_situacao'].lower()}\" desde {desde}; a "
                      f"conta movimentou {_brl(valor)} nos 30 dias anteriores.")
            produto = regra.produto
        elif regra.entidade == "estabelecimento":
            c = est.loc[e]
            rec7, q7 = JM["rec7"][e, d], JM["qtd7"][e, d]
            base = dict(cliente_id=f"L{e}", codigo=c["codigo"], doc_mascarado=c["doc"],
                        tipo_cliente="Estabelecimento (PJ)", uf=c["uf"],
                        area=c["area"], faixa_risco=c["risco"], pep="Não PEP",
                        segmento=f"Estabelecimento · {c['categoria'].lower()}")
            valor = rec7
            if r.regra_id == "R05":
                share = JM["top7"][e, d] / rec7 if rec7 else 0
                ev = (f"{_brl(rec7)} recebidos no POS em 7 dias, "
                      f"{str(round(r.indicador, 1)).replace('.', ',')}× a receita "
                      f"semanal esperada ({_brl(JM['receita_semanal'][e])}); "
                      f"{share * 100:.0f}% vieram de cartões de uma mesma empresa "
                      f"cliente.")
            else:
                ev = (f"{int(JM['noturno7'][e, d])} de {int(q7)} transações "
                      f"({r.indicador * 100:.0f}%) entre 23h e 5h em 7 dias, num "
                      f"estabelecimento de horário comercial "
                      f"({c['categoria'].lower()}).")
            produto = regra.produto
        else:
            c = emp.loc[e]
            rec30, colab = JE["recarga30"][e, d], JE["colaboradores"][e, d]
            base = dict(cliente_id=f"E{e}", codigo=c["codigo"], doc_mascarado=c["doc"],
                        tipo_cliente="Empresa cliente (PJ)", uf=c["uf"],
                        area=c["area"], faixa_risco=c["risco"], pep="Não PEP",
                        segmento=f"Empresa {c['porte'].lower()}")
            valor = rec30
            ev = (f"{_brl(rec30)} em recargas de benefício em 30 dias para "
                  f"{int(colab)} colaboradores ativos — {_brl(r.indicador)} por "
                  f"pessoa. Faturamento mensal declarado de "
                  f"{_brl(c['faturamento'])}; cliente desde "
                  f"{c['inicio'].strftime('%m/%Y')}.")
            produto = regra.produto
        linhas.append({**base, "data": dia, "regra_id": r.regra_id,
                       "indicador": float(r.indicador), "valor_envolvido": float(valor),
                       "evidencia": ev, "produto": produto})
    al = pd.DataFrame(linhas).sort_values(["data", "cliente_id", "regra_id"])
    al = al.reset_index(drop=True)
    al["alerta_id"] = [f"A{i + 1:06d}" for i in range(len(al))]
    return al


# =========================================================================== #
# 4. Análise
# =========================================================================== #

def analisar(al, rng, gabarito):
    """Fila de analistas em dia útil, com decisão e comunicação."""
    al = al.copy()
    n = len(al)
    data = al["data"].tolist()
    regra = al["regra_id"].tolist()
    valor = al["valor_envolvido"].to_numpy()
    cliente = al["cliente_id"].tolist()
    risco = dict(zip(al["cliente_id"], al["faixa_risco"]))
    pep = dict(zip(al["cliente_id"], al["pep"] == "PEP"))
    fronteira = dict(zip(al["cliente_id"], al["area"] == "Fronteira"))
    decisao: list = [None] * n
    data_decisao: list = [None] * n
    data_com: list = [None] * n

    por_dia: dict = {}
    for i, d in enumerate(data):
        por_dia.setdefault(d, []).append(i)
    abertos: dict[str, list[int]] = {}
    ja_comunicados: set[str] = set()

    SUSPEITAS = {"passagem", "renda", "fracionamento", "fachada_titular",
                 "fachada_empresa", "anel_troca", "obito_movimenta"}

    for dia in DIAS[I_MON:]:
        for i in por_dia.get(dia, []):
            abertos.setdefault(cliente[i], []).append(i)
        if not eh_dia_util(dia) or not abertos:
            continue
        capacidade = 11.5 if dia >= AUTOMACAO else 10.7
        if FERIAS[0] <= dia <= FERIAS[1]:
            capacidade *= 0.58    # duas analistas de férias no pico da onda

        candidatos = []
        for cid, idxs in abertos.items():
            mais_antigo = min(data[i] for i in idxs)
            idade = (dia - mais_antigo).days
            # triagem antes de a análise começar; caso com mais de uma regra
            # aberta pede coleta de informação e leva mais tempo
            if idade < (9 if len(set(regra[i] for i in idxs)) > 1 else 2):
                continue
            ids = [regra[i] for i in idxs]
            p = prioridade(ids, float(valor[idxs].sum()), risco[cid], pep[cid],
                           fronteira[cid], cid in ja_comunicados)
            prazo = PRAZO_ANALISE_DIAS - idade
            so_cadastral = set(ids) <= {"R10", "R06"}
            custo = (0.1 if dia >= AUTOMACAO else 0.35) if so_cadastral else 1.0
            urgente = prazo <= 10
            candidatos.append((0 if urgente else 1, prazo if urgente else -p,
                               cid, custo, ids))
        candidatos.sort()

        # força-tarefa: quando o que vence em 10 dias não cabe no dia, a equipe
        # estica o expediente — até 25% a mais, não infinito
        urgente_custo = sum(c[3] * (1.6 if gabarito.get(c[2], "normal") != "normal"
                                    else 1.0) for c in candidatos if c[0] == 0)
        if urgente_custo > capacidade:
            capacidade = min(urgente_custo, capacidade * 1.25)

        usado = 0.0
        for _, _, cid, custo, ids in candidatos:
            tip = gabarito.get(cid, "normal")
            if tip != "normal":
                custo *= 1.6          # caso com indício de verdade dá mais trabalho
            if usado + custo > capacidade:
                continue
            usado += custo
            u = rng.random()
            if tip in SUSPEITAS:
                dec = ("Comunicado ao COAF" if u < 0.82 else
                       "Monitoramento reforçado" if u < 0.97 else "Descartado")
            elif tip == "pep_habitual":
                dec = ("Comunicado ao COAF" if u < 0.35 else
                       "Monitoramento reforçado" if u < 0.95 else "Descartado")
            elif set(ids) == {"R09"}:
                dec = "Monitoramento reforçado" if u < 0.5 else "Descartado"
            elif set(ids) == {"R10"}:
                dec = "Descartado" if u < 0.97 else "Monitoramento reforçado"
            else:
                dec = ("Descartado" if u < 0.91 else
                       "Monitoramento reforçado" if u < 0.975 else
                       "Comunicado ao COAF")
            envio = None
            if dec == "Comunicado ao COAF":
                envio = (proximo_dia_util(dia) if rng.random() < 0.975
                         else somar_dias_uteis(dia, 2))
            for i in abertos.pop(cid):
                decisao[i], data_decisao[i], data_com[i] = dec, dia, envio
            if dec == "Comunicado ao COAF":
                ja_comunicados.add(cid)

    al["decisao"] = decisao
    al["data_decisao"] = pd.to_datetime(pd.Series(data_decisao, dtype="object"))
    al["data_comunicacao"] = pd.to_datetime(pd.Series(data_com, dtype="object"))
    return al


def fato(al):
    f = al.copy()
    f["data"] = pd.to_datetime(f["data"])
    base = pd.Timestamp(DATA_BASE)
    concl = f["decisao"].notna()
    idade = (base - f["data"]).dt.days
    maduro = idade >= PRAZO_ANALISE_DIAS
    dias = (f["data_decisao"] - f["data"]).dt.days

    f["regra"] = f["regra_id"].map(lambda r: REGRAS[r].rotulo)
    f["tipo_regra"] = f["regra_id"].map(lambda r: REGRAS[r].tipo)
    f["ciclo"] = f["regra_id"].map(lambda r: REGRAS[r].frequencia)
    from vulcano.pld.normas import TRECHOS
    f["situacao_4001"] = f["regra_id"].map(
        lambda r: TRECHOS[REGRAS[r].enquadramento[0]].rotulo)
    f["regiao"] = f["uf"].map(UF_REGIAO)
    f["decisao"] = f["decisao"].fillna("Em análise")
    f["status"] = np.where(concl, "Concluído", "Em análise")
    f["faixa_valor"] = pd.cut(f["valor_envolvido"], [-1, 5e3, 20e3, 1e5, 1e12],
                              labels=["Até R$ 5 mil", "R$ 5 a 20 mil",
                                      "R$ 20 a 100 mil", "Acima de R$ 100 mil"]
                              ).astype(str)

    f["alertas"] = 1
    f["em_aberto"] = (~concl).astype(int)
    f["concluido"] = concl.astype(int)
    # tempo de análise só de alerta maduro: nos alertas recentes só os rápidos
    # já terminaram, e a média sairia enganosamente baixa
    f["dias_analise"] = dias.where(concl & maduro)
    f["no_prazo"] = np.where(concl, (dias <= PRAZO_ANALISE_DIAS).astype(float),
                             np.where(idade > PRAZO_ANALISE_DIAS, 0.0, np.nan))
    f["fora_do_prazo"] = (f["no_prazo"] == 0).astype(int)
    for nome, rot in (("descartado_m", "Descartado"),
                      ("comunicado_m", "Comunicado ao COAF"),
                      ("reforcado_m", "Monitoramento reforçado")):
        f[nome] = np.where(maduro & concl, (f["decisao"] == rot).astype(float), np.nan)
    f["comunicado"] = (f["decisao"] == "Comunicado ao COAF").astype(int)
    # contagem de comunicações também censurada: alerta recente ainda não teve
    # tempo de virar comunicação, e o mês corrente pareceria uma queda
    f["comunicado_maduro"] = np.where(maduro, f["comunicado"], np.nan)
    prazo_com = f["data_decisao"].map(
        lambda x: pd.Timestamp(proximo_dia_util(x.date())) if pd.notna(x) else pd.NaT)
    f["com_no_prazo"] = np.where(f["comunicado"] == 1,
                                 (f["data_comunicacao"] <= prazo_com).astype(float),
                                 np.nan)
    f["data"] = f["data"].dt.date
    f["data_decisao"] = f["data_decisao"].dt.date
    f["data_comunicacao"] = f["data_comunicacao"].dt.date
    return f


# =========================================================================== #
# Saídas auxiliares
# =========================================================================== #

def evidencias(fato_df, series, recarga_tit, recarga_emp, rec_v, rec_q, noturno, JE):
    primeiro = fato_df.groupby("cliente_id")["data"].min()
    linhas = []
    for cid, d0 in primeiro.items():
        tipo, e = cid[0], int(cid[1:])
        i0 = max(0, IDX[d0] - 90)
        dias = np.arange(i0, ND)
        if tipo == "T":
            cols = {"Pix recebidos": series["in_v"][e, dias],
                    "Pix enviados": series["out_v"][e, dias],
                    "Recarga de benefício": recarga_tit[e, dias]}
        elif tipo == "L":
            cols = {"Recebido no POS": rec_v[e, dias],
                    "Transações": rec_q[e, dias],
                    "Transações entre 23h e 5h": noturno[e, dias]}
        else:
            cols = {"Recarga de benefício": recarga_emp[e, dias],
                    "Colaboradores ativos": JE["colaboradores"][e, dias]}
        for serie, vals in cols.items():
            nz = np.nonzero(vals)[0]
            linhas.append(pd.DataFrame({
                "cliente_id": cid, "data": [DIAS[dias[k]] for k in nz],
                "serie": serie, "valor": np.round(vals[nz].astype(float), 2)}))
    return pd.concat(linhas, ignore_index=True)


def contrapartes(fato_df, pix, compras_anel, tit, est, emp):
    alvo = set(fato_df["cliente_id"])
    tits = {int(c[1:]) for c in alvo if c[0] == "T"}
    p = pix[pix["t"].isin(tits)].copy()
    g = (p.groupby(["t", "sentido", "cp"])
         .agg(qtd=("valor", "size"), valor=("valor", "sum")).reset_index())
    # quantos clientes em atenção compartilham a mesma contraparte
    comp = g.groupby("cp")["t"].nunique()
    g["compartilhada"] = g["cp"].map(comp) - 1
    g = g.sort_values("valor", ascending=False).groupby(["t", "sentido"]).head(6)
    g["cliente_id"] = "T" + g["t"].astype(str)
    g["contraparte"] = "Conta ***" + (g["cp"] % 10_000).astype(str).str.zfill(4)
    g["sentido"] = g["sentido"].map({"in": "Recebido de", "out": "Enviado para"})
    saida = [g[["cliente_id", "sentido", "contraparte", "qtd", "valor",
                "compartilhada"]]]

    if not compras_anel.empty:
        c = compras_anel.copy()
        c["empresa"] = tit.loc[c["t"], "e"].to_numpy()
        a = (c.groupby(["m", "empresa"]).agg(qtd=("valor", "size"),
                                             valor=("valor", "sum")).reset_index())
        a["cliente_id"] = "L" + a["m"].astype(str)
        a["sentido"] = "Cartões da empresa"
        a["contraparte"] = emp.loc[a["empresa"], "codigo"].to_numpy()
        a["compartilhada"] = a.groupby("empresa")["m"].transform("nunique") - 1
        b = (c.groupby(["empresa", "m"]).agg(qtd=("valor", "size"),
                                             valor=("valor", "sum")).reset_index())
        b["cliente_id"] = "E" + b["empresa"].astype(str)
        b["sentido"] = "Gasto dos colaboradores em"
        b["contraparte"] = est.loc[b["m"], "codigo"].to_numpy()
        b["compartilhada"] = b.groupby("m")["empresa"].transform("nunique") - 1
        saida += [a[["cliente_id", "sentido", "contraparte", "qtd", "valor",
                     "compartilhada"]],
                  b[["cliente_id", "sentido", "contraparte", "qtd", "valor",
                     "compartilhada"]]]
    out = pd.concat(saida, ignore_index=True)
    out = out[out["cliente_id"].isin(alvo)]
    out["valor"] = out["valor"].round(2)
    return out


def comportamento(pix, recarga_tit, rec_v, rec_q, noturno, tit, JT):
    """
    Os sinais brutos do mês — o que a regra olha ANTES de virar alerta.

    A causa raiz de "os alertas subiram" só fecha com isto: se o número de Pix
    recebidos e de pagadores distintos subiu junto, o movimento é dos clientes;
    se não subiu, foi a régua. São contadores da população inteira, sem filtro
    de alerta, e é de propósito: filtrar por quem já alertou responderia a
    pergunta com a própria resposta.
    """
    mes_de = np.array([DIAS[d].strftime("%Y-%m") for d in range(ND)])
    dentro = np.arange(ND) >= I_MON
    ent = pix["sentido"].to_numpy() == "in"
    linhas = []

    def por_mes(valores_por_dia, rotulo, unidade):
        df = pd.DataFrame({"mes": mes_de[dentro],
                           "valor": np.asarray(valores_por_dia)[dentro]})
        for mes, g in df.groupby("mes"):
            linhas.append({"mes": mes, "indicador": rotulo, "unidade": unidade,
                           "valor": float(g["valor"].sum())})

    d_ = pix["d"].to_numpy()
    v_ = pix["valor"].to_numpy()
    qtd_in = np.bincount(d_[ent], minlength=ND)
    qtd_out = np.bincount(d_[~ent], minlength=ND)
    val_in = np.bincount(d_[ent], weights=v_[ent], minlength=ND)
    val_out = np.bincount(d_[~ent], weights=v_[~ent], minlength=ND)
    perto = (~ent) & (v_ >= 0.9 * LIMITE_PIX) & (v_ < LIMITE_PIX)

    por_mes(qtd_in, "Pix recebidos", "transações")
    por_mes(qtd_out, "Pix enviados", "transações")
    por_mes(val_in, "Valor recebido por Pix", "moeda")
    por_mes(val_out, "Valor enviado por Pix", "moeda")
    por_mes(np.bincount(d_[perto], minlength=ND),
            "Pix logo abaixo do limite", "transações")
    por_mes(recarga_tit.sum(axis=0), "Recarga de benefícios", "moeda")
    por_mes(rec_q.sum(axis=0), "Compras no cartão (POS)", "transações")
    por_mes(noturno.sum(axis=0), "Compras entre 23h e 5h", "transações")
    por_mes(rec_v.sum(axis=0), "Valor recebido pelos estabelecimentos", "moeda")

    ab = np.array([IDX.get(d, -1) for d in tit["abertura"]])
    aberturas = np.bincount(ab[ab >= 0], minlength=ND)
    por_mes(aberturas, "Contas abertas", "contas")

    # médias por conta ativa: o que muda o indicador de cada regra
    ativos = (JT["in30"] + JT["out30"]) > 0
    for rotulo, matriz in (("Contas que movimentaram", ativos.astype(float)),
                           ("Pagadores distintos por conta (7 dias)",
                            JT["origens7"])):
        df = pd.DataFrame({"mes": mes_de[dentro]})
        if rotulo.startswith("Contas"):
            # conta única no mês, não soma de dias
            for mes in sorted(set(mes_de[dentro])):
                col = mes_de == mes
                linhas.append({"mes": mes, "indicador": rotulo,
                               "unidade": "contas",
                               "valor": float(ativos[:, col].any(axis=1).sum())})
        else:
            for mes in sorted(set(mes_de[dentro])):
                col = mes_de == mes
                m = matriz[:, col]
                vivos = m[m > 0]
                linhas.append({"mes": mes, "indicador": rotulo,
                               "unidade": "media",
                               "valor": float(vivos.mean()) if len(vivos) else 0.0})
    return pd.DataFrame(linhas)


def ciclo(tit):
    ab = np.array([IDX.get(d, -1) for d in tit["abertura"]])
    lote = tit["lote"].to_numpy()
    linhas = []
    for d, dia in enumerate(DIAS[I_MON:], start=I_MON):
        previstos_lotes = {dia.day - 1} if dia.day <= 28 else set()
        ativos = (ab <= d)
        previstos = int((ativos & np.isin(lote, list(previstos_lotes))).sum())
        feitos = slot_do_ciclo(dia)
        checados = int((ativos & np.isin(lote, list(feitos))).sum())
        linhas.append({"data": dia, "previstos": previstos, "checados": checados,
                       "situacao": ("Falha do job" if dia in FALHA_CICLO else
                                    "Reprocessamento" if dia == REPROCESSO else
                                    "Sem lote" if not previstos_lotes else "Ok")})
    return pd.DataFrame(linhas)


def main():
    rng = np.random.default_rng(SEMENTE)
    emp, tit, est = cadastro(rng)
    pix, recarga_tit, recarga_emp, rec_v, rec_q, noturno, top_emp_v, ativo, anel = \
        movimentacao(rng, emp, tit, est)
    JT, JM, JE, series = janelas(pix, tit, emp, est, recarga_emp, rec_v, rec_q,
                                 noturno, top_emp_v, ativo)
    hits, sombra, perfil = monitorar(JT, JM, JE, tit, emp, est)
    al = enriquecer(hits, JT, JM, JE, tit, emp, est)

    gabarito = {f"T{i}": t for i, t in tit["tipologia"].items()}
    gabarito.update({f"E{i}": t for i, t in emp["tipologia"].items()})
    gabarito.update({f"L{i}": t for i, t in est["tipologia"].items()})
    al = analisar(al, rng, gabarito)
    f = fato(al)

    # calibração: liga o máximo mensal ao alerta que de fato saiu naquele mês
    pref = {"titular": "T", "estabelecimento": "L", "empresa": "E"}
    sombra["cliente_id"] = [pref[REGRAS[r].entidade] + str(e)
                            for r, e in zip(sombra["regra_id"], sombra["ent"])]
    f_mes = f.assign(mes=[_mes(d) for d in f["data"]])
    sombra = sombra.merge(f_mes[["cliente_id", "regra_id", "mes", "alerta_id",
                                 "decisao"]],
                          on=["cliente_id", "regra_id", "mes"], how="left")
    sombra["mes"] = sombra["mes"].map(lambda m: f"{(m - 1) // 12}-{(m - 1) % 12 + 1:02d}")
    sombra = sombra.drop(columns="ent")

    PASTA.mkdir(exist_ok=True)
    f.to_parquet(PASTA / "fato_pld.parquet", index=False)
    evidencias(f, series, recarga_tit, recarga_emp, rec_v, rec_q, noturno, JE
               ).to_parquet(PASTA / "pld_evidencias.parquet", index=False)
    contrapartes(f, pix, anel, tit, est, emp).to_parquet(
        PASTA / "pld_contrapartes.parquet", index=False)
    sombra.to_parquet(PASTA / "pld_calibracao.parquet", index=False)
    perfil["mes"] = perfil["mes"].map(
        lambda m: f"{(m - 1) // 12}-{(m - 1) % 12 + 1:02d}")
    perfil.to_parquet(PASTA / "pld_indicadores.parquet", index=False)
    ciclo(tit).to_parquet(PASTA / "pld_ciclo.parquet", index=False)
    comportamento(pix, recarga_tit, rec_v, rec_q, noturno, tit, JT).to_parquet(
        PASTA / "pld_comportamento.parquet", index=False)
    pd.DataFrame([{"cliente_id": k, "tipologia": v} for k, v in gabarito.items()
                  if v != "normal"]).to_parquet(PASTA / "pld_gabarito.parquet",
                                                index=False)

    # resumo para quem roda
    print(f"alertas: {len(f):,} | clientes: {f['cliente_id'].nunique():,}")
    print(f.groupby("regra_id").agg(alertas=("alertas", "sum"),
                                    fp=("descartado_m", "mean"),
                                    com=("comunicado_m", "mean")).round(3))
    print("por mês:\n", pd.Series([d.strftime('%Y-%m') for d in f["data"]]).value_counts().sort_index())
    print("FP geral (maduro):", round(f["descartado_m"].mean(), 3),
          "| comunicados:", int(f["comunicado"].sum()),
          "| com no prazo D+1:", round(f["com_no_prazo"].mean(), 3))
    mm = pd.Series([d.strftime('%Y-%m') for d in f["data"]], index=f.index)
    print(f.groupby(mm).agg(dias=("dias_analise", "mean"), fora=("fora_do_prazo", "sum"),
                            abertos=("em_aberto", "sum")).round(1))
    print("fila em", DATA_BASE, ":", int(f["em_aberto"].sum()), "alertas abertos;",
          int(f["fora_do_prazo"].sum()), "fora do prazo")
    for p in sorted(PASTA.glob("*pld*.parquet")):
        print(f"  {p.name}: {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
