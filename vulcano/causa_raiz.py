"""
Motor de causa raiz: onde exatamente a métrica se moveu, e por que.

Um gráfico de cascata só vale se as barras somarem a variação total. Aqui elas
somam, por construção, e o resíduo é calculado e exibido em vez de escondido.

Duas contas diferentes, porque são dois tipos de métrica
--------------------------------------------------------

**Métrica aditiva** (receita, itens, frete). A variação total é a soma das
variações dos segmentos:

    ΔM = Σ (x_i,B − x_i,A)

Fecha exatamente. Não há o que decompor além disso.

**Métrica de razão** (ticket médio, taxa de cancelamento, % frete). Aqui mora o
erro mais comum de análise: concluir que "o ticket caiu" quando na verdade
nenhum segmento ficou mais barato -- o que mudou foi *quem comprou*. Escrevendo
a razão como média ponderada, R = Σ w_i · r_i, com peso w_i = d_i/D e taxa
r_i = n_i/d_i, a variação abre em três termos que somam exatamente ΔR:

    ΔR = Σ w_i,A · Δr_i     (efeito taxa: o segmento em si mudou)
       + Σ Δw_i · r_i,A     (efeito mix: mudou a composição)
       + Σ Δw_i · Δr_i      (interação: os dois ao mesmo tempo)

Efeito taxa pede ação no segmento. Efeito mix pede ação na aquisição. São
diagnósticos opostos e a média simples não distingue os dois.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import duckdb
import pandas as pd

from .dados import Filtros, agregar
from .formatacao import moeda, numero, pct, variacao_pct
from .i18n import L, V
from .periodos import Comparacao
from .semantica import Dominio


# Nome em inglês das entidades que as métricas de contagem distinta contam.
ENTIDADES_EN = {"pedido": "order", "cliente": "customer", "contrato": "contract",
                "pessoa": "person", "alerta": "alert", "registro": "record",
                "razao_de_medias": "ratio-of-averages value"}


@dataclass
class Decomposicao:
    dominio: Dominio
    chave_metrica: str
    chave_dimensao: str
    comparacao: Comparacao
    df: pd.DataFrame
    total_a: float
    total_b: float
    delta: float
    residuo: float
    fecha: bool
    eh_razao: bool
    aviso: Optional[str] = None

    @property
    def delta_pct(self) -> Optional[float]:
        return variacao_pct(self.total_b, self.total_a)


def decompor(
    con: duckdb.DuckDBPyConnection,
    dom: Dominio,
    chave_metrica: str,
    chave_dimensao: str,
    comp: Comparacao,
    filtros: Optional[Filtros] = None,
    top_n: int = 10,
) -> Decomposicao:
    m = dom.metrica(chave_metrica)
    d = dom.dimensao(chave_dimensao)
    col = d.coluna

    a = agregar(con, dom, [chave_metrica], comp.anterior.inicio, comp.anterior.fim,
                dims=[chave_dimensao], filtros=filtros)
    b = agregar(con, dom, [chave_metrica], comp.atual.inicio, comp.atual.fim,
                dims=[chave_dimensao], filtros=filtros)

    nc, dc = f"{chave_metrica}__num", f"{chave_metrica}__den"
    a = a[[col, nc, dc]].rename(columns={nc: "num_a", dc: "den_a"})
    b = b[[col, nc, dc]].rename(columns={nc: "num_b", dc: "den_b"})

    df = a.merge(b, on=col, how="outer").fillna(0.0)
    df = df.rename(columns={col: "segmento"})
    df["segmento"] = df["segmento"].astype(str)

    # Totais verdadeiros, medidos SEM quebra por dimensao. Para uma metrica de
    # contagem distinta quebrada por dimensao de item, somar os segmentos
    # superestima o total (o pedido misto entra duas vezes); usar o total real
    # aqui e o que faz a sobreposicao aparecer como residuo, em vez de sumir.
    tot_a = agregar(con, dom, [chave_metrica], comp.anterior.inicio, comp.anterior.fim,
                    filtros=filtros)
    tot_b = agregar(con, dom, [chave_metrica], comp.atual.inicio, comp.atual.fim,
                    filtros=filtros)

    def _v(t, sufixo):
        if t.empty:
            return 0.0
        x = t.iloc[0][f"{chave_metrica}{sufixo}"]
        return float(x) if pd.notna(x) else 0.0

    total_num_a, total_den_a = _v(tot_a, "__num"), _v(tot_a, "__den")
    total_num_b, total_den_b = _v(tot_b, "__num"), _v(tot_b, "__den")

    if m.eh_razao:
        total_a = total_num_a / total_den_a if total_den_a else float("nan")
        total_b = total_num_b / total_den_b if total_den_b else float("nan")

        df["taxa_a"] = df.apply(
            lambda r: r["num_a"] / r["den_a"] if r["den_a"] else 0.0, axis=1)
        df["taxa_b"] = df.apply(
            lambda r: r["num_b"] / r["den_b"] if r["den_b"] else 0.0, axis=1)
        df["peso_a"] = df["den_a"] / total_den_a if total_den_a else 0.0
        df["peso_b"] = df["den_b"] / total_den_b if total_den_b else 0.0

        d_taxa = df["taxa_b"] - df["taxa_a"]
        d_peso = df["peso_b"] - df["peso_a"]

        df["efeito_taxa"] = df["peso_a"] * d_taxa
        df["efeito_mix"] = d_peso * df["taxa_a"]
        df["interacao"] = d_peso * d_taxa
        df["contribuicao"] = df["efeito_taxa"] + df["efeito_mix"] + df["interacao"]
        df["valor_a"], df["valor_b"] = df["taxa_a"], df["taxa_b"]
    else:
        total_a, total_b = total_num_a, total_num_b
        df["valor_a"], df["valor_b"] = df["num_a"], df["num_b"]
        df["contribuicao"] = df["num_b"] - df["num_a"]
        df["efeito_taxa"] = df["contribuicao"]
        df["efeito_mix"] = 0.0
        df["interacao"] = 0.0
        df["peso_a"] = df["num_a"] / total_num_a if total_num_a else 0.0
        df["peso_b"] = df["num_b"] / total_num_b if total_num_b else 0.0

    delta = total_b - total_a
    residuo = float(delta - df["contribuicao"].sum())

    fecha = dom.decomposicao_fecha(chave_metrica, chave_dimensao)
    aviso = None
    if not fecha:
        entidade = m.entidade or "registro"
        alt_dims = [x.rotulo.lower() for x in dom.dimensoes.values()
                    if entidade in x.unica_por][:3]
        alt_mets = [x.rotulo.lower() for x in dom.metricas.values()
                    if x.num_aditivo][:3]
        ent_en = ENTIDADES_EN.get(entidade, entidade)
        aviso = L((
            f"**{m.rotulo}** conta {entidade}s distintos, e um mesmo "
            f"{entidade} pode aparecer em mais de um valor de "
            f"**{d.rotulo.lower()}** — então ele entra em mais de um segmento e "
            f"a soma das barras não reconstrói o total. O resíduo abaixo mede "
            f"exatamente essa sobreposição: ele está exposto, não redistribuído "
            f"entre as barras. Para uma decomposição que fecha, use uma "
            f"dimensão que seja única por {entidade}"
            + (f" ({', '.join(alt_dims)})" if alt_dims else "")
            + (f", ou uma métrica aditiva como {', '.join(alt_mets)}."
               if alt_mets else ".")
        ), (
            f"**{m.rotulo}** counts distinct {ent_en}s, and the same "
            f"{ent_en} can show up under more than one value of "
            f"**{d.rotulo.lower()}** — so it enters more than one segment and "
            f"the bars don't add up to the total. The residual below measures "
            f"exactly that overlap: it is exposed, not spread across the "
            f"bars. For a decomposition that closes, use a dimension that is "
            f"unique per {ent_en}"
            + (f" ({', '.join(alt_dims)})" if alt_dims else "")
            + (f", or an additive metric such as {', '.join(alt_mets)}."
               if alt_mets else ".")
        ))

    df["contrib_abs"] = df["contribuicao"].abs()
    df = df.sort_values("contrib_abs", ascending=False).reset_index(drop=True)
    df["share_da_variacao"] = (
        df["contribuicao"] / delta if delta not in (0,) else float("nan")
    )

    if len(df) > top_n:
        cabeca = df.head(top_n).copy()
        cauda = df.iloc[top_n:]
        outros = {
            "segmento": f"Outros ({len(cauda)} segmentos)",
            "num_a": cauda["num_a"].sum(), "num_b": cauda["num_b"].sum(),
            "den_a": cauda["den_a"].sum(), "den_b": cauda["den_b"].sum(),
            "valor_a": float("nan"), "valor_b": float("nan"),
            "efeito_taxa": cauda["efeito_taxa"].sum(),
            "efeito_mix": cauda["efeito_mix"].sum(),
            "interacao": cauda["interacao"].sum(),
            "contribuicao": cauda["contribuicao"].sum(),
            "peso_a": cauda["peso_a"].sum(), "peso_b": cauda["peso_b"].sum(),
            "contrib_abs": abs(cauda["contribuicao"].sum()),
            "share_da_variacao": (
                cauda["contribuicao"].sum() / delta if delta else float("nan")),
        }
        df = pd.concat([cabeca, pd.DataFrame([outros])], ignore_index=True)

    return Decomposicao(
        dominio=dom, chave_metrica=chave_metrica, chave_dimensao=chave_dimensao,
        comparacao=comp, df=df, total_a=float(total_a), total_b=float(total_b),
        delta=float(delta), residuo=residuo, fecha=fecha,
        eh_razao=m.eh_razao, aviso=aviso,
    )


# --------------------------------------------------------------------------- #
# Explicacao em portugues, com a conta na mao
# --------------------------------------------------------------------------- #

def explicar(dec: Decomposicao, quantos: int = 3) -> list[str]:
    """Traduz a decomposição em frases que mostram a aritmética, não só o
    resultado. A pessoa tem de conseguir refazer a conta no papel."""
    m = dec.dominio.metrica(dec.chave_metrica)
    d = dec.dominio.dimensao(dec.chave_dimensao)
    linhas: list[str] = []

    linhas.append(L(
        f"**{m.rotulo}** {'subiu' if dec.delta > 0 else 'caiu'} de "
        f"{numero(dec.total_a, m)} para "
        f"{numero(dec.total_b, m)} — variação de {numero(dec.delta, m, sinal=True)} "
        f"({pct(dec.delta_pct)}), comparando {dec.comparacao.atual} contra "
        f"{dec.comparacao.anterior}.",
        f"**{m.rotulo}** {'rose' if dec.delta > 0 else 'fell'} from "
        f"{numero(dec.total_a, m)} to {numero(dec.total_b, m)} — a change of "
        f"{numero(dec.delta, m, sinal=True)} ({pct(dec.delta_pct)}), comparing "
        f"{dec.comparacao.atual} against {dec.comparacao.anterior}."
    ))

    reais = dec.df[~dec.df["segmento"].str.startswith("Outros (")]
    topo = reais.head(quantos)

    for _, r in topo.iterrows():
        contrib, share = r["contribuicao"], r["share_da_variacao"]
        if abs(contrib) < 1e-12:
            continue
        seg = V(r["segmento"])
        va, vb = numero(r['valor_a'], m), numero(r['valor_b'], m)
        pa, pb = (pct(r['peso_a'], 1, sinal=False),
                  pct(r['peso_b'], 1, sinal=False))
        cab = L(
            f"**{seg}** {'puxou para baixo' if contrib < 0 else 'puxou para cima'} "
            f"{numero(abs(contrib), m)} "
            f"— {pct(abs(share), 0, sinal=False)} de toda a variação.",
            f"**{seg}** {'pulled down' if contrib < 0 else 'pulled up'} "
            f"{numero(abs(contrib), m)} "
            f"— {pct(abs(share), 0, sinal=False)} of the whole change."
        )

        if dec.eh_razao:
            partes = []
            if abs(r["efeito_taxa"]) > 1e-12:
                et = numero(r['efeito_taxa'], m, sinal=True)
                dif = numero(r['valor_b'] - r['valor_a'], m, sinal=True)
                partes.append(L(
                    f"*efeito taxa* {et}: dentro do segmento a métrica foi de "
                    f"{va} para {vb}, e o segmento pesava {pa} da base "
                    f"({vb} − {va} = {dif}, vezes {pa})",
                    f"*rate effect* {et}: within the segment the metric went "
                    f"from {va} to {vb}, and the segment weighed {pa} of the "
                    f"base ({vb} − {va} = {dif}, times {pa})"
                ))
            if abs(r["efeito_mix"]) > 1e-12:
                ganhou = r["peso_b"] > r["peso_a"]
                em = numero(r['efeito_mix'], m, sinal=True)
                partes.append(L(
                    f"*efeito mix* {em}: o segmento "
                    f"{'ganhou' if ganhou else 'perdeu'} participação, de {pa} "
                    f"para {pb}, e ele roda a {va} contra "
                    f"{numero(dec.total_a, m)} da média geral",
                    f"*mix effect* {em}: the segment "
                    f"{'gained' if ganhou else 'lost'} share, from {pa} to "
                    f"{pb}, and it runs at {va} against "
                    f"{numero(dec.total_a, m)} for the overall average"
                ))
            if abs(r["interacao"]) > 1e-12:
                ei = numero(r['interacao'], m, sinal=True)
                partes.append(L(
                    f"*interação* {ei}: mudou de tamanho e de patamar ao mesmo "
                    f"tempo",
                    f"*interaction* {ei}: it changed size and level at the "
                    f"same time"
                ))
            if partes:
                cab += L(" Isso se abre em ", " That breaks down into ") \
                    + "; ".join(partes) + "."
        else:
            cn = numero(contrib, m, sinal=True)
            cab += L(f" Saiu de {va} para {vb} ({vb} − {va} = {cn}).",
                     f" It went from {va} to {vb} ({vb} − {va} = {cn}).")
        linhas.append(cab)

    if dec.eh_razao:
        t = dec.df["efeito_taxa"].sum()
        x = dec.df["efeito_mix"].sum()
        i = dec.df["interacao"].sum()
        if abs(t) + abs(x) > 1e-12:
            dominante = "taxa" if abs(t) >= abs(x) else "mix"
            tn, xn, iN = (numero(t, m, sinal=True), numero(x, m, sinal=True),
                          numero(i, m, sinal=True))
            if dominante == "taxa":
                leitura = L("os segmentos em si mudaram de patamar — a ação é "
                            "dentro do segmento",
                            "the segments themselves changed level — the "
                            "action is inside the segment")
            else:
                leitura = L("os segmentos não mudaram tanto; mudou quem comprou "
                            "— a ação é em aquisição e mix, não na operação do "
                            "segmento",
                            "the segments didn't change much; who bought "
                            "changed — the action is in acquisition and mix, "
                            "not in the segment's operations")
            linhas.append(L(
                f"**Leitura geral.** Somando tudo: efeito taxa {tn}, efeito "
                f"mix {xn}, interação {iN}. Predomina o efeito "
                f"**{dominante}** — {leitura}.",
                f"**Overall reading.** Adding it all up: rate effect {tn}, mix "
                f"effect {xn}, interaction {iN}. The "
                f"**{'rate' if dominante == 'taxa' else 'mix'}** effect "
                f"dominates — {leitura}."
            ))

    if abs(dec.residuo) > max(1e-6, abs(dec.delta) * 0.001):
        rn = numero(dec.residuo, m, sinal=True)
        linhas.append(L(
            f"**Resíduo de {rn}** entre a soma dos segmentos e a variação "
            f"total. Vem da sobreposição entre pedido e item descrita acima; "
            f"está exposto de propósito, e não redistribuído.",
            f"**Residual of {rn}** between the sum of the segments and the "
            f"total change. It comes from the overlap described above; it is "
            f"exposed on purpose, not redistributed."
        ))

    return linhas


def dados_cascata(dec: Decomposicao) -> pd.DataFrame:
    """Monta o formato que o gráfico de cascata espera: inicio, contribuições
    ordenadas por tamanho, resíduo (se houver) e fim."""
    m = dec.dominio.metrica(dec.chave_metrica)
    linhas = [{"rotulo": str(dec.comparacao.anterior), "valor": dec.total_a,
               "tipo": "total"}]
    for _, r in dec.df.iterrows():
        if abs(r["contribuicao"]) < 1e-12:
            continue
        linhas.append({"rotulo": V(r["segmento"]),
                       "valor": float(r["contribuicao"]), "tipo": "delta"})
    if abs(dec.residuo) > max(1e-6, abs(dec.delta) * 0.001):
        linhas.append({"rotulo": L("Resíduo (sobreposição)",
                                   "Residual (overlap)"),
                       "valor": dec.residuo, "tipo": "delta"})
    linhas.append({"rotulo": str(dec.comparacao.atual), "valor": dec.total_b,
                   "tipo": "total"})
    return pd.DataFrame(linhas)
