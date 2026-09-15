# Analytics com agente — quatro domínios, um motor

Produto de analytics em que o agente não é um chatbot colado ao lado do
dashboard: ele lê a mesma camada semântica que desenha os gráficos, respeita os
mesmos filtros e devolve o mesmo número, por construção.

Quatro domínios rodam no mesmo motor — **Marketing e CRM**, **Crédito**,
**Produto e Operação** e **Compliance e PLD** — cada um com o seu próprio
agente, com nome, rosto, personalidade e vocabulário:

| Agente | Domínio | Como fala |
|---|---|---|
| **Abigail** 🐱 | Marketing e CRM | jovem e esperta: frases curtas, energia, já emenda o próximo passo |
| **Bailey** 🐶 | Crédito | mais velho e metódico: primeiro a ressalva, depois o número, depois o que fazer |
| **R2** 🐕 | Produto e Operação | mais velho e muito inteligente: fala pouco e certo, liga as pontas |
| **Ravena** 🐕‍🦺 | Compliance e PLD | mais velha, calma e vigilante: sem pressa de concluir — o fato, depois a norma, depois o próximo passo, e nunca decide por ninguém |

Quem responde sobre crédito não é quem responde sobre marketing, porque as
ressalvas e o que conta como resposta boa são outros. A personalidade aparece
no **tom** — nunca no número: os quatro leem o mesmo motor e devolvem o mesmo
valor. Cada um tem duas caras: a animada na aba de conversa e a atenta na aba
de alertas, para a pessoa reconhecer quem está falando sem legenda.

```
streamlit run app.py
```

Há também uma **amostra estática** em `amostra/` — um retrato dos três
primeiros domínios em uma página só, que abre no celular sem servidor. Os números dela saem dos motores
de verdade (`scripts/exportar_amostra.py` roda o app e exporta o JSON); só a
interação é que fica de fora.

---

## O que aparece na tela

Seis abas por domínio, na ordem em que a pergunta costuma chegar:

| Aba | O que resolve |
|---|---|
| **Alertas** | o que fugiu do padrão hoje, já com o **motivo provável** — qual segmento carregou o desvio — em vez de só "está estranho"; a lista completa para conferência fica no fim da página |
| **Pergunte ao agente** | conversa com memória, e um botão de **análise geral** que varre tudo e devolve insights, tendência e o que fazer primeiro |
| **Visão geral** | cartões dizendo o que está selecionado e contra qual data está sendo comparado, e os gráficos de todas as métricas, com quebra opcional por dimensão |
| **Comparação de períodos** | as mesmas métricas em **quatro bases ao mesmo tempo** — contra ontem, contra D-7, mês acumulado contra mês acumulado, e contra a média dos 3 mesmos dias da semana. A seta diz a direção, a cor diz o julgamento |
| **Causa raiz** | cascata com a comparação escolhida na hora (d vs d-1, semana vs semana X, mês vs mês X), com a conta em português e exemplo numérico |
| **Sobre os dados** | origem, recorte, o que é real e o que é simulado |

Toda resposta do agente sai em três camadas: **o número**, **o que explica o
número**, **o que fazer**. Uma resposta que para no número devolve o trabalho
para quem perguntou.

E o agente não responde só sobre dado. Ele conversa (`vulcano/conversa.py`):
cumprimenta de volta, agradece, explica o que é z robusto, o que é MOB, por que
a cascata tem resíduo, de onde vem cada base — e, quando não entende, **diz que
não entendeu** em vez de chutar uma métrica. Um número que a pessoa não pediu
vira slide de reunião; é o pior desfecho possível, e é o que um agente que
tenta sempre acertar produz.

---

## O problema

Em toda área que depende de dados existe a mesma fila: alguém precisa de um
número, abre um chamado para o time de analytics, e a decisão espera dois dias
por uma resposta que era uma consulta. Quem tem pressa decide sem o dado; quem
espera decide tarde.

Um dashboard tradicional resolve as perguntas que alguém previu no momento de
construí-lo. A pergunta seguinte — *por que* caiu, *onde* caiu, se já estava
caindo antes — volta para a fila.

O primeiro destes agentes, o **Vulcano**, nasceu na Petlove para fechar essa
fila. Esta versão pública reconstrói o produto sobre dados abertos e o estende a
outros três domínios, para mostrar a arquitetura e as decisões técnicas.

---

## Compliance e PLD — a Ravena

