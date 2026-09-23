"""
Domínio de Crédito, sobre carteira SIMULADA.

Ver `scripts/build_crédito.py` para como o dado foi gerado é o que foi
deliberadamente embutido nele. O app declara em toda tela que este domínio
não usa dado real.

A métrica que importa aqui e inadimplência por safra, com MOB respeitado: a
safra só entra na conta depois de ter tido tempo de quebrar. Safra imatura
aparece como vazia, nunca como zero.
"""

from ..semantica import Dimensao, Dominio, Limite, Metrica, indexar

_APROVADAS = "SUM(aprovado)"

METRICAS = indexar([
    Metrica("originacao", "Originação", "SUM(valor_liberado)", formato="moeda",
            descricao="Valor total liberado no período."),
    Metrica("propostas", "Propostas", "SUM(propostas)", formato="inteiro",
            descricao="Propostas de crédito recebidas."),
    Metrica("contratos", "Contratos aprovados", _APROVADAS, formato="inteiro",
            descricao="Propostas que viraram contrato."),
    Metrica("taxa_aprovacao", "Taxa de aprovação", _APROVADAS,
            den_sql="SUM(propostas)", formato="percentual", casas=1,
            formula="Contratos aprovados ÷ Propostas",
            descricao="Propostas aprovadas sobre propostas recebidas."),
    Metrica("ticket_medio", "Ticket médio", "SUM(valor_liberado)",
            den_sql=_APROVADAS, formato="moeda", casas=2,
            formula="Originação ÷ Contratos aprovados",
            descricao="Valor médio liberado por contrato aprovado."),
    Metrica("prazo_medio", "Prazo médio", "SUM(prazo_meses)", den_sql=_APROVADAS,
            formato="decimal", casas=1,
            formula="Soma dos prazos ÷ Contratos aprovados",
            descricao="Prazo médio contratado, em meses."),
    Metrica("juros_medio", "Juros médio (% a.m.)", "SUM(taxa_juros_am)",
            den_sql="COUNT(taxa_juros_am)", formato="decimal", casas=2,
            formula="Soma das taxas ÷ Contratos aprovados",
            descricao="Taxa média ao mês dos contratos originados."),
    Metrica("saldo", "Saldo em aberto", "SUM(saldo)", formato="moeda",
            descricao="Saldo devedor remanescente da carteira."),
    Metrica("over30_mob3", "Over30 em MOB3", "SUM(over30_mob3)",
            den_sql="COUNT(over30_mob3)", formato="percentual", casas=2,
            bom_quando_sobe=False,
            formula="Contratos em atraso >30d ÷ Contratos de safra madura",
            descricao="Contratos com mais de 30 dias de atraso até o 3o mês de "
                      "vida. Só safras com 3 meses completos entram na conta."),
    Metrica("over90_mob6", "Over90 em MOB6", "SUM(over90_mob6)",
            den_sql="COUNT(over90_mob6)", formato="percentual", casas=2,
            bom_quando_sobe=False,
            formula="Contratos em atraso >90d ÷ Contratos de safra madura",
            descricao="Atraso acima de 90 dias até o 6o mês de vida. Só safras "
                      "com 6 meses completos entram na conta."),
    Metrica("default_mob12", "Default em MOB12", "SUM(default_mob12)",
            den_sql="COUNT(default_mob12)", formato="percentual", casas=2,
            bom_quando_sobe=False,
            formula="Contratos em perda ÷ Contratos de safra madura",
            descricao="Perda confirmada até o 12o mês. Só safras com 12 meses "
                      "completos entram na conta."),
    Metrica("perda_esperada", "Perda esperada", "SUM(over90_mob6 * saldo)",
            den_sql="SUM(CASE WHEN over90_mob6 IS NOT NULL THEN saldo END)",
            formato="percentual", casas=2, bom_quando_sobe=False,
            formula="Saldo em over90 ÷ Saldo das safras maduras",
            descricao="Saldo em over90 sobre o saldo das safras já maduras."),
])

