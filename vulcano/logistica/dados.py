"""
As três leituras que só o domínio de Logística tem.

    fila()              os pedidos travados numa data de referência, já com a
                        ação da régua D+3/D+7 e de quem é a vez de agir
    ponto_sem_volta()   para cada dia depois do prometido, quantos dos ainda
                        pendentes acabam chegando -- com intervalo de Wilson
    controle()          o gráfico de controle (p-chart) semanal da taxa fora do
                        prazo, por origem
    pedido()            a linha do tempo de um pedido, com o que a régua
                        mandava fazer em cada data

Tudo lê o mesmo `fato` do motor genérico e respeita os mesmos filtros da barra
lateral. Nenhuma função aqui olha o futuro da data de referência, com uma
exceção declarada: o desfecho de um pedido no detalhe, que aparece rotulado
como tal.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from ..dados import Filtros

# Faixas da fila, em dias depois do prometido. Os dois cortes do meio são a
# régua; o último separa quem a régua deveria ter resolvido e não resolveu.
FAIXAS = [
    (1, 2, "vencido"),
    (3, 6, "d3"),
    (7, 30, "d7"),
    (31, 10_000, "esquecido"),
]

# Janela do gráfico de controle: 52 semanas até a data de referência. Com
# menos que isso a linha central de um p-chart é a média de poucas semanas e
# muda conforme o período escolhido na barra lateral.
SEMANAS_CONTROLE = 52


def _d(x) -> date:
    return x.date() if hasattr(x, "date") else x


def _extra(dom, filtros: Optional[Filtros]) -> str:
    return "".join(" AND " + c for c in (filtros.clausulas(dom) if filtros
                                         else []))


def corte(con) -> date:
    """O último evento conhecido da base. Depois disso não se sabe se chegou."""
    v = con.execute("""SELECT MAX(GREATEST(COALESCE(dt_entrega, data),
                                           COALESCE(dt_postagem, data)))
                         FROM fato""").fetchone()[0]
    return _d(v)


def wilson(x: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """
    Intervalo de Wilson para uma proporção.

    O intervalo "normal" (p ± 1,96·erro) se comporta mal justamente onde esta
    régua mais olha: proporção perto de 0% ou de 100% e n pequeno, como uma
    origem com 20 pedidos pendentes no D+7. Ali ele pode até passar de 100%.
    O de Wilson fica dentro de [0, 1] e se lê do mesmo jeito.
    """
    if not n:
        return float("nan"), float("nan")
    p = x / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - meia), min(1.0, centro + meia)


# --------------------------------------------------------------------------- #
# Fila de travados
# --------------------------------------------------------------------------- #

def faixa(dias_vencido: int) -> str:
    for a, b, k in FAIXAS:
        if a <= dias_vencido <= b:
            return k
    return "vencido"


def fila(con, dom, ref: date, filtros: Optional[Filtros] = None
         ) -> pd.DataFrame:
    """
    Os pedidos vencidos e não entregues NA DATA `ref`, como se sabia naquele
    dia: o pedido entregue depois de `ref` está na fila, e o evento posterior
    a `ref` (postagem, aprovação) não conta.
    """
    r = f"DATE '{ref}'"
    df = con.execute(f"""
        SELECT order_id, pedido, CAST(data AS DATE) AS prometida,
               CAST(dt_compra AS DATE) AS compra,
               origem, uf_origem, estado_destino, rota, categoria, seller_id,
               valor, itens,
               CASE WHEN dt_postagem <= {r} THEN 'transito'
                    WHEN dt_aprovacao <= {r} THEN 'postagem'
                    ELSE 'aprovacao' END AS etapa,
               CAST(GREATEST(dt_compra,
                     COALESCE(CASE WHEN dt_aprovacao <= {r}
                                   THEN dt_aprovacao END, dt_compra),
                     COALESCE(CASE WHEN dt_postagem <= {r}
                                   THEN dt_postagem END, dt_compra))
                    AS DATE) AS ultimo_evento,
               date_diff('day', CAST(data AS DATE), {r}) AS dias_vencido
          FROM fato
         WHERE CAST(data AS DATE) < {r}
           AND CAST(dt_compra AS DATE) <= {r}
           AND (dt_entrega IS NULL OR CAST(dt_entrega AS DATE) > {r})
           {_extra(dom, filtros)}
         ORDER BY dias_vencido DESC, valor DESC
    """).fetchdf()
    if df.empty:
        return df
    df["dias_parado"] = (pd.Timestamp(ref) - pd.to_datetime(
        df["ultimo_evento"])).dt.days
    df["faixa"] = df["dias_vencido"].map(faixa)
    df["quem"] = df["etapa"].map({"transito": "transportadora",
                                  "postagem": "seller",
                                  "aprovacao": "pagamento"})
    return df


def resumo_fila(f: pd.DataFrame) -> dict:
    """Contagens por faixa e o que entrou na régua exatamente hoje."""
    if f.empty:
        return {k: 0 for _, _, k in FAIXAS} | {
            "total": 0, "valor": 0.0, "hoje_d3": 0, "hoje_d7": 0,
            "transportadora": 0, "seller": 0}
    c = f["faixa"].value_counts()
    return {
        **{k: int(c.get(k, 0)) for _, _, k in FAIXAS},
        "total": len(f),
        "valor": float(f["valor"].sum()),
        "hoje_d3": int((f["dias_vencido"] == 3).sum()),
        "hoje_d7": int((f["dias_vencido"] == 7).sum()),
        "transportadora": int((f["quem"] == "transportadora").sum()),
        "seller": int((f["quem"] != "transportadora").sum()),
    }


def fila_diaria(con, dom, inicio: date, fim: date,
                filtros: Optional[Filtros] = None) -> pd.DataFrame:
    """Tamanho da fila em cada dia, por faixa -- para ver se ela cresce."""
    df = con.execute(f"""
        WITH dias AS (
          SELECT CAST(range AS DATE) AS ref
            FROM range(DATE '{inicio}', DATE '{fim}' + INTERVAL 1 DAY,
                       INTERVAL 1 DAY)
        ), p AS (
          SELECT CAST(data AS DATE) AS prom, CAST(dt_entrega AS DATE) AS ent,
                 CAST(dt_compra AS DATE) AS compra
            FROM fato WHERE TRUE {_extra(dom, filtros)}
        )
        SELECT ref,
               SUM(CASE WHEN date_diff('day', prom, ref) BETWEEN 1 AND 2
                        THEN 1 ELSE 0 END) AS vencido,
               SUM(CASE WHEN date_diff('day', prom, ref) BETWEEN 3 AND 6
                        THEN 1 ELSE 0 END) AS d3,
               SUM(CASE WHEN date_diff('day', prom, ref) BETWEEN 7 AND 30
                        THEN 1 ELSE 0 END) AS d7,
               SUM(CASE WHEN date_diff('day', prom, ref) > 30
                        THEN 1 ELSE 0 END) AS esquecido
          FROM dias JOIN p
            ON p.prom < dias.ref AND p.compra <= dias.ref
           AND (p.ent IS NULL OR p.ent > dias.ref)
         GROUP BY 1 ORDER BY 1
    """).fetchdf()
    if not df.empty:
        df["ref"] = pd.to_datetime(df["ref"])
    return df


# --------------------------------------------------------------------------- #
# Ponto de não retorno
# --------------------------------------------------------------------------- #

def ponto_sem_volta(con, dom, inicio: date, fim: date,
                    filtros: Optional[Filtros] = None,
                    por: Optional[str] = None, max_dias: int = 30
                    ) -> pd.DataFrame:
    """
    Para k = 0..max_dias: dos pedidos vencidos no período que ainda não
    tinham chegado k dias depois do prometido, quantos chegaram depois.

    Só entra o dia k que a base consegue observar (prometido + k até o corte).
    É uma versão simplificada da curva de sobrevivência -- o tratamento formal
    da censura seria Kaplan-Meier --, e aqui ela basta: o corte da base fica a
    pelo menos 47 dias do último prometido, então todo k até 30 é visto.
    """
    lim = corte(con)
    col = dom.dimensao(por).coluna if por else None
    grupo = f", {col} AS segmento" if col else ""
    gb = ", 2" if col else ""
    df = con.execute(f"""
        WITH b AS (
          SELECT CAST(data AS DATE) AS prom, CAST(dt_entrega AS DATE) AS ent
                 {"," + col if col else ""}
            FROM fato
           WHERE data BETWEEN DATE '{inicio}' AND DATE '{fim}'
                 {_extra(dom, filtros)}
        )
        SELECT k.range AS k {grupo},
               SUM(CASE WHEN ent IS NULL OR ent > prom + CAST(k.range AS INT)
                        THEN 1 ELSE 0 END) AS pendentes,
               SUM(CASE WHEN ent > prom + CAST(k.range AS INT)
                        THEN 1 ELSE 0 END) AS chegaram
          FROM b, range(0, {max_dias + 1}) k
         WHERE prom + CAST(k.range AS INT) <= DATE '{lim}'
         GROUP BY 1{gb} ORDER BY {"2, " if col else ""}1
    """).fetchdf()
    if df.empty:
        return df
    df["k"] = df["k"].astype(int)
    df["taxa"] = df["chegaram"] / df["pendentes"].where(df["pendentes"] > 0)
    ic = [wilson(x, n) for x, n in zip(df["chegaram"], df["pendentes"])]
    df["ic_inf"] = [a for a, _ in ic]
    df["ic_sup"] = [b for _, b in ic]
    return df


def dia_da_virada(curva: pd.DataFrame, nivel: float = 0.5) -> Optional[int]:
    """Primeiro dia em que menos da metade dos pendentes ainda chega -- o
    ponto em que esperar vira cara ou coroa perdida."""
    abaixo = curva[curva["taxa"] < nivel]
    return int(abaixo["k"].min()) if not abaixo.empty else None


# --------------------------------------------------------------------------- #
# Gráfico de controle
# --------------------------------------------------------------------------- #

def janela_controle(ref: date, dmin: date) -> tuple[date, date]:
    ini = ref - timedelta(weeks=SEMANAS_CONTROLE) + timedelta(days=1)
    return max(ini, dmin), ref


def controle(con, dom, inicio: date, fim: date,
             filtros: Optional[Filtros] = None, por: Optional[str] = "origem"
             ) -> pd.DataFrame:
    """
    p-chart semanal da taxa fora do prazo, uma série por segmento.

    Para cada série: p̄ = fora do prazo ÷ pedidos na janela inteira; o limite
    de cada semana é p̄ ± 3·raiz(p̄(1−p̄)/n), com o n DAQUELA semana -- semana
    com pouco pedido tem limite mais largo, e é isso que impede uma origem
    pequena de acender alerta todo mês por puro ruído.

    Duas regras de sinal: ponto fora do limite (a semana em si foi anormal) e
    oito semanas seguidas do mesmo lado da linha central (o nível mudou, mesmo
    sem nenhum ponto estourar).
    """
    col = dom.dimensao(por).coluna if por else "'Total'"
    df = con.execute(f"""
        SELECT CAST(date_trunc('week', data) AS DATE) AS semana,
               {col} AS segmento,
               COUNT(*) AS n, SUM(1 - no_prazo) AS fora
          FROM fato
         WHERE data BETWEEN DATE '{inicio}' AND DATE '{fim}'
               {_extra(dom, filtros)}
         GROUP BY 1, 2 ORDER BY 2, 1
    """).fetchdf()
    if df.empty:
        return df
    df["semana"] = pd.to_datetime(df["semana"])
    df["segmento"] = df["segmento"].astype(str)
    df["p"] = df["fora"] / df["n"]
    tot = df.groupby("segmento")[["fora", "n"]].transform("sum")
    df["p_bar"] = tot["fora"] / tot["n"]
    sd = (df["p_bar"] * (1 - df["p_bar"]) / df["n"]) ** 0.5
    df["lsc"] = (df["p_bar"] + 3 * sd).clip(upper=1.0)
    df["lic"] = (df["p_bar"] - 3 * sd).clip(lower=0.0)
    df["acima"] = df["p"] > df["lsc"]
    df["abaixo"] = df["p"] < df["lic"]

    # Sequência de 8 do mesmo lado: marca a oitava semana em diante, com o
    # lado (+1 acima da média, -1 abaixo). Abaixo também é mudança de nível --
    # a operação melhorou, ou a promessa ficou folgada demais --, mas não é
    # alarme, e a leitura trata os dois lados de forma diferente.
    def _seq(g: pd.DataFrame) -> pd.Series:
        lado = ((g["p"] > g["p_bar"]).astype(int)
                - (g["p"] < g["p_bar"]).astype(int))
        bloco = (lado != lado.shift()).cumsum()
        tam = lado.groupby(bloco).cumcount() + 1
        return lado.where((tam >= 8) & (lado != 0), 0)

    df["sequencia"] = pd.concat(
        [_seq(g) for _, g in df.groupby("segmento")]).reindex(df.index)
    return df


def resumo_controle(c: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por segmento: nível, semanas fora, como está a última."""
    if c.empty:
        return c
    linhas = []
    for seg, g in c.groupby("segmento"):
        g = g.sort_values("semana")
        u = g.iloc[-1]
        acima = g[g["acima"]]
        linhas.append({
            "segmento": seg,
            "pedidos": int(g["n"].sum()),
            "p_bar": float(g["p_bar"].iloc[0]),
            "semanas": len(g),
            "semanas_acima": int(g["acima"].sum()),
            "semanas_abaixo": int(g["abaixo"].sum()),
            "ultima_semana": u["semana"],
            "p_ultima": float(u["p"]),
            "lsc_ultima": float(u["lsc"]),
            "ultima_acima": bool(u["acima"]),
            "ultima_sequencia": int(u["sequencia"]),
            "pior_semana": (acima.sort_values("p").iloc[-1]["semana"]
                            if not acima.empty else None),
            "p_pior": (float(acima["p"].max()) if not acima.empty
                       else float("nan")),
        })
    out = pd.DataFrame(linhas)
    return out.sort_values(["ultima_acima", "semanas_acima", "pedidos"],
                           ascending=[False, False, False])


