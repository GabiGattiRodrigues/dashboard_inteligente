"""
O que cada agente recomenda, no assunto dele.

O motor de leitura (`analise.ler`) sabe dizer ONDE a métrica mexeu e se foi
taxa ou mix. O que fazer com isso depende do assunto: CAC subindo pede
criativo e segmentação; seller postando atrasado pede cobrar o seller, não a
transportadora; eNPS caindo pede ouvir o grupo antes de mexer em política.
Uma recomendação genérica ("a ação é dentro do segmento") vale para todo
domínio e não ajuda em nenhum.

Aqui mora o repertório de cada agente: para cada métrica, o que fazer quando
ela piora e quando melhora, escrito no vocabulário e no tom de quem cuida
daquilo. `{onde}` vira " — começando por <dimensão> = <segmento>" quando a
variação está concentrada num segmento, e some quando está espalhada.

Abigail (Marketing e CRM), Bailey (Crédito), R2 (Produto e Operação),
Ravena (Compliance e PLD), Tomoyo (People), Vulcão (Logística).
"""

from __future__ import annotations

from typing import Optional

from .i18n import L

# chave do domínio -> métrica -> {"piora": (pt, en), "melhora": (pt, en)}
P: dict[str, dict[str, dict[str, tuple[str, str]]]] = {}