O quarto domínio leva o motor para onde a pergunta muda de natureza. Para a
liderança de Compliance, a pergunta é agregada: quantos alertas as regras
selecionam, quanto vira falso positivo, se a fila cabe no prazo. Para a
analista, às nove da manhã, a pergunta é **quem**: qual cliente se enquadra em
qual situação da Carta Circular 4.001, com qual evidência, e o que vence
primeiro. O painel responde as duas — o agregado pelo motor genérico, o
cliente a cliente por duas abas que só este domínio tem.

| Aba | O que resolve |
|---|---|
| **Clientes em atenção** | a fila de análise em qualquer data: prioridade explicável, regras abertas, enquadramento na 4.001, valor e prazo de 45 dias em colunas separadas. Um clique abre o **dossiê**: o que disparou com a evidência em número, a conta da prioridade, a movimentação diária, as contrapartes (inclusive as que aparecem em outros clientes com alerta), o histórico e o rascunho de parecer — e o registro da decisão, com justificativa obrigatória |
| **Regras e calibração** | as dez regras com indicador, corte, condições fixas e o trecho da norma de cada uma; o desempenho por regra; a **calibração** — o que acontece com o volume de alertas e com as comunicações se o corte mudar —; e a cobertura do ciclo mensal de checagem de CPFs |

A **Causa raiz** ganha uma decomposição que nenhuma dimensão dá: o número de
alertas é escrito como **avaliados × taxa de seleção**, e a variação entre dois
meses abre em efeito população, efeito seleção e interação — subiu porque mais
gente passou a se comportar assim, ou porque a régua passou a pegar mais? Junto
vêm os **sinais brutos do mês** (quantos Pix, quanto valor, quantos pagadores
distintos por conta, compras de madrugada, contas abertas), da população
inteira e sem filtro de alerta, para conferir a conclusão contra o
comportamento de verdade.

A aba de **Alertas** também traz, logo abaixo dos cartões, **quem entrou na
fila naquele dia** e **quem está com o prazo estourando** — o alerta da
operação diz que o volume da R02 subiu; a pergunta seguinte é sempre de quem,
e ela não deveria custar uma troca de aba. E a **Visão geral** acompanha o que
está em investigação (entradas contra conclusões por semana, o que está em
análise por regra, quem está parado há mais tempo) e o **indicador antes do
corte**: a distribuição mensal do indicador de cada regra na população
avaliada, com o corte desenhado por cima.

A Ravena responde também no chat: `quais clientes precisam de atenção?`,
`me mostra o dossiê do T-01160`, `o que é a R02?`, `o que diz a 3.978 sobre o
prazo de análise?` — além de tudo o que o motor genérico já responde, como
`qual regra tem mais falso positivo?`.

### As regras

Cada regra traduz uma situação da **Carta Circular BCB 4.001/2020** em um
indicador, **um** parâmetro e condições fixas, com base na **Circular BCB
3.978/2020**:

| | Regra | Situação da 4.001 |
|---|---|---|
| R01 | Movimentação incompatível com a renda | IV, a |
| R02 | Muitas origens e saída rápida (conta de passagem) | IV, n e IV, c |
| R03 | Transferências logo abaixo do limite | IV, b e IV, l |
| R04 | Conta pouco movimentada que acorda | IV, e e IV, i |
| R05 | Recebimento no POS incompatível com o estabelecimento | IV, w |
| R06 | Transações em horário incompatível | IV, y |
| R07 | Recarga de benefício incompatível com o porte da empresa | IV, ac e III, j |
| R08 | Contas abertas em lote no mesmo dispositivo | III, f e III, l |
| R09 | PEP com movimentação relevante | IV, s |
| R10 | CPF irregular na checagem mensal | III, e |

Os resumos das normas no painel são para leitura rápida; a referência é sempre
o normativo publicado pelo Banco Central.

### As decisões que valem discussão

**Falso positivo só conta alerta maduro.** É o problema da safra de crédito
com outra roupa. Num alerta de ontem, só os casos fáceis já foram decididos —
e caso fácil costuma ser descarte. Falso positivo, conversão em comunicação,
contagem de comunicações e tempo de análise só entram na conta para alertas
com 45 dias ou mais, o prazo máximo de análise (art. 43, § 1º). O que passou
disso sem decisão não some: vira "fora do prazo".

