"""
Constroi a tabela fato do Vulcano a partir dos CSVs brutos do Olist.

Grao: item de pedido (order_id x order_item_id).
Pedidos sem item (cancelados antes do faturamento) sao preservados com
receita/itens zerados, para que a taxa de cancelamento nao fique enviesada.

Saida: data/fato_olist.parquet
"""

from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
OUT = Path(__file__).resolve().parents[1] / "data" / "fato_olist.parquet"

DATA_INICIO = "2017-01-01"
DATA_FIM = "2018-08-31"

REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte",
    "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste",
    "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste",
    "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

PAGAMENTO = {
    "credit_card": "Cartão de crédito",
    "boleto": "Boleto",
    "voucher": "Voucher",
    "debit_card": "Cartão de débito",
    "not_defined": "Não identificado",
}



# Os nomes de categoria do Olist vem sem acento e com underline. Traduzir isso
# uma vez no ETL e melhor do que corrigir na tela: o nome sai certo no grafico,
# na tabela, no filtro e na resposta do agente, porque todos leem a mesma
# coluna. O mapa e por PALAVRA, e nao por categoria inteira, para nao precisar
# manter 74 linhas quando o vocabulario e o mesmo.
ACENTOS_CATEGORIA = {
    "saude": "saúde", "relogios": "relógios", "informatica": "informática",
    "acessorios": "acessórios", "moveis": "móveis", "decoracao": "decoração",
    "domesticas": "domésticas", "jardim": "jardim", "bebes": "bebês",
    "escritorio": "escritório", "eletroportateis": "eletroportáteis",
    "eletronicos": "eletrônicos", "construcao": "construção",
    "malas": "malas", "eletrodomesticos": "eletrodomésticos",
    "industria": "indústria", "comercio": "comércio",
    "climatizacao": "climatização", "audio": "áudio",
    "portateis": "portáteis", "cafe": "café", "servico": "serviço",
    "iluminacao": "iluminação", "seguranca": "segurança",
    "negocios": "negócios", "calcados": "calçados",
    "sinalizacao": "sinalização", "tecnicos": "técnicos",
    "musica": "música", "musicais": "musicais", "natal": "natal",
    "impressao": "impressão", "artigos": "artigos", "colchao": "colchão",
    "servicos": "serviços", "higiene": "higiene", "cine": "cine",
    "pc": "PC", "pcs": "PCs", "cds": "CDs", "dvds": "DVDs",
    "tv": "TV", "la": "la", "area": "área", "video": "vídeo",
}


def _acentua_categoria(nome: str) -> str:
    """
    Acentua palavra a palavra e recapitaliza no fim.

    A ordem importa: o mapa e indexado em minusculas, entao capitalizar antes
    faria "Relogios" virar "relogios presentes" -- perdendo a maiuscula que a
    tela espera. Acentua primeiro, capitaliza depois.
    """
    palavras = [ACENTOS_CATEGORIA.get(w.lower(), w) for w in nome.split()]
    if not palavras:
        return nome
    primeira = palavras[0]
    # Siglas ja vem em caixa alta do mapa (PC, PCs, CDs) e ficam como estao.
    if not primeira.isupper():
        primeira = primeira[0].upper() + primeira[1:]
    return " ".join([primeira] + palavras[1:])


def _limpa_categoria(s: pd.Series) -> pd.Series:
    return (
        s.fillna("Sem categoria")
        .str.replace("_", " ", regex=False)
        .str.strip()
        .str.capitalize()
        .map(_acentua_categoria)
    )


def _faixa_parcelas(n):
    if pd.isna(n) or n <= 1:
        return "À vista"
    if n <= 3:
        return "2 a 3x"
    if n <= 6:
        return "4 a 6x"
    if n <= 12:
        return "7 a 12x"
    return "Acima de 12x"


