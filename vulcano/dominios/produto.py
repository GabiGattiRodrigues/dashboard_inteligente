"""
Domínio de Produto e Operação, sobre a mesma base do Olist.

Mesma tabela fato do domínio de Marketing, lente diferente. Aqui a pergunta não
é quanto entrou, é se a promessa feita ao cliente foi cumprida — e onde a
jornada trava.

A jornada
---------
O Olist carimba os quatro eventos da vida de um pedido, e isso é um funil de
verdade, não uma métrica de vendas:

    comprou  →  pagamento aprovou  →  seller postou  →  cliente recebeu

Cada perna tem uma taxa de passagem e um tempo. É o que a área de produto
acompanha: quantos caem em cada etapa, quanto tempo cada trecho leva, e qual
etapa está segurando a jornada inteira.

Todas as taxas do funil contam PEDIDOS DISTINTOS, não itens. Um pedido com
cinco itens é um pedido só na jornada; medir por item faria pedidos grandes
pesarem cinco vezes mais na taxa de aprovação, que é uma decisão por pedido.
"""

from ..semantica import Dimensao, Dominio, Limite, Metrica, indexar

_PEDIDOS = "COUNT(DISTINCT order_id)"


def _etapa(coluna: str) -> str:
    """Pedidos distintos que alcançaram um evento da jornada."""
    return f"COUNT(DISTINCT CASE WHEN {coluna} = 1 THEN order_id END)"


METRICAS = indexar([
    # --- volume ---------------------------------------------------------- #
    Metrica("pedidos", "Pedidos", _PEDIDOS, formato="inteiro", grao="grosso",
            num_aditivo=False, entidade="pedido",
            descricao="Pedidos distintos no período."),

    # --- jornada: taxas de passagem -------------------------------------- #
    Metrica("passou_aprovacao", "Passou da aprovação",
            _etapa("ev_aprovou"), den_sql=_PEDIDOS,
            formato="percentual", casas=1, grao="grosso", num_aditivo=False,
            entidade="pedido",
            formula="Pedidos aprovados ÷ Pedidos criados",
            descricao="Pedidos cujo pagamento foi aprovado, sobre os criados. "
                      "Primeira perna do funil."),
    Metrica("passou_postagem", "Passou da postagem",
            _etapa("ev_postou"), den_sql=_etapa("ev_aprovou"),
            formato="percentual", casas=1, grao="grosso", num_aditivo=False,
            entidade="pedido",
            formula="Pedidos postados ÷ Pedidos aprovados",
            descricao="Pedidos postados ao transportador, sobre os aprovados. "
                      "Segunda perna: depende do seller."),
    Metrica("passou_entrega", "Passou da entrega",
            _etapa("ev_entregou"), den_sql=_etapa("ev_postou"),
            formato="percentual", casas=1, grao="grosso", num_aditivo=False,
            entidade="pedido",
            formula="Pedidos entregues ÷ Pedidos postados",
            descricao="Pedidos entregues ao cliente, sobre os postados. "
                      "Terceira perna: depende da logística."),
    Metrica("jornada_completa", "Jornada completa",
            _etapa("ev_entregou"), den_sql=_PEDIDOS,
            formato="percentual", casas=1, grao="grosso", num_aditivo=False,
            entidade="pedido",
            formula="Pedidos entregues ÷ Pedidos criados",
            descricao="Pedidos que percorreram a jornada inteira, da compra à "
                      "entrega. É o produto das três pernas."),

    # --- jornada: tempo de cada perna ------------------------------------ #
    Metrica("h_ate_aprovar", "Horas até aprovar", "SUM(h_ate_aprovar)",
            den_sql="COUNT(h_ate_aprovar)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma das horas ÷ Pedidos aprovados",
            descricao="Horas entre a compra e a aprovação do pagamento."),
    Metrica("d_aprovar_postar", "Dias até postar", "SUM(d_aprovar_postar)",
            den_sql="COUNT(d_aprovar_postar)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias ÷ Pedidos postados",
            descricao="Dias entre a aprovação e a postagem ao transportador."),
    Metrica("d_postar_entregar", "Dias em trânsito", "SUM(d_postar_entregar)",
            den_sql="COUNT(d_postar_entregar)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias ÷ Pedidos entregues",
            descricao="Dias entre a postagem e a chegada ao cliente."),

    # --- promessa e satisfação -------------------------------------------- #
    Metrica("prazo_entrega", "Prazo total", "SUM(dias_entrega)",
            den_sql="COUNT(dias_entrega)", formato="decimal", casas=1,
            bom_quando_sobe=False,
            formula="Soma dos dias ÷ Entregas concluídas",
            descricao="Dias entre a compra e a entrega, ponta a ponta."),
    Metrica("taxa_atraso", "Taxa de atraso", "SUM(CAST(atraso AS DOUBLE))",
            den_sql="COUNT(atraso)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="Entregas atrasadas ÷ Entregas concluídas",
            descricao="Entregas que passaram da data prometida ao cliente."),
    Metrica("folga_prazo", "Folga do prazo", "SUM(folga_prazo)",
            den_sql="COUNT(folga_prazo)", formato="decimal", casas=1,
            formula="Soma da folga ÷ Entregas concluídas",
            descricao="Dias de antecedência sobre a data prometida. "
                      "Negativo significa entrega atrasada."),
    Metrica("nota_media", "Nota média", "SUM(review_score)",
            den_sql="COUNT(review_score)", formato="decimal", casas=2,
            formula="Soma das notas ÷ Avaliações recebidas",
            descricao="Média das avaliações de 1 a 5 recebidas."),
    Metrica("pct_nota_baixa", "Avaliações 1 e 2", "SUM(nota_baixa)",
            den_sql="COUNT(nota_baixa)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="Avaliações 1 ou 2 ÷ Avaliações recebidas",
            descricao="Fatia das avaliações que veio como 1 ou 2 estrelas."),
    Metrica("taxa_cancelamento", "Taxa de cancelamento",
            "COUNT(DISTINCT CASE WHEN cancelado = 1 THEN order_id END)",
            den_sql=_PEDIDOS, formato="percentual", casas=2,
            bom_quando_sobe=False, grao="grosso", num_aditivo=False,
            entidade="pedido",
            formula="Pedidos cancelados ÷ Pedidos",
            descricao="Pedidos cancelados ou indisponíveis sobre o total."),
    Metrica("itens_por_pedido", "Itens por pedido", "SUM(itens)", den_sql=_PEDIDOS,
            formato="decimal", grao="grosso", casas=2,
            formula="Itens vendidos ÷ Pedidos",
            descricao="Tamanho médio da cesta."),
])

