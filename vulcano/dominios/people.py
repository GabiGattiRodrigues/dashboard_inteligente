"""
Domínio de People Analytics, sobre base SIMULADA — a Tomoyo.

Ver `scripts/build_people.py` para como o dado foi gerado e o que foi
deliberadamente embutido nele. O app declara em toda tela que este domínio não
usa dado real.

O grão é pessoa-dia: uma linha por pessoa por dia em que ela está ativa. É o
que deixa as contas de RH honestas com o motor genérico:

- **headcount** de um período é a média dos dias, não a soma;
- **turnover** é desligamento sobre pessoa-dia exposta, anualizado. Um mês de
  28 dias e um de 31 comparam na mesma régua, e o peso de cada área na base
  vira o efeito mix da decomposição;
- **turnover precoce** é lido pela safra de admissão, com a mesma censura da
  safra de crédito: quem entrou há menos de 90 dias aparece vazio, nunca zero.

E uma regra que não é de conta, é de ética: a Tomoyo só fala de grupo. Não
existe pergunta sobre uma pessoa, e recorte com menos de GRUPO_MINIMO pessoas
não é mostrado nas respostas próprias dela (ver vulcano/people/agente.py).
"""

from ..semantica import Dimensao, Dominio, Limite, Metrica, indexar

GRUPO_MINIMO = 10

_PESSOA_DIA = "SUM(ativo)"
_F = "genero = 'Feminino'"
_M = "genero = 'Masculino'"

