"""
Constrói a tabela fato do domínio de Logística a partir dos CSVs do Olist.

Grão: PEDIDO. A data da linha é a DATA PROMETIDA ao cliente -- o dia em que o
pedido vence --, e não a data da compra.

Por que a data prometida
------------------------
Em logística a pergunta é "o que venceu hoje e não chegou?". Se a linha
ficasse na data da compra, o pedido de ontem ainda não teria tido tempo de
atrasar, e os últimos dias do painel sairiam sempre bonitos (censura à
direita). Pela data prometida, todo pedido do período já venceu, e o pedido
que nunca chegou entra como atraso -- é o mesmo critério do case da SBF:
travado conta como fora do prazo.

O que é "travado"
-----------------
Pedido com prazo vencido, não entregue e sem nenhum evento novo. A fila de
travados muda a cada dia, então ela não mora aqui como coluna: quem monta a
fila numa data qualquer é `vulcano/logistica/dados.py`, a partir das datas de
cada evento guardadas abaixo. Aqui ficam só as colunas que não dependem da
data de referência.

A régua D+3 / D+7
-----------------
`pend_d3` marca o pedido que ainda não tinha chegado três dias depois do
prometido; `cheg_d3` marca, entre esses, o que chegou depois. A razão entre os
dois é o "ponto de não retorno": de quem passou do D+3, quantos ainda chegam.
É o que diz se vale cobrar a transportadora (ainda chega) ou se já é hora de
falar com o cliente (não chega mais).

Saída: data/fato_logistica.parquet
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_fact import REGIAO, _limpa_categoria  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
OUT = Path(__file__).resolve().parents[1] / "data" / "fato_logistica.parquet"

# Primeiro dia com volume cheio de pedidos vencendo (o Olist começa ralo em
# 2016) e último dia do painel, igual aos outros domínios do Olist.
DATA_INICIO = "2017-02-01"
DATA_FIM = "2018-08-31"

# As seis UFs de origem que concentram ~95% dos pedidos. As outras viram uma
# origem só: um p-chart de UF com 3 pedidos por semana só mostra ruído.
ORIGENS = ["SP", "MG", "PR", "RJ", "SC", "RS"]
OUTRAS = "Outras UFs"

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado",
               "Domingo"]


def _faixa_promessa(d):
    if pd.isna(d):
        return "Não identificado"
    if d <= 10:
        return "Até 10 dias"
    if d <= 20:
        return "11 a 20 dias"
    if d <= 30:
        return "21 a 30 dias"
    return "Mais de 30 dias"


def build() -> pd.DataFrame:
    datas = ["order_purchase_timestamp", "order_approved_at",
             "order_delivered_carrier_date", "order_delivered_customer_date",
             "order_estimated_delivery_date"]
    orders = pd.read_csv(RAW / "olist_orders_dataset.csv", parse_dates=datas)
    items = pd.read_csv(RAW / "olist_order_items_dataset.csv",
                        parse_dates=["shipping_limit_date"])
    products = pd.read_csv(RAW / "olist_products_dataset.csv")
    customers = pd.read_csv(RAW / "olist_customers_dataset.csv")
    sellers = pd.read_csv(RAW / "olist_sellers_dataset.csv")
    reviews = pd.read_csv(RAW / "olist_order_reviews_dataset.csv")

    # Data de corte: o último carimbo da base inteira. É até aqui que se sabe
    # se um pedido chegou -- o que vem depois é desconhecido, não "não chegou".
    corte = max(orders[c].max() for c in datas[:4]).normalize()

    # Cancelado e indisponível saem: não são falha de entrega, são pedido que
    # deixou de existir. Medir prazo neles faria o cancelamento virar atraso.
    o = orders[~orders["order_status"].isin(["canceled", "unavailable"])].copy()

    # --- vendedor e categoria principais (item de maior valor) ---------------
    # 1,3% dos pedidos têm mais de um vendedor. Um pedido é uma entrega só
    # para o cliente, então ele fica com a origem do item que mais pesa.
    it = items.merge(sellers[["seller_id", "seller_state"]], on="seller_id",
                     how="left")
    it = it.merge(products[["product_id", "product_category_name",
                            "product_weight_g"]],
                  on="product_id", how="left")
    principal = (it.sort_values("price", ascending=False)
                   .drop_duplicates("order_id")
                   [["order_id", "seller_id", "seller_state",
                     "product_category_name"]])
    # O prazo que o marketplace dá ao seller para postar: o limite mais cedo
    # entre os itens do pedido. Peso é o do pedido inteiro.
    valor = it.groupby("order_id", as_index=False).agg(
        valor=("price", "sum"), frete=("freight_value", "sum"),
        itens=("order_item_id", "count"),
        limite_postagem=("shipping_limit_date", "min"),
        peso_g=("product_weight_g", "sum"))
    nota = reviews.groupby("order_id", as_index=False)["review_score"].mean()

    df = (o.merge(principal, on="order_id", how="left")
           .merge(valor, on="order_id", how="left")
           .merge(nota, on="order_id", how="left")
           .merge(customers[["customer_id", "customer_state"]],
                  on="customer_id", how="left"))

    df["data"] = df["order_estimated_delivery_date"].dt.normalize()
    df = df[(df["data"] >= DATA_INICIO) & (df["data"] <= DATA_FIM)].copy()
    # Meia dúzia de pedidos não tem item nem vendedor no arquivo: não há de
    # onde saiu a entrega, e uma origem "não identificada" com 5 pedidos e
    # 100% de atraso viraria o pior segmento de todo ranking.
    df = df[df["seller_state"].notna()].copy()

    d_compra = df["order_purchase_timestamp"].dt.normalize()
    d_aprov = df["order_approved_at"].dt.normalize()
    d_post = df["order_delivered_carrier_date"].dt.normalize()
    d_ent = df["order_delivered_customer_date"].dt.normalize()
    prom = df["data"]

    # --- datas de cada evento, para a fila "como estava no dia X" ------------
    df["dt_compra"] = d_compra
    df["dt_aprovacao"] = d_aprov
    df["dt_postagem"] = d_post
    df["dt_entrega"] = d_ent

    # --- dimensões -------------------------------------------------------------
    uf = df["seller_state"]
    df["uf_origem"] = uf.fillna("Não identificado")
    df["origem"] = np.where(uf.isin(ORIGENS), uf, OUTRAS)
    df["regiao_origem"] = uf.map(REGIAO).fillna("Não identificado")
    df["estado_destino"] = df["customer_state"].fillna("Não identificado")
    df["regiao_destino"] = df["customer_state"].map(REGIAO).fillna(
        "Não identificado")
    df["rota"] = np.where(uf == df["customer_state"], "Dentro do estado",
                          "Entre estados")
    df["categoria"] = _limpa_categoria(df["product_category_name"])
    df["dia_semana_compra"] = d_compra.dt.dayofweek.map(
        dict(enumerate(DIAS_SEMANA)))
    df["dias_promessa"] = (prom - d_compra).dt.days.astype(float)
    df["faixa_promessa"] = df["dias_promessa"].apply(_faixa_promessa)

    # --- prazo -----------------------------------------------------------------
    entregue = d_ent.notna()
    no_prazo = entregue & (d_ent <= prom)
    df["entregue"] = entregue.astype(int)
    df["no_prazo"] = no_prazo.astype(int)
    df["nao_entregue"] = (~entregue).astype(int)
    df["atrasou"] = (entregue & ~no_prazo).astype(int)
    atraso_d = (d_ent - prom).dt.days.where(entregue & ~no_prazo)
    df["dias_atraso"] = atraso_d.astype(float)
    df["atraso_grave"] = ((atraso_d > 7) | ~entregue).astype(int)
    df["lead_time"] = (d_ent - d_compra).dt.days.where(entregue).astype(float)
    df["folga"] = (prom - d_ent).dt.days.where(entregue).astype(float)

    df["situacao"] = np.select(
        [no_prazo, entregue & (atraso_d <= 7), entregue],
        ["No prazo", "Atrasou até 7 dias", "Atrasou mais de 7 dias"],
        default="Não entregue")
    # Onde o pedido que nunca chegou parou. É o que separa "cobrar o seller"
    # (não postou) de "cobrar a transportadora" (postou e sumiu).
    df["etapa_parada"] = np.select(
        [entregue, d_post.notna(), d_aprov.notna()],
        ["Entregue", "Em trânsito", "Aguardando postagem"],
        default="Aguardando aprovação")

    # --- quem atrasou: seller ou transporte ----------------------------------
    # O Olist dá a cada item um limite para o seller postar. Se o pedido
    # atrasou e o seller postou depois do limite, o atraso começou no seller;
    # se postou dentro do limite e mesmo assim atrasou, o atraso é do
    # transporte (ou da promessa curta demais para a rota).
    lim = df["limite_postagem"].dt.normalize()
    postou_ok = d_post.notna() & lim.notna() & (d_post <= lim)
    df["postou"] = d_post.notna().astype(int)
    df["seller_no_prazo"] = postou_ok.astype(int)
    df.loc[d_post.isna(), "seller_no_prazo"] = np.nan
    df["d_postagem"] = (d_post - d_aprov).dt.days.where(
        d_post.notna() & d_aprov.notna()).astype(float).clip(lower=0)
    df["d_transito"] = (d_ent - d_post).dt.days.where(
        d_ent.notna() & d_post.notna()).astype(float).clip(lower=0)
    atrasado = ~no_prazo
    df["responsavel_atraso"] = np.select(
        [no_prazo, ~entregue & d_post.isna(), ~entregue,
         atrasado & ~postou_ok, atrasado],
        ["No prazo", "Seller (não postou)", "Transporte (sumiu)",
         "Seller (postou tarde)", "Transporte"],
        default="No prazo")
    df["atraso_seller"] = (atrasado & ~postou_ok).astype(int)
    df["promessa_folgada"] = ((d_ent.notna())
                              & ((prom - d_ent).dt.days >= 10)).astype(int)
    peso = df["peso_g"] / 1000
    df["peso_kg"] = peso
    df["porte"] = np.select([peso.isna(), peso <= 1, peso <= 5, peso <= 15],
                            ["Não identificado", "Leve (até 1 kg)",
                             "Médio (1 a 5 kg)", "Pesado (5 a 15 kg)"],
                            default="Muito pesado (mais de 15 kg)")
    df["frete"] = df["frete"].fillna(0.0)
    df["valor_produtos"] = df["valor"].fillna(0.0)

    # --- régua D+3 / D+7 -------------------------------------------------------
    # Pendente no D+k = não tinha chegado até k dias depois do prometido.
    # Chegou depois = estava pendente e chegou antes do corte da base.
    for k in (3, 7):
        lim = prom + pd.Timedelta(days=k)
        pend = (lim <= corte) & (~entregue | (d_ent > lim))
        df[f"pend_d{k}"] = pend.astype(int)
        df[f"cheg_d{k}"] = (pend & entregue).astype(int)

    df["valor"] = df["valor"].fillna(0.0) + df["frete"].fillna(0.0)
    df["itens"] = df["itens"].fillna(0).astype(int)
    df["nota"] = df["review_score"]
    df["status"] = df["order_status"]
    df["pedido"] = df["order_id"].str[:8]

    fato = df[[
        "data", "order_id", "pedido", "status",
        "dt_compra", "dt_aprovacao", "dt_postagem", "dt_entrega",
        "origem", "uf_origem", "regiao_origem", "estado_destino",
        "regiao_destino", "rota", "categoria", "dia_semana_compra",
        "faixa_promessa", "situacao", "etapa_parada", "seller_id",
        "entregue", "no_prazo", "nao_entregue", "atrasou", "atraso_grave",
        "dias_atraso", "dias_promessa", "lead_time", "folga",
        "pend_d3", "cheg_d3", "pend_d7", "cheg_d7",
        "valor", "itens", "nota",
        "postou", "seller_no_prazo", "d_postagem", "d_transito",
        "responsavel_atraso", "atraso_seller", "promessa_folgada",
        "frete", "valor_produtos", "peso_kg", "porte",
    ]].sort_values(["data", "order_id"]).reset_index(drop=True)
    fato.attrs["corte"] = str(corte.date())
    return fato, corte


if __name__ == "__main__":
    fato, corte = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fato.to_parquet(OUT, index=False, compression="zstd")
    print(f"pedidos: {len(fato):,}")
    print(f"vencimentos: {fato['data'].min().date()} a "
          f"{fato['data'].max().date()}")
    print(f"corte da base (último evento): {corte.date()}")
    print(f"no prazo: {fato['no_prazo'].mean():.1%} | não entregues: "
          f"{fato['nao_entregue'].mean():.2%}")
    print(f"ainda chegam no D+3: {fato.cheg_d3.sum() / fato.pend_d3.sum():.1%}"
          f" | no D+7: {fato.cheg_d7.sum() / fato.pend_d7.sum():.1%}")
    print(f"arquivo: {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
