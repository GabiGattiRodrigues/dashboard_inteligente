"""
Gera a base de colaboradores SIMULADA do domínio de People Analytics (Tomoyo).

Este dado não é real e o app diz isso em toda tela. Ele existe porque não há
base pública de RH com linha do tempo: as conhecidas (IBM HR Attrition e
parecidas) são uma fotografia sem data, e sem data não dá para mostrar o que
importa em People Analytics — quando as pessoas entram, quando saem e o que
aconteceu antes de saírem.

A empresa é uma varejista fictícia com operação digital, ~3.700 pessoas.

O grão
------
Uma linha por **pessoa por dia em que ela está ativa**. Parece grande, e é o
que faz as contas de RH ficarem honestas com o motor:

- headcount de um período é a MÉDIA dos dias, não a soma — sai de
  `SUM(ativo) / COUNT(DISTINCT data)`;
- turnover é desligamento sobre **pessoa-dia exposta**, então um mês de 28 dias
  e um de 31 comparam na mesma régua, e o efeito mix (quem pesa mais na base)
  vem de graça na decomposição do motor;
- o evento (admissão, desligamento, promoção, resposta de pesquisa, ausência)
  mora na linha do dia em que aconteceu.

O que foi simulado com intenção (e não com ruído aleatório)
----------------------------------------------------------
1. **Onda de saída em Tecnologia (mar–jun/2026)**, concentrada em Pleno e
   Sênior, depois do congelamento de mérito anunciado em dez/2025. O **eNPS de
   Tecnologia cai três meses antes** da onda — o indicador antecedente que a
   Tomoyo precisa encontrar.
2. **Temporários de fim de ano** em Lojas e CD (out–nov), contratados pelo
   canal "Contratação em massa": tempo de contratação curto, turnover precoce
   alto e uma leva de encerramentos de contrato em janeiro.
3. **Reestruturação do CD em 12/08/2025**: pico de desligamento involuntário,
   seguido de queda de eNPS no CD e respingo no resto da empresa, e de
   absenteísmo maior no CD nos meses seguintes (sobrecarga de quem ficou).
4. **Gap salarial de gênero que é mais mix do que taxa.** No mesmo nível a
   diferença é pequena (~3,5%); no agregado é bem maior, porque há menos
   mulheres em Liderança e em Tecnologia. É o caso exato em que efeito taxa e
   efeito mix contam histórias diferentes.
5. **Sazonalidade de absenteísmo** (inverno e Quarta-feira de Cinzas) e de
   promoção (ciclos de março e setembro; o de mar/2026 quase não promove em
   Tecnologia — parte da história 1).

Turnover precoce e censura
--------------------------
"Saiu em até 90 dias" é marcado na linha da ADMISSÃO. Quem foi admitido há
menos de 90 dias ainda não teve tempo de sair — fica NULO, não zero, e a
censura é pela safra (mês de admissão) inteira, pelo mesmo motivo da safra de
crédito do Bailey: a safra só entra quando o seu último admitido completou 90
dias.

Saída: data/fato_people.parquet
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "fato_people.parquet"

DATA_INICIO = pd.Timestamp("2024-09-01")
DATA_FIM = pd.Timestamp("2026-08-31")
SEMENTE = 20260921

# --------------------------------------------------------------------------- #
# Estrutura da empresa
# --------------------------------------------------------------------------- #

AREAS = ["Lojas", "Centro de distribuição", "Atendimento", "Tecnologia",
         "Comercial", "Corporativo"]
HC_INICIAL = dict(zip(AREAS, [1500, 700, 500, 480, 250, 270]))
CRESC_ANUAL = dict(zip(AREAS, [0.04, 0.03, 0.02, 0.10, 0.06, 0.03]))
VOL_ANUAL = dict(zip(AREAS, [0.30, 0.24, 0.34, 0.14, 0.18, 0.10]))
INV_ANUAL = dict(zip(AREAS, [0.07, 0.06, 0.06, 0.035, 0.06, 0.035]))
ABS_AREA = dict(zip(AREAS, [1.30, 1.40, 1.35, 0.60, 0.85, 0.70]))
F_AREA = dict(zip(AREAS, [0.58, 0.30, 0.66, 0.26, 0.45, 0.57]))
CLIMA_AREA = dict(zip(AREAS, [-0.10, -0.20, -0.25, 0.30, 0.05, 0.20]))
TTF_AREA = dict(zip(AREAS, [16, 14, 18, 46, 32, 38]))      # dias p/ contratar
CUSTO_AREA = dict(zip(AREAS, [1800, 1500, 1600, 9500, 5200, 6800]))
ACEITE_AREA = dict(zip(AREAS, [0.86, 0.88, 0.84, 0.70, 0.78, 0.80]))
OPERACAO = {"Lojas", "Centro de distribuição", "Atendimento"}

NIVEIS = ["Operacional", "Júnior", "Pleno", "Sênior", "Liderança"]
PESO_NIVEL = {
    "Lojas": [0.72, 0.08, 0.06, 0.04, 0.10],
    "Centro de distribuição": [0.75, 0.07, 0.06, 0.04, 0.08],
    "Atendimento": [0.70, 0.10, 0.08, 0.04, 0.08],
    "Tecnologia": [0.00, 0.22, 0.36, 0.30, 0.12],
    "Comercial": [0.10, 0.25, 0.30, 0.20, 0.15],
    "Corporativo": [0.05, 0.25, 0.30, 0.22, 0.18],
}
SAL_NIVEL = dict(zip(NIVEIS, [2100, 3800, 6500, 10500, 16000]))
SAL_AREA = dict(zip(AREAS, [0.92, 0.95, 0.90, 1.35, 1.05, 1.10]))
F_NIVEL = dict(zip(NIVEIS, [1.0, 1.0, 1.0, 0.88, 0.70]))
VOL_NIVEL = dict(zip(NIVEIS, [1.0, 1.15, 1.0, 0.80, 0.55]))
GAP_NO_NIVEL = 0.965          # mulher ganha 3,5% menos NO MESMO nível e área

REGIMES = ["Presencial", "Híbrido", "Remoto"]
PESO_REGIME = {
    "Lojas": [1, 0, 0], "Centro de distribuição": [1, 0, 0],
    "Atendimento": [0.5, 0.3, 0.2], "Tecnologia": [0.15, 0.50, 0.35],
    "Comercial": [0.40, 0.45, 0.15], "Corporativo": [0.25, 0.55, 0.20],
}
REGIOES = ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]
PESO_REGIAO = [0.55, 0.15, 0.18, 0.07, 0.05]

CANAIS = ["Portais de vagas", "Indicação", "LinkedIn", "Consultoria",
          "Contratação em massa"]
PESO_CANAL_OPS = [0.70, 0.22, 0.06, 0.02, 0.0]
PESO_CANAL_ESC = [0.12, 0.25, 0.43, 0.20, 0.0]
VOL_CANAL = dict(zip(CANAIS, [1.0, 0.75, 1.0, 0.95, 1.0]))

# --------------------------------------------------------------------------- #
# Os eventos plantados
# --------------------------------------------------------------------------- #

ONDA_TECH = (pd.Timestamp("2026-03-01"), pd.Timestamp("2026-06-30"), 3.6)
CLIMA_TECH = (pd.Timestamp("2025-12-01"), pd.Timestamp("2026-08-31"), -0.85)
REESTRUTURACAO_CD = (pd.Timestamp("2025-08-12"), 0.08)
CLIMA_CD = (pd.Timestamp("2025-08-12"), pd.Timestamp("2025-11-15"), -1.0)
CLIMA_EMPRESA = (pd.Timestamp("2025-08-12"), pd.Timestamp("2025-09-30"), -0.30)
ABS_CD = (pd.Timestamp("2025-08-15"), pd.Timestamp("2025-11-30"), 1.30)
CINZAS = [pd.Timestamp("2025-03-05"), pd.Timestamp("2026-02-18")]
CICLOS_PROMOCAO = [pd.Timestamp("2025-03-03"), pd.Timestamp("2025-09-01"),
                   pd.Timestamp("2026-03-02")]
REAJUSTE = {pd.Timestamp("2025-01-01"): 1.05, pd.Timestamp("2026-01-01"): 1.048}
# Temporarios de fim de ano: janela de contratacao e acrescimo de quadro.
TEMPORARIOS = {"Lojas": 0.13, "Centro de distribuição": 0.16}
EFETIVACAO = 0.45              # fracao dos temporarios que fica em janeiro

TEMPO_CASA = ["Até 3 meses", "3 a 12 meses", "1 a 3 anos", "Mais de 3 anos"]
FAIXA_IDADE = ["Até 24 anos", "25 a 34 anos", "35 a 44 anos", "45 anos ou mais"]


def _em(d, janela) -> bool:
    return janela[0] <= d <= janela[1]


class Empresa:
    """Estado da população, uma linha por pessoa já contratada."""

    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.cols: dict[str, list] = {k: [] for k in (
            "area", "nivel", "genero", "regime", "regiao", "canal",
            "admissao", "nascimento", "salario", "clima", "ativo",
            "temporario", "saida")}

    # -- contratação -------------------------------------------------------- #
    def contratar(self, area: str, n: int, data: pd.Timestamp,
                  canal: str | None = None, estoque: bool = False,
                  temporario: bool = False) -> np.ndarray:
        rng = self.rng
        ini = len(self.cols["area"])
        for _ in range(n):
            if temporario:
                nivel = "Operacional"
            else:
                nivel = rng.choice(NIVEIS, p=PESO_NIVEL[area])
                # quem entra de fora entra menos em Liderança do que o estoque
                if not estoque and nivel == "Liderança" and rng.random() < 0.6:
                    nivel = "Sênior" if area not in OPERACAO else "Operacional"
            p_f = min(0.95, F_AREA[area] * F_NIVEL[nivel])
            genero = "Feminino" if rng.random() < p_f else "Masculino"
            regime = rng.choice(REGIMES, p=PESO_REGIME[area])
            if canal is None:
                pc = PESO_CANAL_OPS if area in OPERACAO else PESO_CANAL_ESC
                c = rng.choice(CANAIS, p=pc)
            else:
                c = canal
            if estoque:
                media_casa = 1.8 if area in OPERACAO else 3.4
                casa = rng.exponential(media_casa * 365)
                adm = data - pd.Timedelta(days=int(casa) + 1)
            else:
                adm = data
            idade_media = 28 if area in OPERACAO else 33
            idade_media += {"Sênior": 6, "Liderança": 9}.get(nivel, 0)
            idade = max(18.0, rng.normal(idade_media, 7))
            nasc = data - pd.Timedelta(days=int(idade * 365.25))
            sal = (SAL_NIVEL[nivel] * SAL_AREA[area]
                   * rng.lognormal(0, 0.12)
                   * (GAP_NO_NIVEL if genero == "Feminino" else 1.0))
            self.cols["area"].append(area)
            self.cols["nivel"].append(nivel)
            self.cols["genero"].append(genero)
            self.cols["regime"].append(regime)
            self.cols["regiao"].append(rng.choice(REGIOES, p=PESO_REGIAO))
            self.cols["canal"].append(c)
            self.cols["admissao"].append(adm)
            self.cols["nascimento"].append(nasc)
            self.cols["salario"].append(round(sal, 2))
            self.cols["clima"].append(rng.normal(0, 1))
            self.cols["ativo"].append(True)
            self.cols["temporario"].append(temporario)
            self.cols["saida"].append(pd.NaT)
        return np.arange(ini, ini + n)

    def arrays(self):
        return {k: np.array(v) for k, v in self.cols.items()}


def _gerar_admissao(rng, area, data, canal, temporario):
    """Dados do processo seletivo, gravados na linha da admissão."""
    ttf = 7.0 if temporario else TTF_AREA[area]
    aceite = ACEITE_AREA[area]
    if area == "Tecnologia" and data >= ONDA_TECH[0]:
        ttf *= 1.35            # mercado aquecido: vaga de tech demora mais
        aceite -= 0.14
    dias = max(3.0, rng.gamma(4.0, ttf / 4.0))
    ofertas = 1 + rng.geometric(aceite) - 1
    custo = (600.0 if temporario else CUSTO_AREA[area]) * rng.lognormal(0, 0.3)
    if canal == "Consultoria":
        custo *= 2.2
    elif canal == "Indicação":
        custo *= 0.6
    return round(dias, 0), round(custo, 2), int(ofertas)


def gerar() -> pd.DataFrame:
    rng = np.random.default_rng(SEMENTE)
    emp = Empresa(rng)
    for a in AREAS:
        emp.contratar(a, HC_INICIAL[a], DATA_INICIO, estoque=True)

    datas = pd.date_range(DATA_INICIO, DATA_FIM, freq="D")
    lotes: list[pd.DataFrame] = []
    selecao: dict[int, tuple] = {}            # dados do seletivo por pessoa

    for d in datas:
        c = emp.cols
        n = len(c["area"])
        area = np.array(c["area"])
        nivel = np.array(c["nivel"], dtype=object)
        ativo = np.array(c["ativo"])
        adm = pd.to_datetime(np.array(c["admissao"]))
        tenure = (d - adm).days.to_numpy()
        clima = np.array(c["clima"])
        regime = np.array(c["regime"])
        canal = np.array(c["canal"])
        temp = np.array(c["temporario"])
        util = d.dayofweek < 5
        idx = np.flatnonzero(ativo)

        # --- reajuste anual -------------------------------------------------
        if d in REAJUSTE:
            for i in idx:
                c["salario"][i] = round(c["salario"][i] * REAJUSTE[d], 2)

        # --- promoções ------------------------------------------------------
        promovido = np.zeros(n, dtype=np.int8)
        ciclo = d in CICLOS_PROMOCAO
        for i in idx:
            if nivel[i] == "Liderança" or tenure[i] < 365 or temp[i]:
                p = 0.0
            elif ciclo:
                p = 0.09
                if area[i] == "Tecnologia" and d == CICLOS_PROMOCAO[2]:
                    p = 0.025           # mérito congelado em tech
                if area[i] in OPERACAO and nivel[i] == "Operacional":
                    p = 0.05
            else:
                p = 0.015 / 365
            if p and rng.random() < p:
                novo = NIVEIS[NIVEIS.index(nivel[i]) + 1]
                c["nivel"][i] = novo
                nivel[i] = novo
                c["salario"][i] = round(c["salario"][i] * 1.12, 2)
                promovido[i] = 1

        # --- clima do dia (entra no eNPS e no risco de saída) ---------------
        clima_ef = clima.copy()
        clima_ef += np.vectorize(CLIMA_AREA.get)(area)
        clima_ef += np.where(tenure <= 90, 0.4, 0.0)
        if _em(d, CLIMA_TECH):
            clima_ef += np.where(area == "Tecnologia", CLIMA_TECH[2], 0.0)
        if _em(d, CLIMA_CD):
            clima_ef += np.where(area == "Centro de distribuição",
                                 CLIMA_CD[2], 0.0)
        if _em(d, CLIMA_EMPRESA):
            clima_ef += CLIMA_EMPRESA[2]

        # --- desligamentos --------------------------------------------------
        vol = np.vectorize(VOL_ANUAL.get)(area) / 365.0
        vol = vol * np.vectorize(VOL_NIVEL.get)(nivel)
        vol = vol * np.select([tenure <= 90, tenure <= 365, tenure <= 1095],
                              [1.9, 1.25, 1.0], 0.6)
        vol = vol * np.vectorize(VOL_CANAL.get)(canal)
        vol = vol * np.where(temp & (tenure <= 90), 2.6, 1.0)
        vol = vol * np.where(regime == "Remoto", 0.8, 1.0)
        vol = vol * np.exp(-0.35 * (clima_ef - np.vectorize(CLIMA_AREA.get)(area)))
        if _em(d, ONDA_TECH):
            vol = vol * np.where((area == "Tecnologia")
                                 & np.isin(nivel, ["Pleno", "Sênior"]),
                                 ONDA_TECH[2], 1.0)
        inv = np.vectorize(INV_ANUAL.get)(area) / 365.0
        inv = inv * np.where(tenure <= 90, 1.6, 1.0)
        if not util:           # quase ninguém é desligado no fim de semana
            vol, inv = vol * 0.15, inv * 0.05

        u = rng.random(n)
        sai_vol = ativo & (u < vol)
        sai_inv = ativo & ~sai_vol & (rng.random(n) < inv)

        # reestruturação do CD
        if d == REESTRUTURACAO_CD[0]:
            cd = np.flatnonzero(ativo & (area == "Centro de distribuição")
                                & ~sai_vol & ~sai_inv)
            corte = rng.choice(cd, int(len(cd) * REESTRUTURACAO_CD[1]),
                               replace=False)
            sai_inv[corte] = True
        # fim de contrato dos temporários, em janeiro
        if d.month == 1 and 5 <= d.day <= 20 and util:
            alvo = np.flatnonzero(ativo & temp & ~sai_vol & ~sai_inv)
            p_dia = (1 - EFETIVACAO) / 12
            sai_inv[alvo[rng.random(len(alvo)) < p_dia * 1.6]] = True
        if d.month == 1 and d.day == 31:
            # quem sobrou foi efetivado
            for i in np.flatnonzero(ativo & temp):
                c["temporario"][i] = False

        saindo = sai_vol | sai_inv

        # --- ausências e pesquisa ------------------------------------------
        m = len(idx)
        horas_prev = np.full(m, 8 if util else 0, dtype=np.int8)
        aus = np.zeros(m, dtype=np.float32)
        if util:
            a_idx = area[idx]
            p = 0.020 * np.vectorize(ABS_AREA.get)(a_idx)
            mes = d.month
            p = p * (1.30 if mes in (6, 7) else 1.12 if mes == 8
                     else 0.85 if mes == 12 else 1.0)
            if d in CINZAS:
                p = p * 2.4
            p = p * np.where(regime[idx] == "Presencial", 1.1,
                             np.where(regime[idx] == "Remoto", 0.8, 1.0))
            if _em(d, ABS_CD):
                p = p * np.where(a_idx == "Centro de distribuição", ABS_CD[2], 1)
            p = p * np.exp(-0.12 * clima_ef[idx])
            dia_todo = rng.random(m) < p
            parcial = ~dia_todo & (rng.random(m) < 0.012)
            aus = np.where(dia_todo, 8.0,
                           np.where(parcial, rng.integers(2, 5, m), 0.0)
                           ).astype(np.float32)

        # eNPS: pulso mensal, cada pessoa responde com prob. 0,55 num dia útil
        # sorteado do mês. Sortear o dia por pessoa-mês de forma estável:
        resp = np.zeros(m, dtype=np.int8)
        prom = np.zeros(m, dtype=np.int8)
        detr = np.zeros(m, dtype=np.int8)
        if util:
            dias_uteis = pd.bdate_range(d.replace(day=1),
                                        d + pd.offsets.MonthEnd(0))
            k = dias_uteis.get_loc(d)
            semente = (idx * 7919 + d.year * 131 + d.month * 17) % 100003
            dia_sorteado = semente % len(dias_uteis)
            participa = ((semente // 7) % 100) < 55
            resp = ((dia_sorteado == k) & participa).astype(np.int8)
            nota = clima_ef[idx] + rng.normal(0, 0.8, m)
            prom = (resp & (nota > 0.25)).astype(np.int8)
            detr = (resp & (nota < -0.95)).astype(np.int8)

        adm_hoje = (adm[idx] == d).astype(np.int8)
        dias_c = np.full(m, np.nan, dtype=np.float32)
        custo_c = np.full(m, np.nan, dtype=np.float32)
        ofertas = np.zeros(m, dtype=np.int16)
        for j in np.flatnonzero(adm_hoje):
            dias_c[j], custo_c[j], ofertas[j] = selecao[idx[j]]

        idade = (d - pd.to_datetime(np.array(c["nascimento"])[idx])).days / 365.25
        lote = pd.DataFrame({
            "data": d,
            "pessoa_id": idx.astype(np.int32),
            "area": area[idx], "nivel": np.array(c["nivel"])[idx],
            "genero": np.array(c["genero"])[idx], "regime": regime[idx],
            "regiao": np.array(c["regiao"])[idx], "canal": canal[idx],
            "faixa_tempo_casa": np.select(
                [tenure[idx] < 90, tenure[idx] < 365, tenure[idx] < 1095],
                TEMPO_CASA[:3], TEMPO_CASA[3]),
            "faixa_etaria": np.select(
                [idade < 25, idade < 35, idade < 45], FAIXA_IDADE[:3],
                FAIXA_IDADE[3]),
            "safra_admissao": np.where(
                adm[idx] < DATA_INICIO, "Antes de set/2024",
                adm[idx].strftime("%Y-%m")),
            "ativo": np.int8(1),
            "admissao": adm_hoje,
            "desligamento": saindo[idx].astype(np.int8),
            "desl_voluntario": sai_vol[idx].astype(np.int8),
            "desl_involuntario": sai_inv[idx].astype(np.int8),
            "promocao": promovido[idx],
            "horas_previstas": horas_prev,
            "horas_ausencia": aus,
            "respondeu_enps": resp, "promotor": prom, "detrator": detr,
            "salario": np.array(c["salario"], dtype=np.float32)[idx],
            "dias_para_contratar": dias_c,
            "custo_contratacao": custo_c,
            "ofertas": ofertas,
        })
        lotes.append(lote)

        for i in np.flatnonzero(saindo):
            c["ativo"][i] = False
            c["saida"][i] = d

        # --- contratações (para amanhã) -------------------------------------
        amanha = d + pd.Timedelta(days=1)
        if amanha.dayofweek < 5 and amanha <= DATA_FIM:
            anos = (amanha - DATA_INICIO).days / 365.0
            ativo_arr = np.array(c["ativo"])
            area_arr = np.array(c["area"])
            temp_arr = np.array(c["temporario"])
            for a in AREAS:
                alvo = HC_INICIAL[a] * (1 + CRESC_ANUAL[a] * anos)
                if a == "Centro de distribuição" and amanha > REESTRUTURACAO_CD[0]:
                    alvo *= 1 - REESTRUTURACAO_CD[1]
                atual = int((ativo_arr & (area_arr == a) & ~temp_arr).sum())
                gap = alvo - atual
                if gap > 0:
                    k = rng.poisson(gap / TTF_AREA[a] * 1.6)
                    for i in emp.contratar(a, int(min(k, gap + 2)), amanha):
                        selecao[i] = _gerar_admissao(rng, a, amanha,
                                                     c["canal"][i], False)
                # temporários: out–nov, só Lojas e CD
                if a in TEMPORARIOS and amanha.month in (10, 11):
                    meta = int(HC_INICIAL[a] * TEMPORARIOS[a])
                    ja = int((ativo_arr & (area_arr == a) & temp_arr).sum())
                    falta = meta - ja
                    if falta > 0:
                        k = min(falta, rng.poisson(meta / 30))
                        novos = emp.contratar(a, int(k), amanha,
                                              canal="Contratação em massa",
                                              temporario=True)
                        for i in novos:
                            selecao[i] = _gerar_admissao(
                                rng, a, amanha, "Contratação em massa", True)

    df = pd.concat(lotes, ignore_index=True)

    # --- turnover precoce, marcado na admissão e censurado por safra --------
    saida = pd.Series(pd.to_datetime(np.array(emp.cols["saida"])))
    adm_pessoa = pd.Series(pd.to_datetime(np.array(emp.cols["admissao"])))
    dias_ate_sair = (saida - adm_pessoa).dt.days
    saiu_90 = (dias_ate_sair <= 90).astype(float).to_numpy()
    eh_adm = df["admissao"].to_numpy() == 1
    df["saiu_90d"] = np.where(eh_adm, saiu_90[df["pessoa_id"].to_numpy()], np.nan)
    ultimo_dia_safra = (df["data"] + pd.offsets.MonthEnd(0))
    imatura = (DATA_FIM - ultimo_dia_safra).dt.days < 90
    df.loc[eh_adm & imatura.to_numpy(), "saiu_90d"] = np.nan
    # desligamento precoce, na linha do desligamento
    df["desl_precoce"] = (
        (df["desligamento"] == 1)
        & (dias_ate_sair.to_numpy()[df["pessoa_id"].to_numpy()] <= 90)
    ).astype(np.int8)

    for col in ("area", "nivel", "genero", "regime", "regiao", "canal",
                "faixa_tempo_casa", "faixa_etaria", "safra_admissao"):
        df[col] = df[col].astype("category")
    df["saiu_90d"] = df["saiu_90d"].astype(np.float32)
    return df


if __name__ == "__main__":
    fato = gerar()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fato.to_parquet(OUT, index=False, compression="zstd")

    dias = fato["data"].nunique()
    pd_ = len(fato)
    print(f"linhas (pessoa-dia): {pd_:,} | pessoas: {fato['pessoa_id'].nunique():,}")
    print(f"periodo: {fato['data'].min().date()} a {fato['data'].max().date()}")
    print(f"headcount medio: {pd_ / dias:,.0f}")
    print(f"turnover anualizado: {fato['desligamento'].sum() * 365 / pd_:.1%} "
          f"(voluntario {fato['desl_voluntario'].sum() * 365 / pd_:.1%})")
    r = fato["respondeu_enps"].sum()
    print(f"eNPS: {(fato['promotor'].sum() - fato['detrator'].sum()) * 100 / r:.0f}")
    print(f"absenteismo: {fato['horas_ausencia'].sum() / fato['horas_previstas'].sum():.2%}")
    print(f"turnover precoce (90d): {fato['saiu_90d'].mean():.1%}")
    print(f"arquivo: {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