DIMENSOES = indexar([
    Dimensao("etapa_jornada", "Etapa da jornada", "etapa_jornada",
             unica_por=("pedido",),
             descricao="Etapa mais avançada que o pedido alcançou. Serve para "
                       "perguntar quem trava, e onde."),
    Dimensao("categoria", "Categoria", "categoria", nivel="fino", unica_por=(),
             descricao="Categoria do produto comprado."),
    Dimensao("regiao", "Região", "regiao", unica_por=("pedido",),
             descricao="Região do cliente no pedido."),
    Dimensao("estado", "Estado", "estado", unica_por=("pedido",),
             descricao="UF do cliente no pedido."),
    Dimensao("meio_pagamento", "Meio de pagamento", "meio_pagamento",
             unica_por=("pedido",),
             descricao="Meio de pagamento de maior valor no pedido."),
    Dimensao("status", "Status do pedido", "status", unica_por=("pedido",),
             descricao="Situação do pedido no fluxo do marketplace."),
    # Recortes de operação: são estes que respondem "de onde vem a nota baixa"
    # e "qual perna estoura o prazo" sem sair da mesma camada semântica.
    Dimensao("cumpriu_prazo", "Cumprimento do prazo", "cumpriu_prazo",
             unica_por=("pedido",),
             descricao="Se o pedido chegou dentro do prazo prometido, "
                       "atrasado, ou ainda não foi entregue."),
    Dimensao("rota_envio", "Rota do envio", "rota_envio", nivel="fino",
             unica_por=(),
             descricao="Se o item saiu de um vendedor do mesmo estado do "
                       "cliente ou de outro estado — é a perna logística que "
                       "mais pesa no prazo."),
    Dimensao("faixa_nota", "Faixa da nota", "faixa_nota",
             unica_por=("pedido",),
             descricao="Faixa da nota que o cliente deu ao pedido."),
    Dimensao("dia_semana", "Dia da semana", "dia_semana",
             unica_por=("pedido",),
             descricao="Dia da semana da compra."),
    Dimensao("tipo_dia", "Dia útil ou fim de semana", "tipo_dia",
             unica_por=("pedido",),
             descricao="Se a compra caiu em dia útil ou fim de semana."),
])

