"""Domínio de Marketing e CRM, sobre a base pública do Olist."""

from ..semantica import Dimensao, Dominio, Limite, Metrica, indexar

_PEDIDOS = "COUNT(DISTINCT order_id)"

METRICAS = indexar([
    Metrica("receita", "Receita", "SUM(receita)", formato="moeda", grao="fino",
            descricao="Soma do preco dos itens, sem frete."),
    Metrica("pedidos", "Pedidos", _PEDIDOS, formato="inteiro", grao="grosso",
            num_aditivo=False, entidade="pedido",
            descricao="Pedidos distintos no período, pela data de compra."),
    Metrica("itens", "Itens vendidos", "SUM(itens)", formato="inteiro",
            descricao="Quantidade de itens faturados."),
    Metrica("clientes", "Clientes", "COUNT(DISTINCT cliente_id)",
            formato="inteiro", grao="grosso", num_aditivo=False, entidade="cliente",
            descricao="Clientes distintos que compraram no período."),
    Metrica("ticket_medio", "Ticket médio", "SUM(receita)", den_sql=_PEDIDOS,
            formato="moeda", grao="grosso", casas=2,
            formula="Receita ÷ Pedidos",
            descricao="Receita dividida por pedidos distintos."),
    Metrica("receita_por_item", "Receita por item", "SUM(receita)",
            den_sql="SUM(itens)", formato="moeda", casas=2,
            formula="Receita ÷ Itens vendidos",
            descricao="Preco médio do item vendido."),
    Metrica("itens_por_pedido", "Itens por pedido", "SUM(itens)", den_sql=_PEDIDOS,
            formato="decimal", grao="grosso", casas=2,
            formula="Itens vendidos ÷ Pedidos",
            descricao="Quantos itens entram, em média, em cada pedido."),
    Metrica("receita_por_cliente", "Receita por cliente", "SUM(receita)",
            den_sql="COUNT(DISTINCT cliente_id)", formato="moeda", casas=2, grao="grosso",
            formula="Receita ÷ Clientes",
            descricao="Quanto cada cliente comprou, em média, no período."),
    Metrica("frete", "Frete", "SUM(frete)", formato="moeda",
            descricao="Soma do valor de frete cobrado."),
    Metrica("pct_frete", "Frete sobre receita", "SUM(frete)",
            den_sql="SUM(receita)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="Frete ÷ Receita",
            descricao="Peso do frete no valor da venda."),
    Metrica("taxa_cancelamento", "Taxa de cancelamento",
            "COUNT(DISTINCT CASE WHEN cancelado = 1 THEN order_id END)",
            den_sql=_PEDIDOS, formato="percentual", casas=2,
            bom_quando_sobe=False, grao="grosso", num_aditivo=False,
            entidade="pedido",
            formula="Pedidos cancelados ÷ Pedidos",
            descricao="Pedidos cancelados ou indisponíveis sobre o total."),
])

DIMENSOES = indexar([
    Dimensao("categoria", "Categoria", "categoria", nivel="fino", unica_por=(),
             descricao="Categoria do produto comprado."),
    Dimensao("regiao", "Região", "regiao", unica_por=("pedido",),
             descricao="Região do cliente no pedido."),
    Dimensao("estado", "Estado", "estado", unica_por=("pedido",),
                 descricao="UF do cliente no pedido."),
    Dimensao("meio_pagamento", "Meio de pagamento", "meio_pagamento",
             unica_por=("pedido",), descricao="Meio de pagamento de maior valor no pedido."),
    Dimensao("faixa_parcelas", "Parcelamento", "faixa_parcelas",
             unica_por=("pedido",), descricao="Faixa de parcelas do pagamento."),
    # `unica_por` inclui "cliente" só onde a dimensão realmente não muda para a
    # mesma pessoa. Dia da semana e faixa de valor mudam a cada compra, então
    # contar CLIENTES por elas não fecha -- e a cascata mostra o resíduo em vez
    # de fingir que fechou.
    Dimensao("tipo_cliente", "Novo ou recorrente", "tipo_cliente",
             unica_por=("pedido",),
             descricao="Se é a primeira compra da pessoa na base ou uma "
                       "recompra. Vale para toda a base, não para o período "
                       "filtrado — senão o mesmo pedido mudaria de rótulo "
                       "conforme o filtro."),
    Dimensao("faixa_valor", "Faixa de preço do item", "faixa_valor",
             nivel="fino", unica_por=(),
             descricao="Faixa de preço do item comprado."),
    Dimensao("dia_semana", "Dia da semana", "dia_semana",
             unica_por=("pedido",),
             descricao="Dia da semana da compra."),
    Dimensao("tipo_dia", "Dia útil ou fim de semana", "tipo_dia",
             unica_por=("pedido",),
             descricao="Se a compra caiu em dia útil ou fim de semana."),
    Dimensao("status", "Status do pedido", "status",
             unica_por=("pedido",),
             descricao="Situação do pedido no sistema do marketplace."),
])