def ultimo_domingo(ref: date) -> date:
    """Fim da última semana completa (segunda a domingo) até `ref`."""
    return ref if ref.weekday() == 6 else ref - timedelta(days=ref.weekday() + 1)


def semana_da_malha(con, dom, ref: date, filtros: Optional[Filtros] = None,
                    dmin: Optional[date] = None, por: str = "regiao_destino"
                    ) -> dict:
    """
    A pergunta de toda segunda-feira: a última semana fechada saiu do
    controle? E se saiu, quem puxou?

    Lê o p-chart da malha inteira nas 52 semanas até `ref` e pega a última
    semana COMPLETA (semana pela metade tem pouco pedido e limite largo). Se
    ela passou do limite superior, decompõe o excesso de atraso por
    `por` (região de destino, por padrão): para cada segmento, quantos
    pedidos fora do prazo vieram acima do que o próprio nível dele (p̄ do
    segmento) previa, sobre o total da semana. A soma dessas parcelas é o
    excesso da malha; a maior é quem puxou.
    """
    fim_sem = ultimo_domingo(ref)
    ini = fim_sem - timedelta(weeks=SEMANAS_CONTROLE) + timedelta(days=1)
    if dmin:
        ini = max(ini, dmin)
    malha = controle(con, dom, ini, fim_sem, filtros, por=None)
    if malha.empty:
        return {}
    u = malha.sort_values("semana").iloc[-1]
    out = {"semana": u["semana"].date(), "p": float(u["p"]),
           "p_bar": float(u["p_bar"]), "lsc": float(u["lsc"]),
           "n": int(u["n"]), "acima": bool(u["acima"]),
           "abaixo": bool(u["abaixo"]),
           "semanas_acima_8": int(malha.sort_values("semana")
                                  .tail(8)["acima"].sum()),
           "puxou": None, "contribuicoes": pd.DataFrame()}

    seg = controle(con, dom, ini, fim_sem, filtros, por=por)
    if seg.empty:
        return out
    s = seg[seg["semana"] == u["semana"]].copy()
    s["excesso"] = (s["fora"] - s["n"] * s["p_bar"]) / u["n"]
    s = s.sort_values("excesso", ascending=False)
    out["contribuicoes"] = s[["segmento", "n", "fora", "p", "p_bar",
                              "excesso", "acima"]].reset_index(drop=True)
    total = float(s["excesso"].clip(lower=0).sum())
    if total > 0:
        t = s.iloc[0]
        out["puxou"] = {"segmento": t["segmento"], "p": float(t["p"]),
                        "p_bar": float(t["p_bar"]),
                        "excesso_pp": float(t["excesso"]),
                        "parte": float(t["excesso"]) / total,
                        "acima": bool(t["acima"])}
    return out


# --------------------------------------------------------------------------- #
# Um pedido
# --------------------------------------------------------------------------- #

def achar_pedido(con, codigo: str) -> pd.DataFrame:
    cod = "".join(ch for ch in codigo.lower() if ch in "0123456789abcdef")
    if len(cod) < 6:
        return pd.DataFrame()
    return con.execute(f"""
        SELECT * FROM fato WHERE order_id LIKE '{cod}%' LIMIT 5
    """).fetchdf()
