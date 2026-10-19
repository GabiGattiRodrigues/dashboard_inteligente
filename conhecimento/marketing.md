# Playbook da Abigail — Marketing e CRM

Cada bloco `##` é um trecho que a Abigail pode recuperar. Os metadados dizem
para qual situação ele serve; o texto diz o que fazer. Nada de número de
resultado aqui: o número é sempre do motor.

O playbook complementa a recomendação curta de cada métrica
(`vulcano/playbooks.py`): lá fica o primeiro diagnóstico, aqui o como fazer.

## Como ler o resultado de uma campanha de CRM | How to read a CRM campaign result
- id: mkt-campanha-leitura
- metricas: lift_crm, lift_impactados, taxa_resp_impactados, pedidos_incrementais, receita_incremental, receita_crm
- quando: ambos
- tipo: criterio

### pt
Campanha só conta como resultado se ganhar do grupo controle. Compara a taxa
de resposta de quem abriu contra o controle, na janela de 7 dias depois do
disparo, e olha o ticket médio dos dois lados. Lift alto com controle pequeno
é ruído até prova em contrário: antes de escalar, repete o disparo com um
controle maior.

### en
A campaign only counts as a result if it beats the control group. Compare
the response rate of openers against control, in the 7-day window after the
send, and check the average ticket on both sides. A high lift with a small
control is noise until proven otherwise: before scaling, repeat the send
with a bigger control.

## Incremental da campanha caindo | Campaign incrementality falling
- id: mkt-lift-caindo
- metricas: lift_crm, lift_impactados, taxa_resp_impactados, pedidos_incrementais, receita_incremental
- quando: piora
- tipo: playbook

### pt
A primeira suspeita é fadiga: a mesma base recebendo disparo demais. Confere
a frequência por cliente e o opt-out da semana. Se a frequência está normal,
o problema é oferta ou segmentação — testa uma variação de mensagem contra a
atual, com controle, antes de trocar a régua inteira.

### en
The first suspect is fatigue: the same base getting too many sends. Check
frequency per customer and the week's opt-out. If frequency is normal, the
problem is the offer or the targeting — test a message variant against the
current one, with control, before replacing the whole cadence.

## Abertura e clique caindo | Opens and clicks falling
- id: mkt-abertura-caindo
- metricas: taxa_abertura, taxa_clique_crm, conversao_crm, taxa_optout
- quando: piora
- tipo: playbook

### pt
Abertura caindo em todos os segmentos ao mesmo tempo costuma ser
entregabilidade, não conteúdo: checa a reputação do domínio e quanto da base
está inativa. Se cai só num segmento, é assunto e horário. Opt-out subindo
junto é sinal de que a frequência passou do ponto — reduz volume antes de
mexer no criativo.

### en
Opens falling across every segment at once is usually deliverability, not
content: check domain reputation and how much of the base is inactive. If it
falls in one segment only, it's subject line and timing. Opt-out rising at
the same time means frequency went too far — cut volume before touching the
creative.

## Mídia ficando cara | Media getting expensive
- id: mkt-midia-cara
- metricas: cac, roas, investimento, cpc, ctr, conversao_midia, novos_clientes
- quando: piora
- dimensoes: canal, campanha, tipo_campanha
- tipo: playbook

### pt
Antes de cortar, olha a campanha e não o canal: dentro de canal ruim quase
sempre tem campanha boa. Desliga primeiro a que rende abaixo do resto com
volume relevante, e mede prospecção por cliente novo, não por ROAS —
remarketing infla o ROAS e esconde quanto custa trazer gente nova.

### en
Before cutting, look at the campaign, not the channel: a bad channel almost
always has a good campaign inside it. Switch off first the one that
underperforms with relevant volume, and measure prospecting by new
customers, not ROAS — retargeting inflates ROAS and hides what it costs to
bring new people in.

## Quando a variação é de mix | When the change is a mix effect
- id: mkt-efeito-mix
- quando: ambos
- sinais: efeito_mix
- tipo: armadilha

### pt
Efeito mix quer dizer que mudou quem comprou, não como cada grupo compra. A
conversa é com aquisição e canal: quais campanhas trouxeram o público novo e
se ele tem cara de recompra. Cobrar a categoria ou o time de produto aqui é
cobrar a pessoa errada.

### en
A mix effect means who bought changed, not how each group buys. The
conversation is with acquisition and channel: which campaigns brought the
new audience and whether it looks like repeat buyers. Pushing the category
or the product team here is pushing the wrong person.

## Queda concentrada num segmento | Drop concentrated in one segment
- id: mkt-queda-concentrada
- quando: piora
- sinais: concentrado
- dimensoes: categoria, regiao, estado, canal, campanha, tipo_cliente
- tipo: playbook

### pt
Queda concentrada pede ação cirúrgica: campanha específica para aquele
público, checagem de estoque e preço da categoria, e revisão do calendário de
CRM daquele segmento. Ação para a base toda dilui o esforço e gasta verba com
quem não mudou.

### en
A concentrated drop calls for a surgical action: a campaign aimed at that
audience, a check on the category's stock and price, and a review of that
segment's CRM calendar. Acting on the whole base dilutes the effort and
spends budget on people who didn't change.

## Melhorou: proteger antes de comemorar | Improved: protect it before celebrating
- id: mkt-melhora-proteger
- quando: melhora
- tipo: criterio

### pt
Antes de comemorar, confere se a melhora é incremental (lift contra o
controle) ou só antecipação de compra que vai faltar na semana seguinte. Se
for incremental, registra campanha, público e oferta para virar régua —
resultado bom que ninguém documenta não se repete.

### en
Before celebrating, check whether the improvement is incremental (lift
against control) or just pulled-forward purchases that will be missing next
week. If it is incremental, record campaign, audience and offer so it becomes
a cadence — a good result nobody documents doesn't repeat.

## Piora que vem de semanas | A decline that has been going on for weeks
- id: mkt-tendencia
- quando: piora
- sinais: tendencia
- tipo: armadilha

### pt
Inclinação sustentada não se resolve com uma campanha de resgate: ela
compensa a semana e esconde a causa. Leva para o planejamento do mês com
hipótese, dono e teste com controle, e acompanha a métrica contra a mesma
semana do mês anterior.

### en
A sustained slope isn't fixed by a rescue campaign: it covers the week and
hides the cause. Take it to the monthly plan with a hypothesis, an owner and
a controlled test, and track the metric against the same week of the
previous month.
