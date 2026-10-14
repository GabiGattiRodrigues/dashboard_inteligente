"""
Domínio de Logística, sobre a base pública do Olist -- o agente é o Vulcão.

Produto e Operação (o R2) já olha a jornada do pedido: onde trava, quanto
tempo cada perna leva. Logística faz outra pergunta, a da manhã de quem cuida
da entrega: **o que venceu e não chegou, de quem é a vez de agir, e se o atraso
de hoje é ruído ou é a malha saindo do controle.**

Três decisões de modelagem
--------------------------
1. **A data da linha é a data prometida**, não a da compra. Pela data da
   compra, o pedido de ontem ainda não teve tempo de atrasar e os últimos
   dias saem sempre bonitos. Pela data prometida, todo pedido do período já
   venceu.
2. **Pedido que nunca chegou conta como fora do prazo.** É o critério do case
   da SBF: travado não é "ainda sem dado", é a pior experiência possível.
3. **A régua D+3 / D+7 vem de dado, não de costume.** Para cada dia depois do
   prometido, mede-se quantos dos pedidos ainda pendentes acabam chegando (o
   ponto de não retorno), com intervalo de Wilson. Enquanto a chance é alta,
   cobra-se a transportadora; quando cai, é hora de falar com o cliente.

O que é próprio deste domínio (a fila de travados numa data, a curva do ponto
de não retorno e o gráfico de controle por origem) mora em
`vulcano/logistica/`. O resto -- alertas, comparação, causa raiz, agente --
é o mesmo motor dos outros domínios.
"""

from ..semantica import Dimensao, Dominio, Limite, Metrica, indexar

_P = ("pedido",)

