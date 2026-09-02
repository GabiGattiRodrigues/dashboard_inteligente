"""
Acesso a dados e montagem de SQL.

Todo número do Vulcano nasce aqui, e nasce como SQL DuckDB montado a partir da
camada semântica do domínio -- nunca a partir de texto livre. O SQL fica
visível na tela porque, num produto que responde em linguagem natural, poder
auditar a conta é requisito.

Para cada métrica saem três colunas: `<m>__num`, `<m>__den` e `<m>`. Numerador
e denominador separados são o que permite decompor uma razão em efeito taxa e
efeito mix em `causa_raiz`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

import duckdb
import pandas as pd

from .semantica import Dominio

PASTA_DADOS = Path(__file__).resolve().parents[1] / "data"


# --------------------------------------------------------------------------- #
# Conexao
# --------------------------------------------------------------------------- #

def conectar(dom: Dominio, pasta: Path | str = PASTA_DADOS) -> duckdb.DuckDBPyConnection:
    caminho = Path(pasta) / dom.arquivo
    if not caminho.exists():
        raise FileNotFoundError(
            f"Falta o arquivo de dados do domínio '{dom.chave}': {caminho}. "
            f"Rode os scripts em scripts/ para gerar."
        )
    con = duckdb.connect(database=":memory:")
    con.execute(
        f"CREATE OR REPLACE VIEW fato AS SELECT * FROM read_parquet('{caminho}')"
    )
    return con


def periodo_disponivel(con: duckdb.DuckDBPyConnection) -> tuple[date, date]:
    a, b = con.execute("SELECT MIN(data), MAX(data) FROM fato").fetchone()
    return (a.date() if hasattr(a, "date") else a,
            b.date() if hasattr(b, "date") else b)


def valores_da_dimensao(
    con: duckdb.DuckDBPyConnection, dom: Dominio, chave: str,
    limite: int | None = None,
) -> list[str]:
    d = dom.dimensao(chave)
    ordem = dom.metricas_painel[0]
    m = dom.metrica(ordem)
    sql = (
        f"SELECT {d.coluna} AS v, {m.num_sql} AS ord FROM fato "
        f"WHERE {d.coluna} IS NOT NULL GROUP BY 1 ORDER BY ord DESC NULLS LAST"
    )
    if limite:
        sql += f" LIMIT {int(limite)}"
    return [str(r[0]) for r in con.execute(sql).fetchall()]


# --------------------------------------------------------------------------- #
# Filtros
# --------------------------------------------------------------------------- #

@dataclass
class Filtros:
    """Seleção da barra lateral. Lista vazia ou ausente = sem restrição."""

    valores: dict[str, list[str]] = field(default_factory=dict)

    def clausulas(self, dom: Dominio) -> list[str]:
        out = []
        for chave, vals in self.valores.items():
            if not vals or chave not in dom.dimensoes:
                continue
            col = dom.dimensao(chave).coluna
            lista = ", ".join("'" + str(v).replace("'", "''") + "'" for v in vals)
            out.append(f"{col} IN ({lista})")
        return out

    def resumo(self, dom: Optional[Dominio] = None) -> str:
        partes = []
        for k, v in self.valores.items():
            if not v:
                continue
            rot = dom.dimensao(k).rotulo if (dom and k in dom.dimensoes) else k
            partes.append(f"{rot}: {', '.join(map(str, v[:3]))}"
                          + (f" +{len(v) - 3}" if len(v) > 3 else ""))
        return " | ".join(partes) if partes else "sem filtro"

    def __bool__(self) -> bool:
        return any(bool(v) for v in self.valores.values())


# --------------------------------------------------------------------------- #
# Motor de agregacao
# --------------------------------------------------------------------------- #

ultimo_sql: str = ""


def _selects(dom: Dominio, chaves: Sequence[str]) -> str:
    partes = []
    for c in chaves:
        m = dom.metrica(c)
        partes.append(f"{m.num_sql} AS {c}__num")
        if m.eh_razao:
            partes.append(f"{m.den_sql} AS {c}__den")
            partes.append(
                f"CASE WHEN ({m.den_sql}) IS NULL OR ({m.den_sql}) = 0 THEN NULL "
                f"ELSE ({m.num_sql}) * 1.0 / ({m.den_sql}) END AS {c}"
            )
        else:
            partes.append(f"CAST(1 AS DOUBLE) AS {c}__den")
            partes.append(f"{m.num_sql} AS {c}")
    return ",\n       ".join(partes)


def montar_sql(
    dom: Dominio, metricas: Sequence[str], inicio: date, fim: date,
    dims: Sequence[str] = (), filtros: Optional[Filtros] = None,
    por_dia: bool = False, ordenar_por: Optional[str] = None,
    limite: Optional[int] = None,
) -> str:
    grupos: list[str] = (["data"] if por_dia else []) + \
                        [dom.dimensao(d).coluna for d in dims]

    onde = [f"data BETWEEN DATE '{inicio}' AND DATE '{fim}'"]
    if filtros:
        onde += filtros.clausulas(dom)

    sel = (", ".join(grupos) + ",\n       ") if grupos else ""
    sql = (f"SELECT {sel}{_selects(dom, metricas)}\n"
           f"  FROM fato\n"
           f" WHERE " + "\n   AND ".join(onde))
    if grupos:
        sql += "\n GROUP BY " + ", ".join(str(i + 1) for i in range(len(grupos)))
    if ordenar_por:
        sql += f"\n ORDER BY {ordenar_por} DESC NULLS LAST"
    elif por_dia:
        sql += "\n ORDER BY data"
    if limite:
        sql += f"\n LIMIT {int(limite)}"
    return sql


def agregar(
    con: duckdb.DuckDBPyConnection, dom: Dominio, metricas: Sequence[str],
    inicio: date, fim: date, dims: Sequence[str] = (),
    filtros: Optional[Filtros] = None, por_dia: bool = False,
    ordenar_por: Optional[str] = None, limite: Optional[int] = None,
) -> pd.DataFrame:
    global ultimo_sql
    sql = montar_sql(dom, metricas, inicio, fim, dims, filtros, por_dia,
                     ordenar_por, limite)
    ultimo_sql = sql
    return con.execute(sql).fetchdf()


def valor_unico(
    con: duckdb.DuckDBPyConnection, dom: Dominio, chave: str,
    inicio: date, fim: date, filtros: Optional[Filtros] = None,
    sufixo: str = "",
) -> float:
    df = agregar(con, dom, [chave], inicio, fim, filtros=filtros)
    if df.empty:
        return float("nan")
    v = df.iloc[0][f"{chave}{sufixo}"]
    return float(v) if pd.notna(v) else float("nan")


def serie_diaria(
    con: duckdb.DuckDBPyConnection, dom: Dominio, metricas: Sequence[str],
    inicio: date, fim: date, filtros: Optional[Filtros] = None,
) -> pd.DataFrame:
    df = agregar(con, dom, metricas, inicio, fim, filtros=filtros, por_dia=True)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"])
    return df


# --------------------------------------------------------------------------- #
# Comparação entre períodos, com base simples ou composta
# --------------------------------------------------------------------------- #

def comparar(
    con: duckdb.DuckDBPyConnection, dom: Dominio, metricas: Sequence[str],
    comp, filtros: Optional[Filtros] = None,
) -> dict[str, dict]:
    """
    Devolve, por métrica, o valor atual e o valor da base de comparação.

    Quando a base é composta (a média dos últimos 3 mesmos dias da semana),
    cada janela é medida separadamente e as MÉDIAS DOS VALORES é que entram na
    conta -- não a razão agregada das janelas somadas.

    A diferença aparece em métrica de razão. Somando três terças e dividindo,
    a terça de maior volume domina o resultado; quem pede "a média das últimas
    três terças" quer as três pesando igual. Pooling responde outra pergunta.
    """
    atual = agregar(con, dom, list(metricas), comp.atual.inicio, comp.atual.fim,
                    filtros=filtros)

    por_janela = [
        agregar(con, dom, list(metricas), j.inicio, j.fim, filtros=filtros)
        for j in comp.anteriores
    ]

    def _v(df, chave):
        if df.empty or pd.isna(df.iloc[0][chave]):
            return float("nan")
        return float(df.iloc[0][chave])

    saida: dict[str, dict] = {}
    for mk in metricas:
        va = _v(atual, mk)
        valores = [_v(df, mk) for df in por_janela]
        validos = [x for x in valores if x == x]
        base = (sum(validos) / len(validos)) if validos else float("nan")

        delta = va - base if (va == va and base == base) else float("nan")
        pct = (delta / abs(base)) if (base == base and base != 0
                                      and delta == delta) else None

        saida[mk] = {
            "atual": va,
            "base": base,
            "delta": delta,
            "delta_pct": pct,
            "por_janela": valores,
            "composta": comp.composta,
        }
    return saida
