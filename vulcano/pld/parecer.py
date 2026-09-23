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
from .. import i18n
from ..i18n import L, V
from .en import evidencia as ev_local, verificar
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
    return i18n.brl(v)


def _data(d: date) -> str:
    return i18n.data(d)


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
    # As CHAVES do cabeçalho ficam em português: o resto do código lê
    # d.cabecalho["PEP"], ["Área"]... Os VALORES também ficam como no dado
    # (a regra compara "Fronteira"); quem mostra traduz com `rotulos_cabecalho`.
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


ROTULOS_CABECALHO_EN = {"Código": "Code", "Documento": "Document",
                        "Tipo": "Type", "Segmento": "Segment", "UF": "State",
                        "Área": "Area", "Risco cadastral": "Risk rating",
                        "PEP": "PEP"}


def rotulos_cabecalho(cab: dict) -> dict:
    """O cabeçalho do dossiê como ele aparece na tela, na língua ativa."""
    if not i18n.en():
        return dict(cab)
    return {ROTULOS_CABECALHO_EN.get(k, k): V(v) for k, v in cab.items()}


def _leitura(d: Dossie) -> list[str]:
    """Os sinais em conjunto — sem decidir por ninguém."""
    ids = sorted(set(d.abertos["regra_id"]))
    compartilhadas = d.contrapartes[d.contrapartes["compartilhada"] > 0]
    sinais = []
    if len(ids) > 1:
        sinais.append(L(f"{len(ids)} regras independentes abertas ao mesmo "
                        f"tempo ({', '.join(ids)})",
                        f"{len(ids)} independent rules open at the same time "
                        f"({', '.join(ids)})"))
    if not compartilhadas.empty:
        maior = int(compartilhadas["compartilhada"].max())
        sinais.append(L(f"contraparte que também aparece em {maior} outro(s) "
                        f"cliente(s) com alerta",
                        f"a counterparty that also shows up in {maior} other "
                        f"client(s) with alerts"))
    if d.reincidente:
        sinais.append(L("cliente já comunicado ao Coaf anteriormente",
                        "client previously reported to COAF"))
    if d.cabecalho["PEP"] == "PEP":
        sinais.append(L("titular qualificado como PEP",
                        "account holder qualified as a PEP"))
    if d.cabecalho["Área"] == "Fronteira":
        sinais.append(L("operação em região de fronteira",
                        "activity in a border region"))

    if not ids:
        return [L("Não há alerta aberto para este cliente nesta data.",
                  "There is no open alert for this client on this date.")]
    decide = L("A decisão é da analista.", "The decision is the analyst's.")
    if len(sinais) >= 2:
        return [
            L("**Os sinais convergem:** ", "**The signals converge:** ")
            + "; ".join(sinais) + ".",
            L("Indícios independentes apontando para o mesmo lugar sustentam "
              "aprofundar a análise e avaliar a comunicação. ",
              "Independent red flags pointing to the same place support "
              "deepening the analysis and assessing a report. ") + decide,
        ]
    if sinais:
        return [
            L("**Há um sinal além da regra:** ",
              "**There is a signal beyond the rule:** ") + sinais[0] + ".",
            L("Vale cumprir as verificações abaixo antes de concluir. ",
              "Worth running the checks below before concluding. ") + decide,
        ]
    so_volume = all(REGRAS[r].tipo == "Volumétrica" for r in ids)
    return [
        L("**Sinal isolado.** ", "**Isolated signal.** ") + (
            L("É uma regra volumétrica, sem outro indício no cliente — o "
              "desfecho mais comum é o descarte com a origem comprovada.",
              "It's a volume-based rule, with no other red flag on the client "
              "— the most common outcome is dismissal once the source of "
              "funds is proven.")
            if so_volume else
            L("Uma regra só, sem contraparte compartilhada nem histórico.",
              "A single rule, with no shared counterparty and no history.")),
        L("Registre a justificativa no dossiê mesmo que descarte "
          "(Circular 3.978, art. 43, § 2º). ",
          "Record the justification in the case file even if you dismiss "
          "(Circular 3,978, art. 43, § 2). ") + decide,
    ]