METRICAS = indexar([
    # --- volume ---------------------------------------------------------- #
    Metrica("pedidos", "Pedidos vencendo", "COUNT(*)", formato="inteiro",
            grao="grosso",
            descricao="Pedidos cuja data prometida ao cliente caiu no "
                      "período. É a base de todas as taxas deste painel."),

    # --- promessa cumprida ----------------------------------------------- #
    Metrica("pct_no_prazo", "No prazo", "SUM(no_prazo)", den_sql="COUNT(*)",
            formato="percentual", casas=1,
            formula="Entregues até a data prometida ÷ Pedidos vencendo",
            descricao="Fatia dos pedidos que chegou até a data prometida. "
                      "Pedido que nunca chegou conta como fora do prazo."),
    Metrica("pct_fora_prazo", "Fora do prazo", "SUM(1 - no_prazo)",
            den_sql="COUNT(*)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="(Atrasados + Não entregues) ÷ Pedidos vencendo",
            descricao="O complemento do 'no prazo': entregues com atraso mais "
                      "os que nunca chegaram. É a taxa que o gráfico de "
                      "controle acompanha."),
    Metrica("pct_atraso_grave", "Atraso grave", "SUM(atraso_grave)",
            den_sql="COUNT(*)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="(Atrasos de mais de 7 dias + Não entregues) ÷ Pedidos "
                    "vencendo",
            descricao="Pedidos que passaram da régua do D+7: chegaram mais "
                      "de uma semana depois do prometido, ou não chegaram."),
    Metrica("pct_nao_entregue", "Nunca chegaram", "SUM(nao_entregue)",
            den_sql="COUNT(*)", formato="percentual", casas=2,
            bom_quando_sobe=False,
            formula="Pedidos sem entrega até o corte da base ÷ Pedidos "
                    "vencendo",
            descricao="Pedidos que não tinham chegado até o último dia da "
                      "base (17/out/2018) — travados ou extraviados."),
    Metrica("valor_fora_prazo", "Valor fora do prazo",
            "SUM(CASE WHEN no_prazo = 0 THEN valor ELSE 0 END)",
            formato="moeda", bom_quando_sobe=False,
            descricao="Valor (produtos + frete) dos pedidos que chegaram "
                      "atrasados ou não chegaram."),

    # --- tempo ------------------------------------------------------------ #
    Metrica("dias_atraso", "Atraso médio", "SUM(dias_atraso)",
            den_sql="COUNT(dias_atraso)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias de atraso ÷ Entregas atrasadas",
            descricao="Quantos dias depois do prometido chegou, em média, "
                      "quem chegou atrasado."),
    Metrica("dias_promessa", "Prazo prometido", "SUM(dias_promessa)",
            den_sql="COUNT(dias_promessa)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias prometidos ÷ Pedidos",
            descricao="Dias entre a compra e a data prometida no checkout."),
    Metrica("lead_time", "Prazo realizado", "SUM(lead_time)",
            den_sql="COUNT(lead_time)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias da compra à entrega ÷ Entregues",
            descricao="Dias entre a compra e a entrega, ponta a ponta."),
    Metrica("folga", "Folga média", "SUM(folga)", den_sql="COUNT(folga)",
            formato="decimal", casas=1,
            formula="Soma de (prometido − entregue) ÷ Entregues",
            descricao="Dias de antecedência sobre a data prometida. Folga "
                      "grande demais é prazo longo no checkout sem motivo."),

    # --- quem atrasou: seller e transporte --------------------------------- #
    Metrica("pct_seller_no_prazo", "Seller postou no prazo",
            "SUM(seller_no_prazo)", den_sql="SUM(postou)",
            formato="percentual", casas=1,
            formula="Postados até o limite do seller ÷ Postados",
            descricao="Pedidos que o seller postou até o limite que o "
                      "marketplace deu a ele. É o SLA da primeira perna."),
    Metrica("d_postagem", "Dias até postar", "SUM(d_postagem)",
            den_sql="COUNT(d_postagem)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias da aprovação à postagem ÷ Postados",
            descricao="Quanto o seller leva, da aprovação do pagamento até "
                      "entregar à transportadora."),
    Metrica("d_transito", "Dias em trânsito", "SUM(d_transito)",
            den_sql="COUNT(d_transito)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias da postagem à entrega ÷ Entregues",
            descricao="Quanto a transportadora leva, da postagem até a casa "
                      "do cliente."),
    Metrica("pct_atraso_seller", "Atraso que começou no seller",
            "SUM(atraso_seller)", den_sql="SUM(1 - no_prazo)",
            formato="percentual", casas=1, bom_quando_sobe=False,
            formula="Atrasos com seller fora do limite ÷ Atrasos",
            descricao="Dos pedidos fora do prazo, quantos o seller postou "
                      "depois do limite (ou nem postou). O resto é "
                      "transporte. Diz para quem ligar primeiro."),
    Metrica("pct_promessa_folgada", "Promessa folgada", "SUM(promessa_folgada)",
            den_sql="SUM(entregue)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="Entregues 10+ dias antes do prometido ÷ Entregues",
            descricao="Entregas que chegaram dez dias ou mais antes da data "
                      "prometida. Prazo longo demais no checkout custa "
                      "conversão sem comprar nota."),
    Metrica("frete_medio", "Frete médio", "SUM(frete)", den_sql="COUNT(*)",
            formato="moeda", casas=2, bom_quando_sobe=False,
            formula="Frete cobrado ÷ Pedidos",
            descricao="Frete cobrado do cliente, por pedido."),
    Metrica("pct_frete", "Frete sobre o valor", "SUM(frete)",
            den_sql="SUM(valor_produtos)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="Frete ÷ Valor dos produtos",
            descricao="Quanto o frete pesa sobre o valor dos produtos do "
                      "pedido."),
    Metrica("nota_atrasados", "Nota de quem atrasou",
            "SUM(CASE WHEN no_prazo = 0 THEN nota END)",
            den_sql="COUNT(CASE WHEN no_prazo = 0 THEN nota END)",
            formato="decimal", casas=2,
            formula="Soma das notas dos atrasados ÷ Avaliações dos atrasados",
            descricao="Nota média dos pedidos que chegaram fora do prazo. "
                      "Comparada com a nota geral, é o custo do atraso em "
                      "satisfação."),

    # --- régua D+3 / D+7 --------------------------------------------------- #
    Metrica("passaram_d3", "Passaram do D+3", "SUM(pend_d3)",
            formato="inteiro", bom_quando_sobe=False,
            descricao="Pedidos ainda não entregues três dias depois do "
                      "prometido. É quem entra na régua: cobrar a "
                      "transportadora (ou o seller, se nem postou)."),
    Metrica("chegam_d3", "Ainda chegam após D+3", "SUM(cheg_d3)",
            den_sql="SUM(pend_d3)", formato="percentual", casas=1,
            formula="Pendentes no D+3 que chegaram depois ÷ Pendentes no D+3",
            descricao="De quem passou do D+3, quantos ainda chegaram. Chance "
                      "alta = vale cobrar e esperar."),
    Metrica("passaram_d7", "Passaram do D+7", "SUM(pend_d7)",
            formato="inteiro", bom_quando_sobe=False,
            descricao="Pedidos ainda não entregues sete dias depois do "
                      "prometido. É quem pede contato proativo com o cliente: "
                      "reenviar ou estornar."),
    Metrica("chegam_d7", "Ainda chegam após D+7", "SUM(cheg_d7)",
            den_sql="SUM(pend_d7)", formato="percentual", casas=1,
            formula="Pendentes no D+7 que chegaram depois ÷ Pendentes no D+7",
            descricao="De quem passou do D+7, quantos ainda chegaram. Quando "
                      "essa chance cai, esperar só piora a experiência."),

    # --- consequência ------------------------------------------------------ #
    Metrica("nota_media", "Nota média", "SUM(nota)", den_sql="COUNT(nota)",
            formato="decimal", casas=2,
            formula="Soma das notas ÷ Avaliações recebidas",
            descricao="Média das avaliações de 1 a 5 dos pedidos vencendo "
                      "no período."),
])

