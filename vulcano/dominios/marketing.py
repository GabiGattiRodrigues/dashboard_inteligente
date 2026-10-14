"""Domínio de Marketing e CRM, sobre a base pública do Olist.

Os pedidos são os do Olist, sem alteração. A camada de campanha -- de que
canal e campanha veio cada pedido, quanto se investiu, quantos disparos de CRM
saíram e o grupo controle de cada um -- é simulada e amarrada aos pedidos
reais (ver scripts/build_campanhas.py). O fato tem dois tipos de linha:
pedido e campanha. Por isso as métricas de campanha declaram `dims`: só
existem nas dimensões que a linha de campanha também tem.
"""

from ..semantica import Dimensao, Dominio, Limite, Metrica, indexar

_PEDIDOS = "COUNT(DISTINCT order_id)"

# --- campanha ---------------------------------------------------------------
_PAGO = "tipo_campanha = 'Mídia paga'"
_CRM = "tipo_campanha = 'CRM'"
_CAMP = "tipo_campanha IN ('Mídia paga', 'CRM')"
_PED_CRM = f"COUNT(DISTINCT CASE WHEN {_CRM} THEN order_id END)"
_PED_PAGO = f"COUNT(DISTINCT CASE WHEN {_PAGO} THEN order_id END)"
_INV_PAGO = f"SUM(CASE WHEN {_PAGO} THEN investimento END)"
_RECEITA_CAMP = f"SUM(CASE WHEN {_CAMP} THEN receita END)"
_RECEITA_CRM = f"SUM(CASE WHEN {_CRM} THEN receita END)"
# Disparos com os 7 dias de resposta inteiros dentro da base.
_AB_W = "CASE WHEN janela_7d = 1 THEN aberturas END"
_ENV_W = "CASE WHEN janela_7d = 1 THEN envios END"
_CTRL_W = "CASE WHEN janela_7d = 1 THEN grupo_controle END"