def _texto(d: Dossie) -> str:
    c = d.cabecalho
    pep = c['PEP'] == 'PEP'
    L_ = [L(f"## Dossiê de análise — {d.codigo}",
            f"## Case file — {d.codigo}"),
          L(f"*Rascunho da Ravena · posição em {_data(d.ref)} · dado simulado*",
            f"*Ravena's draft · position on {_data(d.ref)} · simulated data*"),
          "",
          L("### 1. Identificação", "### 1. Identification"),
          L(f"{c['Tipo']} · {c['Documento'].replace('*', chr(92) + '*')} · "
            f"{c['Segmento']} · {c['UF']} "
            f"({c['Área'].lower()}) · risco cadastral "
            f"{c['Risco cadastral'].lower()} · {'PEP' if pep else 'não PEP'}.",
            f"{V(c['Tipo'])} · {c['Documento'].replace('*', chr(92) + '*')} · "
            f"{V(c['Segmento'])} · {c['UF']} ({V(c['Área']).lower()}) · "
            f"{V(c['Risco cadastral']).lower()} risk rating · "
            f"{'PEP' if pep else 'not PEP'}."),
          "",
          L("### 2. Operações e situações selecionadas",
            "### 2. Selected transactions and situations")]
    if d.abertos.empty:
        L_.append(L("Nenhum alerta aberto nesta data.",
                    "No open alert on this date."))
    for a in d.abertos.itertuples():
        r = REGRAS[a.regra_id].local
        L_.append(f"- **{_data(a.data)} · {r.rotulo}.** {ev_local(a.evidencia)} "
                  + L("*Enquadramento: ", "*Fits: ")
                  + f"{citar(list(r.enquadramento))}; "
                    f"{citar(list(r.base_3978))}.*")

    L_ += ["", L("### 3. Histórico", "### 3. History")]
    if d.historico.empty:
        L_.append(L("Primeira seleção deste cliente no monitoramento.",
                    "First selection of this client in monitoring."))
    else:
        cont = d.historico["decisao"].value_counts()
        partes = [f"{n} {V(dec).lower()}" for dec, n in cont.items()]
        L_.append(L(f"{len(d.historico)} alerta(s) anterior(es) já "
                    f"analisado(s): ",
                    f"{len(d.historico)} previous alert(s) already reviewed: ")
                  + ", ".join(partes) + ".")
        com = d.historico[d.historico["decisao"] == "Comunicado ao COAF"]
        if not com.empty:
            ult = _data(max(com['data_decisao']))
            L_.append(L(f"Última comunicação ao Coaf decidida em {ult}.",
                        f"Last report to COAF decided on {ult}."))

    L_ += ["", L("### 4. Contrapartes relevantes",
                 "### 4. Relevant counterparties")]
    if d.contrapartes.empty:
        L_.append(L("Sem contraparte registrada para este tipo de cliente.",
                    "No counterparty recorded for this client type."))
    for cp in d.contrapartes.head(4).itertuples():
        frase = L(f"- {cp.sentido} {cp.contraparte}: {_brl(cp.valor)} em "
                  f"{int(cp.qtd)} operação(ões)",
                  f"- {V(cp.sentido)} {V(cp.contraparte)}: {_brl(cp.valor)} "
                  f"in {int(cp.qtd)} transaction(s)")
        if cp.compartilhada > 0:
            frase += L(f" — **a mesma contraparte aparece em "
                       f"{int(cp.compartilhada)} outro(s) cliente(s) com "
                       f"alerta**",
                       f" — **the same counterparty shows up in "
                       f"{int(cp.compartilhada)} other client(s) with "
                       f"alerts**")
        L_.append(frase + ".")

    L_ += ["", L("### 5. Verificações sugeridas", "### 5. Suggested checks")]
    for rid in sorted(set(d.abertos["regra_id"])):
        L_.append(f"- {rid}: {verificar(rid, VERIFICAR[rid])}")

    L_ += ["", L("### 6. Prazos", "### 6. Deadlines")]
    if d.prazo_final:
        n = d.dias_para_prazo
        situacao = (L(f"faltam {n} dia(s)", f"{n} day(s) left") if n >= 0 else
                    L(f"**vencido há {-n} dia(s)**", f"**overdue by {-n} day(s)**"))
        ini, fim_ = _data(min(d.abertos['data'])), _data(d.prazo_final)
        L_.append(L(f"Seleção mais antiga em {ini}; a análise vai até {fim_} "
                    f"({situacao}) — Circular 3.978, art. 43, § 1º, "
                    f"{PRAZO_ANALISE_DIAS} dias corridos.",
                    f"Oldest selection on {ini}; the analysis is due by "
                    f"{fim_} ({situacao}) — Circular 3,978, art. 43, § 1, "
                    f"{PRAZO_ANALISE_DIAS} calendar days."))
    L_.append(L("Se a decisão for comunicar, o envio ao Coaf vai até o dia útil "
                "seguinte ao da decisão (art. 48, § 2º), sem dar ciência ao "
                "cliente (Lei 9.613/1998, art. 11). A análise fica registrada "
                "neste dossiê mesmo sem comunicação (art. 43, § 2º).",
                "If the decision is to report, the filing to COAF is due by "
                "the business day after the decision (art. 48, § 2), without "
                "informing the client (Law 9,613/1998, art. 11). The analysis "
                "stays recorded in this case file even without a report "
                "(art. 43, § 2)."))

    L_ += ["", L("### 7. Leitura dos sinais", "### 7. Reading the signals")] \
        + d.leitura
    L_ += ["", L("*Este rascunho organiza os fatos; não decide. A conclusão, a "
                 "justificativa e a assinatura são da analista.*",
                 "*This draft organizes the facts; it doesn't decide. The "
                 "conclusion, the justification and the signature are the "
                 "analyst's.*")]
    return "\n".join(L_)