DIMENSOES = indexar([
    Dimensao("origem", "Origem", "origem", unica_por=_P,
             descricao="UF do vendedor do item principal do pedido. As seis "
                       "UFs que concentram ~95% dos pedidos aparecem "
                       "sozinhas; o resto vira 'Outras UFs'."),
    Dimensao("rota", "Rota", "rota", unica_por=_P,
             descricao="Se o pedido saiu de vendedor do mesmo estado do "
                       "cliente ou de outro estado."),
    Dimensao("regiao_destino", "Região de destino", "regiao_destino",
             unica_por=_P, descricao="Região do cliente."),
    Dimensao("estado_destino", "UF de destino", "estado_destino",
             nivel="fino", unica_por=_P, descricao="UF do cliente."),
    Dimensao("regiao_origem", "Região de origem", "regiao_origem",
             unica_por=_P, descricao="Região do vendedor."),
    Dimensao("uf_origem", "UF de origem", "uf_origem", nivel="fino",
             unica_por=_P,
             descricao="UF do vendedor, sem agrupar as menores."),
    Dimensao("faixa_promessa", "Prazo prometido", "faixa_promessa",
             unica_por=_P,
             descricao="Faixa de dias prometidos no checkout."),
    Dimensao("dia_semana_compra", "Dia da compra", "dia_semana_compra",
             unica_por=_P,
             descricao="Dia da semana em que o cliente comprou. Compra de "
                       "fim de semana espera o seller voltar a postar."),
    Dimensao("categoria", "Categoria", "categoria", nivel="fino",
             unica_por=_P, descricao="Categoria do item principal."),
    Dimensao("responsavel_atraso", "Quem atrasou", "responsavel_atraso",
             unica_por=_P,
             descricao="Para quem chegou fora do prazo: se o seller postou "
                       "depois do limite (ou nem postou) ou se o atraso foi "
                       "no transporte."),
    Dimensao("porte", "Porte", "porte", unica_por=_P,
             descricao="Peso do pedido: leve, médio, pesado ou muito "
                       "pesado. Carga pesada vai por outra malha."),
    Dimensao("situacao", "Situação da entrega", "situacao", unica_por=_P,
             descricao="No prazo, atrasou até 7 dias, atrasou mais de 7 dias "
                       "ou não entregue."),
    Dimensao("etapa_parada", "Onde parou", "etapa_parada", unica_por=_P,
             descricao="Para quem não chegou: se parou antes da postagem "
                       "(cobrar o seller) ou em trânsito (cobrar a "
                       "transportadora)."),
])

# A régua. Fica aqui, ao lado das métricas que a medem, para a tela, o
# agente e os testes lerem o mesmo número.
REGUA = (
    (3, "Cobrar a transportadora",
     "ou o seller, se o pedido nem foi postado"),
    (7, "Falar com o cliente",
     "contato proativo: reenviar ou estornar, ele escolhe"),
)
REGUA_EN = (
    (3, "Chase the carrier", "or the seller, if the order wasn't even shipped"),
    (7, "Contact the customer",
     "proactive contact: resend or refund, the customer chooses"),
)

