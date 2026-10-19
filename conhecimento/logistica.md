# Playbook do Vulcão — Logística

Cada bloco `##` é um trecho que o Vulcão pode recuperar. Os metadados dizem
para qual situação ele serve; o texto diz o que fazer. Nada de número de
resultado aqui: o número é sempre do motor.

O playbook complementa a recomendação curta de cada métrica
(`vulcano/playbooks.py`): lá fica o primeiro diagnóstico, aqui o como fazer.

## Ponto fora do controle | Point out of control
- id: log-fora-controle
- metricas: pct_no_prazo, pct_fora_prazo, pct_atraso_grave, pct_nao_entregue
- quando: piora
- dimensoes: origem, regiao_destino, rota, regiao_origem
- sinais: alerta
- tipo: playbook

### pt
Ponto fora do limite no gráfico de controle é causa especial: tem algo novo
naquela origem ou região. Liga para a transportadora da rota com a lista de
pedidos da semana. Dentro do limite é ruído — mexer no processo por causa de
ruído só aumenta a variação.

### en
A point outside the control limit is a special cause: something new is
happening at that origin or region. Call the route's carrier with the week's
order list. Inside the limit it's noise — changing the process because of
noise only increases variation.

## Régua do pedido atrasado | The late-order cadence
- id: log-regua-d3-d7
- metricas: dias_atraso, pct_atraso_grave, chegam_d3, chegam_d7, nota_atrasados, valor_fora_prazo, pct_fora_prazo
- quando: piora
- tipo: playbook

### pt
Pedido que passou do prazo entra na régua: no D+3, contato proativo com o
cliente e cobrança da transportadora; no D+7, decisão entre reenvio e
estorno. Esperar o cliente reclamar custa a nota e, muitas vezes, o cliente.

### en
An order past its deadline enters the cadence: at D+3, proactive contact
with the customer and a push on the carrier; at D+7, a decision between
resend and refund. Waiting for the customer to complain costs the rating
and, often, the customer.

## Atraso nascendo no seller | Delay starting at the seller
- id: log-seller
- metricas: pct_seller_no_prazo, pct_atraso_seller, d_postagem
- quando: piora
- dimensoes: origem, uf_origem, responsavel_atraso, categoria
- tipo: playbook

### pt
Separa o seller pontual do reincidente. Pontual se resolve com uma ligação e
a lista dos pedidos parados. Reincidente vai para plano de ação com prazo; se
não melhorar, o prazo de checkout dele aumenta até a postagem voltar para
dentro do limite — prometer o que o seller não cumpre é atraso contratado.

### en
Separate the one-off seller from the repeat offender. A one-off is solved
with a call and the list of stuck orders. A repeat offender goes into an
action plan with a deadline; if it doesn't improve, their checkout lead time
goes up until shipping is back within the limit — promising what the seller
can't deliver is a contracted delay.

## Trânsito e rota | Transit and route
- id: log-transito
- metricas: d_transito, lead_time, frete_medio
- quando: piora
- dimensoes: rota, regiao_destino, estado_destino, porte
- tipo: playbook

### pt
Compara a mesma rota em semanas diferentes para separar problema pontual de
mudança de malha. Problema pontual se cobra da transportadora com a lista de
pedidos; mudança de malha pede renegociar SLA ou trocar de parceiro naquela
rota.

### en
Compare the same route across different weeks to separate a one-off problem
from a network change. A one-off gets pushed to the carrier with the order
list; a network change calls for renegotiating the SLA or switching partner
on that route.

## Promessa folgada demais | Promise too loose
- id: log-promessa
- metricas: pct_promessa_folgada, dias_promessa
- quando: ambos
- dimensoes: rota, faixa_promessa, regiao_destino
- tipo: criterio

### pt
Encurtar promessa se faz rota a rota e com volta garantida: muda primeiro o
prazo das rotas mais estáveis, acompanha o no prazo delas por algumas
semanas e só então passa para as próximas. Promessa encurtada em rota
instável troca folga por atraso.

### en
Shortening the promise is done route by route, with a way back: change the
most stable routes first, watch their on-time rate for a few weeks and only
then move to the next ones. Shortening the promise on an unstable route
trades slack for delays.

## Piora espalhada pela malha | Decline spread across the network
- id: log-espalhado
- quando: piora
- sinais: espalhado
- tipo: playbook

### pt
Quando a piora está em todas as origens ao mesmo tempo, a causa é geral:
pico de demanda, greve, feriado ou mudança de transportadora. Confere o
calendário e os avisos dos parceiros antes de abrir chamado rota por rota.

### en
When the decline hits every origin at once, the cause is general: a demand
peak, a strike, a holiday or a carrier change. Check the calendar and the
partners' notices before opening tickets route by route.

## Atraso concentrado numa origem ou rota | Delay concentrated in one origin or route
- id: log-concentrado
- quando: piora
- sinais: concentrado
- dimensoes: origem, rota, regiao_destino, estado_destino, regiao_origem, uf_origem
- tipo: playbook

### pt
Quando o atraso mora numa origem ou rota, abre o gráfico de controle dela
antes de agir. Se a semana passou do limite, é causa especial: a ligação é
com quem opera aquela perna, com a lista de pedidos na mão. Se está dentro do
limite, é a variação de sempre — o caminho é um plano de melhoria da rota,
não um incidente.

### en
When the delay lives in one origin or route, open its control chart before
acting. If the week broke the limit, it's a special cause: the call is with
whoever runs that leg, order list in hand. If it's within the limit, it's
the usual variation — the path is an improvement plan for the route, not an
incident.
