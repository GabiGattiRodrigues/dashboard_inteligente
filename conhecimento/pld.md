# Playbook da Ravena — Compliance e PLD

Cada bloco `##` é um trecho que a Ravena pode recuperar. Os metadados dizem
para qual situação ele serve; o texto diz o que fazer. Nada de número de
resultado aqui: o número é sempre do motor.

O playbook complementa a recomendação curta de cada métrica
(`vulcano/playbooks.py`): lá fica o primeiro diagnóstico, aqui o como fazer.

## Como calibrar uma regra | How to calibrate a rule
- id: pld-falso-positivo
- metricas: taxa_falso_positivo
- quando: piora
- dimensoes: regra, tipo_regra
- tipo: playbook

### pt
Calibrar é olhar os alertas maduros da regra e achar o parâmetro em que o
descarte cai sem perder os casos que viraram comunicação. Antes de aplicar,
roda a régua nova em paralelo por um ciclo e registra a comparação — é isso
que o auditor vai pedir.

### en
Calibrating means looking at the rule's mature alerts and finding the
parameter where dismissals drop without losing the cases that became
reports. Before applying it, run the new rule in parallel for one cycle and
record the comparison — that's what the auditor will ask for.

## Fila que não fecha | A queue that doesn't close
- id: pld-prazo
- metricas: fora_do_prazo, pct_no_prazo, dias_analise, em_aberto
- quando: piora
- dimensoes: faixa_risco, regra, area
- tipo: playbook

### pt
Quando a fila não fecha, o pedido de reforço vai com dado: entradas contra
conclusões por semana e tempo por caso. Caso perto do vencimento ganha
segunda checagem — parecer apressado para cumprir prazo é o outro achado de
auditoria.

### en
When the queue doesn't close, the request for more people goes with data:
inflows against closures per week and time per case. Cases close to the
deadline get a second check — a rushed opinion to meet the deadline is the
other audit finding.

## Régua sensível ou população nova | Sensitive rule or new population
- id: pld-volume
- metricas: alertas, clientes_alertados, valor_envolvido
- quando: piora
- dimensoes: regra, produto, segmento
- tipo: playbook

### pt
Se a régua ficou sensível depois de mudar um parâmetro, volta a calibração.
Se a população mudou — produto novo, campanha, região nova —, avisa a área
de negócio e ajusta a régua com justificativa. Nos dois casos, quem decidiu
a mudança fica registrado.

### en
If the rule became sensitive after a parameter change, roll the calibration
back. If the population changed — a new product, campaign or region —, warn
the business area and adjust the rule with a rationale. Either way, who
decided the change is on record.

## Comunicação ao COAF mexendo | COAF reporting moving
- id: pld-comunicacao
- metricas: taxa_comunicacao, comunicacoes
- quando: ambos
- tipo: criterio

### pt
Taxa de comunicação mexendo pede olhar o motivo dos pareceres, não só o
número. Queda pode ser régua gerando mais ruído; alta pode ser um padrão
novo de risco num produto ou região. Nos dois casos, o racional da decisão
fica escrito no parecer.

### en
A moving reporting rate calls for looking at the reasons in the opinions,
not just the number. A drop may be rules generating more noise; a rise may
be a new risk pattern in a product or region. Either way, the rationale for
the decision is written in the opinion.

## Desvio concentrado em público sensível | Deviation concentrated in a sensitive group
- id: pld-concentrado
- quando: ambos
- sinais: concentrado
- dimensoes: pep, faixa_risco, tipo_cliente, uf, regiao
- tipo: criterio

### pt
Quando o desvio se concentra em PEP ou em clientes de risco alto, a análise
vai para a fila prioritária e passa por revisão de segundo nível. Decisão
sobre esse público precisa de dossiê completo — movimentação, origem dos
recursos e histórico de alertas.

### en
When the deviation concentrates on PEPs or high-risk customers, the review
goes to the priority queue and gets a second-level check. A decision on
this group needs a full dossier — transactions, source of funds and alert
history.