# --------------------------------------------------------------------------- #
# Abigail — Marketing e CRM
# --------------------------------------------------------------------------- #
P["marketing"] = {
    "receita": {
        "piora": ("Separa tráfego de conversão{onde}: se pedidos caíram junto, "
                  "é topo de funil — revisar mídia e o calendário de CRM da "
                  "semana; se só o ticket caiu, é mix ou cupom.",
                  "Split traffic from conversion{onde}: if orders fell too, "
                  "it's top of funnel — check media and the week's CRM "
                  "calendar; if only the ticket fell, it's mix or coupons."),
        "melhora": ("Descobre o que puxou{onde} e protege. Se foi campanha, "
                    "confere no lift de 7 dias se é incremental antes de "
                    "dobrar a verba.",
                    "Find what drove it{onde} and protect it. If it was a "
                    "campaign, check the 7-day lift for incrementality "
                    "before doubling the budget."),
    },
    "pedidos": {
        "piora": ("Olha o funil de mídia (CTR e conversão) e quantos disparos "
                  "de CRM saíram{onde}. Pedido caindo com investimento "
                  "parado é eficiência, não verba.",
                  "Check the media funnel (CTR and conversion) and how many "
                  "CRM sends went out{onde}. Orders falling with flat spend "
                  "is efficiency, not budget."),
    },
    "ticket_medio": {
        "piora": ("Confere se entrou cupom ou campanha de categoria barata"
                  "{onde}. Ticket caindo com pedido subindo costuma ser "
                  "promoção comprando volume — vale se a margem fecha.",
                  "Check whether a coupon or a cheap-category campaign went "
                  "live{onde}. Ticket down with orders up is usually a promo "
                  "buying volume — fine if the margin works."),
        "melhora": ("Testa frete grátis a partir de um valor mínimo{onde} "
                    "para segurar o ticket alto sem perder conversão.",
                    "Test free shipping above a minimum basket{onde} to keep "
                    "the higher ticket without losing conversion."),
    },
    "clientes": {
        "piora": ("Base que não cresce vira CRM falando sempre com os mesmos. "
                  "Revisa prospecção paga e afiliados{onde}.",
                  "A base that doesn't grow means CRM always talking to the "
                  "same people. Review paid prospecting and affiliates"
                  "{onde}."),
    },
    "novos_clientes": {
        "piora": ("Aquisição: revisa segmentação e criativo de prospecção"
                  "{onde}; remarketing não traz cliente novo, então não "
                  "adianta mexer nele.",
                  "Acquisition: review prospecting targeting and creative"
                  "{onde}; retargeting doesn't bring new customers, so "
                  "touching it won't help."),
    },
    "taxa_cancelamento": {
        "piora": ("Cancelamento é operação disfarçada de marketing: cruza com "
                  "meio de pagamento (boleto que não pagou) e ruptura{onde} "
                  "antes de mexer em campanha.",
                  "Cancellation is operations disguised as marketing: cross "
                  "it with payment method (unpaid boleto) and stockouts"
                  "{onde} before touching any campaign."),
    },
    "pct_frete": {
        "piora": ("Frete pesando mais{onde}: testa frete grátis acima de um "
                  "valor mínimo — sobe o ticket e dilui o frete.",
                  "Freight weighing more{onde}: test free shipping above a "
                  "minimum basket — it raises the ticket and dilutes "
                  "freight."),
    },
    "investimento": {
        "piora": ("Investimento subiu{onde}: confere se veio pedido junto. "
                  "Subir sem conversão é configuração de campanha, não "
                  "demanda — começa pelo gerenciador de anúncios.",
                  "Spend went up{onde}: check whether orders came with it. "
                  "Rising without conversion is campaign setup, not demand — "
                  "start with the ads manager."),
        "melhora": ("Investimento caiu{onde}: se o ROAS segurou, era verba "
                    "sobrando; se caiu junto, devolve aos poucos.",
                    "Spend fell{onde}: if ROAS held, it was surplus budget; "
                    "if it fell too, add it back gradually."),
    },
    "roas": {
        "piora": ("ROAS caindo{onde}: separa CPC (leilão, fadiga de criativo) "
                  "de conversão (página, oferta, frete) antes de cortar "
                  "verba — o remédio é outro.",
                  "ROAS falling{onde}: separate CPC (auction, creative "
                  "fatigue) from conversion (page, offer, freight) before "
                  "cutting budget — the fix is different."),
        "melhora": ("ROAS subindo{onde}: testa escalar 20% e acompanha o "
                    "retorno marginal — o médio sempre engana para cima.",
                    "ROAS rising{onde}: test scaling 20% and watch the "
                    "marginal return — the average always flatters."),
    },
    "cac": {
        "piora": ("CAC subindo{onde}: troca criativo e revisa público de "
                  "prospecção; se o CPC subiu junto, é leilão — testa canal "
                  "mais barato para o mesmo público.",
                  "CAC rising{onde}: swap creatives and review the "
                  "prospecting audience; if CPC rose too, it's the auction — "
                  "test a cheaper channel for the same audience."),
    },
    "ctr": {
        "piora": ("CTR caindo{onde} é fadiga de criativo: renova peças e "
                  "testa público novo.",
                  "CTR falling{onde} is creative fatigue: refresh the ads "
                  "and test a new audience."),
    },
    "cpc": {
        "piora": ("CPC subindo{onde}: leilão mais caro (data sazonal, "
                  "concorrente). Revisa lances e horários antes de aumentar "
                  "verba.",
                  "CPC rising{onde}: a pricier auction (seasonal date, "
                  "competitor). Review bids and dayparting before adding "
                  "budget."),
    },
    "conversao_midia": {
        "piora": ("Conversão da mídia caindo{onde}: o problema está depois do "
                  "clique — página, preço ou frete. Olha o funil antes de "
                  "mexer na verba.",
                  "Media conversion falling{onde}: the problem is after the "
                  "click — page, price or freight. Look at the funnel before "
                  "touching the budget."),
    },
    "taxa_abertura": {
        "piora": ("Abertura caindo{onde}: assunto, remetente e higiene de "
                  "base — quem não abre há 90 dias derruba a entregabilidade "
                  "de todo mundo. Tira do envio de massa.",
                  "Open rate falling{onde}: subject line, sender and list "
                  "hygiene — people who haven't opened in 90 days hurt "
                  "everyone's deliverability. Pull them from mass sends."),
    },
    "taxa_clique_crm": {
        "piora": ("Clique do CRM caindo{onde}: conteúdo e oferta. Testa um CTA "
                  "só e personaliza pela categoria de interesse.",
                  "CRM clicks falling{onde}: content and offer. Test a single "
                  "CTA and personalize by category of interest."),
    },
    "conversao_crm": {
        "piora": ("Conversão do CRM caindo{onde}: confirma no lift de 7 dias "
                  "se é efeito real ou só menos gente comprando de qualquer "
                  "jeito — atribuição sozinha não separa.",
                  "CRM conversion falling{onde}: check the 7-day lift to see "
                  "if it's a real effect or just fewer people buying anyway "
                  "— attribution alone can't tell."),
    },
    "taxa_optout": {
        "piora": ("Opt-out subindo{onde}: frequência alta demais. Reduz "
                  "disparo para quem não abre e segmenta por engajamento.",
                  "Opt-out rising{onde}: too much frequency. Cut sends to "
                  "non-openers and segment by engagement."),
    },
    "receita_crm": {
        "piora": ("Receita de CRM caindo{onde}: separa volume de envio de "
                  "resposta, e mede pela régua de 7 dias contra o controle, "
                  "não pela atribuição.",
                  "CRM revenue falling{onde}: separate send volume from "
                  "response, and measure with the 7-day yardstick against "
                  "the control, not attribution."),
    },
    "lift_crm": {
        "piora": ("Lift real caindo{onde}: a régua está falando com quem "
                  "compraria sozinho. Revisa elegibilidade (tira quem "
                  "comprou nos últimos 7 dias) e testa oferta.",
                  "Real lift falling{onde}: the flow is talking to people "
                  "who'd buy anyway. Review eligibility (drop anyone who "
                  "bought in the last 7 days) and test the offer."),
        "melhora": ("Lift real subindo{onde}: hora de escalar audiência — de "
                    "olho no opt-out.",
                    "Real lift rising{onde}: time to scale the audience — "
                    "watch opt-out."),
    },
    "lift_impactados": {
        "piora": ("Lift de quem abriu caindo{onde}: antes de mexer, confere "
                  "o lift real — essa leitura mistura efeito com perfil de "
                  "quem abre.",
                  "Openers' lift falling{onde}: before acting, check the real "
                  "lift — this reading mixes effect with the profile of who "
                  "opens."),
    },
    "taxa_resp_impactados": {
        "piora": ("Resposta de quem abriu caindo{onde}: oferta ou momento do "
                  "envio. Testa horário e criativo, e confirma no lift real.",
                  "Openers' response falling{onde}: offer or send timing. "
                  "Test time of day and creative, and confirm on the real "
                  "lift."),
    },
    "pedidos_incrementais": {
        "piora": ("Incremental caindo{onde}: protege as réguas com efeito "
                  "comprovado (carrinho, WhatsApp) e corta disparo de massa "
                  "sem efeito.",
                  "Incremental falling{onde}: protect the flows with proven "
                  "effect (cart, WhatsApp) and cut mass sends with no "
                  "effect."),
    },
    "receita_incremental": {
        "piora": ("Receita incremental caindo{onde}: olha o ticket de quem "
                  "abriu contra o do controle — cupom costuma comprar volume "
                  "pagando com margem.",
                  "Incremental revenue falling{onde}: compare the openers' "
                  "ticket with the control's — coupons often buy volume with "
                  "margin."),
    },
}