DIMENSOES = indexar([
    Dimensao("faixa_score", "Faixa de score", "faixa_score",
             unica_por=("contrato",), descricao="Faixa de score do proponente na entrada."),
    Dimensao("canal", "Canal", "canal", unica_por=("contrato",),
             descricao="Canal por onde a proposta entrou."),
    Dimensao("produto", "Produto", "produto", unica_por=("contrato",),
             descricao="Linha de crédito contratada."),
    Dimensao("faixa_renda", "Faixa de renda", "faixa_renda",
             unica_por=("contrato",), descricao="Faixa de renda declarada, em salários mínimos."),
    Dimensao("regiao", "Região", "regiao", unica_por=("contrato",),
             descricao="Região do proponente."),
    Dimensao("estado", "Estado", "estado", unica_por=("contrato",),
             descricao="UF do proponente."),
    Dimensao("safra", "Safra", "safra", unica_por=("contrato",),
             descricao="Mês de originação do contrato."),
    # Faixas em vez de números crus: ninguém filtra "prazo = 37 meses", filtra
    # "prazo longo". "Não aprovado" é uma faixa de verdade e não um buraco --
    # proposta recusada não tem prazo, ticket nem taxa, e esconder isso faria
    # a soma das faixas não bater com o total de propostas.
    Dimensao("decisao", "Decisão", "decisao", unica_por=("contrato",),
             descricao="Se a proposta foi aprovada ou recusada."),
    Dimensao("faixa_prazo", "Faixa de prazo", "faixa_prazo",
             unica_por=("contrato",),
             descricao="Faixa de prazo do contrato, em meses."),
    Dimensao("faixa_ticket", "Faixa de ticket", "faixa_ticket",
             unica_por=("contrato",),
             descricao="Faixa do valor liberado no contrato."),
    Dimensao("faixa_taxa", "Faixa de taxa", "faixa_taxa",
             unica_por=("contrato",),
             descricao="Faixa da taxa de juros ao mês contratada."),
])

DOMINIO = Dominio(
    chave="credito",
    nome="Crédito",
    subtitulo="Originação, política e risco por safra",
    descricao=(
        "Quanto se originou, com que política e como cada safra se comportou "
        "depois. É o painel de quem responde por volume sem estourar o risco — "
        "e onde a leitura errada de MOB faz uma carteira ruim parecer ótima."
    ),
    fonte=(
        "CARTEIRA SIMULADA. Não há base pública de crédito com data de "
        "originação e marcação de inadimplência disponível, então a carteira "
        "foi gerada com estrutura declarada: curva de maturação, choque de "
        "política em set-nov/2017, aperto em 2018 e censura a direita nas "
        "safras jovens. A modelagem é real; o dado não."
    ),
    simulado=True,
    arquivo="fato_credito.parquet",
    metricas=METRICAS,
    dimensoes=DIMENSOES,
    metricas_painel=["originacao", "contratos", "taxa_aprovacao", "ticket_medio",
                     "over30_mob3", "over90_mob6", "juros_medio", "saldo"],
    dims_filtro=["faixa_score", "canal", "produto", "faixa_renda", "regiao",
                 "estado", "safra", "decisao", "faixa_prazo", "faixa_ticket",
                 "faixa_taxa"],
    metricas_alerta=["originacao", "propostas", "taxa_aprovacao", "ticket_medio",
                     "juros_medio"],
    dims_alerta=["canal", "faixa_score", "produto"],
    limites=[
        Limite("over30_mob3", ">", 0.055,
               "Acima de 5,5% de over30 em MOB3 a política de crédito e revista."),
        Limite("over90_mob6", ">", 0.030,
               "Over90 acima de 3% em MOB6 estoura o apetite de risco aprovado."),
        Limite("taxa_aprovacao", ">", 0.72,
               "Aprovação acima de 72% costuma indicar afrouxamento de política."),
    ],
    sinonimos_metrica={
        "originacao": ["originacao", "originado", "liberado", "volume liberado",
                       "concessao", "desembolso"],
        "propostas": ["proposta", "propostas", "pedido de crédito", "solicitacao"],
        "contratos": ["contrato", "contratos", "aprovado", "aprovados"],
        "taxa_aprovacao": ["aprovacao", "taxa de aprovação", "aprovabilidade"],
        "ticket_medio": ["ticket", "ticket médio", "valor médio do contrato"],
        "prazo_medio": ["prazo", "prazo médio", "meses"],
        "juros_medio": ["juros", "taxa de juros", "taxa média"],
        "saldo": ["saldo", "carteira", "saldo devedor", "estoque"],
        "over30_mob3": ["over30", "over 30", "atraso 30", "inadimplência 30",
                        "mob3"],
        "over90_mob6": ["over90", "over 90", "atraso 90", "inadimplencia",
                        "inadimplência 90", "mob6"],
        "default_mob12": ["default", "perda", "write off", "mob12", "calote"],
        "perda_esperada": ["perda esperada", "provisao", "expected loss"],
    },
    sinonimos_dimensao={
        "faixa_score": ["score", "faixa de score", "rating", "faixa"],
        "canal": ["canal", "canais", "origem"],
        "produto": ["produto", "produtos", "linha", "modalidade"],
        "faixa_renda": ["renda", "faixa de renda", "salario"],
        "regiao": ["regiao", "regioes", "regional"],
        "estado": ["estado", "estados", "uf"],
        "safra": ["safra", "safras", "cohort", "coorte", "vintage"],
        "decisao": ["decisao", "aprovado", "recusado", "aprovacao ou recusa"],
        "faixa_prazo": ["prazo", "faixa de prazo", "meses", "prazo do contrato"],
        "faixa_ticket": ["faixa de ticket", "faixa de valor", "valor liberado",
                         "tamanho do contrato"],
        "faixa_taxa": ["faixa de taxa", "faixa de juros", "taxa contratada"],
    },
    perguntas_exemplo=[
        "Qual a originação no período?",
        "Qual a inadimplência over30 por safra?",
        "Por que a taxa de aprovação mudou em relação ao mês passado?",
        "Quais os piores canais em over30?",
        "A originação está crescendo?",
        "Tem algo fora do padrão no último dia?",
        "Qual faixa de score concentra a perda?",
    ],
    agente_nome="Bailey",
    agente_rosto="🐶",
    agente_genero="m",
    agente_voz="bailey",
    agente_imagem="bailey",
    agente_papel=("Cuido de crédito: originação, política e risco por safra. "
                  "Leio a carteira safra a safra e cobro MOB antes de afirmar "
                  "qualquer coisa sobre risco — safra jovem, para mim, aparece "
                  "vazia e nunca como zero."),
    guia_conversa=(
        ("qual a originação?", "dá o volume liberado no período selecionado"),
        ("e por quê?", "decompõe a variação contra a base e mostra a cascata"),
        ("e por canal?", "refaz a mesma leitura quebrada por canal"),
        ("e o over30?", "troca só a métrica — e avisa se a safra ainda não "
                        "completou o MOB"),
        ("quais as piores faixas de score em over30?",
         "ranking lido como risco: pior é a inadimplência mais ALTA"),
    ),
    dica_conversa=("Inadimplência é sempre por safra, com MOB respeitado. Se o "
                   "período for recente demais, a resposta vem vazia de "
                   "propósito — amplie o período para trás para alcançar "
                   "safras maduras."),
    notas=[
        "DADO SIMULADO. Nenhum número deste domínio vem de carteira real.",
        "Inadimplência é sempre lida por safra de originação com MOB respeitado: "
        "a safra só entra na conta depois de completar 3, 6 ou 12 meses de vida. "
        "Safra jovem aparece vazia, nunca como zero — preencher com zero é o que "
        "faz um painel mostrar risco caindo quando ele só ainda não teve tempo "
        "de aparecer.",
        "Como as safras recentes ficam de fora das métricas de risco, a série "
        "diária de over30 termina antes do fim do período. Isso e proposital.",
    ],
)


