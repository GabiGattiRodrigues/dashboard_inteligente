"""
O que a Ravena responde que nenhum outro agente responde.

O motor genérico cobre as perguntas agregadas — "qual regra tem mais falso
positivo?", "por que os alertas subiram?". Estas três intenções existem porque
em PLD a pergunta mais importante é sobre **alguém**, não sobre um total:

- **fila**    — quem precisa de atenção, em que ordem e com qual prazo;
- **dossie**  — o que se sabe de um cliente específico (T-01160, L-41167…);
- **regra**   — o que uma regra mede, qual o corte e em que trecho da norma
                ela se apoia.

As perguntas sobre a norma em si ("o que diz a 3.978 sobre prazo?") ficam em
`vulcano/conversa.py`, junto dos outros conceitos: são explicação, não dado.

A interpretação é determinística e roda ANTES do planejador com modelo. São
perguntas com marcadores inequívocos — um código de cliente, "fila",
"R02" — e mandar isso para o modelo só abriria espaço para ele escolher uma
métrica agregada no lugar do cliente que a pessoa nomeou.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

import pandas as pd

from ..dados import Filtros, agregar, periodo_disponivel
from .. import i18n
from ..formatacao import numero
from ..i18n import L, V
from . import dados as pld_dados
from . import fila as mod_fila
from . import parecer as mod_parecer
from .en import evidencia as ev_local
from .normas import citar
from .regras import REGRAS

INTENCOES = {
    "fila": "quais clientes precisam de atenção, em que ordem e com qual prazo",
    "dossie": "o dossiê de um cliente específico, pelo código (T-, L- ou E-)",
    "regra": "o que uma regra mede, o corte, as condições e o enquadramento",
}

CODIGO = re.compile(r"\b([tle])\s?-?\s?(\d{4,5})\b", re.I)
REGRA_ID = re.compile(r"\br\s?-?\s?(0?[1-9]|10)\b", re.I)

GATILHOS_FILA = [
    "precisa de atencao", "precisam de atencao", "clientes em atencao",
    "quem olhar", "por onde comeco", "por onde comecar", "fila",
    "prioridade", "priorizar", "quais clientes", "que clientes",
    "quem esta na fila", "vencendo", "vence primeiro", "casos abertos",
    "quem se enquadra", "clientes suspeitos", "quem investigar",
    "quem analisar", "mais urgentes", "prazo vencido", "vencidos",
    # English
    "need attention", "needs attention", "clients to review",
    "who should i look at", "where do i start", "where should i start",
    "queue", "priority", "prioritize", "which clients", "what clients",
    "who is in the queue", "due first", "expiring", "open cases",
    "suspicious clients", "who to investigate", "who to review",
    "most urgent", "overdue cases",
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def interpretar(pergunta: str, ctx) -> Optional[dict[str, Any]]:
    t = _norm(pergunta)
    m = CODIGO.search(t)
    if m:
        largura = 5 if m.group(1).lower() in "tl" else 4
        codigo = f"{m.group(1).upper()}-{int(m.group(2)):0{largura}d}"
        return {"intencao": "dossie", "codigo": codigo}

    r = REGRA_ID.search(t)
    fala_de_metrica = any(x in t for x in ("falso positivo", "quantos",
                                            "quanto", "conversao", "alertas",
                                            "false positive", "how many",
                                            "how much", "conversion", "alerts"))
    if r and not fala_de_metrica:
        return {"intencao": "regra", "regra_id": f"R{int(r.group(1)):02d}"}

    # "como a prioridade é calculada?" é dúvida de conceito, não pedido da
    # fila — quem responde é o verbete em conversa.py
    from ..conversa import pergunta_de_conceito
    if pergunta_de_conceito(pergunta) or re.search(
            r"calculad|como funciona|como e feit|como e montad|calculated|"
            r"how does it work|how is it built", t):
        return None
    if any(g in t for g in GATILHOS_FILA):
        return {"intencao": "fila"}
    return None


def _ref(con, ctx):
    _, dmax = periodo_disponivel(con)
    return pld_dados.referencia(ctx.fim, dmax)


def executar(con, plano: dict[str, Any], ctx):
    dom = ctx.dominio
    fatos: dict[str, Any] = {"dominio": dom.nome, "intencao": plano["intencao"],
                             "aviso_de_dado": L("Domínio com dado SIMULADO.",
                                                "SIMULATED data domain.")}
    linhas: list[str] = []
    tabela = None

    if plano["intencao"] == "fila":
        ref = _ref(con, ctx)
        fl = mod_fila.posicao(con, dom, ref, ctx.filtros)
        res = mod_fila.resumir(fl)
        fatos.update({
            "posicao_em": ref.strftime("%d/%m/%Y"),
            "filtros_ativos": ctx.filtros.resumo(dom),
            "clientes_na_fila": res.clientes, "alertas_abertos": res.alertas,
            "clientes_vencidos": res.vencidos, "vencem_em_7_dias": res.vencem_7d,
            "prioridade_critica": res.criticos,
            "primeiros": [
                {"codigo": r.codigo, "tipo": V(r.tipo_cliente),
                 "prioridade": r.prioridade, "regras": r.regras,
                 "enquadramento_4001": V(r.enquadramento),
                 "valor": numero(r.valor_envolvido, dom.metrica("valor_envolvido")),
                 "dias_para_o_prazo": r.dias_para_prazo,
                 "ja_comunicado_antes": bool(r.reincidente)}
                for r in fl.head(5).itertuples()],
        })
        data_ref = i18n.data(ref)
        if fl.empty:
            linhas.append(L(f"A fila está vazia em {data_ref} com o filtro "
                            f"{ctx.filtros.resumo(dom)}.",
                            f"The queue is empty on {data_ref} with the "
                            f"filter {ctx.filtros.resumo(dom)}."))
            return fatos, None, None, linhas

        linhas.append(L(
            f"Em {data_ref} há **{res.clientes} clientes** na "
            f"fila, com {res.alertas} alertas abertos — {res.criticos} de "
            f"prioridade crítica"
            + (f", **{res.vencidos} já fora do prazo de 45 dias**"
               if res.vencidos else "")
            + (f" e {res.vencem_7d} vencendo em até 7 dias" if res.vencem_7d
               else "") + ".",
            f"On {data_ref} there are **{res.clientes} clients** in the "
            f"queue, with {res.alertas} open alerts — {res.criticos} of "
            f"critical priority"
            + (f", **{res.vencidos} already past the 45-day deadline**"
               if res.vencidos else "")
            + (f" and {res.vencem_7d} due within 7 days" if res.vencem_7d
               else "") + "."))
        topo = fl.head(3)

        def _prazo(r):
            if r.dias_para_prazo < 0:
                return L("vencido", "overdue")
            return L(f"{r.dias_para_prazo} dias de prazo",
                     f"{r.dias_para_prazo} days left")

        def _tipo(r):
            return (V(r.tipo_cliente).split(' (')[0].lower() if i18n.en()
                    else r.tipo_cliente.split(' ')[0].lower())

        linhas.append(L("**Por onde começar:** ", "**Where to start:** ")
                      + "; ".join(
            f"**{r.codigo}** ({_tipo(r)}, "
            + L(f"prioridade {r.prioridade:.0f}", f"priority {r.prioridade:.0f}")
            + f", {r.regras}, {_prazo(r)}"
            + (L(", já comunicado antes", ", previously reported")
               if r.reincidente else "") + ")"
            for r in topo.itertuples()) + ".")
        vencidos = fl[fl["dias_para_prazo"] < 0]
        if not vencidos.empty:
            linhas.append(L(
                f"**O que fazer:** os {len(vencidos)} vencidos vêm antes de "
                f"qualquer prioridade — já é descumprimento do art. 43, § 1º. "
                f"Depois, a ordem da tabela.",
                f"**What to do:** the {len(vencidos)} overdue ones come before "
                f"any priority — that is already non-compliance with art. 43, "
                f"§ 1. After that, the table's order."))
        else:
            cod = topo.iloc[0]['codigo']
            linhas.append(L(
                f"**O que fazer:** abra o dossiê de {cod} — é "
                f"só pedir. A prioridade soma gravidade da regra, valor, sinais "
                f"que se somam e histórico; o prazo anda em coluna separada "
                f"para o caso médio que vence amanhã não sumir.",
                f"**What to do:** open {cod}'s case file — just ask. The "
                f"priority adds up rule severity, amount, signals that stack "
                f"and history; the deadline runs in a separate column so the "
                f"medium case due tomorrow doesn't disappear."))
        topo10 = fl.head(10)
        tabela = pd.DataFrame({
            L("Cliente", "Client"): topo10["codigo"],
            L("Tipo", "Type"): topo10["tipo_cliente"].map(V),
            L("Prioridade", "Priority"): topo10["prioridade"].round(0).astype(int),
            L("Regras", "Rules"): topo10["regras"],
            "4.001": topo10["enquadramento"],
            L("Valor", "Amount"): [mod_parecer._brl(v)
                                   for v in topo10["valor_envolvido"]],
            L("Dias p/ prazo", "Days to deadline"): topo10["dias_para_prazo"]})
        return fatos, tabela, None, linhas

    if plano["intencao"] == "dossie":
        cid = mod_parecer.cliente_por_codigo(con, plano["codigo"])
        if cid is None:
            fatos["resultado"] = L(f"cliente {plano['codigo']} não encontrado",
                                   f"client {plano['codigo']} not found")
            linhas.append(L(
                f"Não encontrei **{plano['codigo']}** entre os clientes com "
                f"alerta. Só quem foi selecionado por alguma regra tem dossiê "
                f"— confira o código na aba Clientes em atenção.",
                f"I couldn't find **{plano['codigo']}** among clients with "
                f"alerts. Only those selected by some rule have a case file — "
                f"check the code in the Clients to review tab."))
            return fatos, None, None, linhas
        d = mod_parecer.montar(con, dom, cid, _ref(con, ctx))
        abertos = d.abertos
        fatos.update({
            "cliente": d.codigo,
            "cabecalho": mod_parecer.rotulos_cabecalho(d.cabecalho),
            "posicao_em": i18n.data(d.ref),
            "alertas_abertos": [
                {"data": i18n.data(a.data), "regra": V(a.regra),
                 "evidencia": ev_local(a.evidencia),
                 "enquadramento": citar(list(REGRAS[a.regra_id].enquadramento))}
                for a in abertos.itertuples()],
            "prioridade": d.prioridade,
            "fatores_da_prioridade": [{"fator": f, "pontos": p}
                                      for f, p in d.fatores],
            "dias_para_o_prazo": d.dias_para_prazo,
            "historico": {V(k): n for k, n in
                          d.historico["decisao"].value_counts().items()},
            "leitura": d.leitura,
        })
        if abertos.empty:
            hist = ", ".join(f"{n} {V(k).lower()}" for k, n in
                             d.historico["decisao"].value_counts().items())
            linhas.append(L(
                f"**{d.codigo}** não tem alerta aberto em "
                f"{i18n.data(d.ref)}. Histórico: {hist or 'nenhum'}.",
                f"**{d.codigo}** has no open alert on {i18n.data(d.ref)}. "
                f"History: {hist or 'none'}."))
            return fatos, None, None, linhas
        c = d.cabecalho
        prazo = (L(f"{d.dias_para_prazo} dias até o prazo.",
                   f"{d.dias_para_prazo} days to the deadline.")
                 if d.dias_para_prazo >= 0 else
                 L(f"**prazo vencido há {-d.dias_para_prazo} dias**.",
                   f"**deadline passed {-d.dias_para_prazo} days ago**."))
        linhas.append(L(
            f"**{d.codigo}** — {c['Tipo']}, "
            f"{c['Segmento'].lower()}, {c['UF']}, risco "
            f"{c['Risco cadastral'].lower()}. Prioridade "
            f"**{d.prioridade:.0f}**, com {len(abertos)} alerta(s) aberto(s) e ",
            f"**{d.codigo}** — {V(c['Tipo'])}, {V(c['Segmento']).lower()}, "
            f"{c['UF']}, {V(c['Risco cadastral']).lower()} risk rating. "
            f"Priority **{d.prioridade:.0f}**, with {len(abertos)} open "
            f"alert(s) and ") + prazo)
        for a in abertos.itertuples():
            linhas.append(f"- **{V(a.regra)}** ({i18n.data_curta(a.data)}): "
                          f"{ev_local(a.evidencia)}")
        linhas += d.leitura
        linhas.append(L("O dossiê completo, com contrapartes, verificações e "
                        "prazos, está na aba **Clientes em atenção**.",
                        "The full case file, with counterparties, checks and "
                        "deadlines, is in the **Clients to review** tab."))
        tabela = pd.DataFrame({
            L("Seleção", "Selected"): [i18n.data(x) for x in abertos["data"]],
            L("Regra", "Rule"): abertos["regra"].map(V),
            "4.001": abertos["situacao_4001"].map(V),
            L("Valor", "Amount"): [mod_parecer._brl(v)
                                   for v in abertos["valor_envolvido"]]})
        return fatos, tabela, None, linhas

    # regra
    r_pt = REGRAS[plano["regra_id"]]
    r = r_pt.local
    # O filtro compara contra o valor gravado no dado, que é o rótulo em
    # português -- a tradução é só para o texto.
    filtros = Filtros({**ctx.filtros.valores, "regra": [r_pt.rotulo]})
    perf = agregar(con, dom, ["alertas", "taxa_falso_positivo",
                              "taxa_comunicacao"], ctx.inicio, ctx.fim,
                   filtros=filtros)
    m_al, m_fp, m_co = (dom.metrica(k) for k in
                        ("alertas", "taxa_falso_positivo", "taxa_comunicacao"))
    v = perf.iloc[0] if not perf.empty else None
    fatos.update({
        "regra": r.rotulo, "indicador": r.indicador,
        "parametro": f"{r.parametro.nome}: {r.parametro.formatar()}",
        "condicoes_fixas": list(r.condicoes), "frequencia": r.frequencia,
        "enquadramento": citar(list(r.enquadramento)),
        "base_na_3978": citar(list(r.base_3978)), "racional": r.racional,
        "alertas_no_periodo": numero(float(v["alertas"]), m_al) if v is not None else "—",
        "falso_positivo": numero(float(v["taxa_falso_positivo"]), m_fp)
        if v is not None and pd.notna(v["taxa_falso_positivo"]) else "—",
        "conversao": numero(float(v["taxa_comunicacao"]), m_co)
        if v is not None and pd.notna(v["taxa_comunicacao"]) else "—",
    })
    linhas.append(L(
        f"**{r.rotulo}** — {r.tipo.lower()}, {r.frequencia.lower()}. "
        f"Mede: {r.indicador.lower()}. Dispara a partir de "
        f"**{r.parametro.formatar()}**, desde que ",
        f"**{r.rotulo}** — {r.tipo.lower()}, {r.frequencia.lower()}. "
        f"Measures: {r.indicador[0].lower() + r.indicador[1:]}. Fires from "
        f"**{r.parametro.formatar()}**, provided that ")
        + "; ".join(r.condicoes) + ".")
    linhas.append(L(f"Enquadramento: {citar(list(r.enquadramento))}; base na "
                    f"{citar(list(r.base_3978))}.",
                    f"Fits: {citar(list(r.enquadramento))}; grounded in "
                    f"{citar(list(r.base_3978))}."))
    linhas.append(r.racional)
    linhas.append(L(
        f"No período da tela: {fatos['alertas_no_periodo']} alertas, "
        f"falso positivo de {fatos['falso_positivo']} e conversão em "
        f"comunicação de {fatos['conversao']} (taxas só de alertas "
        f"maduros). A calibração do corte está na aba **Regras e "
        f"calibração**.",
        f"In the on-screen period: {fatos['alertas_no_periodo']} alerts, a "
        f"false positive rate of {fatos['falso_positivo']} and conversion to "
        f"report of {fatos['conversao']} (rates from mature alerts only). "
        f"Threshold calibration is in the **Rules & calibration** tab."))
    return fatos, None, None, linhas
