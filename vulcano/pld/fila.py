"""
A fila de análise: quem olhar primeiro, e por quê.

Prioridade explicável, não modelo
---------------------------------
A pergunta da analista às nove da manhã não é "qual a probabilidade de este
cliente ser lavagem" — é "por onde eu começo". Um modelo responderia com um
número que ninguém sabe defender na frente do auditor. Aqui a prioridade é uma
**soma de pontos com fatores nomeados**, e a tela mostra a conta:

    gravidade da regra mais grave aberta     até 35
    valor envolvido (escala log)             até 25
    regras distintas abertas no cliente      até 20   (sinais que se somam)
    classificação de risco do cliente        até 10   (art. 20 da 3.978)
    já comunicado ao Coaf antes                 10   (reincidência)
    PEP                                          5
    região de fronteira                          5   (4.001, XVII, a)

A soma pode passar de 100 e é cortada em 100: cliente reincidente com três
regras abertas é o topo da fila de qualquer jeito.

Dois sinais independentes no mesmo cliente valem mais do que um sinal forte
sozinho — conta de passagem aberta em lote no mesmo celular é outra conversa
do que só a conta de passagem. É o único lugar onde a soma "ganha" do máximo.

Prioridade e prazo andam separados
----------------------------------
Prioridade diz o que é mais grave; prazo diz o que vence primeiro. Juntar os
dois num número só esconde o alerta de gravidade média que vence amanhã. A
tabela mostra as duas colunas, e a fila simulada trabalha primeiro o que está
a menos de 10 dias do prazo, e depois por prioridade.

A posição em qualquer data
--------------------------
Cada alerta guarda a data de seleção e a data da decisão. Um alerta está na
fila em `F` se foi selecionado até `F` e ainda não tinha decisão em `F`. Isso
permite reconstruir a fila de qualquer dia — e é o que garante que o número de
"alertas em aberto" desta aba seja o mesmo número do motor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

import duckdb
import pandas as pd

from ..dados import Filtros
from ..semantica import Dominio
from .calendario import PRAZO_ANALISE_DIAS
from .regras import REGRAS

PONTOS_RISCO = {"Alto": 10, "Médio": 4, "Baixo": 0}
VALOR_PISO, VALOR_TETO = 1_000.0, 500_000.0


def pontos_valor(valor: float) -> float:
    if not valor or valor <= VALOR_PISO:
        return 0.0
    x = (math.log10(valor) - math.log10(VALOR_PISO)) / \
        (math.log10(VALOR_TETO) - math.log10(VALOR_PISO))
    return round(25.0 * min(1.0, max(0.0, x)), 1)


def fatores(regras_abertas: list[str], valor: float, risco: str,
            pep: bool, fronteira: bool,
            reincidente: bool = False) -> list[tuple[str, float]]:
    """A conta da prioridade, fator a fator. A soma é a prioridade."""
    ids = sorted(set(regras_abertas))
    mais_grave = max(ids, key=lambda r: REGRAS[r].gravidade) if ids else None
    from ..i18n import L, V
    saida: list[tuple[str, float]] = []
    if mais_grave:
        saida.append((L("Regra mais grave aberta: ", "Most severe open rule: ")
                      + REGRAS[mais_grave].local.rotulo,
                      float(REGRAS[mais_grave].gravidade)))
    saida.append((L("Valor envolvido", "Amount involved"), pontos_valor(valor)))
    if len(ids) > 1:
        saida.append((L(f"{len(ids)} regras distintas abertas",
                        f"{len(ids)} distinct rules open"),
                      float(min(20, 10 * (len(ids) - 1)))))
    if reincidente:
        saida.append((L("Já comunicado ao Coaf antes",
                        "Previously reported to COAF"), 10.0))
    if PONTOS_RISCO.get(risco, 0):
        saida.append((L(f"Risco cadastral {risco.lower()}",
                        f"{V(risco)} customer risk rating"),
                      float(PONTOS_RISCO[risco])))
    if pep:
        saida.append((L("Pessoa exposta politicamente",
                        "Politically exposed person"), 5.0))
    if fronteira:
        saida.append((L("Região de fronteira", "Border region"), 5.0))
    return saida


def prioridade(regras_abertas: list[str], valor: float, risco: str,
               pep: bool, fronteira: bool, reincidente: bool = False) -> float:
    return round(min(100.0, sum(p for _, p in fatores(
        regras_abertas, valor, risco, pep, fronteira, reincidente))), 1)


def faixa_prioridade(p: float) -> str:
    if p >= 70:
        return "Crítica"
    if p >= 50:
        return "Alta"
    if p >= 30:
        return "Média"
    return "Baixa"


# --------------------------------------------------------------------------- #
# Posição da fila numa data
# --------------------------------------------------------------------------- #

def _onde(dom: Dominio, ate: date, filtros: Optional[Filtros]) -> str:
    clausulas = [f"data <= DATE '{ate}'",
                 f"(data_decisao IS NULL OR data_decisao > DATE '{ate}')"]
    if filtros:
        clausulas += filtros.clausulas(dom)
    return " AND ".join(clausulas)


def alertas_abertos(con: duckdb.DuckDBPyConnection, dom: Dominio, ate: date,
                    filtros: Optional[Filtros] = None) -> pd.DataFrame:
    """Um alerta por linha, na fila em `ate`."""
    df = con.execute(f"""
        SELECT alerta_id, cliente_id, codigo, doc_mascarado, tipo_cliente,
               regra_id, regra, situacao_4001, produto, uf, area, faixa_risco,
               pep, data, valor_envolvido, evidencia, indicador
          FROM fato
         WHERE {_onde(dom, ate, filtros)}
         ORDER BY data
    """).fetchdf()
    if df.empty:
        return df
    df["data"] = pd.to_datetime(df["data"]).dt.date
    df["idade"] = [(ate - d).days for d in df["data"]]
    df["dias_para_prazo"] = PRAZO_ANALISE_DIAS - df["idade"]
    return df


def comunicados_ate(con: duckdb.DuckDBPyConnection, ate: date) -> set[str]:
    """Clientes com comunicação ao Coaf decidida ANTES de `ate`."""
    return {r[0] for r in con.execute(f"""
        SELECT DISTINCT cliente_id FROM fato
         WHERE decisao = 'Comunicado ao COAF'
           AND data_decisao < DATE '{ate}'""").fetchall()}


def posicao(con: duckdb.DuckDBPyConnection, dom: Dominio, ate: date,
            filtros: Optional[Filtros] = None) -> pd.DataFrame:
    """
    A fila agrupada por cliente, já com prioridade e prazo.

    O prazo do cliente é o do alerta MAIS ANTIGO aberto: é ele que estoura
    primeiro, e analisar o cliente resolve todos os alertas dele de uma vez.
    """
    al = alertas_abertos(con, dom, ate, filtros)
    colunas = ["cliente_id", "codigo", "doc_mascarado", "tipo_cliente",
               "prioridade", "faixa", "regras", "enquadramento", "alertas",
               "valor_envolvido", "selecao_mais_antiga", "dias_para_prazo",
               "faixa_risco", "pep", "uf", "area", "reincidente"]
    if al.empty:
        return pd.DataFrame(columns=colunas)

    reincidentes = comunicados_ate(con, ate)
    linhas = []
    for cid, g in al.groupby("cliente_id", sort=False):
        ids = sorted(set(g["regra_id"]))
        risco = g["faixa_risco"].iloc[0]
        pep = g["pep"].iloc[0] == "PEP"
        fronteira = g["area"].iloc[0] == "Fronteira"
        valor = float(g["valor_envolvido"].sum())
        reinc = cid in reincidentes
        p = prioridade(ids, valor, risco, pep, fronteira, reinc)
        linhas.append({
            "cliente_id": cid,
            "codigo": g["codigo"].iloc[0],
            "doc_mascarado": g["doc_mascarado"].iloc[0],
            "tipo_cliente": g["tipo_cliente"].iloc[0],
            "prioridade": p,
            "faixa": faixa_prioridade(p),
            "regras": ", ".join(ids),
            "enquadramento": " · ".join(sorted(set(
                REGRAS[r].rotulo_enquadramento for r in ids))),
            "alertas": len(g),
            "valor_envolvido": valor,
            "selecao_mais_antiga": g["data"].min(),
            "dias_para_prazo": int(g["dias_para_prazo"].min()),
            "faixa_risco": risco,
            "pep": g["pep"].iloc[0],
            "uf": g["uf"].iloc[0],
            "area": g["area"].iloc[0],
            "reincidente": reinc,
        })
    fila = pd.DataFrame(linhas, columns=colunas)
    return fila.sort_values(["prioridade", "dias_para_prazo"],
                            ascending=[False, True]).reset_index(drop=True)


@dataclass
class Resumo:
    clientes: int
    alertas: int
    vencidos: int          # clientes com prazo estourado
    vencem_7d: int         # clientes que vencem em até 7 dias
    criticos: int
    valor: float


def resumir(fila: pd.DataFrame) -> Resumo:
    if fila.empty:
        return Resumo(0, 0, 0, 0, 0, 0.0)
    return Resumo(
        clientes=len(fila),
        alertas=int(fila["alertas"].sum()),
        vencidos=int((fila["dias_para_prazo"] < 0).sum()),
        vencem_7d=int(fila["dias_para_prazo"].between(0, 7).sum()),
        criticos=int((fila["faixa"] == "Crítica").sum()),
        valor=float(fila["valor_envolvido"].sum()),
    )


def idade_da_fila(fila_alertas: pd.DataFrame) -> pd.DataFrame:
    """Alertas abertos por faixa de idade — a régua é o prazo de 45 dias."""
    faixas = [("0 a 15 dias", 0, 15), ("16 a 30 dias", 16, 30),
              ("31 a 45 dias", 31, 45), ("Vencidos (mais de 45)", 46, 10_000)]
    saida = []
    for rotulo, a, b in faixas:
        n = int(fila_alertas["idade"].between(a, b).sum()) \
            if not fila_alertas.empty else 0
        saida.append({"faixa": rotulo, "alertas": n})
    return pd.DataFrame(saida)
