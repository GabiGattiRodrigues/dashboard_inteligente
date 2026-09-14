"""
Tabelas auxiliares do domínio de PLD.

O fato do motor é o alerta. O dossiê precisa de mais três coisas que não cabem
numa linha de alerta — a movimentação diária do cliente, as contrapartes e o
histórico do ciclo de checagem — e a calibração precisa do máximo mensal de
cada indicador. Tudo sai do mesmo job (scripts/build_pld.py) e é lido aqui.
"""

from __future__ import annotations

import functools
from datetime import date
from pathlib import Path

import pandas as pd

from ..dados import PASTA_DADOS


@functools.lru_cache(maxsize=8)
def _ler(nome: str, pasta: str = str(PASTA_DADOS)) -> pd.DataFrame:
    caminho = Path(pasta) / nome
    if not caminho.exists():
        raise FileNotFoundError(
            f"Falta {caminho}. Rode `python scripts/build_pld.py`.")
    df = pd.read_parquet(caminho)
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"]).dt.date
    return df


def evidencias() -> pd.DataFrame:
    return _ler("pld_evidencias.parquet")


def contrapartes() -> pd.DataFrame:
    return _ler("pld_contrapartes.parquet")


def calibracao() -> pd.DataFrame:
    return _ler("pld_calibracao.parquet")


def indicadores() -> pd.DataFrame:
    """Percentis do indicador de cada regra, por mês, na população avaliada."""
    return _ler("pld_indicadores.parquet")


def comportamento() -> pd.DataFrame:
    """Sinais brutos por mês: Pix, POS, recargas, contas — antes do alerta."""
    return _ler("pld_comportamento.parquet")


def ciclo() -> pd.DataFrame:
    return _ler("pld_ciclo.parquet")


def data_base() -> date:
    """
    A data-base da operação simulada: o último dia processado pelo job.

    Não é o último dia com alerta. Num dia sem alerta selecionado a fila ainda
    anda — a analista decide casos antigos —, e usar a última data de alerta
    como "hoje" faria a fila desta aba divergir do "em aberto" do motor.
    """
    return max(ciclo()["data"])


def referencia(fim: date, dmax: date) -> date:
    """A data da fila para um fim de período escolhido na barra lateral."""
    return data_base() if fim >= dmax else fim
