# Analytics com agente — três domínios, um motor

Produto de analytics em que o agente não é um chatbot colado ao lado do
dashboard: ele lê a mesma camada semântica que desenha os gráficos, respeita os
mesmos filtros e devolve o mesmo número, por construção.

Três domínios rodam no mesmo motor — **Marketing e CRM**, **Crédito** e
**Produto e Operação** — cada um com o seu próprio agente, com nome, rosto,
personalidade e vocabulário:

| Agente | Domínio | Como fala |
|---|---|---|
| **Abigail** 🐱 | Marketing e CRM | jovem e esperta: frases curtas, energia, já emenda o próximo passo |
| **Bailey** 🐶 | Crédito | mais velho e metódico: primeiro a ressalva, depois o número, depois o que fazer |
| **R2** 🐕 | Produto e Operação | mais velho e muito inteligente: fala pouco e certo, liga as pontas |

Quem responde sobre crédito não é quem responde sobre marketing, porque as
ressalvas e o que conta como resposta boa são outros. A personalidade aparece
no **tom** — nunca no número: os três leem o mesmo motor e devolvem o mesmo
valor. Cada um tem duas caras: a animada na aba de conversa e a atenta na aba
de alertas, para a pessoa reconhecer quem está falando sem legenda.

```
streamlit run app.py
```

Há também uma **amostra estática** em `amostra/` — um retrato do app em uma
página só, que abre no celular sem servidor. Os números dela saem dos motores
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
outros dois domínios, para mostrar a arquitetura e as decisões técnicas.

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
vulcano/
  semantica.py              Metrica, Dimensao, Limite, Dominio
  dominios/                 um arquivo por domínio (a única coisa a escrever
    marketing.py            para adicionar um quarto)
    credito.py
    produto.py
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
  acentuar.py               acentuação do texto (só dentro de literais)
  exportar_amostra.py       roda os motores e exporta o JSON da amostra
  build_amostra.py          injeta o JSON no template e gera a amostra
  recortar_agentes.py       recorta os rostos dos agentes (fundo transparente)
  smoke.js                  percorre o app no navegador e caça exceções
  ver_amostra.js            abre a amostra em 390px, nos dois temas
assets/                     rostos dos agentes, PNG com fundo transparente
amostra/                    amostra estática de uma página (dados + HTML)
tests/test_motor.py         invariantes do motor
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
node scripts/smoke.js              # percorre as 18 telas no navegador
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
