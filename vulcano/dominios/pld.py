"""
Domínio de Compliance e PLD, sobre base SIMULADA — a Ravena.

O fato aqui é o ALERTA: uma linha por regra que disparou para um cliente, com
a data da seleção, a decisão da analista e a data da comunicação. Em cima dele
o motor genérico responde o que a liderança de Compliance acompanha — volume,
falso positivo, prazo, comunicações — e a extensão em `vulcano/pld` responde o
que a analista precisa: quem, especificamente, olhar primeiro.

Falso positivo só conta alerta maduro
-------------------------------------
É o mesmo problema da safra de crédito, com outra roupa. Num alerta de ontem,
só os casos fáceis já foram concluídos — e caso fácil é quase sempre descarte.
Medir falso positivo sobre tudo que já tem decisão faz a taxa dos alertas
recentes parecer pior do que é, e a leitura vira "as regras novas estão
piores" quando o que se vê é a ordem em que a fila anda.

Por isso as taxas de decisão (falso positivo, conversão em comunicação) e o
tempo de análise só entram na conta para alertas com **45 dias ou mais** na
data-base — o prazo máximo de análise da Circular 3.978, art. 43, § 1º. Nessa
idade todo alerta já deveria ter decisão; o que não tem aparece em "fora do
prazo", e não some da conta.
"""

from ..semantica import Dimensao, Dominio, Limite, Metrica, indexar

ALERTA = ("alerta",)
CLIENTE = ("alerta", "cliente")

METRICAS = indexar([
    Metrica("alertas", "Alertas gerados", "SUM(alertas)", formato="inteiro",
            bom_quando_sobe=False,
            descricao="Alertas selecionados pelas regras no período, já com "
                      "a supressão de um alerta por cliente, regra e mês."),
    Metrica("clientes_alertados", "Clientes com alerta",
            "COUNT(DISTINCT cliente_id)", formato="inteiro",
            bom_quando_sobe=False, num_aditivo=False, entidade="cliente",
            descricao="Clientes distintos com pelo menos um alerta no "
                      "período. Um cliente com três regras conta uma vez."),
    Metrica("valor_envolvido", "Valor envolvido", "SUM(valor_envolvido)",
            formato="moeda", bom_quando_sobe=False,
            descricao="Soma do valor movimentado na janela de cada alerta "
                      "(7 ou 30 dias, conforme a regra)."),
    Metrica("taxa_falso_positivo", "Falso positivo", "SUM(descartado_m)",
            den_sql="COUNT(descartado_m)", formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="Alertas descartados ÷ Alertas maduros com decisão",
            descricao="Parcela dos alertas descartados na análise. Só entram "
                      "alertas com 45 dias ou mais na data-base — nos "
                      "recentes, só os casos fáceis já foram decididos."),
    Metrica("taxa_comunicacao", "Conversão em comunicação", "SUM(comunicado_m)",
            den_sql="COUNT(comunicado_m)", formato="percentual", casas=1,
            formula="Alertas comunicados ao Coaf ÷ Alertas maduros com decisão",
            descricao="Parcela dos alertas que terminou em comunicação ao "
                      "Coaf. É a medida de precisão da regra. Só alertas "
                      "maduros."),
    Metrica("comunicacoes", "Comunicações ao Coaf", "SUM(comunicado_maduro)",
            formato="inteiro", bom_quando_sobe=False,
            descricao="Alertas que terminaram em comunicação de operação "
                      "suspeita, pela data de seleção. Só alertas maduros: "
                      "o mês corrente ainda não teve tempo de comunicar, e "
                      "contar tudo faria parecer uma queda."),
    Metrica("pct_no_prazo", "Análises no prazo de 45 dias", "SUM(no_prazo)",
            den_sql="COUNT(no_prazo)", formato="percentual", casas=1,
            formula="Alertas analisados em até 45 dias ÷ Alertas com prazo já "
                    "verificável",
            descricao="Circular 3.978, art. 43, § 1º. Conta os alertas "
                      "concluídos e os abertos que já passaram de 45 dias; "
                      "alerta aberto dentro do prazo ainda não tem veredito."),
    Metrica("fora_do_prazo", "Alertas fora do prazo", "SUM(fora_do_prazo)",
            formato="inteiro", bom_quando_sobe=False,
            descricao="Alertas analisados depois de 45 dias da seleção, ou "
                      "ainda abertos com mais de 45 dias na data-base."),
    Metrica("dias_analise", "Tempo médio de análise (dias)",
            "SUM(dias_analise)", den_sql="COUNT(dias_analise)",
            formato="decimal", casas=1, bom_quando_sobe=False,
            formula="Soma dos dias entre seleção e decisão ÷ Alertas maduros "
                    "com decisão",
            descricao="Dias corridos entre a seleção e a decisão. Só alertas "
                      "maduros, pelo mesmo motivo do falso positivo."),
    Metrica("em_aberto", "Alertas em aberto na data-base", "SUM(em_aberto)",
            formato="inteiro", bom_quando_sobe=False,
            descricao="Dos alertas selecionados no período, quantos seguiam "
                      "sem decisão em 31/08/2026. A fila de qualquer outra "
                      "data está na aba Clientes em atenção."),
    Metrica("com_no_prazo", "Comunicações até D+1 útil", "SUM(com_no_prazo)",
            den_sql="COUNT(com_no_prazo)", formato="percentual", casas=1,
            formula="Comunicações enviadas até o dia útil seguinte à decisão "
                    "÷ Comunicações",
            descricao="Circular 3.978, art. 48, § 2º: a comunicação vai até o "
                      "dia útil seguinte ao da decisão de comunicar."),
])