DOMINIO = Dominio(
    chave="logistica",
    nome="Logística",
    subtitulo="Pedidos travados, régua D+3/D+7 e controle por origem",
    descricao=(
        "O que venceu e não chegou, de quem é a vez de agir e se o atraso de "
        "hoje é ruído ou é a malha saindo do controle. Fila de travados com a "
        "régua D+3/D+7 e gráfico de controle por origem."
    ),
    fonte=(
        "Brazilian E-Commerce Public Dataset by Olist — dado público real, "
        "96 mil pedidos não cancelados, lidos pela DATA PROMETIDA ao cliente "
        "(fev/2017 a ago/2018). Entrega conhecida até o último evento da "
        "base, 17/out/2018."
    ),
    simulado=False,
    arquivo="fato_logistica.parquet",
    metricas=METRICAS,
    dimensoes=DIMENSOES,
    metricas_painel=["pct_no_prazo", "pct_atraso_grave", "pct_seller_no_prazo",
                     "pct_atraso_seller", "d_postagem", "d_transito",
                     "lead_time", "pct_promessa_folgada", "chegam_d3",
                     "chegam_d7", "frete_medio", "nota_atrasados"],
    dims_filtro=["origem", "rota", "regiao_destino", "responsavel_atraso",
                 "faixa_promessa", "porte", "dia_semana_compra",
                 "estado_destino", "regiao_origem", "uf_origem", "categoria",
                 "situacao", "etapa_parada"],
    metricas_alerta=["pct_no_prazo", "pct_atraso_grave", "pct_seller_no_prazo",
                     "d_transito", "dias_atraso", "lead_time", "pedidos"],
    dims_alerta=["origem", "regiao_destino", "rota"],
    limites=[
        Limite("pct_no_prazo", "<", 0.90,
               "Abaixo de 90% no prazo, um em cada dez clientes já está "
               "esperando além do prometido."),
        Limite("pct_atraso_grave", ">", 0.05,
               "Acima de 5% de atraso grave, a fila do D+7 passa a não caber "
               "no time de atendimento."),
        Limite("pct_seller_no_prazo", "<", 0.90,
               "Abaixo de 90% de postagem no prazo, o atraso nasce antes de o "
               "pedido sair do seller — cobrar transportadora não resolve."),
        Limite("dias_atraso", ">", 10.0,
               "Atraso médio acima de 10 dias: quem atrasa não está "
               "atrasando um pouco, está sumindo."),
    ],
    sinonimos_metrica={
        "pedidos": ["pedidos vencendo", "vencendo", "volume", "quantos pedidos",
                    "pedidos", "venceram"],
        "pct_no_prazo": ["no prazo", "otd", "on time", "entrega no prazo",
                         "pontualidade", "cumprimento do prazo",
                         "promessa cumprida", "nivel de servico", "sla"],
        "pct_fora_prazo": ["fora do prazo", "taxa de atraso", "atraso",
                           "atrasos", "atrasados", "atrasando", "atrasou"],
        "pct_atraso_grave": ["atraso grave", "muito atrasado", "mais de 7 dias",
                             "mais de uma semana", "atraso longo"],
        "pct_nao_entregue": ["nunca chegou", "nunca chegaram", "nao entregue",
                             "nao entregues", "extravio", "extraviado",
                             "extraviados", "perdido", "sumiu"],
        "valor_fora_prazo": ["valor fora do prazo", "valor atrasado",
                             "valor em atraso", "quanto dinheiro",
                             "valor em risco"],
        "dias_atraso": ["atraso medio", "dias de atraso", "quanto atrasa",
                        "tamanho do atraso"],
        "dias_promessa": ["prazo prometido", "promessa", "prazo do checkout",
                          "prazo informado", "quanto prometemos"],
        "lead_time": ["prazo realizado", "lead time", "tempo de entrega",
                      "prazo real", "quanto demora", "dias para entregar"],
        "folga": ["folga", "antecedencia", "adiantado", "sobra de prazo",
                  "prazo sobrando"],
        "passaram_d3": ["passaram do d+3", "d+3", "d3", "cobrar transportadora",
                        "cobranca"],
        "chegam_d3": ["ainda chegam apos d+3", "chegam depois do d+3",
                      "chance no d+3"],
        "passaram_d7": ["passaram do d+7", "d+7", "d7", "reenviar", "estornar",
                        "reenvio", "estorno"],
        "chegam_d7": ["ainda chegam apos d+7", "chegam depois do d+7",
                      "chance no d+7"],
        "nota_media": ["nota", "notas", "avaliacao", "review", "satisfacao",
                       "estrelas"],
        "pct_seller_no_prazo": ["seller no prazo", "sla do seller",
                                "postou no prazo", "postagem no prazo",
                                "seller postou"],
        "d_postagem": ["dias ate postar", "tempo de postagem", "handling",
                       "demora do seller", "tempo do seller"],
        "d_transito": ["transito", "em transito", "dias em transito",
                       "tempo de transporte", "tempo da transportadora"],
        "pct_atraso_seller": ["atraso do seller", "culpa do seller",
                              "do seller ou da transportadora",
                              "atraso que comecou no seller",
                              "seller ou transportadora",
                              "seller ou transporte", "de quem e a culpa"],
        "pct_promessa_folgada": ["promessa folgada", "prazo folgado",
                                 "esta folgada", "folgada demais",
                                 "prazo longo demais", "promessa longa",
                                 "chega muito antes"],
        "frete_medio": ["frete", "frete medio", "custo de frete",
                        "valor do frete"],
        "pct_frete": ["frete sobre o valor", "peso do frete",
                      "frete sobre o pedido"],
        "nota_atrasados": ["nota de quem atrasou", "nota dos atrasados",
                           "satisfacao dos atrasados", "custo do atraso"],
    },
    sinonimos_dimensao={
        "origem": ["origem", "origens", "uf do vendedor", "de onde sai",
                   "de onde saiu", "estado do vendedor", "cd", "centro de "
                   "distribuicao", "polo"],
        "rota": ["rota", "rotas", "mesmo estado", "entre estados",
                 "interestadual"],
        "regiao_destino": ["regiao de destino", "regiao do cliente",
                           "destino", "regiao", "regioes"],
        "estado_destino": ["uf de destino", "estado do cliente", "estado",
                           "estados", "uf", "ufs"],
        "regiao_origem": ["regiao de origem", "regiao do vendedor"],
        "uf_origem": ["uf de origem", "todas as ufs de origem"],
        "faixa_promessa": ["faixa de prazo", "faixa de promessa",
                           "prazo prometido", "tamanho da promessa"],
        "dia_semana_compra": ["dia da compra", "dia da semana", "fim de "
                              "semana", "sabado", "domingo", "segunda"],
        "categoria": ["categoria", "categorias", "produto", "produtos"],
        "situacao": ["situacao", "situacao da entrega", "status da entrega"],
        "responsavel_atraso": ["quem atrasou", "responsavel", "responsavel "
                               "pelo atraso", "por responsavel"],
        "porte": ["porte", "peso", "tamanho", "pesado", "leve"],
        "etapa_parada": ["onde parou", "etapa", "onde trava", "parado onde",
                         "parou onde"],
    },
    perguntas_exemplo=[
        "Quais pedidos estão travados?",
        "Como foi a semana? Qual região puxou?",
        "O atraso é do seller ou da transportadora?",
        "A régua D+3/D+7 faz sentido aqui?",
        "Por que o no prazo caiu em relação ao mês passado?",
        "Qual origem tem mais atraso grave?",
        "A promessa do checkout está folgada demais?",
        "Tem algo fora do padrão no último dia?",
    ],
    guia_conversa=(
        ("quais pedidos estão travados?",
         "monta a fila na data de referência, do mais vencido para o menos, "
         "já com a ação da régua"),
        ("qual origem está fora de controle?",
         "lê o gráfico de controle semanal de cada origem e diz quem passou "
         "do limite"),
        ("a régua D+3/D+7 faz sentido?",
         "mostra quantos ainda chegam em cada dia depois do prometido, com "
         "margem de erro"),
        ("e por que o no prazo caiu?",
         "decompõe a variação por origem e separa taxa de mix"),
        ("e por rota?", "refaz a mesma leitura por rota"),
    ),
    dica_conversa=("Pedido aqui entra pela data em que VENCE, não pela data da "
                   "compra — então todo pedido do período já teve a chance de "
                   "chegar, e quem não chegou conta como atraso. Para ver um "
                   "pedido específico, me passa os 8 primeiros caracteres do "
                   "código."),
    notas=[
        "A data deste domínio é a data prometida ao cliente, não a da compra. "
        "Todo pedido do período já venceu, então não há censura à direita "
        "nas taxas de prazo.",
        "Cancelados e indisponíveis ficam de fora: não são falha de entrega, "
        "são pedido que deixou de existir.",
        "Pedido que nunca chegou conta como fora do prazo e como atraso grave. "
        "'Nunca' quer dizer: até o último evento registrado na base, "
        "17/out/2018 — pelo menos 47 dias depois do prometido.",
        "A fila de travados é montada como estava NA DATA de referência: só "
        "entra o que se sabia naquele dia. O que aconteceu depois aparece "
        "apenas no detalhe de um pedido, marcado como desfecho.",
        "Origem é a UF do vendedor do item de maior valor. 1,3% dos pedidos "
        "têm mais de um vendedor; para o cliente continua sendo uma entrega.",
        "O Olist não informa a transportadora. 'Cobrar a transportadora' "
        "vale para pedido já postado; o que não foi postado é cobrança ao "
        "seller.",
    ],
    agente_nome="Vulcão",
    agente_rosto="🐕",
    agente_genero="m",
    agente_voz="vulcao",
    agente_imagem="vulcao",
    agente_papel=("Cuido da entrega — e adoro! Começo o dia pela fila do que "
                  "venceu e não chegou, digo de quem é a vez de agir (seller, "
                  "transportadora ou atendimento), aviso quando a semana sai "
                  "do controle e qual região puxou, e separo ruído de sinal "
                  "antes de apontar culpado."),
    extensao="vulcano.logistica.agente",
)