# --------------------------------------------------------------------------- #
# English
# --------------------------------------------------------------------------- #

EN = {
    "nome": "Credit",
    "subtitulo": "Origination, policy and risk by vintage",
    "descricao": (
        "How much was originated, under which policy, and how each vintage "
        "behaved afterwards. The dashboard for whoever owns volume without "
        "blowing the risk budget — and where misreading MOB makes a bad "
        "portfolio look great."
    ),
    "fonte": (
        "SIMULATED PORTFOLIO. There is no public credit dataset with "
        "origination date and delinquency flags, so the portfolio was "
        "generated with a declared structure: maturation curve, a policy "
        "shock in Sep–Nov 2017, tightening in 2018 and right-censoring on "
        "young vintages. The modeling is real; the data is not."
    ),
    "metricas": {
        "originacao": ("Origination", "Total amount disbursed in the period."),
        "propostas": ("Applications", "Credit applications received."),
        "contratos": ("Approved contracts",
                      "Applications that became contracts."),
        "taxa_aprovacao": ("Approval rate",
                           "Approved applications over applications received.",
                           "Approved contracts ÷ Applications"),
        "ticket_medio": ("Average ticket",
                         "Average amount disbursed per approved contract.",
                         "Origination ÷ Approved contracts"),
        "prazo_medio": ("Average term", "Average contracted term, in months.",
                        "Sum of terms ÷ Approved contracts"),
        "juros_medio": ("Average interest (% per month)",
                        "Average monthly rate of originated contracts.",
                        "Sum of rates ÷ Approved contracts"),
        "saldo": ("Outstanding balance",
                  "Remaining outstanding balance of the portfolio."),
        "over30_mob3": ("Over30 at MOB3",
                        "Contracts more than 30 days past due by month 3 on "
                        "book. Only vintages with 3 full months count.",
                        "Contracts >30 days past due ÷ Contracts in mature "
                        "vintages"),
        "over90_mob6": ("Over90 at MOB6",
                        "More than 90 days past due by month 6 on book. Only "
                        "vintages with 6 full months count.",
                        "Contracts >90 days past due ÷ Contracts in mature "
                        "vintages"),
        "default_mob12": ("Default at MOB12",
                          "Confirmed loss by month 12. Only vintages with 12 "
                          "full months count.",
                          "Contracts in loss ÷ Contracts in mature vintages"),
        "perda_esperada": ("Expected loss",
                           "Over90 balance over the balance of mature "
                           "vintages.",
                           "Over90 balance ÷ Balance of mature vintages"),
    },
    "dimensoes": {
        "faixa_score": ("Score band", "Applicant's score band at entry."),
        "canal": ("Channel", "Channel the application came through."),
        "produto": ("Product", "Credit line contracted."),
        "faixa_renda": ("Income band",
                        "Declared income band, in minimum wages."),
        "regiao": ("Region", "Applicant's region."),
        "estado": ("State", "Applicant's state."),
        "safra": ("Vintage", "Origination month of the contract."),
        "decisao": ("Decision", "Whether the application was approved or "
                                "declined."),
        "faixa_prazo": ("Term band", "Contract term band, in months."),
        "faixa_ticket": ("Ticket band", "Band of the amount disbursed."),
        "faixa_taxa": ("Rate band", "Band of the monthly interest rate."),
    },
    "limites": [
        "Above 5.5% over30 at MOB3, credit policy is reviewed.",
        "Over90 above 3% at MOB6 breaks the approved risk appetite.",
        "Approval above 72% usually signals a loosened policy.",
    ],
    "sinonimos_metrica": {
        "originacao": ["origination", "originated", "disbursed",
                       "disbursement", "loan volume", "volume originated"],
        "propostas": ["application", "applications", "credit requests"],
        "contratos": ["contract", "contracts", "approved contracts",
                      "approvals"],
        "taxa_aprovacao": ["approval", "approval rate", "approval ratio"],
        "ticket_medio": ["ticket", "average ticket", "average loan",
                         "average contract value", "loan size"],
        "prazo_medio": ["term", "average term", "months"],
        "juros_medio": ["interest", "interest rate", "average rate", "apr"],
        "saldo": ["balance", "portfolio", "outstanding", "outstanding balance"],
        "over30_mob3": ["over30", "over 30", "30 days past due", "30 dpd",
                        "dpd30", "delinquency 30", "mob3"],
        "over90_mob6": ["over90", "over 90", "90 days past due", "90 dpd",
                        "delinquency", "default rate 90", "mob6"],
        "default_mob12": ["default", "loss", "write off", "write-off",
                          "charge-off", "mob12"],
        "perda_esperada": ["expected loss", "provision", "provisions"],
    },
    "sinonimos_dimensao": {
        "faixa_score": ["score", "score band", "credit score", "rating"],
        "canal": ["channel", "channels", "source"],
        "produto": ["product", "products", "credit line", "loan type"],
        "faixa_renda": ["income", "income band", "salary"],
        "regiao": ["region", "regions"],
        "estado": ["state", "states"],
        "safra": ["vintage", "vintages", "cohort", "cohorts"],
        "decisao": ["decision", "approved or declined", "declined"],
        "faixa_prazo": ["term band", "loan term", "contract term"],
        "faixa_ticket": ["ticket band", "loan size band", "amount band"],
        "faixa_taxa": ["rate band", "interest band"],
    },
    "perguntas_exemplo": [
        "What was origination in the period?",
        "What is over30 delinquency by vintage?",
        "Why did the approval rate change vs last month?",
        "Which are the worst channels for over30?",
        "Is origination growing?",
        "Is anything out of pattern on the last day?",
        "Which score band concentrates the loss?",
    ],
    "agente_papel": (
        "I look after credit: origination, policy and risk by vintage. I read "
        "the portfolio vintage by vintage and insist on MOB before saying "
        "anything about risk — to me a young vintage shows up empty, never as "
        "zero."
    ),
    "guia_conversa": [
        ("what was origination?",
         "gives the amount disbursed in the selected period"),
        ("and why?", "breaks the change down against the baseline and draws "
                     "the waterfall"),
        ("and by channel?", "redoes the same reading, split by channel"),
        ("what about over30?", "switches only the metric — and warns you if "
                               "the vintage has not reached MOB yet"),
        ("which are the worst score bands for over30?",
         "a ranking read as risk: worst is the HIGHEST delinquency"),
    ],
    "dica_conversa": (
        "Delinquency is always by vintage, with MOB respected. If the period "
        "is too recent, the answer comes back empty on purpose — extend the "
        "period backwards to reach mature vintages."
    ),
    "notas": [
        "SIMULATED DATA. No number in this domain comes from a real portfolio.",
        "Delinquency is always read by origination vintage with MOB "
        "respected: a vintage only counts after 3, 6 or 12 months on book. A "
        "young vintage shows up empty, never as zero — filling it with zero "
        "is what makes a dashboard show risk falling when it simply has not "
        "had time to show up.",
        "Because recent vintages are left out of the risk metrics, the daily "
        "over30 series ends before the end of the period. This is on purpose.",
    ],
}