DIMENSOES = indexar([
    Dimensao("regra", "Regra", "regra", unica_por=ALERTA,
             descricao="Regra de monitoramento que selecionou o alerta."),
    Dimensao("situacao_4001", "Situação da Carta Circular 4.001",
             "situacao_4001", unica_por=ALERTA,
             descricao="Inciso e alínea do art. 1º da 4.001 que a regra "
                       "traduz."),
    Dimensao("tipo_cliente", "Tipo de cliente", "tipo_cliente",
             unica_por=CLIENTE,
             descricao="Titular (PF), empresa cliente ou estabelecimento."),
    Dimensao("produto", "Produto", "produto", unica_por=ALERTA,
             descricao="Onde o sinal nasce: conta digital, cartão, recarga "
                       "ou cadastro."),
    Dimensao("regiao", "Região", "regiao", unica_por=CLIENTE,
             descricao="Região do cliente."),
    Dimensao("uf", "UF", "uf", unica_por=CLIENTE, descricao="UF do cliente."),
    Dimensao("area", "Área de risco", "area", unica_por=CLIENTE,
             descricao="Município em região de fronteira (4.001, XVII, a) "
                       "ou demais áreas."),
    Dimensao("faixa_risco", "Risco cadastral", "faixa_risco",
             unica_por=CLIENTE,
             descricao="Classificação de risco do cliente (Circular 3.978, "
                       "art. 20)."),
    Dimensao("pep", "PEP", "pep", unica_por=CLIENTE,
             descricao="Pessoa exposta politicamente."),
    Dimensao("decisao", "Decisão", "decisao", unica_por=ALERTA,
             descricao="Descartado, monitoramento reforçado, comunicado ao "
                       "Coaf ou ainda em análise na data-base."),
    Dimensao("faixa_valor", "Faixa de valor", "faixa_valor", unica_por=ALERTA,
             descricao="Valor envolvido no alerta."),
    Dimensao("tipo_regra", "Tipo de regra", "tipo_regra", unica_por=ALERTA,
             descricao="Volumétrica, comportamental ou cadastral."),
    Dimensao("ciclo", "Frequência", "ciclo", unica_por=ALERTA,
             descricao="Regra diária ou do ciclo mensal por lotes."),
    Dimensao("segmento", "Segmento do cliente", "segmento", unica_por=CLIENTE,
             descricao="Porte da empresa empregadora, porte da empresa "
                       "cliente ou categoria do estabelecimento."),
])

