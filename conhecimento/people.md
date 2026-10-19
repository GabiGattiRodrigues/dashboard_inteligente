# Playbook da Tomoyo — People Analytics

Cada bloco `##` é um trecho que a Tomoyo pode recuperar. Os metadados dizem
para qual situação ele serve; o texto diz o que fazer. Nada de número de
resultado aqui: o número é sempre do motor.

O playbook complementa a recomendação curta de cada métrica
(`vulcano/playbooks.py`): lá fica o primeiro diagnóstico, aqui o como fazer.

## Turnover voluntário subindo | Voluntary turnover rising
- id: ppl-turnover-voluntario
- metricas: turnover_voluntario
- quando: piora
- dimensoes: area, nivel, faixa_tempo_casa
- tipo: playbook

### pt
Abre por área e liderança e cruza com o eNPS do mesmo grupo: saída
concentrada num time costuma ser gestão; espalhada costuma ser mercado ou
remuneração. As entrevistas de desligamento dos últimos casos dizem mais do
que qualquer média — lê antes de propor programa.

### en
Break it down by area and leadership and cross it with the same group's
eNPS: exits concentrated in one team are usually management; spread out,
usually market or pay. The exit interviews of the latest cases say more
than any average — read them before proposing a programme.

## Gente saindo cedo | People leaving early
- id: ppl-turnover-precoce
- metricas: turnover_precoce
- quando: piora
- dimensoes: safra_admissao, canal, area
- tipo: playbook

### pt
Para as próximas admissões, coloca um check-in do gestor no fim do primeiro
e do terceiro mês e pergunta direto se a vaga é o que foi prometido. Quem
sai cedo costuma avisar nessa conversa — quase nunca na entrevista de
desligamento.

### en
For the next hires, add a manager check-in at the end of the first and
third months and ask straight out whether the job is what was promised.
People who leave early usually say so in that conversation — almost never
in the exit interview.

## Ouvir e voltar | Listen and come back
- id: ppl-enps
- metricas: enps, absenteismo
- quando: piora
- dimensoes: area, nivel, regime
- tipo: playbook

### pt
Ouvir só funciona se tiver volta: retorna para o time em poucas semanas com
o que foi ouvido e uma ação pequena já feita. Pesquisa sem resposta derruba
o próximo eNPS mais do que o problema original. Absenteísmo subindo junto é
desgaste — confere carga e horas extras.

### en
Listening only works if you come back: return to the team within a few
weeks with what you heard and one small action already done. A survey with
no answer drags the next eNPS down more than the original problem.
Absenteeism rising at the same time is burnout — check workload and
overtime.

## Vaga parada | A stuck opening
- id: ppl-recrutamento
- metricas: tempo_contratacao, aceite_oferta
- quando: piora
- dimensoes: canal, area, nivel
- tipo: playbook

### pt
Mede o tempo de cada etapa da vaga — triagem, entrevista, decisão, proposta
— e mostra para o gestor onde ela fica parada. Na maioria das vezes, cortar
uma etapa ou reservar agenda fixa de entrevista resolve antes de mexer em
salário.

### en
Measure the time of each step of the opening — screening, interview,
decision, offer — and show the manager where it gets stuck. Most of the
time, cutting a step or blocking fixed interview slots solves it before
touching pay.

## Gap de gênero e promoção | Gender gap and promotion
- id: ppl-gap-genero
- metricas: gap_genero, taxa_promocao
- quando: ambos
- dimensoes: nivel, area, genero
- tipo: criterio

### pt
Gap de gênero mexendo pede olhar promoção e contratação por nível, não só o
número geral. Se o gap abre nos níveis mais altos, o problema é a esteira de
promoção; leva para o comitê com o recorte por área.

### en
A moving gender gap calls for looking at promotion and hiring by level, not
just the overall number. If the gap opens at senior levels, the problem is
the promotion pipeline; take it to the committee with the breakdown by
area.

## Movimento concentrado numa área | Movement concentrated in one area
- id: ppl-concentrado
- quando: ambos
- sinais: concentrado
- dimensoes: area, nivel, regiao
- tipo: armadilha

### pt
Quando o movimento é de uma área só, a conversa é com a liderança daquela
área, com o dado na mão e sem expor ninguém. Recorte pequeno identifica
pessoa — cuidado com o que vai para o slide.

### en
When the movement belongs to one area, the conversation is with that area's
leadership, data in hand and without exposing anyone. A small slice
identifies people — be careful with what goes on the slide.