# --------------------------------------------------------------------------- #
# Bailey — Crédito
# --------------------------------------------------------------------------- #
P["credito"] = {
    "originacao": {
        "piora": ("Vamos por partes{onde}: primeiro ver se caiu proposta "
                  "(demanda) ou aprovação (política). Afrouxar política para "
                  "recuperar volume costuma aparecer seis meses depois, no "
                  "over90.",
                  "Let's take it step by step{onde}: first see whether "
                  "applications fell (demand) or approvals did (policy). "
                  "Loosening policy to win back volume usually shows up six "
                  "months later, in over90."),
    },
    "taxa_aprovacao": {
        "piora": ("Aprovação caindo{onde}: conferir se mudou o mix de score "
                  "das propostas antes de concluir que a política apertou.",
                  "Approval falling{onde}: check whether the score mix of "
                  "applications changed before concluding the policy got "
                  "tighter."),
        "melhora": ("Aprovação subindo{onde}: bom para volume, mas eu "
                    "marcaria essa safra para acompanhar o over30 no MOB3 "
                    "antes de comemorar.",
                    "Approval rising{onde}: good for volume, but I'd flag "
                    "this vintage and watch over30 at MOB3 before "
                    "celebrating."),
    },
    "over30_mob3": {
        "piora": ("Over30 no MOB3 subindo{onde}: é o primeiro sinal de safra "
                  "ruim. Rever a régua de cobrança preventiva e o corte de "
                  "score dessa faixa antes que vire over90.",
                  "Over30 at MOB3 rising{onde}: it's the first sign of a bad "
                  "vintage. Review early collections and the score cutoff "
                  "for this band before it becomes over90."),
    },
    "over90_mob6": {
        "piora": ("Over90 no MOB6 subindo{onde}: a perda já está contratada "
                  "nessa safra. Para as próximas, apertar o corte de score "
                  "e reduzir limite inicial no segmento.",
                  "Over90 at MOB6 rising{onde}: the loss is already locked "
                  "into this vintage. For the next ones, tighten the score "
                  "cutoff and lower starting limits in the segment."),
    },
    "default_mob12": {
        "piora": ("Default no MOB12 subindo{onde}: revisar o preço do risco — "
                  "o juro dessa faixa paga a perda que ela está dando?",
                  "Default at MOB12 rising{onde}: review risk pricing — does "
                  "this band's rate pay for the loss it's producing?"),
    },
    "perda_esperada": {
        "piora": ("Perda esperada subindo{onde}: separar se é mais saldo "
                  "(volume) ou mais risco por real emprestado — cada um pede "
                  "uma conversa diferente com a diretoria.",
                  "Expected loss rising{onde}: separate more balance "
                  "(volume) from more risk per real lent — each needs a "
                  "different conversation with leadership."),
    },
    "juros_medio": {
        "piora": ("Juro médio caindo{onde}: conferir se foi mix (mais score "
                  "alto) ou desconto comercial. Mix é saudável; desconto "
                  "precisa caber na perda.",
                  "Average rate falling{onde}: check whether it's mix (more "
                  "high scores) or commercial discount. Mix is healthy; a "
                  "discount has to fit the loss."),
    },
    "ticket_medio": {
        "piora": ("Ticket caindo{onde}: pode ser política de limite inicial "
                  "mais conservadora — se foi isso, a inadimplência das "
                  "próximas safras deve responder.",
                  "Ticket falling{onde}: it may be a more conservative "
                  "starting-limit policy — if so, delinquency in the next "
                  "vintages should respond."),
    },
}