METRICAS = indexar([
    Metrica("headcount", "Headcount médio",
            # O divisor é o número de dias do PERÍODO, não o do segmento. Com
            # COUNT(DISTINCT data) por grupo, a safra admitida no dia 20 teria
            # o headcount dividido por 11 dias em vez de 31 e pareceria três
            # vezes maior -- e a cascata por safra não fecharia. A janela
            # pega o maior número de dias entre os grupos da consulta, que é
            # o período inteiro (e 1 quando a consulta é por dia).
            "SUM(ativo) * 1.0 / MAX(COUNT(DISTINCT data)) OVER ()",
            formato="inteiro",
            formula="Pessoas ativas somadas dia a dia ÷ Dias do período",
            descricao="Média de pessoas ativas por dia no período. É média e "
                      "não soma: somar headcount de 30 dias contaria cada "
                      "pessoa 30 vezes."),
    Metrica("admissoes", "Admissões", "SUM(admissao)", formato="inteiro",
            contagem_esparsa=True,
            descricao="Pessoas contratadas no período."),
    Metrica("desligamentos", "Desligamentos", "SUM(desligamento)",
            formato="inteiro", contagem_esparsa=True, bom_quando_sobe=False,
            descricao="Pessoas desligadas no período, voluntária ou "
                      "involuntariamente."),
    Metrica("turnover", "Turnover (a.a.)", "SUM(desligamento) * 365.0",
            den_sql=_PESSOA_DIA, formato="percentual", casas=1,
            bom_quando_sobe=False,
            formula="Desligamentos × 365 ÷ Pessoa-dia ativa",
            descricao="Desligamentos sobre a base exposta, anualizado: quanto "
                      "da empresa sairia em um ano se o ritmo do período "
                      "continuasse."),
    Metrica("turnover_voluntario", "Turnover voluntário (a.a.)",
            "SUM(desl_voluntario) * 365.0", den_sql=_PESSOA_DIA,
            formato="percentual", casas=1, bom_quando_sobe=False,
            formula="Pedidos de demissão × 365 ÷ Pessoa-dia ativa",
            descricao="Só quem pediu para sair, anualizado. É o turnover que "
                      "fala de clima, liderança e mercado."),
    Metrica("turnover_involuntario", "Turnover involuntário (a.a.)",
            "SUM(desl_involuntario) * 365.0", den_sql=_PESSOA_DIA,
            formato="percentual", casas=1, bom_quando_sobe=False,
            formula="Desligamentos pela empresa × 365 ÷ Pessoa-dia ativa",
            descricao="Desligamentos por iniciativa da empresa, inclusive fim "
                      "de contrato de temporário, anualizado."),
    Metrica("turnover_precoce", "Turnover precoce (90 dias)",
            "SUM(saiu_90d)", den_sql="COUNT(saiu_90d)", formato="percentual",
            casas=1, bom_quando_sobe=False,
            formula="Admitidos que saíram em até 90 dias ÷ Admitidos de safra madura",
            descricao="Das pessoas admitidas no período, quantas saíram em até "
                      "90 dias. Lido na data da ADMISSÃO: só safras com 90 "
                      "dias completos entram na conta."),
    Metrica("absenteismo", "Absenteísmo", "SUM(horas_ausencia)",
            den_sql="SUM(horas_previstas)", formato="percentual", casas=2,
            bom_quando_sobe=False,
            formula="Horas de ausência ÷ Horas previstas",
            descricao="Horas de ausência não planejada sobre as horas de "
                      "trabalho previstas em dia útil."),
    Metrica("enps", "eNPS", "(SUM(promotor) - SUM(detrator)) * 100.0",
            den_sql="SUM(respondeu_enps)", formato="decimal", casas=1,
            formula="(Promotores − Detratores) × 100 ÷ Respostas",
            descricao="Employee Net Promoter Score da pesquisa de pulso "
                      "mensal: vai de −100 a +100."),
    Metrica("respostas_enps", "Respostas de eNPS", "SUM(respondeu_enps)",
            formato="inteiro",
            descricao="Respostas da pesquisa de pulso no período. Serve para "
                      "saber se o eNPS de um recorte tem gente o bastante "
                      "para ser lido."),
    Metrica("tempo_contratacao", "Tempo para contratar",
            "SUM(dias_para_contratar)", den_sql="SUM(admissao)",
            formato="decimal", casas=1, bom_quando_sobe=False,
            formula="Soma dos dias de vaga aberta ÷ Admissões",
            descricao="Dias corridos entre a abertura da vaga e a admissão, "
                      "em média."),
    Metrica("custo_contratacao", "Custo por contratação",
            "SUM(custo_contratacao)", den_sql="SUM(admissao)",
            formato="moeda", casas=0, bom_quando_sobe=False,
            formula="Custo de recrutamento ÷ Admissões",
            descricao="Anúncio, consultoria, exames e horas de entrevista, "
                      "por pessoa contratada."),
    Metrica("aceite_oferta", "Aceite de oferta", "SUM(admissao)",
            den_sql="SUM(ofertas)", formato="percentual", casas=1,
            formula="Admissões ÷ Ofertas feitas",
            descricao="Das propostas feitas, quantas foram aceitas. Cai quando "
                      "o mercado paga mais do que a empresa."),
    Metrica("taxa_promocao", "Promoções (a.a.)", "SUM(promocao) * 365.0",
            den_sql=_PESSOA_DIA, formato="percentual", casas=1,
            formula="Promoções × 365 ÷ Pessoa-dia ativa",
            descricao="Promoções sobre a base exposta, anualizado. Concentra "
                      "nos ciclos de março e setembro."),
    Metrica("salario_medio", "Salário médio", "SUM(salario)",
            den_sql=_PESSOA_DIA, formato="moeda", casas=0,
            formula="Soma dos salários de cada dia ÷ Pessoa-dia ativa",
            descricao="Salário-base mensal médio de quem esteve ativo no "
                      "período."),
    Metrica("gap_genero", "Gap salarial de gênero (bruto)",
            f"1 - (SUM(CASE WHEN {_F} THEN salario END) "
            f"/ SUM(CASE WHEN {_F} THEN ativo END)) "
            f"/ (SUM(CASE WHEN {_M} THEN salario END) "
            f"/ SUM(CASE WHEN {_M} THEN ativo END))",
            formato="percentual", casas=1, bom_quando_sobe=False,
            # Não é soma nem contagem: é uma razão entre duas médias. Nenhuma
            # dimensão "fecha" com ela, e a cascata mostra o resíduo inteiro
            # em vez de fingir que os segmentos somam o gap.
            num_aditivo=False, entidade="razao_de_medias",
            formula="1 − Salário médio das mulheres ÷ Salário médio dos homens",
            descricao="Quanto o salário médio das mulheres fica abaixo do dos "
                      "homens, sem ajuste nenhum. Mistura duas coisas: pagar "
                      "diferente no mesmo cargo e ter menos mulheres nos "
                      "cargos que pagam mais. O gap ajustado separa as duas."),
])