**Prioridade é soma de fatores nomeados, não modelo.** A analista precisa
defender a ordem da fila na frente do auditor. A prioridade soma gravidade da
regra mais grave aberta, valor em escala log, regras distintas abertas no
mesmo cliente, reincidência, risco cadastral, PEP e fronteira — e o dossiê
mostra a conta. Dois sinais independentes valem mais que um forte sozinho: é
a convergência que separa indício de coincidência. **Prazo anda em coluna
separada**, para o caso médio que vence amanhã não sumir atrás do grave que
ainda tem um mês.

**Contar alerta mede a régua e o comportamento ao mesmo tempo.** Quando o
volume sobe, a primeira pergunta é qual dos dois se mexeu: o cliente ou o
corte. Por isso o painel guarda, mês a mês, os percentis do indicador de cada
regra na população avaliada — se o p95 está parado e o volume dobrou, quem se
moveu foi o parâmetro. A leitura dessa comparação é escrita na tela.

**Um parâmetro por regra e supressão mensal tornam a calibração exata.** Com
um alerta por cliente, regra e mês, a regra dispara no mês se, e só se, o
máximo mensal do indicador passar do corte. O volume de alertas em qualquer
corte vira conta exata — e um teste garante que, no corte vigente, ela devolve
o mesmo número que o motor. A tela mostra o custo dos dois lados: quantos
alertas somem e **quantas comunicações se perderiam**. Baixar o corte não tem
esse número, e a tela diz isso em vez de estimar.

**A fila de qualquer dia é reconstruída, não guardada.** Cada alerta tem data
de seleção e data de decisão; um alerta está na fila em `F` se foi
selecionado até `F` e não tinha decisão em `F`. É o que permite voltar a
junho e ver a fila estourando o prazo — e o que garante que o "em aberto" da
aba seja o "em aberto" do motor.

**O dossiê organiza, não decide.** O rascunho de parecer só usa números que
estão nas evidências e nas contrapartes (há teste para isso), fala em indício
e nunca em culpa, e termina com uma leitura dos sinais — convergentes ou
isolados — e não com "comunicar" ou "descartar". A decisão exige justificativa
mesmo no descarte, porque sem ela não existe dossiê (art. 43, § 2º).

**Prazo de comunicação é em dia útil.** Análise conta dias corridos;
comunicação vai até o dia útil seguinte ao da decisão (art. 48, § 2º). O
calendário tem os feriados do período, e o teste cobra a Sexta-feira Santa e
o Corpus Christi.

### A base simulada

Nenhuma instituição publica os próprios alertas, então a operação foi gerada
com estrutura declarada em `scripts/build_pld.py`: uma plataforma fictícia de
benefícios flexíveis com conta digital, 9,2 mil titulares, 425 empresas e 1,2
mil estabelecimentos, de set/2025 a ago/2026. O job roda as mesmas funções de
`vulcano/pld/regras.py` que a tela explica e simula uma fila de analistas com
capacidade limitada. O que foi plantado de propósito:

- contas de passagem abertas em lote no mesmo celular, em onda de jun a ago;
- troca de benefício em mercearias de fronteira, abastecida por empresas
  recém-cadastradas;
- incompatibilidade com renda, fracionamento, PEP com movimentação habitual e
  conta de titular falecido que continua movimentando;
- a mudança do corte da R01 de 4× para 3× a renda em mar/2026;
- férias de duas analistas no pico da onda, que fazem a fila estourar o prazo
  em junho;
- uma pré-triagem automática a partir de jul/2026;
- a falha do job de checagem de CPF em 14–16/abr, reprocessada em 20/abr;
- ruído legítimo: venda de carro, vaquinha, inauguração, PLR de dezembro,
  farmácia 24h cadastrada como comercial.

O gabarito das tipologias fica em `data/pld_gabarito.parquet` e só os testes
o leem — um deles verifica que cada tipologia é encontrada pela regra que diz
encontrá-la. Documentos aparecem mascarados, e os códigos de cliente (T-, L-,
E-) são inventados.

### Automação de baixo custo: a fila em Google Sheets

`automacoes/apps_script/fila_pld.gs` leva a mesma fila para uma planilha, sem
squad de engenharia:

1. `python scripts/exportar_fila.py` gera o CSV dos alertas abertos, com a
   prioridade já calculada pelo Python (a planilha não reimplementa a regra,
   para as duas nunca divergirem). Importe na aba `alertas`; cadastre os
   feriados na aba `feriados`.
2. Em **Extensões › Apps Script**, cole o arquivo e, em Propriedades do
   script, crie `SLACK_WEBHOOK` com o webhook do canal de Compliance.