# Dimensões que a linha de campanha (investimento, disparo) também carrega.
# Investimento não tem categoria de produto, meio de pagamento, parcela,
# faixa de preço, status nem "novo ou recorrente": o dinheiro sai antes de
# existir pedido.
DIMS_CAMPANHA = ("canal", "campanha", "tipo_campanha", "regiao", "estado",
                 "dia_semana", "tipo_dia")

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

    # ---- aquisição e mídia paga ----------------------------------------- #
    Metrica("investimento", "Investimento", "SUM(investimento)",
            formato="moeda", bom_quando_sobe=False, dims=DIMS_CAMPANHA,
            descricao="Mídia paga (CPC de busca e social, comissão de "
                      "afiliado) mais o custo de disparo de CRM. Simulado."),
    Metrica("receita_campanhas", "Receita de campanhas", _RECEITA_CAMP,
            formato="moeda",
            descricao="Receita dos pedidos atribuídos (último clique) a "
                      "mídia paga ou CRM. Fica de fora o orgânico e o direto."),
    Metrica("roas", "ROAS", _RECEITA_CAMP, den_sql="SUM(investimento)",
            formato="decimal", casas=2, dims=DIMS_CAMPANHA,
            formula="Receita de campanhas ÷ Investimento",
            descricao="Quantos reais de receita voltam para cada real "
                      "investido em campanha."),
    Metrica("novos_clientes", "Novos clientes",
            "COUNT(DISTINCT CASE WHEN tipo_cliente = 'Primeira compra' "
            "THEN cliente_id END)", formato="inteiro", grao="grosso",
            num_aditivo=False, entidade="cliente",
            descricao="Clientes que fizeram a primeira compra da vida na "
                      "base no período."),
    Metrica("cac", "CAC (mídia paga)", _INV_PAGO,
            den_sql=f"COUNT(DISTINCT CASE WHEN {_PAGO} AND tipo_cliente = "
                    f"'Primeira compra' THEN cliente_id END)",
            formato="moeda", casas=2, bom_quando_sobe=False, grao="grosso",
            dims=DIMS_CAMPANHA,
            # O denominador conta PESSOAS distintas: quem fez duas primeiras
            # compras no mesmo dia, para dois estados, entra nos dois
            # segmentos. A cascata do CAC mostra o resíduo em vez de fingir
            # que fecha.
            num_aditivo=False, entidade="cliente",
            formula="Investimento em mídia paga ÷ Novos clientes trazidos "
                    "por mídia paga",
            descricao="Quanto custa trazer um cliente novo pela mídia paga. "
                      "CRM fica de fora: não adquire, retém."),
    Metrica("cliques", "Cliques (mídia)", "SUM(cliques)", formato="inteiro",
            dims=DIMS_CAMPANHA,
            descricao="Cliques nos anúncios de busca, social e afiliados."),
    Metrica("ctr", "CTR (mídia)", "SUM(cliques)", den_sql="SUM(impressoes)",
            formato="percentual", casas=2, dims=DIMS_CAMPANHA,
            formula="Cliques ÷ Impressões",
            descricao="De cada 100 vezes que o anúncio aparece, quantas viram "
                      "clique."),
    Metrica("cpc", "CPC", _INV_PAGO, den_sql="SUM(cliques)", formato="moeda",
            casas=2, bom_quando_sobe=False, dims=DIMS_CAMPANHA,
            formula="Investimento em mídia paga ÷ Cliques",
            descricao="Custo médio de cada clique na mídia paga."),
    Metrica("conversao_midia", "Conversão da mídia", _PED_PAGO,
            den_sql="SUM(cliques)", formato="percentual", casas=2,
            grao="grosso", num_aditivo=False, entidade="pedido",
            dims=DIMS_CAMPANHA,
            formula="Pedidos de mídia paga ÷ Cliques",
            descricao="De cada 100 cliques em anúncio, quantos viram pedido."),

    # ---- CRM ------------------------------------------------------------- #
    Metrica("envios", "Envios de CRM", "SUM(envios)", formato="inteiro",
            dims=DIMS_CAMPANHA,
            descricao="Mensagens de e-mail, push e WhatsApp entregues ao "
                      "grupo que recebe (o controle não entra)."),
    Metrica("taxa_abertura", "Taxa de abertura", "SUM(aberturas)",
            den_sql="SUM(envios)", formato="percentual", casas=1,
            dims=DIMS_CAMPANHA, formula="Aberturas ÷ Envios",
            descricao="Mensagens abertas (lidas, no WhatsApp) sobre enviadas."),
    Metrica("taxa_clique_crm", "Taxa de clique do CRM", "SUM(cliques_crm)",
            den_sql="SUM(envios)", formato="percentual", casas=2,
            dims=DIMS_CAMPANHA, formula="Cliques ÷ Envios",
            descricao="Mensagens que geraram clique sobre enviadas."),
    Metrica("conversao_crm", "Conversão do CRM", _PED_CRM,
            den_sql="SUM(envios)", formato="percentual", casas=3,
            grao="grosso", num_aditivo=False, entidade="pedido",
            dims=DIMS_CAMPANHA, formula="Pedidos de CRM ÷ Envios",
            descricao="Pedidos atribuídos ao CRM para cada 100 mensagens "
                      "enviadas."),
    Metrica("taxa_optout", "Taxa de opt-out", "SUM(optouts)",
            den_sql="SUM(envios)", formato="percentual", casas=2,
            bom_quando_sobe=False, dims=DIMS_CAMPANHA,
            formula="Opt-outs ÷ Envios",
            descricao="Quem pediu para não receber mais, sobre enviados. É o "
                      "custo escondido de disparar demais."),
    Metrica("receita_crm", "Receita de CRM", _RECEITA_CRM, formato="moeda",
            descricao="Receita dos pedidos atribuídos a e-mail, push e "
                      "WhatsApp."),
    Metrica("pct_receita_crm", "Receita de CRM sobre o total", _RECEITA_CRM,
            den_sql="SUM(receita)", formato="percentual", casas=1,
            formula="Receita de CRM ÷ Receita",
            descricao="Quanto da receita vem da base que o CRM trabalha."),
    # ---- CRM: mensuração do disparo em 7 dias --------------------------- #
    # A régua de quem opera CRM: de quem recebeu, quem abriu (foi
    # impactado) e quem comprou em até 7 dias depois do disparo, contra o
    # grupo controle. Só entram disparos com os 7 dias inteiros dentro da
    # base (`janela_7d`) -- janela pela metade pareceria queda de resposta.
    Metrica("impactados", "Impactados (abriram)", f"SUM({_AB_W})",
            formato="inteiro", dims=DIMS_CAMPANHA,
            descricao="Quem abriu a mensagem nos disparos com janela de 7 "
                      "dias completa. É a audiência que de fato viu a "
                      "campanha."),
    Metrica("resp_impactados", "Respondentes que abriram (7d)",
            "SUM(resp_abriu)", formato="inteiro", dims=DIMS_CAMPANHA,
            descricao="Quem abriu e comprou em até 7 dias depois do "
                      "disparo."),
    Metrica("taxa_resp_impactados", "Resposta de quem abriu (7d)",
            "SUM(resp_abriu)", den_sql=f"SUM({_AB_W})",
            formato="percentual", casas=2, dims=DIMS_CAMPANHA,
            formula="Compraram em 7 dias ÷ Abriram",
            descricao="Dos que abriram, quantos compraram em até 7 dias. É a "
                      "taxa de resposta que se compara com a do controle."),
    Metrica("taxa_resp_recebeu", "Resposta de quem recebeu (7d)",
            "SUM(resp_recebeu)", den_sql=f"SUM({_ENV_W})",
            formato="percentual", casas=3, dims=DIMS_CAMPANHA,
            formula="Compraram em 7 dias ÷ Receberam",
            descricao="Dos que receberam -- abrindo ou não --, quantos "
                      "compraram em até 7 dias."),
    Metrica("taxa_resp_controle", "Resposta do controle (7d)",
            "SUM(resp_controle)", den_sql=f"SUM({_CTRL_W})",
            formato="percentual", casas=3, dims=DIMS_CAMPANHA,
            formula="Compraram em 7 dias ÷ Grupo controle",
            descricao="Dos 10% sorteados que não receberam nada, quantos "
                      "compraram em 7 dias. É quanto essa audiência compra "
                      "sozinha."),
    Metrica("lift_impactados", "Lift de quem abriu sobre o controle",
            f"SUM(resp_abriu) * SUM({_CTRL_W}) - SUM({_AB_W}) * "
            f"SUM(resp_controle)",
            den_sql=f"SUM({_AB_W}) * SUM(resp_controle)",
            formato="percentual", casas=0, grao="grosso", num_aditivo=False,
            entidade=None, dims=DIMS_CAMPANHA,
            formula="Resposta de quem abriu ÷ Resposta do controle − 1",
            descricao="A leitura clássica de CRM: quanto a resposta de quem "
                      "abriu supera a do controle. Superestima o efeito -- "
                      "quem abre e-mail já compra mais por natureza --, e "
                      "por isso vem sempre ao lado do lift de quem recebeu."),
    Metrica("lift_crm", "Lift do CRM sobre o controle",
            f"SUM(resp_recebeu) * SUM({_CTRL_W}) - SUM({_ENV_W}) * "
            f"SUM(resp_controle)",
            den_sql=f"SUM({_ENV_W}) * SUM(resp_controle)",
            formato="percentual", casas=0, grao="grosso", num_aditivo=False,
            # Sem entidade de propósito: o numerador é um produto de somas,
            # e produto não se decompõe por soma de segmentos em dimensão
            # nenhuma. A cascata do lift mostra sempre o resíduo.
            entidade=None, dims=DIMS_CAMPANHA,
            formula="Resposta de quem recebeu ÷ Resposta do controle − 1",
            descricao="Quanto a resposta em 7 dias de quem RECEBEU -- "
                      "abrindo ou não -- supera a do controle. As duas "
                      "populações foram sorteadas da mesma audiência, então "
                      "a diferença é efeito do disparo, e não de perfil."),
    Metrica("pedidos_incrementais", "Compradores incrementais (7d)",
            f"SUM(resp_recebeu) - SUM({_ENV_W}) * SUM(resp_controle) * 1.0 "
            f"/ NULLIF(SUM({_CTRL_W}), 0)",
            formato="inteiro", grao="grosso", num_aditivo=False,
            entidade=None, dims=DIMS_CAMPANHA,
            formula="Compraram (recebeu) − Receberam × Resposta do controle",
            descricao="Compras em 7 dias que não teriam acontecido sem o "
                      "disparo: as de quem recebeu menos o que a mesma "
                      "audiência compraria sozinha, medido no controle."),
    Metrica("receita_incremental", "Receita incremental (7d)",
            f"SUM(receita_recebeu) - SUM({_ENV_W}) * SUM(receita_controle) "
            f"* 1.0 / NULLIF(SUM({_CTRL_W}), 0)",
            formato="moeda", grao="grosso", num_aditivo=False,
            entidade=None, dims=DIMS_CAMPANHA,
            formula="Receita (recebeu) − Receberam × Receita por pessoa do "
                    "controle",
            descricao="Receita em 7 dias que o disparo causou, pela mesma "
                      "conta dos compradores incrementais."),
    Metrica("ticket_impactados", "Ticket de quem abriu (7d)",
            "SUM(receita_abriu)", den_sql="SUM(resp_abriu)",
            formato="moeda", casas=2, dims=DIMS_CAMPANHA,
            formula="Receita de quem abriu e comprou ÷ Compradores",
            descricao="Ticket médio de quem abriu e comprou em 7 dias."),
    Metrica("ticket_controle", "Ticket do controle (7d)",
            "SUM(receita_controle)", den_sql="SUM(resp_controle)",
            formato="moeda", casas=2, dims=DIMS_CAMPANHA,
            formula="Receita do controle ÷ Compradores do controle",
            descricao="Ticket médio de quem comprou no grupo controle. "
                      "Comparado com o de quem abriu, mostra se a campanha "
                      "mexeu no tamanho da compra -- cupom costuma "
                      "derrubar."),
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
    Dimensao("canal", "Canal", "canal", unica_por=("pedido",),
             descricao="Canal que trouxe o pedido (último clique) ou em que o "
                       "investimento e o disparo aconteceram. Simulado."),
    Dimensao("campanha", "Campanha", "campanha", unica_por=("pedido",),
             descricao="Campanha que trouxe o pedido (último clique) ou que "
                       "recebeu o investimento. Simulado."),
    Dimensao("tipo_campanha", "Tipo de campanha", "tipo_campanha",
             unica_por=("pedido",),
             descricao="Mídia paga, CRM, ou orgânico e direto (sem campanha). "
                       "Simulado."),
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
    arquivo="fato_marketing.parquet",
    em_memoria=True,
    metricas=METRICAS,
    dimensoes=DIMENSOES,
    metricas_painel=["receita", "pedidos", "ticket_medio", "clientes",
                     "investimento", "roas", "cac", "pct_receita_crm",
                     "itens_por_pedido", "taxa_cancelamento", "pct_frete",
                     "receita_por_item"],
    dims_filtro=["categoria", "canal", "campanha", "regiao", "estado",
                 "tipo_campanha", "meio_pagamento", "faixa_parcelas",
                 "tipo_cliente", "faixa_valor", "dia_semana", "tipo_dia",
                 "status"],
    metricas_alerta=["receita", "pedidos", "ticket_medio", "taxa_cancelamento",
                     "pct_frete", "investimento", "roas"],
    dims_alerta=["categoria", "canal", "regiao", "meio_pagamento"],
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
        "investimento": ["investimento", "investimentos", "investido",
                         "investimento em midia", "gasto", "gastos",
                         "gasto com midia", "verba", "custo de midia",
                         "custo de campanha", "spend"],
        "receita_campanhas": ["receita de campanha", "receita de campanhas",
                              "receita atribuida", "receita das campanhas",
                              "venda de campanha", "vendas de campanha"],
        "roas": ["roas", "retorno sobre investimento",
                 "retorno do investimento", "retorno de midia",
                 "retorno das campanhas", "retorno da campanha"],
        "novos_clientes": ["novos clientes", "clientes novos",
                           "clientes adquiridos", "aquisicao de clientes",
                           "primeiras compras"],
        "cac": ["cac", "custo de aquisicao", "custo por cliente novo",
                "custo por aquisicao", "custo de aquisicao de cliente"],
        "cliques": ["clique", "cliques", "cliques na midia",
                    "cliques nos anuncios"],
        "ctr": ["ctr", "ctr da midia", "taxa de clique da midia",
                "taxa de clique dos anuncios", "click through"],
        "cpc": ["cpc", "custo por clique"],
        "conversao_midia": ["conversao", "taxa de conversao",
                            "conversao da midia", "conversao de midia",
                            "conversao dos anuncios", "conversao do clique"],
        "envios": ["envio", "envios", "disparo", "disparos",
                   "mensagens enviadas", "volume de disparo"],
        "taxa_abertura": ["abertura", "aberturas", "taxa de abertura",
                          "open rate"],
        "taxa_clique_crm": ["taxa de clique do crm", "clique do crm",
                            "cliques do crm", "ctr do crm", "ctr de crm",
                            "clique no email", "clique no e-mail"],
        "conversao_crm": ["conversao do crm", "conversao de crm",
                          "conversao crm", "conversao dos disparos",
                          "conversao do email", "conversao do e-mail"],
        "taxa_optout": ["optout", "opt-out", "opt out", "taxa de opt-out",
                        "descadastro", "descadastros", "descadastramento"],
        "receita_crm": ["receita de crm", "receita do crm", "receita crm",
                        "venda de crm", "vendas do crm",
                        "faturamento do crm"],
        "pct_receita_crm": ["participacao do crm", "share do crm",
                            "share de crm", "peso do crm",
                            "receita de crm sobre o total",
                            "quanto da receita vem do crm"],
        "lift_crm": ["lift", "lift do crm", "incrementalidade",
                     "ganho sobre o controle", "grupo controle", "holdout",
                     "lift de quem recebeu", "lift real"],
        "lift_impactados": ["lift de quem abriu", "lift dos impactados",
                            "lift dos abertos", "lift sobre quem abriu",
                            "lift aparente"],
        "pedidos_incrementais": ["pedidos incrementais", "incrementais",
                                 "vendas incrementais", "pedido incremental",
                                 "compradores incrementais"],
        "receita_incremental": ["receita incremental", "receita causada",
                                "faturamento incremental"],
        "impactados": ["impactados", "quantos abriram", "quem abriu",
                       "abriram"],
        "resp_impactados": ["respondentes", "quantos responderam",
                            "quantos compraram depois"],
        "taxa_resp_impactados": ["resposta de quem abriu", "taxa de resposta",
                                 "% de respondentes", "respondentes sobre "
                                 "quem abriu", "resposta dos impactados",
                                 "taxa de resposta dos impactados"],
        "taxa_resp_recebeu": ["resposta de quem recebeu",
                              "taxa de resposta de quem recebeu"],
        "taxa_resp_controle": ["resposta do controle", "taxa do controle",
                               "conversao do controle"],
        "ticket_impactados": ["ticket de quem abriu", "ticket dos impactados",
                              "ticket da campanha"],
        "ticket_controle": ["ticket do controle"],
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
        "canal": ["canal", "canais", "midia", "canal de aquisicao",
                  "origem", "fonte de trafego"],
        "campanha": ["campanha", "campanhas"],
        "tipo_campanha": ["tipo de campanha", "tipo da campanha",
                          "pago ou crm", "midia paga ou crm",
                          "pago, crm ou organico"],
    },
    perguntas_exemplo=[
        "Como foram as campanhas de CRM?",
        "Como foi a campanha de carrinho abandonado?",
        "Como foi o último disparo da newsletter?",
        "Qual o ROAS por canal?",
        "Por que o ROAS caiu em relação ao mês passado?",
        "Quais as campanhas com o pior CAC?",
        "Por que o ticket médio mudou em relação ao mês passado?",
        "Tem algo fora do padrão no último dia?",
        "Quanto foi a receita no período?",
        "Quais as 5 maiores categorias por receita?",
        "A receita está crescendo ou caindo?",
    ],
    agente_nome="Abigail",
    agente_rosto="🐱",
    agente_genero="f",
    agente_voz="abigail",
    agente_imagem="abigail",
    extensao="vulcano.marketing.agente",
    agente_papel=("Cuido de marketing e CRM: receita, aquisição e comportamento "
                  "de compra. Sou a herdeira direta do Vulcano, o agente que "
                  "nasceu na Petlove para acabar com a fila de pedidos de "
                  "número."),
    guia_conversa=(
        ("quanto foi a receita?", "dá o número do período selecionado"),
        ("e por quê?", "decompõe a variação contra a base e mostra a cascata"),
        ("e por região?", "refaz a mesma leitura quebrada por região"),
        ("e o ticket médio?", "troca só a métrica e mantém o resto"),
        ("quais os piores estados em cancelamento?",
         "ranking já lido como negócio: pior é a taxa mais ALTA"),
        ("qual o ROAS por campanha?",
         "ranking de campanha pelo retorno de cada real investido"),
        ("como foi a campanha de carrinho abandonado?",
         "mede do jeito de CRM: recebeu, abriu, comprou em 7 dias, resposta "
         "de quem abriu contra o controle e ticket médio"),
        ("e o último disparo da newsletter?",
         "a mesma régua, só para o disparo mais recente com janela fechada"),
    ),
    dica_conversa=("Métrica de razão (ticket médio, cancelamento, frete sobre "
                   "receita) vem com a conta aberta: a fórmula aparece com os "
                   "números do período, e a causa raiz separa efeito taxa de "
                   "efeito mix. Métrica de campanha (investimento, ROAS, "
                   "CAC, abertura) só existe por canal, campanha, região e "
                   "dia: dinheiro de mídia não tem meio de pagamento."),
    notas=[
        "Receita considera o preco dos itens e exclui frete.",
        "Pedidos cancelados antes do faturamento entram na contagem de pedidos "
        "com receita zero, para não enviesar a taxa de cancelamento.",
        "Pedidos, receita, clientes, categorias e estados são os do Olist, "
        "reais. A camada de campanha é SIMULADA e amarrada a eles: canal e "
        "campanha de cada pedido (último clique), investimento, impressões, "
        "cliques, disparos de CRM, aberturas, opt-outs e grupo controle.",
        "Atribuição por último clique: o pedido vai inteiro para a última "
        "campanha tocada. Ela superestima canal de fundo de funil (busca de "
        "marca, carrinho abandonado) — é por isso que o CRM é lido também pelo "
        "lift sobre o grupo controle, que não depende de atribuição.",
        "Todo disparo de CRM separa 10% da audiência como grupo controle, que "
        "não recebe nada. Com poucas compras no controle o lift oscila muito: "
        "leia junto com o volume.",
        "Investimento, ROAS, CAC, CTR, CPC e as taxas de CRM só existem por "
        "canal, campanha, tipo de campanha, região, estado e dia: a linha de "
        "investimento não tem categoria, meio de pagamento, faixa de preço, "
        "status nem novo/recorrente. Com um desses filtros ativo, essas "
        "métricas ficam vazias de propósito.",
        "Eventos plantados na simulação, para o painel ter o que achar: Black "
        "Friday de 2017 com CPC 25% mais caro; CPC de Social • Prospecção 35% "
        "mais caro e CTR 20% menor a partir de jun/2018; WhatsApp de recompra "
        "lançado em mar/2018; e orçamento de Social • Prospecção 2,6x maior "
        "por erro de configuração nos dois últimos dias da base.",
    ],
)