DOMINIO = Dominio(
    chave="marketing",
    nome="Marketing e CRM",
    subtitulo="Receita, aquisição e comportamento de compra",
    descricao=(
        "Como a receita se forma: quanto entra, de quem, de que categoria e por "
        "que meio de pagamento. É o painel de quem responde por meta de vendas "
        "e por eficiência de canal."
    ),
    fonte=(
        "Brazilian E-Commerce Public Dataset by Olist — 99 mil pedidos reais de "
        "marketplace brasileiro, de jan/2017 a ago/2018."
    ),
    simulado=False,
    arquivo="fato_olist.parquet",
    metricas=METRICAS,
    dimensoes=DIMENSOES,
    metricas_painel=["receita", "pedidos", "ticket_medio", "clientes",
                     "itens_por_pedido", "taxa_cancelamento", "pct_frete",
                     "receita_por_item"],
    dims_filtro=["categoria", "regiao", "estado", "meio_pagamento",
                 "faixa_parcelas", "tipo_cliente", "faixa_valor",
                 "dia_semana", "tipo_dia", "status"],
    metricas_alerta=["receita", "pedidos", "ticket_medio", "taxa_cancelamento",
                     "pct_frete"],
    dims_alerta=["categoria", "regiao", "meio_pagamento"],
    limites=[
        Limite("taxa_cancelamento", ">", 0.015,
               "Acima de 1,5% de cancelamento o time de operações entra."),
        Limite("pct_frete", ">", 0.22,
               "Frete acima de 22% da receita corroi a margem do pedido."),
    ],
    sinonimos_metrica={
        "receita": ["receita", "faturamento", "venda", "vendas", "gmv"],
        "pedidos": ["pedido", "pedidos", "ordem", "ordens", "volume"],
        "itens": ["item", "itens", "unidade", "unidades", "pecas"],
        "clientes": ["cliente", "clientes", "comprador", "compradores", "base"],
        "ticket_medio": ["ticket", "ticket médio", "valor médio do pedido",
                         "gasto médio"],
        "receita_por_item": ["preco médio", "receita por item", "valor por item"],
        "itens_por_pedido": ["itens por pedido", "cesta", "tamanho da cesta"],
        "receita_por_cliente": ["receita por cliente", "gasto por cliente"],
        "frete": ["frete", "valor de frete"],
        "pct_frete": ["frete sobre receita", "peso do frete", "percentual de frete"],
        "taxa_cancelamento": ["cancelamento", "cancelado", "cancelados",
                              "taxa de cancelamento"],
    },
    sinonimos_dimensao={
        "categoria": ["categoria", "categorias", "produto", "produtos", "linha"],
        "regiao": ["regiao", "regioes", "regional"],
        "estado": ["estado", "estados", "uf", "ufs"],
        "meio_pagamento": ["pagamento", "meio de pagamento", "forma de pagamento",
                           "cartao", "boleto"],
        "faixa_parcelas": ["parcela", "parcelas", "parcelamento", "vezes"],
        "tipo_cliente": ["novo", "novos", "recorrente", "recorrentes",
                         "recompra", "primeira compra", "base",
                         "novo ou recorrente"],
        "faixa_valor": ["faixa de preco", "faixa de valor", "ticket do item",
                        "preco", "caro", "barato"],
        "dia_semana": ["dia da semana", "dia de semana", "segunda", "sabado",
                       "domingo"],
        "tipo_dia": ["dia util", "fim de semana", "final de semana",
                     "util ou fim de semana"],
        "status": ["status", "situacao", "status do pedido"],
    },
    perguntas_exemplo=[
        "Quanto foi a receita no período?",
        "Quais as 5 maiores categorias por receita?",
        "Por que o ticket médio mudou em relação ao mês passado?",
        "A receita está crescendo ou caindo?",
        "Tem algo fora do padrão no último dia?",
        "Quais os piores estados em taxa de cancelamento?",
        "A receita tem sazonalidade por dia da semana?",
    ],
    agente_nome="Abigail",
    agente_rosto="🐱",
    agente_genero="f",
    agente_voz="abigail",
    agente_imagem="abigail",
    agente_papel=("Cuido de marketing e CRM: receita, aquisição e comportamento "
                  "de compra. Sou a herdeira direta do Vulcano, o agente que "
                  "nasceu na Petlove para acabar com a fila de pedidos de "
                  "número."),
    notas=[
        "Receita considera o preco dos itens e exclui frete.",
        "Pedidos cancelados antes do faturamento entram na contagem de pedidos "
        "com receita zero, para não enviesar a taxa de cancelamento.",
    ],
)