# --------------------------------------------------------------------------- #
# English
# --------------------------------------------------------------------------- #

EN = {
    "nome": "Logistics",
    "subtitulo": "Stuck orders, D+3/D+7 rule and control by origin",
    "descricao": (
        "What came due and didn't arrive, whose turn it is to act, and "
        "whether today's delay is noise or the network going out of control. "
        "Stuck-order queue with the D+3/D+7 rule and a control chart by "
        "origin."
    ),
    "fonte": (
        "Brazilian E-Commerce Public Dataset by Olist — real public data, 96k "
        "non-canceled orders, read by the DATE PROMISED to the customer (Feb "
        "2017 to Aug 2018). Deliveries known up to the last event in the "
        "dataset, Oct 17, 2018."
    ),
    "metricas": {
        "pedidos": ("Orders due",
                    "Orders whose promised delivery date fell in the period. "
                    "The base for every rate on this dashboard."),
        "pct_no_prazo": ("On time",
                         "Share of orders delivered by the promised date. An "
                         "order that never arrived counts as late.",
                         "Delivered by the promised date ÷ Orders due"),
        "pct_fora_prazo": ("Late",
                           "The complement of 'on time': late deliveries plus "
                           "orders that never arrived. The rate the control "
                           "chart tracks.",
                           "(Late + Not delivered) ÷ Orders due"),
        "pct_atraso_grave": ("Severely late",
                             "Orders past the D+7 mark: arrived more than a "
                             "week after the promise, or never arrived.",
                             "(Late by more than 7 days + Not delivered) ÷ "
                             "Orders due"),
        "pct_nao_entregue": ("Never arrived",
                             "Orders not delivered by the last day of the "
                             "dataset (Oct 17, 2018) — stuck or lost.",
                             "Orders with no delivery by the cutoff ÷ Orders "
                             "due"),
        "valor_fora_prazo": ("Value late",
                             "Value (products + freight) of orders that "
                             "arrived late or never arrived."),
        "dias_atraso": ("Average delay",
                        "How many days after the promise late orders "
                        "arrived, on average.",
                        "Sum of days late ÷ Late deliveries"),
        "dias_promessa": ("Promised lead time",
                          "Days between purchase and the date promised at "
                          "checkout.", "Sum of promised days ÷ Orders"),
        "lead_time": ("Actual lead time",
                      "Days between purchase and delivery, end to end.",
                      "Sum of days from purchase to delivery ÷ Delivered"),
        "folga": ("Average slack",
                  "Days ahead of the promised date. Too much slack is a long "
                  "checkout promise for no reason.",
                  "Sum of (promised − delivered) ÷ Delivered"),
        "passaram_d3": ("Past D+3",
                        "Orders still not delivered three days after the "
                        "promise. They enter the rule: chase the carrier (or "
                        "the seller, if it wasn't even shipped)."),
        "chegam_d3": ("Still arrive after D+3",
                      "Of those past D+3, how many still arrived. High odds = "
                      "worth chasing and waiting.",
                      "Pending at D+3 that arrived later ÷ Pending at D+3"),
        "passaram_d7": ("Past D+7",
                        "Orders still not delivered seven days after the "
                        "promise. They call for proactive contact with the "
                        "customer: resend or refund."),
        "chegam_d7": ("Still arrive after D+7",
                      "Of those past D+7, how many still arrived. When these "
                      "odds drop, waiting only makes things worse.",
                      "Pending at D+7 that arrived later ÷ Pending at D+7"),
        "nota_media": ("Average rating",
                       "Average 1-to-5 rating of the orders due in the "
                       "period.", "Sum of ratings ÷ Reviews received"),
        "pct_seller_no_prazo": ("Seller shipped on time",
                                "Orders the seller shipped by the deadline "
                                "the marketplace gave them. The first leg's "
                                "SLA.",
                                "Shipped by the seller deadline ÷ Shipped"),
        "d_postagem": ("Days to ship",
                       "How long the seller takes from payment approval to "
                       "handing the order to the carrier.",
                       "Sum of days from approval to shipping ÷ Shipped"),
        "d_transito": ("Days in transit",
                       "How long the carrier takes from pickup to the "
                       "customer's door.",
                       "Sum of days from shipping to delivery ÷ Delivered"),
        "pct_atraso_seller": ("Delay that started at the seller",
                              "Of the late orders, how many the seller "
                              "shipped after the deadline (or never). The "
                              "rest is transport. Says who to call first.",
                              "Late with seller past deadline ÷ Late"),
        "pct_promessa_folgada": ("Loose promise",
                                 "Deliveries that arrived ten days or more "
                                 "before the promised date. A checkout "
                                 "promise that's too long costs conversion "
                                 "without buying ratings.",
                                 "Delivered 10+ days early ÷ Delivered"),
        "frete_medio": ("Average freight", "Freight charged per order.",
                        "Freight charged ÷ Orders"),
        "pct_frete": ("Freight over value",
                      "How much freight weighs on the order's product value.",
                      "Freight ÷ Product value"),
        "nota_atrasados": ("Rating of late orders",
                           "Average rating of orders that arrived late. "
                           "Against the overall rating, it's the cost of "
                           "being late in satisfaction.",
                           "Sum of late ratings ÷ Late reviews"),
    },
    "dimensoes": {
        "origem": ("Origin",
                   "State of the seller of the order's main item. The six "
                   "states holding ~95% of orders show on their own; the "
                   "rest become 'Other states'."),
        "rota": ("Route", "Whether the order shipped from a seller in the "
                          "customer's state or from another state."),
        "regiao_destino": ("Destination region", "Customer's region."),
        "estado_destino": ("Destination state", "Customer's state."),
        "regiao_origem": ("Origin region", "Seller's region."),
        "uf_origem": ("Origin state", "Seller's state, without grouping the "
                                      "small ones."),
        "faixa_promessa": ("Promised lead time",
                           "Band of days promised at checkout."),
        "dia_semana_compra": ("Purchase day",
                              "Day of the week the customer bought. A "
                              "weekend purchase waits for the seller to "
                              "start shipping again."),
        "categoria": ("Category", "Category of the main item."),
        "responsavel_atraso": ("Who was late",
                               "For late orders: whether the seller shipped "
                               "past the deadline (or never) or the delay "
                               "happened in transport."),
        "porte": ("Size", "Order weight: light, medium, heavy or very heavy. "
                          "Heavy cargo goes through a different network."),
        "situacao": ("Delivery outcome",
                     "On time, late up to 7 days, late more than 7 days or "
                     "not delivered."),
        "etapa_parada": ("Where it stopped",
                         "For orders that never arrived: whether it stopped "
                         "before shipping (chase the seller) or in transit "
                         "(chase the carrier)."),
    },
    "limites": [
        "Below 90% on time, one in ten customers is already waiting past the "
        "promise.",
        "Above 5% severely late, the D+7 queue no longer fits the customer "
        "service team.",
        "Below 90% shipped on time, the delay starts before the order leaves "
        "the seller — chasing the carrier won't fix it.",
        "Average delay above 10 days: late orders aren't a bit late, they're "
        "disappearing.",
    ],
    "sinonimos_metrica": {
        "pedidos": ["orders due", "due", "order volume", "how many orders",
                    "orders"],
        "pct_no_prazo": ["on time", "on-time", "otd", "on-time delivery",
                         "punctuality",
                         "promise kept", "service level", "sla"],
        "pct_fora_prazo": ["late", "late rate", "lateness", "delays",
                           "delayed", "late orders"],
        "pct_atraso_grave": ["severely late", "very late", "more than 7 days",
                             "more than a week", "long delay"],
        "pct_nao_entregue": ["never arrived", "not delivered", "undelivered",
                             "lost", "lost orders", "missing"],
        "valor_fora_prazo": ["value late", "late value", "value at risk",
                             "how much money"],
        "dias_atraso": ["average delay", "days late", "how late"],
        "dias_promessa": ["promised lead time", "promise", "checkout promise",
                          "how much we promise"],
        "lead_time": ["actual lead time", "lead time", "delivery time",
                      "how long it takes", "days to deliver"],
        "folga": ["slack", "days early", "ahead of time"],
        "passaram_d3": ["past d+3", "chase the carrier"],
        "chegam_d3": ["still arrive after d+3", "odds at d+3"],
        "passaram_d7": ["past d+7", "resend", "refund"],
        "chegam_d7": ["still arrive after d+7", "odds at d+7"],
        "nota_media": ["rating", "ratings", "review", "satisfaction", "stars"],
        "pct_seller_no_prazo": ["seller on time", "seller sla",
                                "shipped on time", "seller shipped"],
        "d_postagem": ["days to ship", "handling time", "seller time"],
        "d_transito": ["transit", "in transit", "days in transit",
                       "carrier time"],
        "pct_atraso_seller": ["seller delay", "seller's fault",
                              "seller's or the carrier's",
                              "seller or carrier", "whose fault"],
        "pct_promessa_folgada": ["loose promise", "promise too long",
                                 "too loose",
                                 "arrives way early"],
        "frete_medio": ["freight", "average freight", "shipping cost"],
        "pct_frete": ["freight over value", "freight share"],
        "nota_atrasados": ["rating of late orders", "late orders rating",
                           "cost of being late"],
    },
    "sinonimos_dimensao": {
        "origem": ["origin", "origins", "seller state", "where it ships from",
                   "hub", "distribution center"],
        "rota": ["route", "routes", "same state", "interstate"],
        "regiao_destino": ["destination region", "customer region",
                           "destination", "region", "regions"],
        "estado_destino": ["destination state", "customer state", "state",
                           "states"],
        "regiao_origem": ["origin region", "seller region"],
        "uf_origem": ["origin state", "all origin states"],
        "faixa_promessa": ["promise band", "lead time band"],
        "dia_semana_compra": ["purchase day", "day of week", "weekend",
                              "saturday", "sunday", "monday"],
        "categoria": ["category", "categories", "product"],
        "situacao": ["delivery outcome", "outcome", "delivery status"],
        "responsavel_atraso": ["who was late", "responsible", "by responsible"],
        "porte": ["size", "weight", "heavy", "light"],
        "etapa_parada": ["where it stopped", "stage", "where it got stuck"],
    },
    "perguntas_exemplo": [
        "Which orders are stuck?",
        "How did the week go? Which region drove it?",
        "Is the delay the seller's or the carrier's?",
        "Does the D+3/D+7 rule make sense here?",
        "Why did on-time drop vs last month?",
        "Which origin has the most severe delays?",
        "Is the checkout promise too loose?",
        "Is anything out of pattern on the last day?",
    ],
    "guia_conversa": [
        ("which orders are stuck?",
         "builds the queue on the reference date, most overdue first, with "
         "the rule's action already set"),
        ("which origin is out of control?",
         "reads each origin's weekly control chart and says who crossed the "
         "limit"),
        ("does the D+3/D+7 rule make sense?",
         "shows how many still arrive on each day after the promise, with a "
         "margin of error"),
        ("and why did on-time drop?",
         "breaks the change down by origin and separates rate from mix"),
        ("and by route?", "redoes the same reading by route"),
    ],
    "dica_conversa": (
        "Orders here enter by the date they COME DUE, not the purchase date — "
        "so every order in the period already had its chance to arrive, and "
        "the ones that didn't count as late. To see a specific order, give me "
        "the first 8 characters of its code."
    ),
    "notas": [
        "This domain's date is the date promised to the customer, not the "
        "purchase date. Every order in the period has already come due, so "
        "there's no right-censoring in the on-time rates.",
        "Canceled and unavailable orders are left out: they aren't a delivery "
        "failure, they're orders that stopped existing.",
        "An order that never arrived counts as late and as severely late. "
        "'Never' means: up to the last event recorded in the dataset, Oct 17, "
        "2018 — at least 47 days after the promise.",
        "The stuck-order queue is built as it stood ON the reference date: "
        "only what was known that day goes in. What happened afterwards shows "
        "up only in a single order's detail, labeled as the outcome.",
        "Origin is the state of the seller of the highest-value item. 1.3% of "
        "orders have more than one seller; to the customer it's still one "
        "delivery.",
        "Olist doesn't say who the carrier is. 'Chase the carrier' applies to "
        "orders already shipped; an order not yet shipped means chasing the "
        "seller.",
    ],
    "agente_papel": (
        "I look after delivery — and I love it! I start the day with the "
        "queue of what came due and didn't arrive, say whose turn it is to "
        "act (seller, carrier or customer service), warn when the week goes "
        "out of control and which region drove it, and separate noise from "
        "signal before pointing fingers."
    ),
}