# --------------------------------------------------------------------------- #
# R2 — Produto e Operação
# --------------------------------------------------------------------------- #
P["produto"] = {
    "jornada_completa": {
        "piora": ("Achar a perna que quebrou{onde}: aprovação é pagamento, "
                  "postagem é seller, entrega é transportadora. Cada uma tem "
                  "dono.",
                  "Find the leg that broke{onde}: approval is payment, "
                  "shipping is the seller, delivery is the carrier. Each has "
                  "an owner."),
    },
    "passou_aprovacao": {
        "piora": ("Aprovação travando{onde}: antifraude ou boleto não pago. "
                  "Olhar por meio de pagamento.",
                  "Approval stalling{onde}: anti-fraud or unpaid boleto. "
                  "Look by payment method."),
    },
    "passou_postagem": {
        "piora": ("Postagem travando{onde}: seller sem despachar. Ranking de "
                  "sellers por pedido parado e conversa com os cinco "
                  "primeiros.",
                  "Shipping stalling{onde}: sellers not dispatching. Rank "
                  "sellers by stuck orders and talk to the top five."),
    },
    "passou_entrega": {
        "piora": ("Entrega travando{onde}: é transportadora. A fila de "
                  "travados está no Vulcão.",
                  "Delivery stalling{onde}: it's the carrier. The stuck "
                  "queue lives with Vulcão."),
    },
    "h_ate_aprovar": {
        "piora": ("Aprovação mais lenta{onde}: fila do antifraude ou "
                  "compensação de boleto. Medir por meio de pagamento.",
                  "Slower approval{onde}: anti-fraud queue or boleto "
                  "clearing. Measure by payment method."),
    },
    "d_aprovar_postar": {
        "piora": ("Seller mais lento{onde}. O prazo prometido não sabe disso "
                  "— ou cobra o seller, ou ajusta a promessa.",
                  "Slower sellers{onde}. The promised date doesn't know — "
                  "either chase the seller or adjust the promise."),
    },
    "d_postar_entregar": {
        "piora": ("Trânsito mais longo{onde}: rota e transportadora. Comparar "
                  "dentro do estado contra entre estados.",
                  "Longer transit{onde}: route and carrier. Compare "
                  "same-state against interstate."),
    },
    "prazo_entrega": {
        "piora": ("Prazo total subindo{onde}. Decompor nas três pernas: só "
                  "uma delas costuma ser a culpada.",
                  "Total lead time rising{onde}. Break it into the three "
                  "legs: usually only one is to blame."),
    },
    "taxa_atraso": {
        "piora": ("Atraso subindo{onde}: separar promessa curta de operação "
                  "lenta. A primeira se corrige no checkout, a segunda no "
                  "seller ou na rota.",
                  "Lateness rising{onde}: separate a short promise from slow "
                  "operations. The first is fixed at checkout, the second "
                  "with the seller or the route."),
    },
    "nota_media": {
        "piora": ("Nota caindo{onde}: cruzar com cumprimento do prazo. Se a "
                  "nota baixa vem do atraso, o problema é entrega, não "
                  "produto.",
                  "Rating falling{onde}: cross it with on-time delivery. If "
                  "low ratings come from lateness, the problem is delivery, "
                  "not product."),
    },
    "pct_nota_baixa": {
        "piora": ("Mais nota 1 e 2{onde}. Primeiro ver quantas vieram de "
                  "pedido atrasado; o que sobrar é produto ou descrição.",
                  "More 1- and 2-star reviews{onde}. First see how many came "
                  "from late orders; what's left is product or listing."),
    },
    "taxa_cancelamento": {
        "piora": ("Cancelamento subindo{onde}: ruptura de estoque ou "
                  "pagamento. Olhar etapa da jornada em que o pedido parou.",
                  "Cancellations rising{onde}: stockout or payment. Look at "
                  "the journey stage where the order stopped."),
    },
}

