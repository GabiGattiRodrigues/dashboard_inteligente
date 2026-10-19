# Playbook do R2 — Produto e Operação

Cada bloco `##` é um trecho que o R2 pode recuperar. Os metadados dizem para
qual situação ele serve; o texto diz o que fazer. Nada de número de
resultado aqui: o número é sempre do motor.

O playbook complementa a recomendação curta de cada métrica
(`vulcano/playbooks.py`): lá fica o primeiro diagnóstico, aqui o como fazer.

## Etapa travada: levar ao dono | Stuck step: take it to the owner
- id: prod-jornada-trava
- metricas: jornada_completa, passou_aprovacao, passou_postagem, passou_entrega
- quando: piora
- dimensoes: etapa_jornada
- tipo: playbook

### pt
Com a etapa que travou identificada, a conversa vai com a lista de pedidos
parados nela e um prazo de retorno. Combina com o dono da etapa um
acompanhamento diário até normalizar — jornada que trava e ninguém
acompanha volta a travar.

### en
Once the stuck step is identified, the conversation goes with the list of
orders stuck there and a deadline for an answer. Agree a daily check with
the step's owner until it's back to normal — a journey that gets stuck and
nobody follows gets stuck again.

## Pagamento segurando pedido | Payments holding orders
- id: prod-aprovacao-lenta
- metricas: h_ate_aprovar, passou_aprovacao
- quando: piora
- dimensoes: meio_pagamento
- tipo: playbook

### pt
Se é antifraude, pede ao time de risco quantos pedidos retidos acabaram
aprovados depois: regra que segura muito pedido bom está custando venda. Se
é boleto, lembrete de pagamento antes do vencimento recupera parte dos
pedidos sem mexer em regra nenhuma.

### en
If it's anti-fraud, ask the risk team how many held orders ended up
approved: a rule that holds many good orders is costing sales. If it's bank
slips, a payment reminder before the due date recovers part of the orders
without changing any rule.

## Nota caindo | Ratings falling
- id: prod-nota-caindo
- metricas: nota_media, pct_nota_baixa
- quando: piora
- dimensoes: cumpriu_prazo, categoria, faixa_nota
- tipo: playbook

### pt
Para a nota que vem do atraso, o que salva é avisar o cliente antes do prazo
estourar. Para a que sobra entre pedidos entregues no prazo, lê os
comentários: descrição errada e foto que engana aparecem antes de defeito de
produto — e se corrigem no cadastro, não na fábrica.

### en
For ratings driven by delays, what saves them is warning the customer before
the deadline breaks. For what's left among on-time orders, read the
comments: wrong descriptions and misleading photos show up before product
defects — and they're fixed in the listing, not the factory.

## Prazo que não fecha | A lead time that doesn't add up
- id: prod-prazo
- metricas: d_aprovar_postar, d_postar_entregar, prazo_entrega, taxa_atraso
- quando: piora
- dimensoes: rota_envio, regiao, estado, categoria
- tipo: playbook

### pt
A conversa com quem estourou vai com a lista de pedidos da semana, não com a
média — média não liga para ninguém. Se o atraso é estrutural numa rota, a
correção mais barata é a promessa do checkout: prometer certo custa menos do
que prometer rápido e atrasar.

### en
The conversation with whoever broke it goes with the week's order list, not
the average — nobody acts on an average. If the delay is structural on a
route, the cheapest fix is the checkout promise: promising right costs less
than promising fast and being late.

## Cancelamento subindo | Cancellations rising
- id: prod-cancelamento
- metricas: taxa_cancelamento
- quando: piora
- dimensoes: meio_pagamento, status, categoria
- tipo: playbook

### pt
Cada tipo de cancelamento tem remédio próprio: arrependimento costuma vir de
prazo longo ou descrição que não bate; pagamento se resolve com lembrete e
meio alternativo; ruptura, com estoque sincronizado. O número total não vai
para ninguém — cada pedaço vai para o seu dono.

### en
Each kind of cancellation has its own remedy: remorse usually comes from a
long lead time or a description that doesn't match; payment is solved with
reminders and an alternative method; stock-outs, with synced inventory. The
total goes to nobody — each piece goes to its owner.

## Calendário enganando a leitura | The calendar misleading the reading
- id: prod-sazonal
- quando: ambos
- sinais: sazonal
- tipo: armadilha

### pt
Operação sente calendário: pedido de sexta só anda na segunda. Compara com o
mesmo dia da semana anterior antes de abrir incidente — senão o time corre
atrás de fim de semana todo mês.

### en
Operations feel the calendar: a Friday order only moves on Monday. Compare
with the same weekday of the previous week before opening an incident —
otherwise the team chases weekends every month.

## Piora que se repete toda semana | A decline that repeats every week
- id: prod-tendencia
- quando: piora
- sinais: tendencia
- tipo: armadilha

### pt
Piora que se repete semana após semana é processo, não incidente. Leva para
o ritual de produto com dono e prazo, em vez de tratar como alarme do dia —
alarme do dia se resolve e volta na semana seguinte.

### en
A decline that repeats week after week is a process issue, not an incident.
Take it to the product ritual with an owner and a deadline instead of
treating it as the day's alarm — the day's alarm gets fixed and comes back
next week.