# O funil, na ordem. Cada passo é (métrica de taxa, rótulo do evento).
FUNIL = [
    ("ev_comprou", "Comprou", None),
    ("ev_aprovou", "Pagamento aprovado", "passou_aprovacao"),
    ("ev_postou", "Postado ao transportador", "passou_postagem"),
    ("ev_entregou", "Entregue ao cliente", "passou_entrega"),
]

DOMINIO = Dominio(
    chave="produto",
    nome="Produto e Operação",
    subtitulo="Jornada do pedido, prazo e satisfação",
    descricao=(
        "Onde a jornada do pedido trava e quanto tempo cada perna leva: da "
        "compra à aprovação do pagamento, da aprovação à postagem, da postagem "
        "à entrega. E se a promessa feita na compra foi cumprida."
    ),
    fonte=(
        "Brazilian E-Commerce Public Dataset by Olist — mesma base de 99 mil "
        "pedidos reais, lida pelos carimbos de cada evento do pedido."
    ),
    simulado=False,
    arquivo="fato_olist.parquet",
    metricas=METRICAS,
    dimensoes=DIMENSOES,
    metricas_painel=["jornada_completa", "passou_aprovacao", "passou_postagem",
                     "passou_entrega", "h_ate_aprovar", "d_aprovar_postar",
                     "d_postar_entregar", "nota_media"],
    # etapa_jornada sai da primeira posição de propósito: dims_filtro[0] é a
    # dimensão PADRÃO do ranking e da causa raiz, e ranquear uma taxa de
    # jornada por etapa da jornada devolve "etapa final: 100%" — verdadeiro,
    # tautológico e inútil. Categoria é o padrão que responde alguma coisa.
    dims_filtro=["categoria", "regiao", "cumpriu_prazo", "rota_envio",
                 "etapa_jornada", "estado", "meio_pagamento", "faixa_nota",
                 "dia_semana", "tipo_dia", "status"],
    metricas_alerta=["jornada_completa", "passou_postagem", "passou_entrega",
                     "d_aprovar_postar", "d_postar_entregar", "nota_media",
                     "taxa_atraso", "prazo_entrega"],
    dims_alerta=["categoria", "regiao", "rota_envio"],
    funil=FUNIL,
    limites=[
        Limite("jornada_completa", "<", 0.95,
               "Abaixo de 95% de jornadas concluídas, alguma perna está "
               "segurando pedido demais."),
        Limite("passou_postagem", "<", 0.97,
               "Postagem abaixo de 97% aponta seller sem despachar."),
        Limite("d_aprovar_postar", ">", 4.0,
               "Acima de 4 dias para postar, o prazo prometido fica em risco "
               "antes mesmo de o pedido sair."),
        Limite("nota_media", "<", 3.9,
               "Abaixo de 3,9 a nota começa a derrubar a conversão."),
        Limite("prazo_entrega", ">", 15.0,
               "Acima de 15 dias médios a reclamação de prazo dispara."),
        Limite("taxa_atraso", ">", 0.10,
               "Acima de 10% de atraso o SLA combinado com o seller quebra."),
        Limite("pct_nota_baixa", ">", 0.20,
               "Uma em cada cinco avaliações negativas é o limiar do time."),
    ],
    sinonimos_metrica={
        "pedidos": ["pedido", "pedidos", "volume"],
        "jornada_completa": ["jornada", "funil", "jornada completa", "ponta a "
                             "ponta", "conclusao", "conversao"],
        "passou_aprovacao": ["passou da aprovacao", "taxa de aprovacao",
                             "aprovou", "aprovado", "etapa de pagamento"],
        "passou_postagem": ["passou da postagem", "taxa de postagem", "postou",
                            "postado", "despacho", "despachado",
                            "seller postou"],
        # "entrega" sozinha e generica demais: ela aparece em "prazo de
        # entrega", que e outra metrica. Sinonimo de funil precisa carregar a
        # ideia de PASSAGEM, senao rouba a pergunta da metrica vizinha.
        "passou_entrega": ["passou da entrega", "taxa de entrega",
                           "entregou", "foi entregue", "chegou ao cliente"],
        "h_ate_aprovar": ["tempo de aprovacao", "horas ate aprovar", "aprovar",
                          "demora para aprovar", "tempo ate aprovar"],
        "d_aprovar_postar": ["tempo de postagem", "dias ate postar", "postar",
                             "demora do seller", "seller", "handling",
                             "tempo do seller", "leva para postar"],
        "d_postar_entregar": ["transito", "em transito", "tempo de transporte",
                              "dias em transito", "tempo de frete"],
        "prazo_entrega": ["prazo", "prazo total", "prazo de entrega",
                          "tempo de entrega", "lead time", "dias de entrega"],
        "taxa_atraso": ["atraso", "atrasado", "atrasos", "sla", "fora do prazo"],
        "folga_prazo": ["folga", "antecedencia", "adiantado"],
        "nota_media": ["nota", "notas", "avaliacao", "avaliacoes", "review",
                       "satisfacao", "estrela", "estrelas"],
        "pct_nota_baixa": ["nota baixa", "notas baixas", "avaliacao negativa",
                           "avaliacoes negativas", "uma estrela", "duas "
                           "estrelas", "detrator", "detratores", "1 e 2",
                           "nota 1", "nota 2", "insatisfeito", "reclamacao"],
        "taxa_cancelamento": ["cancelamento", "cancelado", "cancelados"],
        "itens_por_pedido": ["itens por pedido", "cesta"],
    },
    sinonimos_dimensao={
        "etapa_jornada": ["etapa", "etapas", "jornada", "funil", "estagio",
                          "onde parou", "onde trava"],
        "categoria": ["categoria", "categorias", "produto", "produtos"],
        "regiao": ["regiao", "regioes", "regional"],
        "estado": ["estado", "estados", "uf", "ufs"],
        "meio_pagamento": ["pagamento", "meio de pagamento", "forma de pagamento"],
        "status": ["status", "situacao"],
        "cumpriu_prazo": ["prazo cumprido", "cumprimento do prazo", "no prazo",
                          "atrasado", "dentro do prazo", "fora do prazo"],
        "rota_envio": ["rota", "rota do envio", "mesmo estado", "entre estados",
                       "origem do envio", "vendedor"],
        "faixa_nota": ["faixa da nota", "nota ruim", "nota boa", "avaliacao",
                       "faixa de avaliacao"],
        "dia_semana": ["dia da semana", "dia de semana"],
        "tipo_dia": ["dia util", "fim de semana", "final de semana"],
    },
    perguntas_exemplo=[
        "Onde a jornada trava?",
        "Quanto tempo o seller leva para postar?",
        "Por que a taxa de atraso mudou em relação ao mês passado?",
        "Quais categorias travam mais na postagem?",
        "O prazo de entrega está melhorando?",
        "Tem algo fora do padrão no último dia?",
        "Qual a nota média e o que explica ela?",
    ],
    notas=[
        "As taxas do funil contam pedidos distintos, não itens: aprovar um "
        "pagamento é uma decisão por pedido, e medir por item faria o pedido "
        "de cinco itens pesar cinco vezes.",
        "Prazo, atraso e nota só existem para pedidos já entregues e avaliados. "
        "Pedidos recentes ainda em trânsito ficam de fora dessas médias, o que "
        "torna os últimos dias otimistas por construção — é censura à direita, "
        "não melhora de operação. As taxas do funil sofrem do mesmo efeito: um "
        "pedido de ontem ainda não teve tempo de ser entregue.",
        "A folga do prazo mede a data prometida menos a realizada: valor "
        "negativo é entrega atrasada.",
    ],
    agente_nome="R2",
    agente_rosto="🐕",
    agente_genero="m",
    agente_voz="r2",
    agente_imagem="r2",
    agente_papel=("Cuido de produto e operação. Acompanho a jornada do pedido "
                  "ponta a ponta — compra, aprovação, postagem, entrega — e "
                  "meu trabalho é dizer onde ela trava e há quanto tempo."),
)