# --------------------------------------------------------------------------- #
# English
# --------------------------------------------------------------------------- #

EN = {
    "nome": "Marketing & CRM",
    "subtitulo": "Revenue, acquisition and purchase behavior",
    "descricao": (
        "How revenue is built: how much comes in, from whom, from which "
        "category and through which payment method. The dashboard for "
        "whoever owns the sales target and channel efficiency."
    ),
    "fonte": (
        "Brazilian E-Commerce Public Dataset by Olist — 99k real orders from "
        "a Brazilian marketplace, Jan 2017 to Aug 2018."
    ),
    "metricas": {
        "receita": ("Revenue", "Sum of item prices, excluding freight."),
        "pedidos": ("Orders", "Distinct orders in the period, by purchase date."),
        "itens": ("Items sold", "Number of items invoiced."),
        "clientes": ("Customers", "Distinct customers who bought in the period."),
        "ticket_medio": ("Average ticket", "Revenue divided by distinct orders.",
                         "Revenue ÷ Orders"),
        "receita_por_item": ("Revenue per item", "Average price of the item sold.",
                             "Revenue ÷ Items sold"),
        "itens_por_pedido": ("Items per order",
                             "How many items go into each order, on average.",
                             "Items sold ÷ Orders"),
        "receita_por_cliente": ("Revenue per customer",
                                "How much each customer bought, on average, in "
                                "the period.", "Revenue ÷ Customers"),
        "frete": ("Freight", "Sum of freight charged."),
        "pct_frete": ("Freight share of revenue",
                      "Weight of freight in the sale value.",
                      "Freight ÷ Revenue"),
        "taxa_cancelamento": ("Cancellation rate",
                              "Canceled or unavailable orders over the total.",
                              "Canceled orders ÷ Orders"),
        "investimento": ("Investment", "Paid media (search and social CPC, "
                         "affiliate commission) plus CRM sending cost. "
                         "Simulated."),
        "receita_campanhas": ("Campaign revenue", "Revenue from orders "
                              "attributed (last click) to paid media or CRM. "
                              "Organic and direct are left out."),
        "roas": ("ROAS", "How many reais of revenue come back for each real "
                 "invested in campaigns.", "Campaign revenue ÷ Investment"),
        "novos_clientes": ("New customers", "Customers who made their "
                           "first-ever purchase in the base in the period."),
        "cac": ("CAC (paid media)", "What it costs to bring in a new customer "
                "through paid media. CRM is left out: it retains, it doesn't "
                "acquire.", "Paid media investment ÷ New customers from paid "
                "media"),
        "cliques": ("Clicks (media)", "Clicks on search, social and "
                    "affiliate ads."),
        "ctr": ("CTR (media)", "Out of every 100 times the ad shows, how many "
                "become a click.", "Clicks ÷ Impressions"),
        "cpc": ("CPC", "Average cost of each paid media click.",
                "Paid media investment ÷ Clicks"),
        "conversao_midia": ("Media conversion", "Out of every 100 ad clicks, "
                            "how many become an order.",
                            "Paid media orders ÷ Clicks"),
        "envios": ("CRM sends", "Email, push and WhatsApp messages delivered "
                   "to the treated group (the control group is excluded)."),
        "taxa_abertura": ("Open rate", "Messages opened (read, on WhatsApp) "
                          "over sent.", "Opens ÷ Sends"),
        "taxa_clique_crm": ("CRM click rate", "Messages that got a click over "
                            "sent.", "Clicks ÷ Sends"),
        "conversao_crm": ("CRM conversion", "Orders attributed to CRM per 100 "
                          "messages sent.", "CRM orders ÷ Sends"),
        "taxa_optout": ("Opt-out rate", "People who asked to stop receiving "
                        "messages, over sent. The hidden cost of over-sending.",
                        "Opt-outs ÷ Sends"),
        "receita_crm": ("CRM revenue", "Revenue from orders attributed to "
                        "email, push and WhatsApp."),
        "pct_receita_crm": ("CRM share of revenue", "How much of revenue comes "
                            "from the base CRM works on.",
                            "CRM revenue ÷ Revenue"),
        "impactados": ("Reached (opened)",
                       "People who opened the message in sends with a full "
                       "7-day window. The audience that actually saw the "
                       "campaign."),
        "resp_impactados": ("Responders who opened (7d)",
                            "People who opened and bought within 7 days of "
                            "the send."),
        "taxa_resp_impactados": ("Response of openers (7d)",
                                 "Of those who opened, how many bought within "
                                 "7 days. The response rate compared with the "
                                 "control's.",
                                 "Bought within 7 days ÷ Opened"),
        "taxa_resp_recebeu": ("Response of recipients (7d)",
                              "Of those who received — opening or not — how "
                              "many bought within 7 days.",
                              "Bought within 7 days ÷ Received"),
        "taxa_resp_controle": ("Control response (7d)",
                               "Of the random 10% who got nothing, how many "
                               "bought within 7 days. What this audience "
                               "buys on its own.",
                               "Bought within 7 days ÷ Control group"),
        "lift_impactados": ("Openers' lift over control",
                            "The classic CRM reading: how much the openers' "
                            "response beats the control's. It overstates the "
                            "effect — people who open emails already buy "
                            "more — so it always comes next to the "
                            "recipients' lift.",
                            "Openers' response ÷ Control response − 1"),
        "lift_crm": ("CRM lift over control",
                     "How much the 7-day response of everyone who RECEIVED — "
                     "opening or not — beats the control's. Both groups were "
                     "drawn at random from the same audience, so the "
                     "difference is the send's effect, not profile.",
                     "Recipients' response ÷ Control response − 1"),
        "pedidos_incrementais": ("Incremental buyers (7d)",
                                 "Purchases within 7 days that wouldn't have "
                                 "happened without the send: recipients' "
                                 "purchases minus what the same audience "
                                 "would buy on its own, measured in the "
                                 "control.",
                                 "Bought (recipients) − Received × Control "
                                 "response"),
        "receita_incremental": ("Incremental revenue (7d)",
                                "7-day revenue the send caused, by the same "
                                "math as incremental buyers.",
                                "Revenue (recipients) − Received × Control "
                                "revenue per person"),
        "ticket_impactados": ("Openers' ticket (7d)",
                              "Average ticket of those who opened and bought "
                              "within 7 days.",
                              "Openers' revenue ÷ Buyers"),
        "ticket_controle": ("Control ticket (7d)",
                            "Average ticket of buyers in the control group. "
                            "Against the openers', it shows whether the "
                            "campaign changed basket size — coupons usually "
                            "push it down.",
                            "Control revenue ÷ Control buyers"),
    },
    "dimensoes": {
        "categoria": ("Category", "Category of the product purchased."),
        "regiao": ("Region", "Customer's region on the order."),
        "estado": ("State", "Customer's state on the order."),
        "meio_pagamento": ("Payment method",
                           "Highest-value payment method on the order."),
        "faixa_parcelas": ("Installments", "Number-of-installments band."),
        "tipo_cliente": ("New or returning",
                         "Whether it is the person's first purchase in the "
                         "base or a repeat purchase. Computed on the whole "
                         "base, not the filtered period — otherwise the same "
                         "order would change label with the filter."),
        "faixa_valor": ("Item price band", "Price band of the item purchased."),
        "dia_semana": ("Day of week", "Day of the week of the purchase."),
        "tipo_dia": ("Weekday or weekend",
                     "Whether the purchase fell on a weekday or the weekend."),
        "status": ("Order status", "Order status in the marketplace system."),
        "canal": ("Channel", "Channel that brought the order (last click) or "
                  "where the investment and the send happened. Simulated."),
        "campanha": ("Campaign", "Campaign that brought the order (last "
                     "click) or received the investment. Simulated."),
        "tipo_campanha": ("Campaign type", "Paid media, CRM, or organic & "
                          "direct (no campaign). Simulated."),
    },
    "limites": [
        "Above 1.5% cancellation the operations team steps in.",
        "Freight above 22% of revenue eats into the order margin.",
    ],
    "sinonimos_metrica": {
        "receita": ["revenue", "sales", "gmv", "turnover", "income"],
        "pedidos": ["order", "orders", "order volume"],
        "itens": ["item", "items", "units", "items sold"],
        "clientes": ["customer", "customers", "buyer", "buyers", "clients"],
        "ticket_medio": ["ticket", "average ticket", "aov",
                         "average order value", "average spend"],
        "receita_por_item": ["average price", "revenue per item",
                             "price per item"],
        "itens_por_pedido": ["items per order", "basket", "basket size"],
        "receita_por_cliente": ["revenue per customer", "spend per customer"],
        "frete": ["freight", "shipping", "shipping cost"],
        "pct_frete": ["freight share", "shipping share",
                      "freight over revenue", "freight percentage"],
        "taxa_cancelamento": ["cancellation", "cancellations", "canceled",
                              "cancelled", "cancellation rate"],
        "investimento": ["investment", "spend", "ad spend", "media spend",
                         "budget", "marketing spend", "campaign spend"],
        "receita_campanhas": ["campaign revenue", "attributed revenue",
                              "revenue from campaigns"],
        "roas": ["roas", "return on ad spend", "return on investment",
                 "campaign return", "media return"],
        "novos_clientes": ["new customers", "acquired customers",
                           "customer acquisition", "first purchases"],
        "cac": ["cac", "acquisition cost", "customer acquisition cost",
                "cost per acquisition", "cost per new customer"],
        "cliques": ["click", "clicks", "ad clicks"],
        "ctr": ["ctr", "click-through rate", "click through rate",
                "ad ctr", "media ctr"],
        "cpc": ["cpc", "cost per click"],
        "conversao_midia": ["conversion", "conversion rate",
                            "media conversion", "ad conversion",
                            "click conversion"],
        "envios": ["sends", "messages sent", "send volume", "sent messages"],
        "taxa_abertura": ["open rate", "opens", "opening rate"],
        "taxa_clique_crm": ["crm click rate", "crm clicks", "crm ctr",
                            "email click rate", "email ctr"],
        "conversao_crm": ["crm conversion", "email conversion",
                          "send conversion"],
        "taxa_optout": ["opt-out", "opt out", "optout", "opt-out rate",
                        "unsubscribe", "unsubscribes", "unsubscribe rate"],
        "receita_crm": ["crm revenue", "revenue from crm", "crm sales"],
        "pct_receita_crm": ["crm share", "crm share of revenue",
                            "share of crm", "crm weight"],
        "lift_crm": ["lift", "crm lift", "incrementality", "uplift",
                     "control group", "holdout", "recipients' lift",
                     "real lift"],
        "lift_impactados": ["openers' lift", "openers lift", "lift of openers",
                            "apparent lift"],
        "pedidos_incrementais": ["incremental orders", "incremental sales",
                                 "incremental", "incremental buyers"],
        "receita_incremental": ["incremental revenue", "revenue caused"],
        "impactados": ["reached", "how many opened", "openers", "opened"],
        "resp_impactados": ["responders", "how many responded"],
        "taxa_resp_impactados": ["response of openers", "response rate",
                                 "openers response", "openers' response"],
        "taxa_resp_recebeu": ["response of recipients",
                              "recipients' response"],
        "taxa_resp_controle": ["control response", "control rate",
                               "control conversion"],
        "ticket_impactados": ["openers' ticket", "campaign ticket"],
        "ticket_controle": ["control ticket"],
    },
    "sinonimos_dimensao": {
        "categoria": ["category", "categories", "product category",
                      "product line"],
        "regiao": ["region", "regions", "regional"],
        "estado": ["state", "states"],
        "meio_pagamento": ["payment", "payment method", "payment type",
                           "credit card", "card"],
        "faixa_parcelas": ["installment", "installments"],
        "tipo_cliente": ["new customers", "returning", "repeat",
                         "first purchase", "new or returning"],
        "faixa_valor": ["price band", "price range", "price", "expensive",
                        "cheap"],
        "dia_semana": ["day of week", "day of the week", "weekday name",
                       "monday", "saturday", "sunday"],
        "tipo_dia": ["weekday or weekend", "weekend", "business day"],
        "status": ["status", "order status"],
        "canal": ["channel", "channels", "media", "acquisition channel",
                  "source", "traffic source"],
        "campanha": ["campaign", "campaigns"],
        "tipo_campanha": ["campaign type", "paid or crm", "paid media or crm"],
    },
    "perguntas_exemplo": [
        "How did the CRM campaigns do?",
        "How did the abandoned cart campaign do?",
        "How did the last newsletter send do?",
        "What is ROAS by channel?",
        "Why did ROAS drop vs last month?",
        "Which campaigns have the worst CAC?",
        "Why did the average ticket change vs last month?",
        "Is anything out of pattern on the last day?",
        "What was revenue in the period?",
        "What are the top 5 categories by revenue?",
        "Is revenue growing or falling?",
    ],
    "agente_papel": (
        "I look after marketing and CRM: revenue, acquisition and purchase "
        "behavior. I'm the direct heir of Vulcano, the agent born at Petlove "
        "to end the queue of 'can you pull this number for me?' requests."
    ),
    "guia_conversa": [
        ("what was revenue?", "gives the number for the selected period"),
        ("and why?", "breaks the change down against the baseline and draws "
                     "the waterfall"),
        ("and by region?", "redoes the same reading, split by region"),
        ("what about the average ticket?",
         "switches only the metric and keeps the rest"),
        ("which are the worst states for cancellation?",
         "a ranking read in business terms: worst is the HIGHEST rate"),
        ("what is ROAS by campaign?",
         "campaigns ranked by the return on each real invested"),
        ("how did the abandoned cart campaign do?",
         "measures it the CRM way: received, opened, bought within 7 days, "
         "openers' response against the control and average ticket"),
        ("and the last newsletter send?",
         "the same yardstick, just for the latest send with a closed "
         "window"),
    ],
    "dica_conversa": (
        "Ratio metrics (average ticket, cancellation, freight share) come with "
        "the math spelled out: the formula shows up with the period's numbers, "
        "and the root cause splits rate effect from mix effect. Campaign "
        "metrics (investment, ROAS, CAC, open rate) only exist by channel, "
        "campaign, region and day: media money has no payment method."
    ),
    "notas": [
        "Revenue uses item prices and excludes freight.",
        "Orders canceled before invoicing count as orders with zero revenue, "
        "so the cancellation rate is not biased.",
        "Orders, revenue, customers, categories and states are Olist's, real. "
        "The campaign layer is SIMULATED and tied to them: each order's "
        "channel and campaign (last click), investment, impressions, clicks, "
        "CRM sends, opens, opt-outs and control group.",
        "Last-click attribution: the order goes entirely to the last campaign "
        "touched. It overstates bottom-of-funnel channels (brand search, "
        "abandoned cart) — which is why CRM is also read by its lift over the "
        "control group, which doesn't depend on attribution.",
        "Every CRM send holds out 10% of the audience as a control group that "
        "gets nothing. With few purchases in the control, lift swings a lot: "
        "read it together with volume.",
        "Investment, ROAS, CAC, CTR, CPC and CRM rates only exist by channel, "
        "campaign, campaign type, region, state and day: an investment row "
        "has no category, payment method, price band, status or "
        "new/returning. With one of those filters on, these metrics are left "
        "empty on purpose.",
        "Events planted in the simulation, so the dashboard has something to "
        "find: Black Friday 2017 with 25% higher CPC; Social • Prospecting CPC "
        "35% higher and CTR 20% lower from Jun/2018; WhatsApp repurchase "
        "launched in Mar/2018; and Social • Prospecting budget 2.6x higher by "
        "misconfiguration on the last two days of the base.",
    ],
}