3. Rode `instalar()` uma vez. Ele cria a aba `fila`, protege as colunas
   calculadas e agenda o `resumoDoDia()` para todo dia útil às 8h.

Daí em diante: a fila é refeita toda manhã preservando as decisões já
digitadas; os vencidos sobem para o topo; a decisão só é carimbada com data e
e-mail se tiver justificativa; comunicação ganha o prazo de envio em dia útil;
tudo vai para a aba `log`; e o Slack recebe o resumo com vencidos, o que vence
em 7 dias, o que precisa ser enviado ao Coaf hoje e os cinco primeiros da fila.

### Rosto da Ravena

Como os outros agentes, a Ravena tem duas imagens em `assets/`, e o painel
escolhe uma ou outra pelo lugar em que ela aparece:

| Arquivo | Onde aparece | Expressão |
|---|---|---|
| `ravena-animada.png` | card do domínio e cabeçalho da conversa | de bom humor, com a bola na boca — é a Ravena quando você chega para perguntar |
| `ravena-alerta.png` | aba de Alertas e topo das telas de PLD | orelha em pé e olho fixo — é a Ravena quando alguma coisa saiu do lugar |

As duas são PNG de 320×320 com fundo transparente, no padrão dos demais
(`scripts/recortar_agentes.py` faz o recorte). Trocar o rosto de um agente é
trocar esses dois arquivos: nenhuma linha de código muda.

---

## Arquitetura

```
                    ┌──────────────────────────────────────┐
   pergunta ───────▶│  Planejador (LLM)                    │
   em linguagem     │  traduz para um plano com chaves     │
   natural          │  conhecidas. Não vê a base.          │
                    └──────────────┬───────────────────────┘
                                   │  plano validado
                                   ▼
   ┌────────────────────────────────────────────────────────────┐
   │  CAMADA SEMÂNTICA DO DOMÍNIO                               │
   │  métricas, dimensões, grão, limites, sinônimos             │
   │  (vulcano/dominios/*.py — um arquivo por domínio)          │
   └───────────────┬────────────────────────────────────────────┘
                   │  mesma declaração para tudo
     ┌────────┬────────┼────────┬──────────┬─────────────┐
     ▼        ▼        ▼        ▼          ▼             ▼
  gráficos  compa-  causa    alertas   tendência    leitura
            ração    raiz   (histórico  (OLS + t,   (insights,
           (4 bases)(cascata) + limite   sazona-    tendência,
                             + motivo)   lidade)    recomendações)
     └────────┴────────┴────────┴──────────┴─────────────┘
                   │  SQL montado a partir da declaração
                   ▼
            DuckDB sobre Parquet
                   │  fatos calculados
                   ▼
        ┌──────────────────────────┐
        │  Narrador (LLM)          │──────▶ resposta em três camadas:
        │  escreve SOBRE os        │        número → o que explica →
        │  números. Não calcula.   │        o que fazer
        └──────────────────────────┘
```

O padrão central é **o modelo planeja, o Python calcula**. O LLM aparece nas
duas pontas e nunca no meio: traduz a pergunta em um plano estruturado, e depois
escreve o texto em cima de números que já foram calculados. Ele não vê a base,
não escreve SQL e não produz nenhum número.

### Por que não texto-para-SQL direto

Deixar o modelo escrever SQL livre traz três problemas que só aparecem quando a
ferramenta começa a ser usada de verdade:

1. **A mesma pergunta devolve dois números.** O modelo reescreve a regra de
   negócio de um jeito ligeiramente diferente a cada execução.
2. **O erro de grão passa em silêncio.** Uma junção a mais duplica linhas e o
   resultado continua parecendo plausível.
3. **Não há o que validar.** SQL livre não tem superfície de teste.

Restringindo a saída a um plano com chaves conhecidas, uma pergunta impossível
falha na validação — e o agente diz o que não sabe fazer — em vez de acertar a
sintaxe e errar a conta.

### A conversa tem memória

Cada agente guarda o plano da pergunta anterior e as últimas trocas. Depois de
`quanto foi a receita?`, a pergunta seguinte é `e por quê?` — não "por que a
receita mudou?". O que o usuário não repete, o agente mantém: métrica, quebra e
período. Sem isso a conversa fica amnésica e cada pergunta precisa ser um
parágrafo completo, o que ninguém faz.

O painel dentro da aba do agente explica isso com uma tabela de sequência
típica, porque a capacidade não é descobrível sozinha.

