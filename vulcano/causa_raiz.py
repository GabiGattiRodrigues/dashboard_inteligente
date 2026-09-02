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
from .periodos import Comparacao
from .semantica import Dominio


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
        aviso = (
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
        )

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

    direcao = "subiu" if dec.delta > 0 else "caiu"
    linhas.append(
        f"**{m.rotulo}** {direcao} de {numero(dec.total_a, m)} para "
        f"{numero(dec.total_b, m)} — variação de {numero(dec.delta, m, sinal=True)} "
        f"({pct(dec.delta_pct)}), comparando {dec.comparacao.atual} contra "
        f"{dec.comparacao.anterior}."
    )

    reais = dec.df[~dec.df["segmento"].str.startswith("Outros (")]
    topo = reais.head(quantos)

    for _, r in topo.iterrows():
        contrib, share = r["contribuicao"], r["share_da_variacao"]
        if abs(contrib) < 1e-12:
            continue
        papel = "puxou para baixo" if contrib < 0 else "puxou para cima"
        cab = (
            f"**{r['segmento']}** {papel} {numero(abs(contrib), m)} "
            f"— {pct(abs(share), 0, sinal=False)} de toda a variação."
        )

        if dec.eh_razao:
            partes = []
            if abs(r["efeito_taxa"]) > 1e-12:
                partes.append(
                    f"*efeito taxa* {numero(r['efeito_taxa'], m, sinal=True)}: dentro "
                    f"do segmento a métrica foi de {numero(r['valor_a'], m)} para "
                    f"{numero(r['valor_b'], m)}, e o segmento pesava "
                    f"{pct(r['peso_a'], 1, sinal=False)} da base "
                    f"({numero(r['valor_b'], m)} − {numero(r['valor_a'], m)} = "
                    f"{numero(r['valor_b'] - r['valor_a'], m, sinal=True)}, "
                    f"vezes {pct(r['peso_a'], 1, sinal=False)})"
                )
            if abs(r["efeito_mix"]) > 1e-12:
                mov = "ganhou" if r["peso_b"] > r["peso_a"] else "perdeu"
                partes.append(
                    f"*efeito mix* {numero(r['efeito_mix'], m, sinal=True)}: o segmento "
                    f"{mov} participação, de {pct(r['peso_a'], 1, sinal=False)} para "
                    f"{pct(r['peso_b'], 1, sinal=False)}, e ele roda a "
                    f"{numero(r['valor_a'], m)} contra "
                    f"{numero(dec.total_a, m)} da média geral"
                )
            if abs(r["interacao"]) > 1e-12:
                partes.append(
                    f"*interação* {numero(r['interacao'], m, sinal=True)}: mudou de "
                    f"tamanho e de patamar ao mesmo tempo"
                )
            if partes:
                cab += " Isso se abre em " + "; ".join(partes) + "."
        else:
            cab += (
                f" Saiu de {numero(r['valor_a'], m)} para {numero(r['valor_b'], m)} "
                f"({numero(r['valor_b'], m)} − {numero(r['valor_a'], m)} = "
                f"{numero(contrib, m, sinal=True)})."
            )
        linhas.append(cab)

    if dec.eh_razao:
        t = dec.df["efeito_taxa"].sum()
        x = dec.df["efeito_mix"].sum()
        i = dec.df["interacao"].sum()
        if abs(t) + abs(x) > 1e-12:
            dominante = "taxa" if abs(t) >= abs(x) else "mix"
            leitura = (
                "os segmentos em si mudaram de patamar — a ação e dentro do segmento"
                if dominante == "taxa"
                else "os segmentos não mudaram tanto; mudou quem comprou — a ação e "
                     "em aquisição e mix, não na operação do segmento"
            )
            linhas.append(
                f"**Leitura geral.** Somando tudo: efeito taxa "
                f"{numero(t, m, sinal=True)}, efeito mix {numero(x, m, sinal=True)}, "
                f"interação {numero(i, m, sinal=True)}. Predomina o efeito "
                f"**{dominante}** — {leitura}."
            )

    if abs(dec.residuo) > max(1e-6, abs(dec.delta) * 0.001):
        linhas.append(
            f"**Resíduo de {numero(dec.residuo, m, sinal=True)}** entre a soma dos "
            f"segmentos e a variação total. Vem da sobreposição entre pedido e item "
            f"descrita acima; está exposto de proposito, e não redistribuido."
        )

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
        linhas.append({"rotulo": r["segmento"], "valor": float(r["contribuicao"]),
                       "tipo": "delta"})
    if abs(dec.residuo) > max(1e-6, abs(dec.delta) * 0.001):
        linhas.append({"rotulo": "Resíduo (sobreposição)", "valor": dec.residuo,
                       "tipo": "delta"})
    linhas.append({"rotulo": str(dec.comparacao.atual), "valor": dec.total_b,
                   "tipo": "total"})
    return pd.DataFrame(linhas)