def _faixa_valor(v):
    """Faixa de preço do item. Os cortes são redondos de propósito: quem lê o
    filtro precisa entender a faixa sem consultar a documentação."""
    if pd.isna(v):
        return "Não identificado"
    if v < 50:
        return "Até R$ 50"
    if v < 100:
        return "R$ 50 a 100"
    if v < 250:
        return "R$ 100 a 250"
    if v < 500:
        return "R$ 250 a 500"
    return "Acima de R$ 500"


DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado",
               "Domingo"]


def _faixa_nota(n):
    if pd.isna(n):
        return "Sem avaliação"
    if n <= 2:
        return "1 a 2 (ruim)"
    if n <= 3:
        return "3 (neutra)"
    return "4 a 5 (boa)"


def build() -> pd.DataFrame:
    orders = pd.read_csv(
        RAW / "olist_orders_dataset.csv",
        parse_dates=[
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    )
    items = pd.read_csv(RAW / "olist_order_items_dataset.csv")
    products = pd.read_csv(RAW / "olist_products_dataset.csv")
    customers = pd.read_csv(RAW / "olist_customers_dataset.csv")
    payments = pd.read_csv(RAW / "olist_order_payments_dataset.csv")
    reviews = pd.read_csv(RAW / "olist_order_reviews_dataset.csv")
    sellers = pd.read_csv(RAW / "olist_sellers_dataset.csv")

    # --- pagamento dominante por pedido (o de maior valor) -------------------
    pag = (
        payments.sort_values("payment_value", ascending=False)
        .drop_duplicates("order_id")
        .loc[:, ["order_id", "payment_type", "payment_installments"]]
    )

    # --- nota media do review por pedido -------------------------------------
    rev = reviews.groupby("order_id", as_index=False)["review_score"].mean()

    # --- monta o fato ---------------------------------------------------------
    df = orders.merge(items, on="order_id", how="left")
    df = df.merge(products[["product_id", "product_category_name"]], on="product_id", how="left")
    # customer_id no Olist e por PEDIDO, nao por pessoa: quem compra duas vezes
    # recebe dois customer_id. Quem identifica a pessoa e customer_unique_id.
    # Usar o primeiro faria "clientes" ser identico a "pedidos" -- uma metrica
    # que parece existir e nao mede nada.
    df = df.merge(
        customers[["customer_id", "customer_unique_id", "customer_state",
                   "customer_city"]],
        on="customer_id", how="left")
    df = df.merge(sellers[["seller_id", "seller_state"]], on="seller_id",
                  how="left")
    df = df.merge(pag, on="order_id", how="left")
    df = df.merge(rev, on="order_id", how="left")

    df["data"] = df["order_purchase_timestamp"].dt.normalize()
    df = df[(df["data"] >= DATA_INICIO) & (df["data"] <= DATA_FIM)].copy()

    df["categoria"] = _limpa_categoria(df["product_category_name"])
    df["estado"] = df["customer_state"].fillna("NA")
    df["regiao"] = df["estado"].map(REGIAO).fillna("Não identificado")
    df["meio_pagamento"] = df["payment_type"].map(PAGAMENTO).fillna("Não identificado")
    df["faixa_parcelas"] = df["payment_installments"].apply(_faixa_parcelas)
    df["status"] = df["order_status"]
    df["cancelado"] = df["order_status"].isin(["canceled", "unavailable"]).astype(int)

    df["receita"] = df["price"].fillna(0.0)
    df["frete"] = df["freight_value"].fillna(0.0)
    df["itens"] = df["order_item_id"].notna().astype(int)

    entrega = (df["order_delivered_customer_date"] - df["order_purchase_timestamp"]).dt.days
    df["dias_entrega"] = entrega
    df["atraso"] = (
        df["order_delivered_customer_date"] > df["order_estimated_delivery_date"]
    ).astype(int)
    df.loc[df["order_delivered_customer_date"].isna(), "atraso"] = pd.NA

    # --- jornada do pedido: quatro eventos, na ordem -------------------------
    #
    # O Olist guarda o carimbo de cada etapa da vida do pedido. Isso e um funil
    # de verdade -- comprou, pagamento aprovou, seller postou, cliente recebeu
    # -- e nao uma metrica de vendas. E o que a area de produto acompanha:
    # onde a jornada trava e quanto tempo cada perna leva.
    df["ev_comprou"] = 1
    df["ev_aprovou"] = df["order_approved_at"].notna().astype(int)
    df["ev_postou"] = df["order_delivered_carrier_date"].notna().astype(int)
    df["ev_entregou"] = df["order_delivered_customer_date"].notna().astype(int)

    # Etapa mais avancada que o pedido alcancou. Vira dimensao: da para
    # perguntar "quem parou na aprovacao vem de qual categoria/estado?".
    def _etapa(r):
        if r["ev_entregou"]:
            return "4. Entregue"
        if r["ev_postou"]:
            return "3. Postado, não entregue"
        if r["ev_aprovou"]:
            return "2. Aprovado, não postado"
        return "1. Criado, não aprovado"

    df["etapa_jornada"] = df.apply(_etapa, axis=1)

    # Tempo de cada perna, em horas para as curtas e dias para as longas.
    df["h_ate_aprovar"] = (
        df["order_approved_at"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 3600.0
    df["d_aprovar_postar"] = (
        df["order_delivered_carrier_date"] - df["order_approved_at"]
    ).dt.total_seconds() / 86400.0
    df["d_postar_entregar"] = (
        df["order_delivered_customer_date"] - df["order_delivered_carrier_date"]
    ).dt.total_seconds() / 86400.0

    # --- colunas de operacao/produto ----------------------------------------
    df["entregue"] = (df["order_status"] == "delivered").astype(int)
    df["dias_aprovacao"] = df["h_ate_aprovar"]          # compatibilidade
    df["avaliado"] = df["review_score"].notna().astype(int)
    df["nota_baixa"] = (df["review_score"] <= 2).astype(float)
    df.loc[df["review_score"].isna(), "nota_baixa"] = pd.NA
    # Folga entre o prazo prometido e o realizado: negativo = entregou atrasado.
    df["folga_prazo"] = (
        df["order_estimated_delivery_date"] - df["order_delivered_customer_date"]
    ).dt.days

    # --- dimensoes derivadas -------------------------------------------------
    #
    # As colunas cruas do Olist dao cinco recortes. Na pratica quem usa o painel
    # quer cruzar por coisas que nao estao no arquivo: e novo ou recorrente? e
    # fim de semana? e pedido caro ou barato? Essas quebras nascem aqui, no ETL,
    # e nao como expressao SQL na camada semantica -- e coluna de verdade, com
    # nome de verdade, que o filtro, o alerta, a cascata e o agente leem igual.

    df["dia_semana"] = pd.Categorical(
        df["data"].dt.dayofweek.map(dict(enumerate(DIAS_SEMANA))),
        categories=DIAS_SEMANA, ordered=True).astype(str)
    df["tipo_dia"] = df["data"].dt.dayofweek.map(
        lambda d: "Fim de semana" if d >= 5 else "Dia útil")

    df["faixa_valor"] = df["receita"].apply(_faixa_valor)
    df["faixa_nota"] = df["review_score"].apply(_faixa_nota)

    # Novo x recorrente: a comparacao e com a PRIMEIRA compra da pessoa em toda
    # a base, nao dentro do periodo filtrado. Recalcular isso por recorte faria
    # o mesmo pedido mudar de rotulo conforme o filtro da barra lateral -- e o
    # numero do agente deixaria de bater com o do grafico.
    primeira = df.groupby("customer_unique_id")["data"].transform("min")
    df["tipo_cliente"] = (df["data"] > primeira).map(
        {True: "Recorrente", False: "Primeira compra"})

    # Entrega: dentro ou fora do prazo prometido. E a dimensao que produto usa
    # para achar de onde vem nota baixa.
    df["cumpriu_prazo"] = "Ainda não entregue"
    entregues = df["order_delivered_customer_date"].notna()
    df.loc[entregues & (df["atraso"] == 1), "cumpriu_prazo"] = "Entregou atrasado"
    df.loc[entregues & (df["atraso"] == 0), "cumpriu_prazo"] = "Entregou no prazo"

    # Envio dentro do proprio estado ou entre estados: a perna logistica mais
    # cara. Sem o dataset de sellers no merge, cai para nao identificado.
    if "seller_state" in df.columns:
        df["rota_envio"] = df.apply(
            lambda r: "Não identificado" if pd.isna(r["seller_state"])
            else ("Dentro do estado" if r["seller_state"] == r["estado"]
                  else "Entre estados"), axis=1)
    else:
        df["rota_envio"] = "Não identificado"

    fato = df[
        [
            "data", "order_id", "customer_unique_id" if "customer_unique_id" in df else "customer_id",
            "categoria", "estado", "regiao", "meio_pagamento", "faixa_parcelas",
            "status", "cancelado", "receita", "frete", "itens",
            "dias_entrega", "atraso", "review_score",
            "entregue", "dias_aprovacao", "avaliado", "nota_baixa", "folga_prazo",
            "ev_comprou", "ev_aprovou", "ev_postou", "ev_entregou",
            "etapa_jornada", "h_ate_aprovar", "d_aprovar_postar",
            "d_postar_entregar",
            "dia_semana", "tipo_dia", "faixa_valor", "faixa_nota",
            "tipo_cliente", "cumpriu_prazo", "rota_envio",
        ]
    ].rename(columns={"customer_id": "cliente_id", "customer_unique_id": "cliente_id"})

    fato = fato.sort_values(["data", "order_id"]).reset_index(drop=True)
    fato = _corta_cauda_de_extracao(fato)
    return fato


def _corta_cauda_de_extracao(fato: pd.DataFrame, piso: float = 0.5) -> pd.DataFrame:
    """
    Remove a cauda incompleta do fim da base.

    O corte da extracao do Olist deixa os ultimos dias com uma fracao dos
    pedidos reais -- de ~250/dia para 1/dia -- e com cancelamento perto de
    100%, porque so o que ja estava resolvido entrou no arquivo. Ler isso como
    queda de vendas seria um erro grosseiro: nao e o negocio caindo, e o
    arquivo acabando.

    A regra e declarada em vez de escolhida a mao: caminhando do fim para tras,
    descarta-se todo dia cujo volume esteja abaixo de `piso` da mediana movel
    de 28 dias, ate encontrar o primeiro dia saudavel. Assim o corte se ajusta
    sozinho se a base for atualizada, e fica auditavel.
    """
    diario = fato.groupby("data")["order_id"].nunique().sort_index()
    if len(diario) < 30:
        return fato

    referencia = diario.rolling(28, min_periods=14).median().shift(1)
    saudavel = diario >= (referencia * piso)

    corte = diario.index[-1]
    for dia in reversed(diario.index):
        if bool(saudavel.get(dia, False)):
            corte = dia
            break

    removidos = int((diario.index > corte).sum())
    if removidos:
        print(
            f"[qualidade] cauda de extracao removida: {removidos} dia(s) apos "
            f"{pd.Timestamp(corte).date()} com volume abaixo de "
            f"{piso:.0%} da mediana movel."
        )
    return fato[fato["data"] <= corte].copy()


if __name__ == "__main__":
    fato = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fato.to_parquet(OUT, index=False, compression="zstd")
    print(f"linhas: {len(fato):,}")
    print(f"periodo: {fato['data'].min().date()} a {fato['data'].max().date()}")
    print(f"pedidos: {fato['order_id'].nunique():,}")
    print(f"receita: R$ {fato['receita'].sum():,.0f}")
    print(f"arquivo: {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")