### Degradação graciosa

Sem `OPENAI_API_KEY`, um interpretador determinístico assume o lugar do modelo:
sinônimos por domínio, expressões de período, e a narração sai dos mesmos
geradores de texto que as abas usam. Fica menos flexível na linguagem e continua
correto no número. Uma ferramenta de portfólio não pode quebrar na frente de
quem está avaliando.

---

## As decisões que valem discussão

### A cascata expõe o resíduo em vez de escondê-lo

Métrica cujo numerador é uma **soma** sempre pode ser quebrada por qualquer
dimensão. Métrica cujo numerador é uma **contagem distinta** só fecha quando a
dimensão assume um valor único por entidade contada:

| | fecha? | por quê |
|---|---|---|
| pedidos por região | sim | um pedido tem uma região só |
| pedidos por categoria | não | um pedido pode ter itens de duas categorias |
| clientes por região | **não** | uma pessoa pode comprar para duas regiões |

O terceiro caso é o que engana, e foi um bug real durante o desenvolvimento:
região é uma dimensão "grossa" e parece segura, mas quando a entidade contada
muda de pedido para pessoa, a regra muda junto. Por isso a métrica declara *que*
entidade conta e a dimensão declara *para quais entidades ela é única* — em vez
de um "grão" único, que não distingue os dois casos. Um teste cobra as duas
direções: que todo caso marcado como fechável realmente feche, e que os casos
marcados como não-fecháveis realmente não fechem (senão o modelo estaria só
sendo conservador).

A saída fácil seria redistribuir a sobra entre as barras para o gráfico ficar
bonito. Aqui o resíduo é calculado, mostrado na cascata e explicado.

### Efeito taxa e efeito mix andam separados

Escrevendo uma razão como média ponderada, `R = Σ wᵢ · rᵢ`, a variação abre em
três termos que somam exatamente `ΔR`:

```
ΔR = Σ wᵢ,A · Δrᵢ      efeito taxa   — o segmento em si mudou
   + Σ Δwᵢ · rᵢ,A      efeito mix    — mudou a composição
   + Σ Δwᵢ · Δrᵢ       interação     — os dois ao mesmo tempo
```

Ticket médio cair porque cada segmento ficou mais barato e ticket médio cair
porque mudou quem comprou são **diagnósticos opostos**: um pede ação no
segmento, o outro em aquisição. A média simples não distingue os dois.

### Alertas: dois cortes, não um

Todo alerta passa por duas provas — ser estatisticamente estranho **e** mover o
total o suficiente para valer o telefonema.

- **Baseline robusto.** Média e desvio padrão são arrastados pelo próprio ponto
  que se quer detectar: uma Black Friday infla os dois e o alerta seguinte não
  dispara. Aqui o baseline é mediana + MAD, com z robusto
  `z = (x − mediana) / (1,4826 · MAD)`.
- **Corte de materialidade.** Segmento pequeno estoura z-score o tempo todo —
  variação relativa em base pequena é enorme por construção. Sem esse corte o
  painel dispara dezenas de alertas por dia, ninguém lê, e o produto morre.

O painel deixa os dois cortes ajustáveis na tela, de propósito: baixar a
materialidade para zero e ver o painel encher de ruído é a demonstração de por
que ele existe.

Para métrica de razão, a materialidade é medida no **denominador**, não no
numerador. Um cancelamento em um único pedido move o numerador em 100% e
passaria como "toda a métrica"; o que decide se vale o telefonema é o tamanho da
população, não o do evento.

### O alerta já vem com o motivo provável

"A receita caiu" manda a pessoa abrir outra aba para descobrir onde. Junto do
alerta roda a decomposição por segmento, e a frase nomeia quem carregou o
desvio.

O segmento escolhido **não é o maior**. Seria tautológico: o maior segmento
carrega o maior pedaço de qualquer variação, todo dia. O critério é
**desproporção** — a fatia do desvio dividida pela fatia normal da métrica. Um
segmento que responde por 4% da receita e por 100% da queda é notícia; um que
responde por 60% dos dois não é.

### Tendência só é afirmada quando há evidência

"Subiu vs ontem" e "está subindo" são perguntas diferentes. A direção só é
afirmada quando a inclinação por mínimos quadrados se distingue de zero (t e
p-valor); caso contrário o painel diz **estável** e mostra o t. Sem isso,
qualquer série tem inclinação diferente de zero e todo ruído vira tendência.