DOMINIO = Dominio(
    chave="pld",
    nome="Compliance e PLD",
    subtitulo="Monitoramento transacional, fila de análise e Coaf",
    descricao=(
        "Quantos alertas as regras selecionam, quanto vira falso positivo e "
        "se a fila cabe no prazo de 45 dias — e, cliente a cliente, quem se "
        "enquadra em qual situação da Carta Circular 4.001 e por onde começar."
    ),
    fonte=(
        "BASE SIMULADA. Nenhuma instituição publica os próprios alertas de "
        "PLD, então a operação foi gerada com estrutura declarada: uma "
        "plataforma fictícia de benefícios com conta digital, dez regras "
        "traduzidas da Carta Circular 4.001, supressão mensal, uma fila de "
        "analistas com capacidade limitada e tipologias plantadas (contas de "
        "passagem, troca de benefício na fronteira, fracionamento). As regras "
        "e as referências normativas são reais; os clientes, não."
    ),
    simulado=True,
    arquivo="fato_pld.parquet",
    metricas=METRICAS,
    dimensoes=DIMENSOES,
    metricas_painel=["alertas", "clientes_alertados", "valor_envolvido",
                     "taxa_falso_positivo", "taxa_comunicacao",
                     "comunicacoes", "pct_no_prazo", "dias_analise"],
    dims_filtro=["regra", "situacao_4001", "tipo_cliente", "produto",
                 "regiao", "uf", "area", "faixa_risco", "pep", "decisao",
                 "faixa_valor", "tipo_regra", "ciclo", "segmento"],
    # Valor envolvido fica fora da varredura: num dia com um alerta só, o
    # valor daquele alerta vira "100% do desvio" de qualquer segmento.
    metricas_alerta=["alertas", "clientes_alertados"],
    dims_alerta=["regra", "regiao", "tipo_cliente"],
    limites=[
        Limite("pct_no_prazo", "<", 1.0,
               "Circular 3.978, art. 43, § 1º: a análise não pode passar de "
               "45 dias da seleção. Abaixo de 100% não é desempenho ruim, é "
               "descumprimento."),
        Limite("com_no_prazo", "<", 1.0,
               "Circular 3.978, art. 48, § 2º: a comunicação vai até o dia "
               "útil seguinte ao da decisão."),
        Limite("taxa_falso_positivo", ">", 0.92,
               "Acima de 92% de descarte a regra consome a equipe sem "
               "selecionar nada — é hora de recalibrar, com registro na "
               "avaliação interna de risco."),
    ],
    sinonimos_metrica={
        "alertas": ["alerta gerado", "alertas gerados", "volume de alertas",
                    "quantos alertas", "selecionados", "selecao"],
        "clientes_alertados": ["clientes com alerta", "clientes alertados",
                               "quantos clientes"],
        "valor_envolvido": ["valor envolvido", "valor movimentado",
                            "valor alertado", "montante"],
        "taxa_falso_positivo": ["falso positivo", "falsos positivos",
                                "descarte", "descartados", "ruido",
                                "taxa de descarte"],
        "taxa_comunicacao": ["conversao", "conversão em comunicação",
                             "precisao", "precisão", "taxa de comunicação"],
        "comunicacoes": ["comunicacoes", "comunicações", "comunicado",
                         "comunicados", "coaf", "ros", "operação suspeita"],
        "pct_no_prazo": ["no prazo", "dentro do prazo", "sla",
                         "prazo de 45 dias", "cumprimento do prazo"],
        "fora_do_prazo": ["fora do prazo", "vencidos", "vencido",
                          "atrasados", "estourou o prazo"],
        "dias_analise": ["tempo de análise", "tempo médio", "dias de análise",
                         "demora", "lead time"],
        "em_aberto": ["em aberto", "abertos", "pendentes"],
        "com_no_prazo": ["d+1", "dia útil seguinte", "prazo de comunicação"],
    },
    sinonimos_dimensao={
        "regra": ["regra", "regras", "cenário", "cenarios", "parametrização"],
        "situacao_4001": ["situação", "4001", "4.001", "enquadramento",
                          "tipologia", "inciso", "alinea"],
        "tipo_cliente": ["tipo de cliente", "pf ou pj", "pessoa física",
                         "pessoa jurídica"],
        "produto": ["produto", "produtos", "pix", "cartão", "recarga",
                    "canal"],
        "regiao": ["região", "regioes", "regional"],
        "uf": ["uf", "estado", "estados"],
        "area": ["fronteira", "área de risco", "região de risco"],
        "faixa_risco": ["risco cadastral", "classificação de risco",
                        "faixa de risco", "risco do cliente"],
        "pep": ["pep", "exposta politicamente"],
        "decisao": ["decisão", "decisoes", "desfecho", "resultado da análise"],
        "faixa_valor": ["faixa de valor", "tamanho do alerta"],
        "tipo_regra": ["tipo de regra", "volumétrica", "comportamental",
                       "cadastral"],
        "ciclo": ["frequência", "ciclo mensal", "diária"],
        "segmento": ["segmento", "porte", "categoria"],
    },
    perguntas_exemplo=[
        "Quais clientes precisam de atenção primeiro?",
        "Qual regra tem mais falso positivo?",
        "O que explica a variação dos alertas contra o mês passado?",
        "O que diz a Circular 3.978 sobre o prazo de análise?",
        "Quantas comunicações ao Coaf no período?",
        "Os alertas estão crescendo?",
        "Me mostra o dossiê do cliente T-01160?",
    ],
    agente_nome="Ravena",
    agente_rosto="🐦‍⬛",
    agente_genero="f",
    agente_voz="ravena",
    agente_imagem="ravena",
    agente_papel=("Cuido do monitoramento de PLD: das regras que selecionam, "
                  "da fila que precisa caber em 45 dias e de cada cliente que "
                  "se enquadra na Carta Circular 4.001. Trago o indício e a "
                  "norma — a decisão de comunicar é sempre da analista."),
    extensao="vulcano.pld.agente",
    notas=[
        "DADO SIMULADO. A empresa, os clientes e os estabelecimentos são "
        "fictícios; documentos aparecem mascarados. As regras e as "
        "referências normativas são reais.",
        "Falso positivo, conversão em comunicação e tempo de análise só contam "
        "alertas com 45 dias ou mais em 31/08/2026. Nos recentes só os casos "
        "fáceis já foram decididos, e a taxa sairia distorcida — por isso a "
        "série dessas métricas termina 45 dias antes do fim.",
        "Supressão: um alerta por cliente, por regra, por mês. A mesma conta "
        "de passagem não gera um alerta por dia.",
        "O corte da R01 caiu de 4× para 3× a renda em 01/03/2026. A quebra no "
        "volume de alertas nessa data é mudança de política, não de "
        "comportamento dos clientes.",
        "\"Alertas em aberto\" é a posição em 31/08/2026. A fila de qualquer "
        "outra data é reconstruída na aba Clientes em atenção.",
    ],
)
