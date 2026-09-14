"""
O dossiê de um cliente e o rascunho de parecer da Ravena.

A Circular 3.978 pede que toda análise seja formalizada em dossiê, haja ou não
comunicação (art. 43, § 2º). Na prática a analista gasta boa parte do tempo
montando o mesmo esqueleto — quem é o cliente, o que disparou, quanto, com
quem, qual o enquadramento, quais os prazos — antes de chegar à parte que só
ela pode fazer, que é julgar.

Este módulo monta o esqueleto. Três regras que ele não quebra:

1. **Nenhum número que não esteja nos dados.** O texto é gerado a partir das
   evidências dos alertas e das tabelas do job. Com chave de API, o modelo
   reescreve a prosa em cima destes mesmos fatos; ele não acrescenta valor.
2. **Nenhuma decisão.** A seção final é uma leitura dos sinais e uma lista de
   verificações, nunca "comunicar" ou "descartar". A norma põe a decisão na
   instituição, e quem assina é a analista.
3. **Nenhuma acusação.** O vocabulário é de indício ("a movimentação é
   incompatível com a renda declarada"), não de culpa ("o cliente lava
   dinheiro").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import duckdb
import pandas as pd

from ..semantica import Dominio
from . import dados as pld_dados
from .calendario import PRAZO_ANALISE_DIAS, prazo_analise
from .fila import comunicados_ate, fatores, prioridade
from .normas import citar
from .regras import REGRAS

VERIFICAR = {
    "R01": "Pedir comprovação da origem dos recursos e checar se a renda "
           "declarada está desatualizada.",
    "R02": "Verificar se os pagadores têm relação entre si e para onde foi o "
           "dinheiro — destino repetido em outras contas é o sinal forte.",
    "R03": "Reconstituir o valor total que se queria transferir e entender por "
           "que foi dividido.",
    "R04": "Checar troca recente de celular, e-mail ou titularidade antes do "
           "aumento de movimentação.",
    "R05": "Confrontar o recebido com o faturamento e o porte declarados no "
           "credenciamento; ver de quais empresas vêm os cartões.",
    "R06": "Confirmar o horário de funcionamento e se as transações noturnas "
           "se repetem nos mesmos cartões.",
    "R07": "Confirmar o quadro real de colaboradores e o faturamento, e onde o "
           "saldo carregado está sendo gasto.",
    "R08": "Verificar o vínculo real dos titulares com a empresa e a "
           "validação de documento das contas do mesmo lote.",
    "R09": "Aplicar a diligência reforçada de PEP: origem dos recursos e "
           "relação com as contrapartes.",
    "R10": "Atualizar o cadastro. Se o titular faleceu e a conta movimenta, "
           "identificar quem está operando.",
}


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def _data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


@dataclass
class Dossie:
    cliente_id: str
    codigo: str
    ref: date
    cabecalho: dict
    abertos: pd.DataFrame
    historico: pd.DataFrame
    contrapartes: pd.DataFrame
    serie: pd.DataFrame
    fatores: list[tuple[str, float]]
    prioridade: float
    prazo_final: Optional[date]
    dias_para_prazo: Optional[int]
    reincidente: bool
    leitura: list[str] = field(default_factory=list)
    texto: str = ""


def cliente_por_codigo(con: duckdb.DuckDBPyConnection, codigo: str
                       ) -> Optional[str]:
    cod = codigo.strip().upper().replace(" ", "-")
    if "-" not in cod and len(cod) > 1:
        cod = f"{cod[0]}-{cod[1:]}"
    r = con.execute("SELECT DISTINCT cliente_id FROM fato WHERE codigo = ?",
                    [cod]).fetchone()
    return r[0] if r else None


def montar(con: duckdb.DuckDBPyConnection, dom: Dominio, cliente_id: str,
           ref: date) -> Optional[Dossie]:
    todos = con.execute(
        "SELECT * FROM fato WHERE cliente_id = ? AND data <= ? ORDER BY data",
        [cliente_id, ref]).fetchdf()
    if todos.empty:
        return None
    for c in ("data", "data_decisao", "data_comunicacao"):
        todos[c] = pd.to_datetime(todos[c]).dt.date
    aberto = todos["data_decisao"].isna() | (
        todos["data_decisao"].map(lambda x: x is not None and x == x and x > ref))
    abertos = todos[aberto].copy()
    historico = todos[~aberto].copy()

    p0 = todos.iloc[0]
    cab = {"Código": p0["codigo"], "Documento": p0["doc_mascarado"],
           "Tipo": p0["tipo_cliente"], "Segmento": p0["segmento"],
           "UF": p0["uf"], "Área": p0["area"],
           "Risco cadastral": p0["faixa_risco"], "PEP": p0["pep"]}

    reinc = cliente_id in comunicados_ate(con, ref)
    ids = sorted(set(abertos["regra_id"]))
    valor = float(abertos["valor_envolvido"].sum())
    fat = fatores(ids, valor, p0["faixa_risco"], p0["pep"] == "PEP",
                  p0["area"] == "Fronteira", reinc) if ids else []
    prio = prioridade(ids, valor, p0["faixa_risco"], p0["pep"] == "PEP",
                      p0["area"] == "Fronteira", reinc) if ids else 0.0

    prazo = prazo_analise(min(abertos["data"])) if not abertos.empty else None
    faltam = (prazo - ref).days if prazo else None

    cp = pld_dados.contrapartes()
    cp = cp[cp["cliente_id"] == cliente_id].sort_values("valor", ascending=False)
    ev = pld_dados.evidencias()
    ev = ev[(ev["cliente_id"] == cliente_id) & (ev["data"] <= ref)]

    d = Dossie(cliente_id=cliente_id, codigo=p0["codigo"], ref=ref,
               cabecalho=cab, abertos=abertos, historico=historico,
               contrapartes=cp, serie=ev, fatores=fat, prioridade=prio,
               prazo_final=prazo, dias_para_prazo=faltam, reincidente=reinc)
    d.leitura = _leitura(d)
    d.texto = _texto(d)
    return d


def _leitura(d: Dossie) -> list[str]:
    """Os sinais em conjunto — sem decidir por ninguém."""
    ids = sorted(set(d.abertos["regra_id"]))
    compartilhadas = d.contrapartes[d.contrapartes["compartilhada"] > 0]
    sinais = []
    if len(ids) > 1:
        sinais.append(f"{len(ids)} regras independentes abertas ao mesmo tempo "
                      f"({', '.join(ids)})")
    if not compartilhadas.empty:
        maior = int(compartilhadas["compartilhada"].max())
        sinais.append(f"contraparte que também aparece em {maior} outro(s) "
                      f"cliente(s) com alerta")
    if d.reincidente:
        sinais.append("cliente já comunicado ao Coaf anteriormente")
    if d.cabecalho["PEP"] == "PEP":
        sinais.append("titular qualificado como PEP")
    if d.cabecalho["Área"] == "Fronteira":
        sinais.append("operação em região de fronteira")

    if not ids:
        return ["Não há alerta aberto para este cliente nesta data."]
    if len(sinais) >= 2:
        return [
            "**Os sinais convergem:** " + "; ".join(sinais) + ".",
            "Indícios independentes apontando para o mesmo lugar sustentam "
            "aprofundar a análise e avaliar a comunicação. A decisão é da "
            "analista.",
        ]
    if sinais:
        return [
            "**Há um sinal além da regra:** " + sinais[0] + ".",
            "Vale cumprir as verificações abaixo antes de concluir. A decisão "
            "é da analista.",
        ]
    so_volume = all(REGRAS[r].tipo == "Volumétrica" for r in ids)
    return [
        "**Sinal isolado.** " + (
            "É uma regra volumétrica, sem outro indício no cliente — o "
            "desfecho mais comum é o descarte com a origem comprovada."
            if so_volume else
            "Uma regra só, sem contraparte compartilhada nem histórico."),
        "Registre a justificativa no dossiê mesmo que descarte "
        "(Circular 3.978, art. 43, § 2º). A decisão é da analista.",
    ]


def _texto(d: Dossie) -> str:
    c = d.cabecalho
    L = [f"## Dossiê de análise — {d.codigo}",
         f"*Rascunho da Ravena · posição em {_data(d.ref)} · dado simulado*",
         "",
         "### 1. Identificação",
         f"{c['Tipo']} · {c['Documento'].replace('*', chr(92) + '*')} · "
         f"{c['Segmento']} · {c['UF']} "
         f"({c['Área'].lower()}) · risco cadastral {c['Risco cadastral'].lower()}"
         f" · {'PEP' if c['PEP'] == 'PEP' else 'não PEP'}.",
         "",
         "### 2. Operações e situações selecionadas"]
    if d.abertos.empty:
        L.append("Nenhum alerta aberto nesta data.")
    for a in d.abertos.itertuples():
        r = REGRAS[a.regra_id]
        L.append(f"- **{_data(a.data)} · {r.rotulo}.** {a.evidencia} "
                 f"*Enquadramento: {citar(list(r.enquadramento))}; "
                 f"{citar(list(r.base_3978))}.*")

    L += ["", "### 3. Histórico"]
    if d.historico.empty:
        L.append("Primeira seleção deste cliente no monitoramento.")
    else:
        cont = d.historico["decisao"].value_counts()
        partes = [f"{n} {dec.lower()}" for dec, n in cont.items()]
        L.append(f"{len(d.historico)} alerta(s) anterior(es) já analisado(s): "
                 + ", ".join(partes) + ".")
        com = d.historico[d.historico["decisao"] == "Comunicado ao COAF"]
        if not com.empty:
            L.append(f"Última comunicação ao Coaf decidida em "
                     f"{_data(max(com['data_decisao']))}.")

    L += ["", "### 4. Contrapartes relevantes"]
    if d.contrapartes.empty:
        L.append("Sem contraparte registrada para este tipo de cliente.")
    for cp in d.contrapartes.head(4).itertuples():
        frase = (f"- {cp.sentido} {cp.contraparte}: {_brl(cp.valor)} em "
                 f"{int(cp.qtd)} operação(ões)")
        if cp.compartilhada > 0:
            frase += (f" — **a mesma contraparte aparece em "
                      f"{int(cp.compartilhada)} outro(s) cliente(s) com "
                      f"alerta**")
        L.append(frase + ".")

    L += ["", "### 5. Verificações sugeridas"]
    for rid in sorted(set(d.abertos["regra_id"])):
        L.append(f"- {rid}: {VERIFICAR[rid]}")

    L += ["", "### 6. Prazos"]
    if d.prazo_final:
        situacao = (f"faltam {d.dias_para_prazo} dia(s)"
                    if d.dias_para_prazo >= 0 else
                    f"**vencido há {-d.dias_para_prazo} dia(s)**")
        L.append(f"Seleção mais antiga em {_data(min(d.abertos['data']))}; a "
                 f"análise vai até {_data(d.prazo_final)} ({situacao}) — "
                 f"Circular 3.978, art. 43, § 1º, {PRAZO_ANALISE_DIAS} dias "
                 f"corridos.")
    L.append("Se a decisão for comunicar, o envio ao Coaf vai até o dia útil "
             "seguinte ao da decisão (art. 48, § 2º), sem dar ciência ao "
             "cliente (Lei 9.613/1998, art. 11). A análise fica registrada "
             "neste dossiê mesmo sem comunicação (art. 43, § 2º).")

    L += ["", "### 7. Leitura dos sinais"] + d.leitura
    L += ["", "*Este rascunho organiza os fatos; não decide. A conclusão, a "
              "justificativa e a assinatura são da analista.*"]
    return "\n".join(L)
