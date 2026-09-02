"""
Agente de alertas: varre métricas x segmentos e traz só o que merece atenção.

Dois tipos de alerta, porque são duas perguntas diferentes:

- **Anomalia** — "está fora do que esse segmento costuma ser". Baseline
  histórico, sem número fixo.
- **Limite de negócio** — "passou do patamar acordado". Número fixo, combinado
  com a área, independente de histórico.

Por que baseline robusto
------------------------
Média e desvio padrão são arrastados justamente pelo ponto que se quer
detectar: uma Black Friday infla a média e o desvio, e o alerta seguinte não
dispara. Aqui o baseline é **mediana + MAD** sobre a janela histórica, ambos
resistentes a outlier, com z robusto

    z = 0,6745 · (x − mediana) / MAD

O fator 0,6745 coloca o MAD na mesma escala do desvio padrão de uma normal,
para que o corte em 3 continue querendo dizer "3 sigmas".

Por que o corte de materialidade
--------------------------------
É o que separa alerta de barulho. Um segmento minusculo estoura z o tempo
todo -- variação relativa em base pequena é enorme por construção. Sem esse
corte o painel dispara dezenas de alertas por dia, ninguém lê, e o produto
morre. Todo alerta precisa passar em DUAS provas: ser estatisticamente
estranho E mover o total o suficiente para valer o telefonema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Sequence

import duckdb
import numpy as np
import pandas as pd

from .dados import Filtros, agregar, serie_diaria
from .formatacao import numero, pct
from .semantica import Dominio, Limite


@dataclass
class Alerta:
    tipo: str                 # "anomalia" | "limite"
    severidade: str           # "alta" | "media" | "baixa"
    chave_metrica: str
    dimensao: Optional[str]
    segmento: Optional[str]
    data: date
    observado: float
    esperado: float
    z: float
    impacto: float            # em unidades da metrica, sobre o total
    participacao: float       # peso do segmento na base
    texto: str
    acao: str

    @property
    def ordem(self) -> float:
        peso = {"alta": 3, "media": 2, "baixa": 1}[self.severidade]
        return peso * 1000 + min(abs(self.z), 20) * abs(self.participacao) * 10


# --------------------------------------------------------------------------- #
# Baseline robusto
# --------------------------------------------------------------------------- #

def _mad(x: np.ndarray) -> float:
    if len(x) == 0:
        return float("nan")
    med = np.nanmedian(x)
    return float(np.nanmedian(np.abs(x - med)))


def _z_robusto(valor: float, hist: np.ndarray) -> tuple[float, float]:
    """Devolve (z robusto, esperado). MAD zero cai para o desvio padrão."""
    hist = hist[np.isfinite(hist)]
    if len(hist) < 7:
        return 0.0, float("nan")
    med = float(np.nanmedian(hist))
    escala = 1.4826 * _mad(hist)

    # MAD zero acontece quando mais da metade da janela tem o mesmo valor --
    # serie muito plana, ou com poucos valores distintos. Cair no desvio padrao
    # aqui seria desfazer justamente a robustez que se queria: o desvio padrao
    # e inflado pelo outlier que se quer detectar, e o alerta some. A escada
    # abaixo desce por alternativas que continuam resistentes.
    if escala <= 1e-9:                                   # 1) amplitude interquartil
        q1, q3 = np.nanpercentile(hist, [25, 75])
        escala = (q3 - q1) / 1.349
    if escala <= 1e-9:                                   # 2) desvio aparado
        baixo, alto = np.nanpercentile(hist, [10, 90])
        miolo = hist[(hist >= baixo) & (hist <= alto)]
        escala = float(np.nanstd(miolo)) if len(miolo) > 1 else 0.0
    if escala <= 1e-9:
        # 3) Serie constante. Qualquer desvio e, a rigor, infinitamente
        # improvavel; devolver z = 0 diria o oposto. Marca-se como desvio
        # forte, com sinal, limitado a um valor finito para nao poluir a
        # ordenacao dos alertas.
        if abs(valor - med) <= 1e-9:
            return 0.0, med
        return float(np.sign(valor - med) * 99.0), med
    return float((valor - med) / escala), med


# --------------------------------------------------------------------------- #
# Varredura
# --------------------------------------------------------------------------- #

def varrer(
    con: duckdb.DuckDBPyConnection,
    dom: Dominio,
    ref: date,
    filtros: Optional[Filtros] = None,
    metricas: Optional[Sequence[str]] = None,
    dims: Optional[Sequence[str]] = None,
    dias_historico: int = 56,
    z_limite: float = 3.0,
    materialidade: float = 0.03,
    limites: Optional[list[Limite]] = None,
    top_segmentos: int = 12,
) -> list[Alerta]:
    """
    Compara o dia `ref` contra os `dias_histórico` anteriores, no total e por
    segmento, e devolve os alertas já ordenados por relevância.
    """
    metricas = list(metricas) if metricas else dom.alertar_metricas
    dims = list(dims) if dims else dom.alertar_dims
    limites = dom.limites if limites is None else limites
    ini_hist = ref - timedelta(days=dias_historico)
    fim_hist = ref - timedelta(days=1)
    alertas: list[Alerta] = []

    # ---------------- total ------------------------------------------------ #
    hist = serie_diaria(con, dom, list(metricas), ini_hist, fim_hist, filtros)
    hoje = serie_diaria(con, dom, list(metricas), ref, ref, filtros)
    if hoje.empty:
        return []

    for mk in metricas:
        m = dom.metrica(mk)
        val = hoje.iloc[0][mk]
        if pd.isna(val):
            continue
        val = float(val)
        z, esp = _z_robusto(val, hist[mk].to_numpy(dtype=float))

        if abs(z) >= z_limite and np.isfinite(esp):
            piorou = (z < 0) if m.bom_quando_sobe else (z > 0)
            sev = "alta" if abs(z) >= 4 else "media"
            alertas.append(Alerta(
                tipo="anomalia",
                severidade=sev if piorou else "baixa",
                chave_metrica=mk, dimensao=None, segmento=None, data=ref,
                observado=val, esperado=esp, z=z,
                impacto=val - esp, participacao=1.0,
                texto=(
                    f"**{m.rotulo}** no total fechou em {numero(val, m)}, contra "
                    f"{numero(esp, m)} esperados pelo histórico de "
                    f"{dias_historico} dias (z robusto = {z:+.1f})."
                ),
                acao=(
                    "Abrir a aba de causa raiz para esta métrica e ver qual "
                    "segmento carrega a variação antes de acionar alguém."
                ),
            ))

        for lim in limites:
            if lim.chave_metrica != mk:
                continue
            estourou = (val > lim.valor) if lim.operador == ">" else (val < lim.valor)
            if estourou:
                alertas.append(Alerta(
                    tipo="limite", severidade="alta",
                    chave_metrica=mk, dimensao=None, segmento=None, data=ref,
                    observado=val, esperado=lim.valor, z=0.0,
                    impacto=val - lim.valor, participacao=1.0,
                    texto=(
                        f"**{m.rotulo}** em {numero(val, m)} rompeu o limite "
                        f"combinado de {numero(lim.valor, m)}. {lim.justificativa}"
                    ),
                    acao="Limite de negócio, não estatístico: acionar o dono da métrica.",
                ))

    # ---------------- por segmento ----------------------------------------- #
    for dk in dims:
        d = dom.dimensao(dk)
        ordem = dom.metricas_painel[0]
        base = agregar(con, dom, [ordem], ini_hist, ref, dims=[dk],
                       filtros=filtros, ordenar_por=ordem, limite=top_segmentos)
        if base.empty:
            continue
        segmentos = base[d.coluna].astype(str).tolist()

        h_seg = agregar(con, dom, list(metricas), ini_hist, fim_hist, dims=[dk],
                        filtros=filtros, por_dia=True)
        r_seg = agregar(con, dom, list(metricas), ref, ref, dims=[dk], filtros=filtros)
        if h_seg.empty or r_seg.empty:
            continue
        h_seg[d.coluna] = h_seg[d.coluna].astype(str)
        r_seg[d.coluna] = r_seg[d.coluna].astype(str)

        for mk in metricas:
            m = dom.metrica(mk)
            # Relevancia se mede sobre a POPULACAO do segmento, e nao sobre o
            # numerador.
            #
            # Para uma taxa, usar o numerador leva a um absurdo: se houve um
            # unico cancelamento no dia e ele caiu num segmento minusculo, esse
            # segmento responde por 100% dos cancelamentos e passa por
            # "material" -- quando na verdade ele e um punhado de pedidos. O que
            # torna um segmento digno de alerta e o tamanho da base dele, que e
            # o denominador.
            coluna_peso = f"{mk}__den" if m.eh_razao else f"{mk}__num"
            total_hoje = float(hoje.iloc[0][coluna_peso] or 0)
            for seg in segmentos:
                linha = r_seg[r_seg[d.coluna] == seg]
                if linha.empty or pd.isna(linha.iloc[0][mk]):
                    continue
                val = float(linha.iloc[0][mk])
                peso_bruto = float(linha.iloc[0][coluna_peso] or 0)

                hs = h_seg[h_seg[d.coluna] == seg][mk].to_numpy(dtype=float)
                z, esp = _z_robusto(val, hs)
                if not np.isfinite(esp) or abs(z) < z_limite:
                    continue

                part = (peso_bruto / total_hoje) if total_hoje else 0.0
                if abs(part) < materialidade:
                    continue  # estatisticamente estranho, mas irrelevante

                piorou = (z < 0) if m.bom_quando_sobe else (z > 0)
                sev = ("alta" if (abs(z) >= 4 and part >= 0.10) else "media") \
                    if piorou else "baixa"

                alertas.append(Alerta(
                    tipo="anomalia", severidade=sev,
                    chave_metrica=mk, dimensao=dk, segmento=seg, data=ref,
                    observado=val, esperado=esp, z=z,
                    impacto=(val - esp), participacao=part,
                    texto=(
                        f"**{m.rotulo}** em *{seg}* ({d.rotulo.lower()}) fechou em "
                        f"{numero(val, m)}, contra {numero(esp, m)} esperados "
                        f"(z robusto = {z:+.1f}). O segmento responde por "
                        f"{pct(part, 1, sinal=False)} "
                        + ("da base da métrica no dia." if m.eh_razao
                           else "da métrica no dia.")
                    ),
                    acao=(
                        f"Segmento material e fora do padrão: vale olhar "
                        f"{d.rotulo.lower()} = {seg} na aba de causa raiz."
                    ),
                ))

    alertas.sort(key=lambda a: a.ordem, reverse=True)
    return alertas


def resumir(alertas: list[Alerta], ref: date) -> str:
    """Uma linha de abertura, para quem só vai ler o topo da tela."""
    if not alertas:
        return (
            f"Nenhum alerta em {ref.strftime('%d/%m/%Y')}: todas as métricas "
            f"acompanhadas ficaram dentro da faixa histórica e dos limites "
            f"combinados. Silêncio aqui é informação, não ausência de checagem."
        )
    altas = [a for a in alertas if a.severidade == "alta"]
    limites = [a for a in alertas if a.tipo == "limite"]
    n = len(alertas)
    partes = [f"**{n} {'alerta' if n == 1 else 'alertas'}** em "
              f"{ref.strftime('%d/%m/%Y')}"]
    if altas:
        partes.append(f"{len(altas)} de severidade alta")
    if limites:
        partes.append(f"{len(limites)} por rompimento de limite de negócio")
    return ", ".join(partes) + "."


# --------------------------------------------------------------------------- #
# Achar um dia que tenha o que mostrar
# --------------------------------------------------------------------------- #

def ultimo_dia_com_alerta(
    con: duckdb.DuckDBPyConnection,
    dom: Dominio,
    ate: date,
    filtros: Optional[Filtros] = None,
    dias_busca: int = 120,
    dias_historico: int = 56,
    z_limite: float = 3.0,
) -> Optional[date]:
    """
    Devolve o dia mais recente, ate `ate`, em que alguma metrica do total
    saiu da faixa ou rompeu um limite.

    Existe por um motivo de produto, nao de estatistica: a aba de alertas e a
    primeira que abre, e cair num dia silencioso e a pior primeira tela
    possivel -- passa a impressao de ferramenta vazia, quando na verdade o
    silencio e o resultado correto para aquele dia. Com isto o painel consegue
    dizer "hoje esta quieto, mas o ultimo movimento foi em tal dia" e levar a
    pessoa ate ele.

    Para ser barato, olha so o nivel total (nao varre segmento) e faz a conta
    vetorizada sobre uma unica serie: mediana e MAD moveis, z robusto, e o
    primeiro dia de tras para frente que estoure o corte. O resultado alimenta
    uma varredura completa depois, no dia escolhido.
    """
    metricas = dom.alertar_metricas
    ini = ate - timedelta(days=dias_busca + dias_historico)
    s = serie_diaria(con, dom, list(metricas), ini, ate, filtros)
    if s.empty:
        return None

    s = s.sort_values("data").reset_index(drop=True)
    marcado = pd.Series(False, index=s.index)

    for mk in metricas:
        if mk not in s.columns:
            continue
        v = pd.to_numeric(s[mk], errors="coerce")
        if v.notna().sum() < dias_historico // 2:
            continue

        med = v.rolling(dias_historico, min_periods=14).median().shift(1)
        desvio = (v - med).abs()
        mad = desvio.rolling(dias_historico, min_periods=14).median().shift(1)
        escala = 1.4826 * mad
        # MAD zero (serie muito plana na janela) cai para o desvio padrao.
        alternativa = v.rolling(dias_historico, min_periods=14).std().shift(1)
        escala = escala.where(escala > 1e-9, alternativa)

        z = (v - med) / escala
        marcado |= z.abs() >= z_limite

        for lim in dom.limites:
            if lim.chave_metrica != mk:
                continue
            marcado |= (v > lim.valor) if lim.operador == ">" else (v < lim.valor)

    candidatos = s.loc[marcado, "data"]
    if candidatos.empty:
        return None
    d = pd.Timestamp(candidatos.iloc[-1])
    return d.date()


# --------------------------------------------------------------------------- #
# Possível motivo: o alerta não para em "está estranho"
# --------------------------------------------------------------------------- #

def _br_num(x: float, casas: int = 1) -> str:
    """Número no padrão brasileiro. 2.3 vira 2,3."""
    return f"{x:.{casas}f}".replace(".", ",")


def _base_por_segmento(
    con, dom: Dominio, mk: str, dk: str, ref: date,
    dias_base: Sequence[date], filtros: Optional[Filtros],
) -> pd.DataFrame:
    """
    Numerador e denominador por segmento no dia, e a média deles nos dias-base.

    Os dias-base são os mesmos dias da semana anteriores, e não os dias
    corridos: comparar uma terça contra segunda, domingo e sábado mediria
    calendário, não desempenho.
    """
    col = dom.dimensao(dk).coluna
    nc, dc = f"{mk}__num", f"{mk}__den"

    hoje = agregar(con, dom, [mk], ref, ref, dims=[dk], filtros=filtros)
    if hoje.empty:
        return pd.DataFrame()
    hoje = hoje[[col, nc, dc]].rename(columns={nc: "num_b", dc: "den_b"})

    partes = []
    for d in dias_base:
        p = agregar(con, dom, [mk], d, d, dims=[dk], filtros=filtros)
        if not p.empty:
            partes.append(p[[col, nc, dc]])
    if not partes:
        return pd.DataFrame()

    base = (pd.concat(partes).groupby(col, as_index=False).mean()
            .rename(columns={nc: "num_a", dc: "den_a"}))

    df = base.merge(hoje, on=col, how="outer").fillna(0.0)
    return df.rename(columns={col: "segmento"})


def motivo_provavel(
    con, dom: Dominio, alerta: Alerta, filtros: Optional[Filtros] = None,
    dias_base: int = 4, dims: Optional[Sequence[str]] = None,
    nomear_metrica: bool = False,
) -> Optional[str]:
    """
    Diz de onde o desvio veio, e não só que ele existe.

    Um alerta que diz "a receita caiu" manda a pessoa abrir outra aba para
    descobrir onde. Aqui a decomposição já roda junto: o dia é comparado com a
    média dos mesmos dias da semana anteriores, por segmento, e o segmento que
    mais carrega a diferença vira a frase.

    Para alerta que já nasceu num segmento, a busca desce um nível: filtra
    naquele segmento e decompõe por outra dimensão. "Cartão de crédito caiu"
    vira "e dentro dele, a queda está em São Paulo".
    """
    m = dom.metrica(alerta.chave_metrica)
    ref = alerta.data
    base = [ref - timedelta(days=7 * (i + 1)) for i in range(dias_base)]

    # Alerta de segmento: olha DENTRO dele, por outra dimensão.
    if alerta.segmento and alerta.dimensao:
        vals = dict((filtros.valores if filtros else {}))
        vals[alerta.dimensao] = [alerta.segmento]
        filtros = Filtros(vals)
        candidatas = [d for d in (dims or dom.alertar_dims)
                      if d != alerta.dimensao]
    else:
        candidatas = list(dims or dom.alertar_dims)

    melhor = None
    for dk in candidatas[:3]:
        df = _base_por_segmento(con, dom, alerta.chave_metrica, dk, ref,
                                base, filtros)
        if df.empty or len(df) < 2:
            continue

        if m.eh_razao:
            tot_a = df["den_a"].sum() or 1.0
            tot_b = df["den_b"].sum() or 1.0
            taxa_a = df.apply(lambda r: r["num_a"] / r["den_a"] if r["den_a"] else 0.0, axis=1)
            taxa_b = df.apply(lambda r: r["num_b"] / r["den_b"] if r["den_b"] else 0.0, axis=1)
            peso_a, peso_b = df["den_a"] / tot_a, df["den_b"] / tot_b
            df["contrib"] = (peso_a * (taxa_b - taxa_a)
                             + (peso_b - peso_a) * taxa_a
                             + (peso_b - peso_a) * (taxa_b - taxa_a))
            df["efeito_taxa"] = peso_a * (taxa_b - taxa_a)
            df["efeito_mix"] = (peso_b - peso_a) * taxa_a
            df["de"], df["para"] = taxa_a, taxa_b
        else:
            df["contrib"] = df["num_b"] - df["num_a"]
            df["efeito_taxa"], df["efeito_mix"] = df["contrib"], 0.0
            df["de"], df["para"] = df["num_a"], df["num_b"]

        total = float(df["contrib"].sum())
        # Desvio perto de zero faz a participacao explodir: um segmento que
        # contribui 0,3 num total de 0,0026 vira "11.627% do desvio", que e
        # aritmeticamente certo e informativamente lixo. So vale decompor um
        # desvio que seja material perto do proprio nivel da metrica.
        nivel = float(abs(df["num_a"].sum() / (df["den_a"].sum() or 1.0))
                      if m.eh_razao else abs(df["num_a"].sum()))
        if abs(total) < 1e-12 or abs(total) < nivel * 0.005:
            continue

        # Participacao normal de cada segmento na metrica, antes do desvio.
        tamanho = df["den_a"] if m.eh_razao else df["num_a"]
        soma_tam = float(tamanho.sum()) or 1.0
        df["parte_normal"] = tamanho / soma_tam
        df["parte_do_desvio"] = df["contrib"] / total

        topo = df.reindex(df["contrib"].abs().sort_values(ascending=False).index).iloc[0]
        peso = abs(float(topo["parte_do_desvio"]))
        normal = max(float(topo["parte_normal"]), 1e-6)

        # DESPROPORCAO, e nao tamanho.
        #
        # Sem isto, a resposta e sempre o maior segmento: cartao de credito
        # carrega 82% do desvio da receita, mas ele ja e 80% da receita todo
        # dia -- dizer isso nao explica nada, so repete a composicao da base.
        # O que informa e o segmento que pesa MUITO mais no desvio do que pesa
        # no normal. Entre as dimensoes candidatas, ganha a de maior
        # desproporcao, desde que o segmento carregue parte relevante.
        desproporcao = peso / normal
        if peso < 0.15:
            continue
        if melhor is None or desproporcao > melhor[0]:
            melhor = (desproporcao, dk, topo, total, peso, normal)

    if melhor is None:
        return None

    desproporcao, dk, topo, total, peso, normal = melhor
    d = dom.dimensao(dk)
    if peso < 0.25:
        return (f"O desvio está **espalhado**: nenhum(a) {d.rotulo.lower()} "
                f"responde por mais de {pct(peso, 0, sinal=False)} dele. "
                f"Isso aponta causa geral — calendário, campanha ampla ou "
                f"mudança de sistema — e não um segmento específico.")

    sentido = "puxou para cima" if topo["contrib"] > 0 else "puxou para baixo"
    # Participacao acima de 100% e legitima e acontece quando outros segmentos
    # puxaram para o lado contrario: o segmento carregou mais do que o desvio
    # liquido. Dizer so "110% do desvio" soa como erro de conta; vale explicar.
    quanto = (f"{pct(peso, 0, sinal=False)} do desvio" if peso <= 1.0 else
              f"mais do que todo o desvio líquido ({pct(peso, 0, sinal=False)}) "
              f"— outros segmentos puxaram no sentido contrário")
    # Quando varios motivos aparecem juntos (analise geral), sem o nome da
    # metrica o leitor nao sabe de qual alerta cada paragrafo esta falando.
    abre = (f"**Possível motivo — {m.rotulo.lower()}:**" if nomear_metrica
            else "**Possível motivo:**")
    frase = (
        f"{abre} {d.rotulo.lower()} **{topo['segmento']}** "
        f"{sentido} {quanto}, saindo de "
        f"{numero(float(topo['de']), m)} para {numero(float(topo['para']), m)} "
        f"(base: média dos {dias_base} mesmos dias da semana anteriores)."
    )
    if desproporcao >= 1.6:
        frase += (f" Esse segmento normalmente responde por apenas "
                  f"{pct(normal, 0, sinal=False)} da métrica — ou seja, ele "
                  f"pesa {_br_num(desproporcao)}× mais no desvio do que pesa "
                  f"no dia a dia. É aí que vale olhar primeiro.")
    else:
        frase += (f" Ressalva: o segmento já responde por "
                  f"{pct(normal, 0, sinal=False)} da métrica no normal, então "
                  f"ele aparecer no topo diz pouco — o desvio acompanha a "
                  f"composição da base, e não se concentra num lugar.")
    if m.eh_razao and abs(float(topo["efeito_mix"])) > abs(float(topo["efeito_taxa"])):
        frase += (" A maior parte vem de **mudança de composição**, não do "
                  "segmento em si ter mudado de patamar — o que aponta "
                  "aquisição, e não operação.")
    return frase