O módulo também mede sazonalidade semanal antes de ler o nível — no varejo o
efeito de dia da semana costuma ser maior que o efeito que se quer medir — e é
por isso que a comparação padrão de um dia é contra **D-7**, e não contra ontem.

### A seta e a cor carregam informações diferentes

Na tabela de comparação a **seta** diz a direção (subiu ou desceu) e a **cor**
diz o julgamento (a favor ou contra o negócio). Cancelamento caindo é ▼ verde;
prazo de entrega subindo é ▲ vermelho. Separar os dois canais é o que permite a
tabela responder sozinha o que um gráfico de barras responderia — e por isso o
gráfico saiu: ele repetia a tabela com menos densidade.

Variação que arredonda para zero na tela fica **cinza**, não vermelha. Pintar um
"-0,0%" de vermelho faz o painel gritar por ruído de arredondamento, e quem lê
aprende a ignorar a cor — que era justamente o canal que precisava ser confiável.

### A escolha da base muda a conclusão, então as quatro aparecem juntas

O mesmo dia contra ontem, contra D-7, contra o mês acumulado anterior e contra a
média dos 3 mesmos dias da semana costuma dar quatro leituras diferentes — e
quem monta o slide escolhe a que conta a história que quer. A aba de comparação
mostra as quatro lado a lado, com **as datas de cada base escritas na tela**:
"-8%" sem saber contra o quê não quer dizer nada.

A base composta (média dos 3 mesmos dias da semana) tira a média dos **valores
da métrica** em cada janela, não das razões empilhadas: juntar os denominadores
de três dias e dividir uma vez só responde outra pergunta.

### Produto olha jornada, não só métrica solta

Marketing pergunta quanto entrou; produto pergunta **onde travou**. Os eventos
do Olist têm carimbo de tempo por etapa — compra, aprovação do pagamento,
postagem, entrega — e viram um funil de pedidos e o tempo de cada perna. A
métrica interessante ali não é "entregas": é a queda entre duas barras e quantas
horas o pedido passou parado em cada etapa.

### "Pior" não é sinônimo de "menor"

O pior prazo de entrega é o **maior**; o pior faturamento é o **menor**. Cada
métrica declara `bom_quando_sobe`, e o agente usa isso para ordenar. Ler
"piores estados em prazo" como ordenação crescente devolve justamente os
melhores, com cara de resposta certa — é o tipo de erro que passa despercebido
porque o formato da resposta está perfeito.

### Crédito: safra jovem aparece vazia, nunca zero

Inadimplência leva meses para aparecer. Preencher safra imatura com zero é o que
faz um painel mostrar risco caindo justamente quando ele ainda não teve tempo de
acontecer.

A censura é aplicada **no nível da safra**, não do contrato: a safra só entra na
conta quando o seu último contrato completou o MOB exigido. Censurar por idade
individual deixaria fevereiro entrar com os contratos do dia 1 marcados e os do
dia 28 não — e a taxa sairia calculada só sobre os contratos mais antigos da
safra, que já tiveram mais tempo de quebrar. A safra parcial aparece pior do que
é, e a leitura vira "a safra nova está horrível" quando o que se está vendo é um
recorte.

### Qualidade de dado é regra declarada, não corte à mão

Os últimos dias da base do Olist são cauda de extração: os pedidos caem de ~250
por dia para 1, e o cancelamento vai a 100%. Ler isso como queda de vendas seria
um erro grosseiro — não é o negócio caindo, é o arquivo acabando.

O corte não é uma data escolhida a dedo: descarta-se, do fim para trás, todo dia
com volume abaixo de 50% da mediana móvel de 28 dias. A regra se ajusta sozinha
se a base for atualizada, e fica auditável.

---

## Dados

| Domínio | Fonte | Período |
|---|---|---|
| Marketing e CRM | Brazilian E-Commerce Public Dataset by Olist — **dado público real**, 99 mil pedidos | jan/2017 – ago/2018 |
| Produto e Operação | Mesma base do Olist, lida pela ótica de operação e satisfação | jan/2017 – ago/2018 |
| Crédito | **Carteira simulada** — ver abaixo | jan/2017 – ago/2018 |
| Compliance e PLD | **Operação simulada** — ver a seção da Ravena | set/2025 – ago/2026 |