# --------------------------------------------------------------------------- #
# Ravena — Compliance e PLD
# --------------------------------------------------------------------------- #
P["pld"] = {
    "alertas": {
        "piora": ("Com calma{onde}: antes de reforçar a equipe, ver se subiu "
                  "a população que se comporta assim ou se a régua passou a "
                  "pegar mais — a causa raiz separa os dois.",
                  "Calmly{onde}: before adding analysts, check whether the "
                  "population behaving this way grew or the rule started "
                  "catching more — root cause separates the two."),
    },
    "taxa_falso_positivo": {
        "piora": ("Falso positivo subindo{onde}: a regra está pegando gente "
                  "que não deveria. Vale abrir a calibração do corte, sem "
                  "esquecer que cada mudança precisa de justificativa "
                  "registrada.",
                  "False positives rising{onde}: the rule is catching people "
                  "it shouldn't. Worth opening the cutoff calibration — "
                  "remembering every change needs a recorded rationale."),
    },
    "fora_do_prazo": {
        "piora": ("Casos passando do prazo de 45 dias{onde}: priorizar a fila "
                  "pelo vencimento antes do valor. Prazo vencido é achado "
                  "de auditoria.",
                  "Cases past the 45-day deadline{onde}: prioritize the "
                  "queue by due date before value. A missed deadline is an "
                  "audit finding."),
    },
    "pct_no_prazo": {
        "piora": ("Menos análise no prazo{onde}: a fila cresceu mais que a "
                  "capacidade. Separar o que é volume de alerta do que é "
                  "tempo de análise.",
                  "Fewer reviews on time{onde}: the queue outgrew capacity. "
                  "Separate alert volume from review time."),
    },
    "dias_analise": {
        "piora": ("Análise mais lenta{onde}: olhar se é caso mais complexo "
                  "ou fila parada. Caso parado há muito tempo vai para o "
                  "topo.",
                  "Slower reviews{onde}: check whether cases got more "
                  "complex or the queue stalled. Long-idle cases go to the "
                  "top."),
    },
    "em_aberto": {
        "piora": ("Fila aberta crescendo{onde}: conferir entradas contra "
                  "conclusões por semana. Se entra mais do que sai, é "
                  "capacidade, não regra.",
                  "Open queue growing{onde}: compare inflows against "
                  "closures per week. If more comes in than goes out, it's "
                  "capacity, not the rule."),
    },
    "taxa_comunicacao": {
        "melhora": ("Mais comunicações ao Coaf{onde}: pode ser regra mais "
                    "precisa ou movimento real. Vale ler os pareceres antes "
                    "de concluir.",
                    "More reports to Coaf{onde}: it may be a sharper rule or "
                    "real activity. Worth reading the case notes before "
                    "concluding."),
    },
}

