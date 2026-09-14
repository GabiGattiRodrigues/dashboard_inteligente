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
from ..formatacao import numero
from . import dados as pld_dados
from . import fila as mod_fila
from . import parecer as mod_parecer
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
                                            "quanto", "conversao", "alertas"))
    if r and not fala_de_metrica:
        return {"intencao": "regra", "regra_id": f"R{int(r.group(1)):02d}"}

    # "como a prioridade é calculada?" é dúvida de conceito, não pedido da
    # fila — quem responde é o verbete em conversa.py
    from ..conversa import pergunta_de_conceito
    if pergunta_de_conceito(pergunta) or re.search(
            r"calculad|como funciona|como e feit|como e montad", t):
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
                             "aviso_de_dado": "Domínio com dado SIMULADO."}
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
                {"codigo": r.codigo, "tipo": r.tipo_cliente,
                 "prioridade": r.prioridade, "regras": r.regras,
                 "enquadramento_4001": r.enquadramento,
                 "valor": numero(r.valor_envolvido, dom.metrica("valor_envolvido")),
                 "dias_para_o_prazo": r.dias_para_prazo,
                 "ja_comunicado_antes": bool(r.reincidente)}
                for r in fl.head(5).itertuples()],
        })
        if fl.empty:
            linhas.append(f"A fila está vazia em {ref.strftime('%d/%m/%Y')} "
                          f"com o filtro {ctx.filtros.resumo(dom)}.")
            return fatos, None, None, linhas

        linhas.append(
            f"Em {ref.strftime('%d/%m/%Y')} há **{res.clientes} clientes** na "
            f"fila, com {res.alertas} alertas abertos — {res.criticos} de "
            f"prioridade crítica"
            + (f", **{res.vencidos} já fora do prazo de 45 dias**"
               if res.vencidos else "")
            + (f" e {res.vencem_7d} vencendo em até 7 dias" if res.vencem_7d
               else "") + ".")
        topo = fl.head(3)
        linhas.append("**Por onde começar:** " + "; ".join(
            f"**{r.codigo}** ({r.tipo_cliente.split(' ')[0].lower()}, "
            f"prioridade {r.prioridade:.0f}, {r.regras}, "
            f"{'vencido' if r.dias_para_prazo < 0 else f'{r.dias_para_prazo} dias de prazo'}"
            + (", já comunicado antes" if r.reincidente else "") + ")"
            for r in topo.itertuples()) + ".")
        vencidos = fl[fl["dias_para_prazo"] < 0]
        if not vencidos.empty:
            linhas.append(
                f"**O que fazer:** os {len(vencidos)} vencidos vêm antes de "
                f"qualquer prioridade — já é descumprimento do art. 43, § 1º. "
                f"Depois, a ordem da tabela.")
        else:
            linhas.append(
                f"**O que fazer:** abra o dossiê de {topo.iloc[0]['codigo']} — é "
                f"só pedir. A prioridade soma gravidade da regra, valor, sinais "
                f"que se somam e histórico; o prazo anda em coluna separada "
                f"para o caso médio que vence amanhã não sumir.")
        topo10 = fl.head(10)
        tabela = pd.DataFrame({
            "Cliente": topo10["codigo"], "Tipo": topo10["tipo_cliente"],
            "Prioridade": topo10["prioridade"].round(0).astype(int),
            "Regras": topo10["regras"], "4.001": topo10["enquadramento"],
            "Valor": [mod_parecer._brl(v) for v in topo10["valor_envolvido"]],
            "Dias p/ prazo": topo10["dias_para_prazo"]})
        return fatos, tabela, None, linhas

    if plano["intencao"] == "dossie":
        cid = mod_parecer.cliente_por_codigo(con, plano["codigo"])
        if cid is None:
            fatos["resultado"] = f"cliente {plano['codigo']} não encontrado"
            linhas.append(
                f"Não encontrei **{plano['codigo']}** entre os clientes com "
                f"alerta. Só quem foi selecionado por alguma regra tem dossiê "
                f"— confira o código na aba Clientes em atenção.")
            return fatos, None, None, linhas
        d = mod_parecer.montar(con, dom, cid, _ref(con, ctx))
        abertos = d.abertos
        fatos.update({
            "cliente": d.codigo, "cabecalho": d.cabecalho,
            "posicao_em": d.ref.strftime("%d/%m/%Y"),
            "alertas_abertos": [
                {"data": a.data.strftime("%d/%m/%Y"), "regra": a.regra,
                 "evidencia": a.evidencia,
                 "enquadramento": citar(list(REGRAS[a.regra_id].enquadramento))}
                for a in abertos.itertuples()],
            "prioridade": d.prioridade,
            "fatores_da_prioridade": [{"fator": f, "pontos": p}
                                      for f, p in d.fatores],
            "dias_para_o_prazo": d.dias_para_prazo,
            "historico": d.historico["decisao"].value_counts().to_dict(),
            "leitura": d.leitura,
        })
        if abertos.empty:
            linhas.append(
                f"**{d.codigo}** não tem alerta aberto em "
                f"{d.ref.strftime('%d/%m/%Y')}. Histórico: "
                + (", ".join(f"{n} {k.lower()}" for k, n in
                             d.historico["decisao"].value_counts().items())
                   or "nenhum") + ".")
            return fatos, None, None, linhas
        linhas.append(
            f"**{d.codigo}** — {d.cabecalho['Tipo']}, "
            f"{d.cabecalho['Segmento'].lower()}, {d.cabecalho['UF']}, risco "
            f"{d.cabecalho['Risco cadastral'].lower()}. Prioridade "
            f"**{d.prioridade:.0f}**, com {len(abertos)} alerta(s) aberto(s) e "
            + (f"{d.dias_para_prazo} dias até o prazo." if d.dias_para_prazo >= 0
               else f"**prazo vencido há {-d.dias_para_prazo} dias**."))
        for a in abertos.itertuples():
            linhas.append(f"- **{a.regra}** ({a.data.strftime('%d/%m')}): "
                          f"{a.evidencia}")
        linhas += d.leitura
        linhas.append("O dossiê completo, com contrapartes, verificações e "
                      "prazos, está na aba **Clientes em atenção**.")
        tabela = pd.DataFrame({
            "Seleção": [x.strftime("%d/%m/%Y") for x in abertos["data"]],
            "Regra": abertos["regra"], "4.001": abertos["situacao_4001"],
            "Valor": [mod_parecer._brl(v) for v in abertos["valor_envolvido"]]})
        return fatos, tabela, None, linhas

    # regra
    r = REGRAS[plano["regra_id"]]
    filtros = Filtros({**ctx.filtros.valores, "regra": [r.rotulo]})
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
    linhas.append(f"**{r.rotulo}** — {r.tipo.lower()}, {r.frequencia.lower()}. "
                  f"Mede: {r.indicador.lower()}. Dispara a partir de "
                  f"**{r.parametro.formatar()}**, desde que "
                  + "; ".join(r.condicoes) + ".")
    linhas.append(f"Enquadramento: {citar(list(r.enquadramento))}; base na "
                  f"{citar(list(r.base_3978))}.")
    linhas.append(r.racional)
    linhas.append(f"No período da tela: {fatos['alertas_no_periodo']} alertas, "
                  f"falso positivo de {fatos['falso_positivo']} e conversão em "
                  f"comunicação de {fatos['conversao']} (taxas só de alertas "
                  f"maduros). A calibração do corte está na aba **Regras e "
                  f"calibração**.")
    return fatos, None, None, linhas