**Sobre o domínio de crédito:** não há base pública de crédito com data de
originação e marcação de inadimplência disponível, e sem ela não dá para mostrar
a análise que importa em crédito — desempenho por safra. A carteira foi gerada
com estrutura declarada em `scripts/build_credito.py`: curva de aprovação por
faixa de score, curva de maturação da inadimplência, choque de política em
set–nov/2017, aperto em 2018, efeito de canal e censura à direita. **A modelagem
é real; o dado não é**, e o app diz isso em toda tela.

O choque plantado serve de gabarito: existe um teste que verifica se o motor de
causa raiz encontra sozinho as safras de set/out/nov de 2017 como as piores.

---

## Estrutura

```
iniciar.bat                 atalho de dois cliques (Windows)
iniciar.command             atalho de dois cliques (macOS/Linux)
app.py                      interface Streamlit — só tela, nenhuma conta
telas_pld.py                as abas que só Compliance tem (fila, dossiê, regras)
vulcano/
  semantica.py              Metrica, Dimensao, Limite, Dominio
  dominios/                 um arquivo por domínio (a única coisa a escrever
    marketing.py            para adicionar um quarto)
    credito.py
    produto.py
    pld.py
  pld/                      o que só existe em PLD
    regras.py               catálogo: indicador, corte, condições, norma
    normas.py               os trechos da 3.978 e da 4.001 citados na tela
    fila.py                 prioridade explicável e a fila em qualquer data
    parecer.py              o dossiê e o rascunho de parecer
    agente.py               intenções da Ravena: fila, dossiê, regra
    calendario.py           dias úteis e prazos
    dados.py                tabelas auxiliares do job
  dados.py                  montagem de SQL e acesso via DuckDB
  periodos.py               resolução de período e período comparável
  causa_raiz.py             decomposição aditiva e taxa/mix/interação
  alertas.py                baseline robusto, materialidade, limites
  tendencia.py              OLS com t, momento, sequência, sazonalidade
  agente.py                 planejador, validador, executor, narrador
  conversa.py               personalidades, conceitos e o "não entendi"
  analise.py                leitura: insights, tendência, recomendações
  graficos.py               Plotly com paleta validada para daltonismo
  estilo.py                 CSS e componentes
scripts/
  build_fact.py             ETL do Olist
  build_credito.py          gerador da carteira simulada
  build_pld.py              gerador da operação de PLD simulada + job de regras
  exportar_fila.py          CSV da fila para a planilha do Apps Script
  acentuar.py               acentuação do texto (só dentro de literais)
  exportar_amostra.py       roda os motores e exporta o JSON da amostra
  build_amostra.py          injeta o JSON no template e gera a amostra
  recortar_agentes.py       recorta os rostos dos agentes (fundo transparente)
  smoke.js                  percorre o app no navegador e caça exceções
  ver_amostra.js            abre a amostra em 390px, nos dois temas
assets/                     rostos dos agentes, PNG com fundo transparente
amostra/                    amostra estática de uma página (dados + HTML)
automacoes/apps_script/     a fila de PLD em Google Sheets, com gatilho e Slack
tests/test_motor.py         invariantes do motor
tests/test_pld.py           invariantes de Compliance
data/                       parquets gerados
```

Adicionar um quarto domínio é escrever um arquivo em `vulcano/dominios/` e
incluí-lo na lista. Nenhum motor precisa ser tocado.

---

## Rodando

**O jeito mais simples — dois cliques:**

| Sistema | Arquivo |
|---|---|
| Windows | `iniciar.bat` |
| macOS / Linux | `iniciar.command` |

Eles acham o Python, criam um ambiente isolado (`.venv`) só na primeira vez,
instalam as bibliotecas e abrem o navegador. Da segunda vez em diante sobem em
poucos segundos. No macOS, se o sistema recusar o arquivo, rode uma vez
`chmod +x iniciar.command`.

Os dados já vêm prontos em `data/`; não é preciso gerar nada.

**Na mão, se preferir:**

```bash
pip install -r requirements.txt
streamlit run app.py
```

Para regerar os dados do zero:

```bash
bash scripts/baixar_olist.sh       # baixa os CSVs públicos do Olist
python scripts/build_fact.py       # tabela fato do Olist
python scripts/build_credito.py    # carteira simulada de crédito
python scripts/build_pld.py        # operação simulada de PLD
```

### Ligando o agente com modelo de linguagem

A chave é procurada em dois lugares, nesta ordem:

1. a variável de ambiente `OPENAI_API_KEY`;
2. os *secrets* do Streamlit — `.streamlit/secrets.toml` local, ou o painel de
   Secrets no Streamlit Cloud.

