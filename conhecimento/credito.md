# Playbook da Bailey — Crédito

Cada bloco `##` é um trecho que a Bailey pode recuperar. Os metadados dizem
para qual situação ele serve; o texto diz o que fazer. Nada de número de
resultado aqui: o número é sempre do motor.

O playbook complementa a recomendação curta de cada métrica
(`vulcano/playbooks.py`): lá fica o primeiro diagnóstico, aqui o como fazer.

## Inadimplência precoce subindo | Early delinquency rising
- id: cred-over30-subindo
- metricas: over30_mob3
- quando: piora
- dimensoes: canal, faixa_score, safra, produto
- tipo: playbook

### pt
Antes de mexer no corte, abre a safra por canal e faixa de score. Se piorou
dentro da mesma faixa, é fraude ou público diferente entrando pelo canal:
pede uma amostra de propostas para checar documento e endereço. Se piorou
porque entrou mais score baixo, aí é política. E só compara safra que já
está madura o bastante.

### en
Before touching the cutoff, break the vintage down by channel and score
band. If it worsened within the same band, it's fraud or a different
audience coming through the channel: pull a sample of applications to check
documents and address. If it worsened because more low scores came in, then
it's policy. And only compare vintages mature enough to compare.

## Inadimplência tardia e perda | Late delinquency and loss
- id: cred-tardia-subindo
- metricas: over90_mob6, default_mob12, perda_esperada
- quando: piora
- dimensoes: safra, faixa_score, canal
- tipo: playbook

### pt
Over90 e default contam a história das safras de meses atrás, não da
política de hoje. Identifica qual safra puxa a piora e o que mudou na
concessão naquela época. A ação vai para a cobrança da carteira que já
existe (régua, renegociação) e só vai para a política se a safra recente
repetir o padrão no over30.

### en
Over90 and default tell the story of vintages from months ago, not of
today's policy. Find which vintage drives the deterioration and what changed
in lending back then. The action goes to collections on the existing book
(cadence, renegotiation) and only goes to policy if the recent vintage
repeats the pattern in over30.

## Corte apertado sem evidência | A tight cutoff with no evidence
- id: cred-aprovacao-caindo
- metricas: taxa_aprovacao, originacao, contratos
- quando: piora
- dimensoes: canal, faixa_score, faixa_renda
- tipo: armadilha

### pt
Se a aprovação caiu porque a política apertou, mede o que deixou de entrar:
aprova uma amostra pequena da faixa recusada com limite baixo e acompanha.
Sem esse grupo de teste, o corte fica apertado para sempre por falta de
evidência — ninguém prova que a faixa recusada era boa.

### en
If approval fell because policy tightened, measure what stopped coming in:
approve a small sample of the rejected band with a low limit and track it.
Without that test group, the cutoff stays tight forever for lack of
evidence — nobody can prove the rejected band was good.

## Crescimento com registro | Growth with a paper trail
- id: cred-crescimento-marcar
- metricas: taxa_aprovacao, originacao, contratos, ticket_medio, saldo
- quando: melhora
- tipo: criterio

### pt
Crescimento rápido pede ritual: cada safra nova entra no acompanhamento com
dono, e o critério que foi afrouxado fica registrado com data. Quando a
perda aparecer meses depois, é esse registro que diz o que desfazer — sem
ele, ninguém lembra o que mudou.

### en
Fast growth needs a ritual: each new vintage goes into tracking with an
owner, and the loosened criterion is recorded with a date. When the loss
shows up months later, that record says what to undo — without it, nobody
remembers what changed.

## Quando a carteira muda de cara | When the book changes its profile
- id: cred-efeito-mix
- quando: ambos
- sinais: efeito_mix
- tipo: armadilha

### pt
Efeito mix quer dizer que entrou gente de outra faixa de score, renda ou
canal. Nenhuma régua de cobrança resolve isso. A conversa é com a política de
concessão e com quem traz o cliente — e a comparação justa é faixa contra
faixa, não o total contra o total.

### en
A mix effect means people from a different score band, income or channel
came in. No collections cadence fixes that. The conversation is with lending
policy and with whoever brings the customer — and the fair comparison is
band against band, not total against total.

## Juros que paga a perda | Interest that pays for the loss
- id: cred-juros
- metricas: juros_medio
- quando: ambos
- dimensoes: faixa_prazo, faixa_score, produto
- tipo: criterio

### pt
Juros não se lê sozinho: compara a taxa de cada faixa de score com a perda
da mesma faixa. A faixa em que o juro não paga a perda é a primeira a ter o
preço revisto — ou a sair da política.

### en
Interest is never read on its own: compare each score band's rate with that
same band's loss. The band where the rate doesn't pay for the loss is the
first to be repriced — or to leave the policy.

## Piora concentrada num segmento | Deterioration concentrated in one segment
- id: cred-concentrado
- quando: piora
- sinais: concentrado
- dimensoes: canal, produto, regiao, estado, faixa_score
- tipo: playbook

### pt
Quando a piora mora num canal ou produto, a ação é local: revisa a regra só
ali, pede amostra de propostas para checar fraude e conversa com o parceiro
do canal. Apertar a política da carteira inteira por causa de um segmento
derruba originação boa junto.

### en
When the deterioration lives in one channel or product, the action is
local: review the rule there only, pull a sample of applications to check
for fraud and talk to the channel partner. Tightening the whole book's
policy because of one segment kills good origination too.