_UNICA = ("pessoa",)

DIMENSOES = indexar([
    Dimensao("area", "Área", "area", unica_por=_UNICA,
             descricao="Área da pessoa."),
    Dimensao("nivel", "Nível", "nivel",
             descricao="Nível do cargo no dia. Muda com promoção."),
    Dimensao("genero", "Gênero", "genero", unica_por=_UNICA,
             descricao="Gênero declarado no cadastro."),
    Dimensao("regime", "Regime de trabalho", "regime", unica_por=_UNICA,
             descricao="Presencial, híbrido ou remoto."),
    Dimensao("regiao", "Região", "regiao", unica_por=_UNICA,
             descricao="Região de lotação."),
    Dimensao("canal", "Canal de contratação", "canal", unica_por=_UNICA,
             descricao="Por onde a pessoa foi contratada."),
    Dimensao("faixa_tempo_casa", "Tempo de casa", "faixa_tempo_casa",
             descricao="Faixa de tempo de empresa no dia."),
    Dimensao("faixa_etaria", "Faixa etária", "faixa_etaria",
             descricao="Faixa de idade no dia."),
    Dimensao("safra_admissao", "Safra de admissão", "safra_admissao",
             unica_por=_UNICA,
             descricao="Mês de admissão. Quem já estava na empresa no início "
                       "da base aparece como 'Antes de set/2024'."),
])