# --------------------------------------------------------------------------- #
# Tomoyo — People Analytics
# --------------------------------------------------------------------------- #
P["people"] = {
    "turnover_voluntario": {
        "piora": ("Turnover voluntário subindo{onde}! Antes de olhar quem "
                  "saiu, vamos olhar o que veio antes: clima, promoção e "
                  "ausência do grupo nos meses anteriores — o sinal quase "
                  "sempre estava lá.",
                  "Voluntary turnover rising{onde}! Before looking at who "
                  "left, let's look at what came before: the group's "
                  "engagement, promotions and absence in prior months — the "
                  "signal was almost always there."),
    },
    "turnover_precoce": {
        "piora": ("Gente saindo nos primeiros 90 dias{onde}: é onboarding "
                  "ou promessa de vaga. Compara por canal de contratação — "
                  "às vezes é a fonte, não o time.",
                  "People leaving in the first 90 days{onde}: it's "
                  "onboarding or the job promise. Compare by hiring channel "
                  "— sometimes it's the source, not the team."),
    },
    "turnover_involuntario": {
        "piora": ("Mais desligamento pela empresa{onde}: conferir se é "
                  "reestruturação planejada ou desempenho — e se a régua de "
                  "avaliação está igual entre áreas.",
                  "More company-initiated exits{onde}: check whether it's a "
                  "planned restructuring or performance — and whether the "
                  "review bar is the same across areas."),
    },
    "absenteismo": {
        "piora": ("Absenteísmo subindo{onde}: costuma vir antes do pedido "
                  "de demissão. Conversa com a liderança do grupo agora, "
                  "não depois.",
                  "Absenteeism rising{onde}: it usually comes before the "
                  "resignation. Talk to the group's leadership now, not "
                  "later."),
    },
    "enps": {
        "piora": ("eNPS caindo{onde}! Ouvir o grupo (pulso aberto ou grupo "
                  "focal) antes de mexer em política — e acompanhar o "
                  "turnover nos próximos 2 a 4 meses.",
                  "eNPS falling{onde}! Listen to the group (open pulse or "
                  "focus group) before changing policy — and watch turnover "
                  "over the next 2 to 4 months."),
        "melhora": ("eNPS subindo{onde}! Descobrir o que mudou e levar para "
                    "os outros times.",
                    "eNPS rising{onde}! Find out what changed and take it to "
                    "the other teams."),
    },
    "tempo_contratacao": {
        "piora": ("Vaga demorando mais{onde}: separar triagem de decisão do "
                  "gestor — o gargalo costuma estar na agenda de entrevista.",
                  "Roles taking longer{onde}: separate screening from the "
                  "manager's decision — the bottleneck is usually interview "
                  "scheduling."),
    },
    "aceite_oferta": {
        "piora": ("Menos aceite de proposta{onde}: salário fora de mercado "
                  "ou processo longo demais. Comparar a oferta com a faixa.",
                  "Fewer accepted offers{onde}: pay below market or a "
                  "process that's too long. Compare the offer with the "
                  "band."),
    },
    "taxa_promocao": {
        "piora": ("Promoção parada{onde}: grupo sem promoção há 12 meses é "
                  "o primeiro a sair. Revisar o ciclo de carreira dali.",
                  "Promotions stalled{onde}: a group without promotions for "
                  "12 months is the first to leave. Review that career "
                  "cycle."),
    },
    "gap_genero": {
        "piora": ("Gap subindo{onde}: separar o de cargo do de composição. "
                  "Um pede revisão salarial; o outro, pipeline de promoção.",
                  "Gap widening{onde}: separate same-job gap from "
                  "composition. One calls for a pay review; the other, a "
                  "promotion pipeline."),
    },
}