O segundo caminho existe porque `st.secrets` **não** exporta nada para o
ambiente: um app publicado no Cloud com a chave configurada no painel cairia no
modo determinístico sem dar nenhum sinal do motivo.

Usando os atalhos `iniciar.bat` / `iniciar.command`, basta criar um arquivo
`chave-openai.txt` na pasta do projeto, com a chave numa linha só. Ele já está
no `.gitignore`, então não vai parar no GitHub por acidente.

Sem chave nenhuma o app roda igual, com o interpretador determinístico — a
linguagem fica menos flexível e os números continuam os mesmos.

---

## Publicando no Streamlit Community Cloud

O repositório já está pronto para deploy: `requirements.txt` na raiz, `app.py`
como arquivo principal, e os dois Parquet versionados em `data/` (11 MB no
total — bem abaixo do limite do GitHub).

1. Faça o push para o GitHub.
2. Em [share.streamlit.io](https://share.streamlit.io), **Create app** →
   **Deploy a public app from GitHub**.
3. Preencha:
   - **Repository:** `SEU-USUARIO/dashboard_inteligente`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Em **Advanced settings**, escolha **Python 3.12** e, se quiser o agente com
   modelo de linguagem, cole em *Secrets*:

   ```toml
   OPENAI_API_KEY = "sk-..."
   ```

   Esse é o único lugar onde a chave entra. Ela **não** vai para o repositório:
   `.streamlit/secrets.toml` está no `.gitignore`, e o app procura a chave
   primeiro no ambiente e depois em `st.secrets` — justamente porque o
   `st.secrets` do Cloud não exporta nada para o ambiente, e ler só
   `os.environ` faria a chave configurada no painel ser ignorada em silêncio.
5. **Deploy**. A primeira subida leva alguns minutos (instala as
   dependências); as seguintes são rápidas.

Depois disso, todo push na `main` reimplanta sozinho.

**O que fazer se algo falhar:**

| Sintoma | Causa provável |
|---|---|
| `FileNotFoundError: falta o arquivo de dados` | os Parquet não foram para o repositório — confira se `data/*.parquet` está versionado (só `data/raw/` é ignorado) |
| app sobe mas o agente responde seco | não é erro: sem chave ele roda no interpretador determinístico |
| erro instalando dependência | troque a versão do Python nas *Advanced settings* |
| app "dorme" e mostra "get this app back up" | comportamento normal do plano gratuito depois de dias sem acesso; um clique acorda |

### Testes

```bash
python tests/test_motor.py         # ou: python -m pytest tests/ -q
node scripts/smoke.js              # percorre as 26 telas no navegador
```

Os testes não verificam "o código roda" — verificam as afirmações que o produto
faz na tela: que a cascata soma exatamente a variação quando promete somar (490
combinações de métrica × dimensão × período), que o resíduo aparece quando não
promete, que o número do agente é o número da aba, que o filtro da barra lateral
chega ao agente, que safra imatura fica vazia, que o baseline robusto detecta um
desvio que média-e-desvio não detectaria, que "pior" respeita a direção da
métrica, que "oi" não vira faturamento, que "o que é um alerta" explica
enquanto "tem alerta hoje?" lista, e que o funil aponta a queda entre duas
etapas em vez do nível da última.

Em Compliance, `tests/test_pld.py` cobra que cada tipologia plantada é
encontrada pela regra certa, que a calibração conta o mesmo que o motor, que a
fila da aba é o "em aberto" do motor, que alerta imaturo não entra em taxa,
que o prazo de comunicação pula feriado, que a prioridade é a soma dos fatores
mostrados, que o dossiê não inventa número nem decide, e que cada pergunta vai
para a rota certa.

---

## Stack

Python, DuckDB, pandas, NumPy, Plotly, Streamlit e a biblioteca da OpenAI para o
agente. Sem scipy: a regressão e o teste t são contas fechadas de OLS simples.

A paleta é azul, e não por gosto só: azul é a cor de série mais separável em
deuteranopia e protanopia, que juntas cobrem a maior parte da visão de cor
atípica. A paleta passa pelos seis testes de acessibilidade — banda de
luminosidade, piso de croma, separação para daltonismo (deuteranopia,
protanopia, tritanopia), piso de visão normal e contraste sobre a superfície.
Toda tela com gráfico tem a tabela ao lado: além da acessibilidade, é o que
permite conferir a conta — num produto que responde em linguagem natural, poder
auditar o número é requisito, não enfeite.