DOMINIO = Dominio(
    chave="people",
    nome="People Analytics",
    subtitulo="Turnover, clima, recrutamento e remuneração",
    descricao=(
        "Quem entra, quem sai, por quê — e o que avisou antes. É o painel de "
        "quem cuida de gente e precisa separar onda de saída de ruído, gap de "
        "cargo de gap de composição, e sinal de clima de alarme falso."
    ),
    fonte=(
        "BASE SIMULADA. Não há base pública de RH com linha do tempo (as "
        "conhecidas, como a IBM HR Attrition, são uma fotografia sem data), "
        "então a empresa — uma varejista fictícia de ~3.700 pessoas — foi "
        "gerada com estrutura declarada: temporários de fim de ano, "
        "reestruturação no CD em ago/2025, congelamento de mérito em "
        "Tecnologia e a onda de saída que veio depois. A modelagem é real; o "
        "dado não."
    ),
    simulado=True,
    arquivo="fato_people.parquet",
    metricas=METRICAS,
    dimensoes=DIMENSOES,
    metricas_painel=["headcount", "turnover_voluntario", "turnover_precoce",
                     "absenteismo", "enps", "tempo_contratacao",
                     "taxa_promocao", "gap_genero"],
    dims_filtro=["area", "nivel", "genero", "regime", "regiao", "canal",
                 "faixa_tempo_casa", "faixa_etaria", "safra_admissao"],
    # Alerta diário só em métrica que tem volume por dia. Turnover anualizado
    # de um dia é ruído puro (três saídas viram 30% a.a.); o que o alerta
    # vigia é a CONTAGEM de desligamentos, e o clima e a ausência, que têm
    # centenas de observações por dia útil.
    metricas_alerta=["desligamentos", "admissoes", "absenteismo", "enps"],
    dims_alerta=["area", "nivel", "regiao"],
    # Limite aqui e checado DIA a DIA pelo motor de alertas. Por isso so
    # absenteismo tem um: turnover de um dia e ruido, e o eNPS diario, com
    # ~100 respostas, oscila +-8 pontos so de amostra. Esses se leem por mes,
    # na Visao geral e com a Tomoyo.
    limites=[
        Limite("absenteismo", ">", 0.045,
               "Absenteísmo acima de 4,5% num dia é o patamar combinado com "
               "Operações para acionar a liderança local no mesmo dia."),
    ],
    sinonimos_metrica={
        "headcount": ["headcount", "quadro", "quantas pessoas", "colaboradores",
                      "funcionarios", "hc", "efetivo", "tamanho do time"],
        "admissoes": ["admissao", "admissoes", "contratacoes", "contratados",
                      "entradas", "novos colaboradores"],
        "desligamentos": ["desligamento", "desligamentos", "saidas",
                          "demissoes", "quantos sairam", "quem saiu"],
        "turnover": ["turnover total", "rotatividade", "turnover geral"],
        "turnover_voluntario": ["turnover", "turnover voluntario",
                                "perdendo gente", "perdendo mais gente",
                                "perde mais gente", "perdendo pessoas",
                                "pedindo demissao", "pedem demissao",
                                "pedido de demissao", "pedidos de demissao",
                                "saida voluntaria", "attrition", "evasao"],
        "turnover_involuntario": ["turnover involuntario", "demissao pela empresa",
                                  "desligamento involuntario", "layoff",
                                  "corte", "fim de contrato"],
        "turnover_precoce": ["turnover precoce", "saida precoce",
                             "90 dias", "experiencia", "periodo de experiencia",
                             "retencao de novos", "early turnover"],
        "absenteismo": ["absenteismo", "absenteísmo", "faltas", "ausencia",
                        "ausencias", "atestado", "atestados"],
        "enps": ["enps", "e-nps", "clima", "engajamento", "satisfacao",
                 "nps interno", "pesquisa de clima", "pulso"],
        "respostas_enps": ["respostas", "adesao", "quantas respostas",
                           "participacao na pesquisa"],
        "tempo_contratacao": ["tempo para contratar", "tempo de contratacao",
                              "time to hire", "time to fill", "sla de vaga",
                              "tempo de vaga", "demora para contratar"],
        "custo_contratacao": ["custo por contratacao", "custo de contratacao",
                              "cost per hire", "custo de recrutamento"],
        "aceite_oferta": ["aceite", "aceite de oferta", "taxa de aceite",
                          "propostas aceitas", "recusa de proposta"],
        "taxa_promocao": ["promocao", "promocoes", "taxa de promocao",
                          "promovidos", "carreira", "mobilidade"],
        "salario_medio": ["salario", "salario medio", "remuneracao",
                          "quanto ganha", "folha"],
        "gap_genero": ["gap", "gap salarial", "gap de genero",
                       "diferenca salarial", "equidade salarial",
                       "desigualdade salarial", "pay gap"],
    },
    sinonimos_dimensao={
        "area": ["area", "areas", "departamento", "diretoria", "time"],
        "nivel": ["nivel", "niveis", "senioridade", "cargo", "cargos"],
        "genero": ["genero", "sexo", "mulheres", "homens"],
        "regime": ["regime", "remoto", "hibrido", "presencial",
                   "modelo de trabalho"],
        "regiao": ["regiao", "regioes", "regional", "localidade"],
        "canal": ["canal de contratacao", "canal", "fonte de contratacao",
                  "origem da contratacao", "indicacao", "consultoria"],
        "faixa_tempo_casa": ["tempo de casa", "tempo de empresa", "tenure",
                             "antiguidade"],
        "faixa_etaria": ["idade", "faixa etaria", "geracao"],
        "safra_admissao": ["safra", "safras", "coorte", "cohort",
                           "mes de admissao", "turma"],
    },
    perguntas_exemplo=[
        "Qual o turnover voluntário no período?",
        "Qual área está perdendo mais gente?",
        "Onde tem risco de saída nos próximos meses?",
        "O gap salarial de gênero é de cargo ou de composição?",
        "Por que o eNPS mudou em relação ao mês passado?",
        "Qual canal de contratação tem mais turnover precoce?",
        "O absenteísmo está crescendo?",
    ],
    agente_nome="Tomoyo",
    agente_rosto="🐾",
    agente_genero="f",
    agente_voz="tomoyo",
    agente_imagem="tomoyo",
    agente_papel=("Cuido de gente — e adoro isso! Quem entra, quem sai, como "
                  "está o clima e se a régua de salário é justa. Leio sempre "
                  "grupo, nunca pessoa, e saio farejando o sinal que avisa "
                  "antes da saída, porque depois do pedido de demissão já é "
                  "tarde."),
    extensao="vulcano.people.agente",
    guia_conversa=(
        ("qual o turnover voluntário?", "dá a taxa anualizada do período "
                                        "selecionado"),
        ("e por quê?", "decompõe a variação por área e separa efeito taxa de "
                       "efeito mix"),
        ("e por nível?", "refaz a mesma leitura quebrada por nível"),
        ("onde tem risco de saída?", "lê os sinais que vêm antes do pedido de "
                                     "demissão, por grupo de área e nível"),
        ("o gap salarial é de cargo ou de composição?",
         "separa o gap bruto do ajustado por nível e área"),
    ),
    dica_conversa=("Eu leio grupo, nunca pessoa: pergunta sobre alguém em "
                   "específico recebe a leitura do grupo, e recorte com menos "
                   "de 10 pessoas não aparece nas minhas respostas."),
    notas=[
        "DADO SIMULADO. A empresa e as pessoas são fictícias.",
        "Grão pessoa-dia: headcount é média dos dias e turnover é anualizado "
        "sobre a base exposta. Um mês de 28 dias e um de 31 comparam na mesma "
        "régua.",
        "Turnover precoce é lido na data da admissão, com safra madura: quem "
        "entrou há menos de 90 dias (em 31/08/2026) aparece vazio, nunca "
        "zero. Por isso a série termina em maio/2026.",
        "Turnover de um dia só é ruído (três saídas viram 30% a.a.). Leia em "
        "mês fechado ou mais; o alerta diário vigia a contagem de "
        "desligamentos, não a taxa.",
        f"A Tomoyo só responde sobre grupo. Nas respostas próprias dela, "
        f"recorte com menos de {GRUPO_MINIMO} pessoas não é mostrado.",
    ],
)