# --------------------------------------------------------------------------- #
# Vulcão — Logística
# --------------------------------------------------------------------------- #
P["logistica"] = {
    "pct_no_prazo": {
        "piora": ("No prazo caindo{onde}! Primeiro: o atraso nasceu no seller "
                  "ou no transporte? Se o seller postou fora do limite, "
                  "cobrar transportadora não resolve nada.",
                  "On-time dropping{onde}! First: did the delay start at the "
                  "seller or in transport? If the seller shipped past the "
                  "deadline, chasing the carrier fixes nothing."),
        "melhora": ("No prazo subindo{onde} — boa! Agora confere a promessa "
                    "folgada: se o prazo do checkout está longo demais, dá "
                    "para encurtar e ganhar conversão sem perder pontualidade.",
                    "On-time rising{onde} — nice! Now check the loose "
                    "promise: if the checkout lead time is too long, you can "
                    "shorten it and win conversion without losing "
                    "punctuality."),
    },
    "pct_fora_prazo": {
        "piora": ("Atraso subindo{onde}: abre o gráfico de controle. Se a "
                  "semana passou do limite, é sinal; se não passou, é ruído "
                  "e mexer agora só piora.",
                  "Lateness rising{onde}: open the control chart. If the "
                  "week broke the limit, it's a signal; if not, it's noise "
                  "and acting now only makes it worse."),
    },
    "pct_atraso_grave": {
        "piora": ("Mais gente passando do D+7{onde}: a cobrança do D+3 não "
                  "está resolvendo. Ativa o contato proativo com o cliente "
                  "antes da reclamação chegar.",
                  "More orders past D+7{onde}: the D+3 chasing isn't working. "
                  "Turn on proactive customer contact before the complaint "
                  "arrives."),
    },
    "pct_nao_entregue": {
        "piora": ("Mais pedido sumindo{onde}: separa quem nem postou (seller) "
                  "de quem postou e sumiu (transportadora). Os esquecidos de "
                  "mais de 30 dias é decidir baixa de uma vez.",
                  "More orders vanishing{onde}: separate never shipped "
                  "(seller) from shipped and lost (carrier). Forgotten ones "
                  "over 30 days: decide the write-off in one go."),
    },
    "valor_fora_prazo": {
        "piora": ("Mais dinheiro atrasado{onde}: prioriza a fila por valor "
                  "dentro da mesma faixa da régua.",
                  "More money late{onde}: prioritize the queue by value "
                  "within the same rule band."),
    },
    "dias_atraso": {
        "piora": ("Quem atrasa está atrasando mais{onde}: não é pico, é "
                  "pedido ficando parado. Olha a fila do D+7 hoje.",
                  "Late orders are getting later{onde}: it's not a peak, "
                  "it's orders sitting still. Check today's D+7 queue."),
    },
    "pct_seller_no_prazo": {
        "piora": ("Seller postando fora do limite{onde}: o atraso começa "
                  "antes da transportadora. Ranking de sellers por postagem "
                  "atrasada e conversa com os maiores — ou prazo maior no "
                  "checkout para eles.",
                  "Sellers shipping past the deadline{onde}: the delay "
                  "starts before the carrier. Rank sellers by late shipping "
                  "and talk to the biggest — or give them a longer checkout "
                  "promise."),
    },
    "d_postagem": {
        "piora": ("Seller mais lento para postar{onde}. Se o prazo do "
                  "checkout não mudou, o atraso vem aí — cobra o seller "
                  "antes.",
                  "Sellers slower to ship{onde}. If the checkout promise "
                  "didn't change, the delay is coming — chase the seller "
                  "first."),
    },
    "d_transito": {
        "piora": ("Trânsito mais longo{onde}: é rota e transportadora. Compara "
                  "dentro do estado contra entre estados e renegocia SLA "
                  "onde estourou.",
                  "Longer transit{onde}: route and carrier. Compare "
                  "same-state against interstate and renegotiate the SLA "
                  "where it broke."),
    },
    "pct_atraso_seller": {
        "piora": ("Mais atraso nascendo no seller{onde}: a conversa é com o "
                  "seller, não com a transportadora. Liga primeiro para "
                  "quem tem mais pedido postado tarde.",
                  "More delay starting at the seller{onde}: the conversation "
                  "is with the seller, not the carrier. Call whoever has the "
                  "most late-shipped orders first."),
    },
    "pct_promessa_folgada": {
        "piora": ("Promessa folgada demais{onde}: entrega chegando dez dias "
                  "antes. Encurta o prazo do checkout nessa rota — "
                  "conversão sobe e a nota não cai.",
                  "Promise too loose{onde}: deliveries arriving ten days "
                  "early. Shorten the checkout lead time on this route — "
                  "conversion goes up and ratings don't drop."),
    },
    "lead_time": {
        "piora": ("Prazo realizado subindo{onde}: decompõe em postagem e "
                  "trânsito — só uma das pernas costuma ser a culpada.",
                  "Actual lead time rising{onde}: split it into shipping "
                  "and transit — usually only one leg is to blame."),
    },
    "dias_promessa": {
        "piora": ("Promessa ficando mais longa{onde}: confere se a operação "
                  "piorou de verdade. Prazo longo no checkout derruba "
                  "conversão.",
                  "Promise getting longer{onde}: check whether operations "
                  "really got worse. A long checkout promise kills "
                  "conversion."),
    },
    "frete_medio": {
        "piora": ("Frete subindo{onde}: separa peso (porte) de rota. Carga "
                  "pesada pede outra malha; rota cara pede renegociação.",
                  "Freight rising{onde}: separate weight (size) from route. "
                  "Heavy cargo needs another network; an expensive route "
                  "needs renegotiation."),
    },
    "pct_frete": {
        "piora": ("Frete pesando mais no pedido{onde}: testa frete grátis "
                  "acima de um mínimo junto com marketing.",
                  "Freight weighing more on the order{onde}: test free "
                  "shipping above a minimum together with marketing."),
    },
    "nota_atrasados": {
        "piora": ("Quem atrasou está avaliando pior{onde}: o custo do atraso "
                  "subiu. Contato proativo no D+3 costuma salvar a nota.",
                  "Late orders are rating worse{onde}: the cost of lateness "
                  "went up. Proactive contact at D+3 usually saves the "
                  "rating."),
    },
    "chegam_d7": {
        "piora": ("Menos gente chegando depois do D+7{onde}: esperar ficou "
                  "mais caro. Antecipa o reenvio ou estorno para quem passa "
                  "do D+7.",
                  "Fewer orders arriving after D+7{onde}: waiting got "
                  "costlier. Bring the resend or refund forward for anyone "
                  "past D+7."),
    },
}


def recomendacao(dom, mk: str, piorou: bool, onde: str = "") -> Optional[str]:
    """A recomendação do agente do domínio para a métrica, ou None."""
    entrada = P.get(dom.chave, {}).get(mk, {}).get(
        "piora" if piorou else "melhora")
    if not entrada:
        return None
    return L(*entrada).format(onde=onde)