# --------------------------------------------------------------------------- #
# English
# --------------------------------------------------------------------------- #

EN = {
    "nome": "People Analytics",
    "subtitulo": "Turnover, engagement, recruiting and pay",
    "descricao": (
        "Who comes in, who leaves, why — and what warned us before. The "
        "dashboard for whoever looks after people and needs to tell an exit "
        "wave from noise, a job-level pay gap from a composition gap, and an "
        "engagement signal from a false alarm."
    ),
    "fonte": (
        "SIMULATED DATA. There is no public HR dataset with a timeline (the "
        "well-known ones, like IBM HR Attrition, are a snapshot without "
        "dates), so the company — a fictional retailer with ~3,700 people — "
        "was generated with a declared structure: year-end temporary staff, a "
        "distribution-center restructuring in Aug 2025, a merit freeze in "
        "Technology and the exit wave that followed. The modeling is real; "
        "the data is not."
    ),
    "metricas": {
        "headcount": ("Average headcount",
                      "Average number of active people per day in the period. "
                      "It is an average, not a sum: summing 30 days of "
                      "headcount would count each person 30 times.",
                      "Active people summed day by day ÷ Days in the period"),
        "admissoes": ("Hires", "People hired in the period."),
        "desligamentos": ("Terminations",
                          "People who left in the period, voluntarily or "
                          "not."),
        "turnover": ("Turnover (annualized)",
                     "Terminations over the exposed base, annualized: how "
                     "much of the company would leave in a year if the "
                     "period's pace continued.",
                     "Terminations × 365 ÷ Active person-days"),
        "turnover_voluntario": ("Voluntary turnover (annualized)",
                                "Only people who chose to leave, annualized. "
                                "The turnover that speaks of engagement, "
                                "leadership and the market.",
                                "Resignations × 365 ÷ Active person-days"),
        "turnover_involuntario": ("Involuntary turnover (annualized)",
                                  "Terminations initiated by the company, "
                                  "including end of temporary contracts, "
                                  "annualized.",
                                  "Company-initiated terminations × 365 ÷ "
                                  "Active person-days"),
        "turnover_precoce": ("Early turnover (90 days)",
                             "Of the people hired in the period, how many "
                             "left within 90 days. Read on the HIRE date: "
                             "only cohorts with 90 full days count.",
                             "Hires who left within 90 days ÷ Hires in mature "
                             "cohorts"),
        "absenteismo": ("Absenteeism",
                        "Unplanned absence hours over scheduled working hours "
                        "on business days.",
                        "Absence hours ÷ Scheduled hours"),
        "enps": ("eNPS", "Employee Net Promoter Score from the monthly pulse "
                         "survey: ranges from −100 to +100.",
                 "(Promoters − Detractors) × 100 ÷ Responses"),
        "respostas_enps": ("eNPS responses",
                           "Pulse-survey responses in the period. Tells "
                           "whether a slice's eNPS has enough people to be "
                           "read."),
        "tempo_contratacao": ("Time to hire",
                              "Calendar days between opening the position and "
                              "the hire, on average.",
                              "Sum of days the position was open ÷ Hires"),
        "custo_contratacao": ("Cost per hire",
                              "Job ads, agencies, medical exams and interview "
                              "hours, per person hired.",
                              "Recruiting cost ÷ Hires"),
        "aceite_oferta": ("Offer acceptance",
                          "Of the offers made, how many were accepted. Falls "
                          "when the market pays more than the company.",
                          "Hires ÷ Offers made"),
        "taxa_promocao": ("Promotions (annualized)",
                          "Promotions over the exposed base, annualized. "
                          "Concentrated in the March and September cycles.",
                          "Promotions × 365 ÷ Active person-days"),
        "salario_medio": ("Average salary",
                          "Average monthly base salary of those active in the "
                          "period.",
                          "Sum of each day's salaries ÷ Active person-days"),
        "gap_genero": ("Gender pay gap (raw)",
                       "How far women's average salary sits below men's, with "
                       "no adjustment. It mixes two things: paying differently "
                       "for the same job and having fewer women in the "
                       "higher-paying jobs. The adjusted gap separates them.",
                       "1 − Women's average salary ÷ Men's average salary"),
    },
    "dimensoes": {
        "area": ("Area", "The person's area."),
        "nivel": ("Level", "Job level on the day. Changes with promotion."),
        "genero": ("Gender", "Gender declared in the HR record."),
        "regime": ("Work arrangement", "On-site, hybrid or remote."),
        "regiao": ("Region", "Work location region."),
        "canal": ("Hiring channel", "Where the person was hired from."),
        "faixa_tempo_casa": ("Tenure", "Tenure band on the day."),
        "faixa_etaria": ("Age band", "Age band on the day."),
        "safra_admissao": ("Hire cohort",
                           "Month of hire. People already at the company when "
                           "the base starts show up as 'Before Sep 2024'."),
    },
    "limites": [
        "Absenteeism above 4.5% on a day is the threshold agreed with "
        "Operations to call local leadership the same day.",
    ],
    "sinonimos_metrica": {
        "headcount": ["headcount", "head count", "how many people",
                      "employees", "staff", "workforce", "team size"],
        "admissoes": ["hire", "hires", "hiring", "new hires", "hired",
                      "joiners"],
        "desligamentos": ["termination", "terminations", "exits", "leavers",
                          "how many left", "who left", "separations"],
        "turnover": ["total turnover", "overall turnover", "churn rate"],
        "turnover_voluntario": ["turnover", "voluntary turnover",
                                "losing people", "losing the most people",
                                "loses the most people", "resignations",
                                "resigning", "quitting", "quits", "attrition",
                                "voluntary exits"],
        "turnover_involuntario": ["involuntary turnover", "layoff", "layoffs",
                                  "fired", "dismissals",
                                  "company-initiated exits",
                                  "end of contract"],
        "turnover_precoce": ["early turnover", "early exits", "90 days",
                             "probation", "probation period",
                             "new-hire retention", "early attrition"],
        "absenteismo": ["absenteeism", "absences", "absence", "sick days",
                        "sick leave", "missed days"],
        "enps": ["enps", "e-nps", "engagement", "climate", "satisfaction",
                 "employee satisfaction", "pulse survey", "morale"],
        "respostas_enps": ["responses", "response rate", "how many responses",
                           "survey participation"],
        "tempo_contratacao": ["time to hire", "time to fill",
                              "hiring time", "days to hire"],
        "custo_contratacao": ["cost per hire", "hiring cost",
                              "recruiting cost"],
        "aceite_oferta": ["offer acceptance", "acceptance rate",
                          "offers accepted", "offer declines"],
        "taxa_promocao": ["promotion", "promotions", "promotion rate",
                          "promoted", "career", "mobility"],
        "salario_medio": ["salary", "average salary", "pay", "compensation",
                          "payroll", "wages"],
        "gap_genero": ["gap", "pay gap", "gender pay gap", "gender gap",
                       "pay equity", "wage gap", "pay inequality"],
    },
    "sinonimos_dimensao": {
        "area": ["area", "areas", "department", "departments", "division",
                 "team"],
        "nivel": ["level", "levels", "seniority", "job level", "grade"],
        "genero": ["gender", "sex", "women", "men"],
        "regime": ["work arrangement", "remote", "hybrid", "on-site",
                   "work model"],
        "regiao": ["region", "regions", "location"],
        "canal": ["hiring channel", "channel", "hiring source", "source",
                  "referral", "agency"],
        "faixa_tempo_casa": ["tenure", "time at the company", "seniority band"],
        "faixa_etaria": ["age", "age band", "age group", "generation"],
        "safra_admissao": ["cohort", "cohorts", "hire cohort", "hire month",
                           "class of"],
    },
    "perguntas_exemplo": [
        "What is voluntary turnover in the period?",
        "Which area is losing the most people?",
        "Where is there flight risk in the coming months?",
        "Is the gender pay gap about job level or composition?",
        "Why did eNPS change vs last month?",
        "Which hiring channel has the most early turnover?",
        "Is absenteeism growing?",
    ],
    "agente_papel": (
        "I look after people — and I love it! Who joins, who leaves, how "
        "engagement is doing and whether the pay scale is fair. I always read "
        "groups, never individuals, and I go sniffing out the signal that "
        "warns before an exit, because after the resignation letter it is "
        "too late."
    ),
    "guia_conversa": [
        ("what's the voluntary turnover?",
         "gives the annualized rate for the selected period"),
        ("and why?", "breaks the change down by area and separates rate "
                     "effect from mix effect"),
        ("and by level?", "redoes the same reading, split by level"),
        ("where is there flight risk?",
         "reads the signals that come before a resignation, by area × level "
         "group"),
        ("is the pay gap about job level or composition?",
         "separates the raw gap from the gap adjusted by level and area"),
    ],
    "dica_conversa": (
        "I read groups, never people: a question about someone specific gets "
        "the group's reading back, and slices with fewer than 10 people don't "
        "show up in my answers."
    ),
    "notas": [
        "SIMULATED DATA. The company and the people are fictional.",
        "Person-day grain: headcount is the average of the days and turnover "
        "is annualized over the exposed base. A 28-day month and a 31-day "
        "month compare on the same scale.",
        "Early turnover is read on the hire date, with mature cohorts only: "
        "people hired less than 90 days before Aug 31, 2026 show up empty, "
        "never zero. That is why the series ends in May 2026.",
        "One day of turnover is noise (three exits become 30% annualized). "
        "Read it by full month or longer; the daily alert watches the count "
        "of terminations, not the rate.",
        f"Tomoyo only answers about groups. In her own answers, slices with "
        f"fewer than {GRUPO_MINIMO} people are not shown.",
    ],
}
