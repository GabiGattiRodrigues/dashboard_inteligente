"""
A parte do agente que não é consulta a dado.

Um agente de analytics passa boa parte do tempo respondendo coisas que não são
uma métrica: "oi", "quem é você", "como você calcula isso?", "o que é MOB?",
"por que o número da aba é diferente do que eu esperava?". Responder essas com
um número, ou com um "não entendi, tente reformular", é o que faz a pessoa
parar de usar a ferramenta -- ela conclui que o negócio é um formulário com
cara de chat.

Este módulo cuida de três coisas:

1. **Conversa social** -- saudação, agradecimento, despedida, identidade.
2. **Explicação de conceito** -- as perguntas técnicas sobre como o produto
   funciona e sobre o vocabulário do domínio.
3. **A saída elegante** -- quando nada foi entendido, dizer isso com jeito e
   oferecer caminho, em vez de devolver um número aleatório ou um erro.

Tudo aqui é determinístico. Com chave de API o modelo reescreve por cima destas
linhas, mas o conteúdo é o mesmo -- é o que garante que o agente continue
simpático e correto quando a chave não está configurada.
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from .semantica import Dominio


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _tem(t: str, termos: list[str]) -> bool:
    """Casa por substring, com os dois lados sem acento."""
    alvo = _normalizar(t)
    return any(_normalizar(x) in alvo for x in termos)


# --------------------------------------------------------------------------- #
# 1. Conversa social — uma voz por agente
# --------------------------------------------------------------------------- #
#
# Os tres agentes nao sao o mesmo texto com nome trocado. Abigail e uma gata
# jovem e esperta; Bailey e um cachorro mais velho e metodico; R2 e um cachorro
# mais velho e muito inteligente. A diferenca aparece onde a personalidade
# aparece de verdade -- no TOM, no comprimento da frase e no que cada um acha
# que vale dizer primeiro --, e nunca no numero: os tres leem o mesmo motor e
# devolvem o mesmo valor.
#
# As variantes de cada fala existem para a segunda vez. Um agente que responde
# a mesma frase toda vez que alguem diz oi deixa de parecer alguem e passa a
# parecer uma macro -- e a conversa perde a naturalidade justo onde ela comeca.


@dataclass(frozen=True)
class Voz:
    """A personalidade de um agente, em texto reaproveitavel.

    `tom` vai para o prompt do narrador quando ha chave de API. As listas
    respondem sem chave nenhuma. As duas rotas dizem a mesma coisa do mesmo
    jeito -- o modelo reescreve, nao inventa outra pessoa.
    """
    tom: str
    saudacao: tuple[str, ...]
    agradecimento: tuple[str, ...]
    despedida: tuple[str, ...]
    como_esta: tuple[str, ...]
    elogio: tuple[str, ...]
    convite: str        # o "pode perguntar" de cada um
    admissao: str       # como cada um admite que não entendeu


VOZES: dict[str, Voz] = {
    "abigail": Voz(
        tom=("Gata jovem e esperta. Fala rápido e direto, com energia e "
             "curiosidade — gosta de puxar o fio da meada e já emendar o "
             "próximo passo. Frases curtas. A esperteza aparece em ir direto "
             "ao ponto e em notar o que ninguém pediu, nunca em gracinha: ela "
             "é ágil, não é fofa."),
        saudacao=(
            "Oi! Cheguei antes de você — já dei uma passada nos números de "
            "{dominio}.",
            "Oi! Bora? Estou com {dominio} aberto aqui, no período da barra "
            "lateral.",
            "Oi! Tudo pronto deste lado. O que você quer saber primeiro?",
        ),
        agradecimento=("Magina!", "De nada — pode pedir mais, eu gosto disso.",
                       "Tamo junto."),
        despedida=("Até! Fico de olho nos alertas enquanto você não está.",
                   "Tchau! Se algo fugir do padrão, eu guardo aqui.",
                   "Falou! Volta quando quiser."),
        como_esta=("Tudo ótimo! E você?",
                   "Tudo bem — nenhum número me deu trabalho hoje. E você?"),
        elogio=("Ah, que bom!",
                "Valeu! Se quiser que eu desça mais um nível, é só falar."),
        convite=("Pergunta do jeito que vier — número, ranking, \"por que isso "
                 "mudou?\", ou até como eu faço a conta."),
        admissao=("Essa eu não peguei. E prefiro dizer isso a chutar um número "
                  "que você levaria para uma reunião."),
    ),
    "bailey": Voz(
        tom=("Cachorro mais velho, metódico e simpático. Fala com calma e em "
             "ordem: primeiro a ressalva que muda a leitura, depois o número, "
             "depois o que fazer. Gosta de separar as coisas em partes e de "
             "avisar o que ainda não dá para afirmar. Cuidadoso nunca é seco: "
             "ele explica porque quer que a pessoa entenda, não para se cobrir."),
        saudacao=(
            "Olá! Que bom te ver. Já deixei os números de {dominio} arrumados "
            "aqui — podemos ir por partes.",
            "Oi! Estou com {dominio} aberto, no período da barra lateral. Pode "
            "perguntar com calma.",
            "Olá. Tudo em ordem por aqui, e o período já está carregado.",
        ),
        agradecimento=("Ora, imagina. É para isso que eu estou aqui.",
                       "De nada. Fico contente que tenha ajudado.",
                       "Por nada. Qualquer dúvida, é só voltar."),
        despedida=("Até logo. Deixo os alertas anotados para quando você "
                   "voltar.",
                   "Tchau! Vou ficando de olho no que sair do lugar.",
                   "Até mais. Bom descanso."),
        como_esta=("Tudo em ordem por aqui, obrigado por perguntar. E você?",
                   "Estou bem — nenhuma safra me pregou peça hoje. E você, "
                   "como vai?"),
        elogio=("Fico contente.",
                "Obrigado. Se quiser que eu detalhe algum ponto, detalho com "
                "prazer."),
        convite=("Pergunte no seu ritmo. Se a resposta tiver uma ressalva "
                 "importante — safra jovem, dado ainda imaturo — eu digo "
                 "antes do número."),
        admissao=("Essa eu não entendi direito, e prefiro dizer isso a "
                  "responder por cima. Número chutado vira decisão errada."),
    ),
    "r2": Voz(
        tom=("Cachorro mais velho e muito inteligente. Fala pouco e certo: "
             "enxerga o sistema inteiro e liga as pontas que ninguém tinha "
             "ligado. Calmo e seguro, nunca arrogante. Corta o supérfluo, mas "
             "não corta a simpatia — a frase é curta porque está afiada, não "
             "porque ele está com pressa."),
        saudacao=(
            "Oi. {dominio} carregado, no período da barra lateral. O que você "
            "quer olhar?",
            "Olá! Já passei os olhos na jornada do período. Pode perguntar.",
            "Oi. Estou pronto — e a jornada tem coisa para contar hoje.",
        ),
        agradecimento=("De nada.", "Por nada — foi rápido.",
                       "Imagina. Chama quando precisar."),
        despedida=("Até. Os alertas ficam guardados.",
                   "Tchau! Se alguma etapa travar, eu registro.",
                   "Até mais."),
        como_esta=("Tudo certo. E você?",
                   "Bem. A jornada fechou inteira hoje até agora. E você?"),
        elogio=("Que bom.",
                "Obrigado. Posso descer mais um nível, se ajudar."),
        convite=("Pode perguntar direto. Se a resposta estiver em outra etapa "
                 "da jornada, eu levo você até lá."),
        admissao=("Não entendi essa. Prefiro dizer do que responder por cima."),
    ),
}

# Voz de reserva: dominio novo que ainda nao declarou personalidade nao pode
# quebrar a conversa -- ele so fala num tom neutro ate alguem escrever a dele.
VOZ_PADRAO = Voz(
    tom="Analista simpático e direto.",
    saudacao=("Oi! Estou com {dominio} aberto aqui, no período da barra "
              "lateral.",),
    agradecimento=("Imagina, é para isso que eu estou aqui.",),
    despedida=("Até! Fico de olho nos alertas.",),
    como_esta=("Tudo bem por aqui, obrigado. E você?",),
    elogio=("Que bom que ajudou!",),
    convite="Pergunte do jeito que vier à cabeça.",
    admissao="Essa eu não peguei — e prefiro dizer isso a chutar um número.",
)


def voz(dom: Dominio) -> Voz:
    return VOZES.get(getattr(dom, "agente_voz", ""), VOZ_PADRAO)


def _artigo(dom: Dominio) -> str:
    """"Sou a Abigail" / "Sou o Bailey". Gênero errado no nome próprio é a
    primeira coisa que denuncia texto gerado em massa."""
    return f"Sou {dom.agente_artigo}"


def _escolher(opcoes, semente: str, **fmt) -> str:
    """
    Variação estável: a mesma frase para a mesma pergunta.

    `random` puro faria a resposta mudar a cada rerun do Streamlit -- e o
    Streamlit reexecuta o script inteiro a cada clique em qualquer lugar da
    tela. A pessoa veria a resposta anterior se reescrevendo sozinha enquanto
    mexe num filtro, o que é assustador. A semente é o próprio texto da
    pergunta: varia entre perguntas e é fixa dentro de uma.
    """
    r = random.Random(semente)
    return r.choice(list(opcoes)).format(**fmt)


# --------------------------------------------------------------------------- #
# 2. Explicação de conceito
# --------------------------------------------------------------------------- #
#
# Cada verbete é (gatilhos, título, texto). Os gatilhos são checados por
# substring sem acento, então "z robusto", "z-robusto" e "Z ROBUSTO" casam.
#
# O texto é escrito para ser lido em voz de conversa, não de documentação: a
# pessoa perguntou no chat, então a resposta começa pela ideia e só depois
# desce para a fórmula.

# Cada verbete traz DOIS conjuntos de gatilhos. Os fortes valem sempre: quem
# escreve "z robusto" está perguntando o que é isso, não pedindo um número. Os
# fracos só valem quando a frase já soa como dúvida ("o que é", "como
# funciona") -- porque "alerta", "tendência" e "filtro" sozinhos são consultas,
# não perguntas de conceito, e sequestrá-las quebraria o painel.
FRACOS: dict[str, list[str]] = {
    "Z robusto": ["mad"],
    "A cascata e o resíduo": ["decompor", "decomposicao"],
    "Efeito taxa e efeito mix": ["mix", "interacao"],
    "Como a tendência é afirmada": ["tendencia", "inclinacao", "regressao"],
    "Safra, MOB e censura": ["safra", "coorte", "cohort", "vintage",
                             "maturacao"],
    # "como você calcula" é fraco de propósito: com uma métrica citada na
    # frase, a pergunta é sobre AQUELA métrica, e não sobre a arquitetura.
    "Como eu funciono por dentro": ["como voce calcula", "como vc calcula",
                                    "como se calcula", "usa ia",
                                    "arquitetura", "voce inventa"],
    "Por que a base de comparação muda a conclusão": ["d-7", "d 7", "d-1"],
    "Filtros e quebra": ["filtro", "filtros", "quebra", "barra lateral"],
    "Como um alerta nasce": ["alerta"],
}

CONCEITOS: list[tuple[list[str], str, str]] = [
    (["z robusto", "z-robusto", "escore z", "z score", "z-score", "mad",
      "desvio absoluto mediano", "quao estranho"],
     "Z robusto",
     "É o quanto o dia de hoje está fora do que essa métrica costuma ser. "
     "A conta usa **mediana** e **MAD** (desvio absoluto mediano) dos 56 dias "
     "anteriores, e não média e desvio padrão: `z = (x − mediana) ÷ "
     "(1,4826 × MAD)`.\n\n"
     "O motivo de não usar média é prático. Uma Black Friday infla a média e "
     "infla mais ainda o desvio padrão — e aí o dia seguinte, que também está "
     "estranho, não dispara nada, porque o próprio pico que se queria detectar "
     "alargou a régua. Mediana e MAD quase não se mexem com um ponto extremo, "
     "então a régua continua valendo."),

    (["materialidade", "quao relevante", "corte de relevancia",
      "segmento pequeno"],
     "Materialidade",
     "É o segundo corte do alerta: além de ser estranho, o movimento precisa "
     "**mexer o total o suficiente para valer o telefonema**.\n\n"
     "Sem ele o painel vira ruído. Segmento pequeno estoura z-score toda "
     "semana — variação relativa sobre base pequena é enorme por construção, e "
     "uma categoria que responde por 0,3% da receita dobrar não muda nada na "
     "vida de ninguém. Em métrica de razão a materialidade é medida no "
     "**denominador**, não no numerador: um cancelamento num único pedido move "
     "o numerador em 100% e passaria como 'toda a métrica'."),

    (["cascata", "waterfall", "decomposicao", "decompor", "residuo"],
     "A cascata e o resíduo",
     "A cascata pega a variação de uma métrica entre dois períodos e mostra "
     "quanto cada segmento contribuiu para ela. As barras somam exatamente a "
     "variação total — quando somam.\n\n"
     "Nem sempre somam, e é aí que aparece o **resíduo**. Métrica cujo "
     "numerador é uma soma fecha com qualquer dimensão. Métrica de contagem "
     "distinta (pedidos, clientes) só fecha quando a dimensão tem um valor "
     "único por entidade contada: um pedido tem uma região só, mas pode ter "
     "itens de duas categorias, e a mesma pessoa pode comprar para duas "
     "regiões. Quando não fecha, o resíduo é calculado e mostrado, em vez de "
     "redistribuído entre as barras para o gráfico ficar bonito."),

    (["efeito taxa", "efeito mix", "taxa vs mix", "interacao", "mix"],
     "Efeito taxa e efeito mix",
     "Toda razão pode ser escrita como média ponderada, `R = Σ wᵢ · rᵢ`, e a "
     "variação abre em três pedaços que somam exatamente ΔR:\n\n"
     "- **efeito taxa** (`Σ wᵢ,A · Δrᵢ`) — cada segmento mudou em si;\n"
     "- **efeito mix** (`Σ Δwᵢ · rᵢ,A`) — mudou a composição, quem entrou na "
     "base;\n"
     "- **interação** (`Σ Δwᵢ · Δrᵢ`) — os dois ao mesmo tempo.\n\n"
     "A separação importa porque os dois diagnósticos pedem ações opostas. "
     "Ticket médio caindo porque cada segmento ficou mais barato é problema de "
     "preço ou de operação. Ticket médio caindo porque mudou quem comprou é "
     "problema de aquisição — mexer no preço ali não resolve nada."),

    (["tendencia", "ols", "regressao", "p-valor", "p valor", "inclinacao",
      "significancia"],
     "Como a tendência é afirmada",
     "'Subiu vs ontem' e 'está subindo' são perguntas diferentes. A direção só "
     "é afirmada quando a inclinação por mínimos quadrados se distingue de "
     "zero — a conta devolve t e p-valor, e abaixo do corte o painel diz "
     "**estável** e mostra o t em vez de inventar uma direção.\n\n"
     "Sem isso qualquer série tem inclinação diferente de zero e todo ruído "
     "vira tendência. O módulo também mede sazonalidade semanal antes de ler o "
     "nível: no varejo o efeito de dia da semana costuma ser maior que o "
     "efeito que se quer medir, e é por isso que a comparação padrão de um dia "
     "é contra **D-7**, e não contra ontem."),

    (["mob", "safra", "coorte", "cohort", "vintage", "censura", "maturacao"],
     "Safra, MOB e censura",
     "**Safra** é o mês em que o contrato foi originado; **MOB** (months on "
     "book) é quanto tempo ele já viveu. Inadimplência leva meses para "
     "aparecer, então uma safra nova ainda não teve tempo de quebrar.\n\n"
     "Preencher safra imatura com zero é o que faz um painel mostrar risco "
     "caindo justamente quando ele ainda não aconteceu. Aqui a safra jovem "
     "aparece **vazia**, nunca zero. E a censura é aplicada no nível da safra "
     "inteira, não do contrato: a safra só entra na conta quando o seu último "
     "contrato completou o MOB exigido. Censurar por idade individual deixaria "
     "a safra entrar só com os contratos do começo do mês — que já tiveram "
     "mais tempo de quebrar — e ela apareceria pior do que é."),

    (["camada semantica", "semantica", "como o numero", "mesmo numero",
      "bate com o grafico", "numero do grafico", "confio no numero",
      "por que confiar"],
     "Por que o meu número é o número da aba",
     "Porque não existem dois caminhos. Cada domínio declara suas métricas e "
     "dimensões num único arquivo — o SQL de cada métrica, se ela é razão, se "
     "subir é bom, sobre que entidade ela conta. Os gráficos leem daí, e eu "
     "leio daí.\n\n"
     "Eu também respeito os mesmos filtros da barra lateral. Então se o "
     "gráfico mostra um número e eu falo outro, isso é bug — e não uma "
     "diferença de interpretação. Pode me cobrar."),

    (["como voce funciona", "como vc funciona", "como voce calcula",
      "como vc calcula", "voce escreve sql", "escreve sql", "text to sql",
      "texto para sql", "usa ia", "usa llm", "qual modelo", "modelo de "
      "linguagem", "chatgpt", "openai", "voce inventa", "alucina",
      "alucinacao", "arquitetura"],
     "Como eu funciono por dentro",
     "O padrão é **o modelo planeja, o Python calcula**. O modelo de linguagem "
     "aparece nas duas pontas e nunca no meio:\n\n"
     "1. ele traduz a sua pergunta num plano estruturado, usando só chaves que "
     "existem no catálogo do domínio;\n"
     "2. o Python executa esse plano contra o banco e devolve números;\n"
     "3. o modelo volta só para escrever o texto **em cima** dos números já "
     "calculados.\n\n"
     "Ele não vê a base, não escreve SQL e não produz nenhum número. É por "
     "isso que eu não invento valor: para eu errar um número, o erro teria de "
     "estar no SQL declarado da métrica — que é o mesmo que desenha o "
     "gráfico.\n\n"
     "E se a chave de API não estiver configurada, um interpretador "
     "determinístico assume: a linguagem fica menos flexível, os números "
     "continuam os mesmos."),

    (["de onde vem o dado", "de onde vem esse dado", "de onde vem os dados",
      "de onde vem esses dados", "de onde saem os dados", "de onde sai o dado",
      "fonte do dado", "fonte dos dados", "qual a fonte", "origem do dado",
      "que base", "qual base", "dado real", "dado simulado", "e simulado",
      "dados sao", "dados reais", "isso e real", "real ou simulado"],
     "De onde vem o dado",
     "Depende do domínio, e a aba **Sobre os dados** conta em detalhe. "
     "Marketing e Produto rodam sobre o Brazilian E-Commerce Public Dataset do "
     "Olist — dado público real, 99 mil pedidos de marketplace brasileiro. "
     "Crédito roda sobre uma carteira **simulada**, gerada com estrutura "
     "declarada (curva de aprovação por score, maturação da inadimplência, "
     "choque de política, censura à direita), porque não existe base pública "
     "de crédito com data de originação e marcação de inadimplência. A "
     "modelagem é real; o dado não é — e a tela diz isso o tempo todo."),

    (["d-7", "d 7", "d-1", "base de comparacao", "por que d-7", "mesmos dias",
      "media dos 3", "quatro niveis", "qual comparacao"],
     "Por que a base de comparação muda a conclusão",
     "O mesmo dia contra ontem, contra D-7, contra o mês acumulado anterior e "
     "contra a média dos 3 mesmos dias da semana costuma dar quatro leituras "
     "diferentes. Quem monta o slide escolhe a que conta a história que quer — "
     "e por isso a aba de comparação mostra as quatro juntas, com as datas de "
     "cada base escritas na tela.\n\n"
     "Contra ontem você mede calendário misturado com desempenho: segunda "
     "contra domingo sempre 'cresce'. Contra D-7 o dia da semana some da conta. "
     "A média dos 3 mesmos dias da semana é a mais estável das quatro, porque "
     "não depende de um único dia de base ter sido normal."),

    (["motivo provavel", "possivel motivo", "por que esse segmento",
      "desproporcao", "maior segmento"],
     "Como eu escolho o segmento culpado",
     "Pelo **desproporcional**, não pelo maior. É uma diferença que muda tudo: "
     "o maior segmento carrega o maior pedaço de qualquer variação, todo dia — "
     "dizer que cartão de crédito responde por 82% da queda é inútil quando "
     "cartão já é 80% da receita normal.\n\n"
     "O critério é a fatia do desvio dividida pela fatia normal da métrica. Um "
     "segmento que responde por 4% da receita e por 100% da queda é notícia. "
     "Um que responde por 60% dos dois não é."),

    (["filtro", "filtros", "barra lateral", "quebrar por", "quebra"],
     "Filtros e quebra",
     "Os filtros da barra lateral valem para **tudo** ao mesmo tempo: os "
     "gráficos, os alertas, a causa raiz e as minhas respostas. Se você filtrar "
     "por uma categoria e me perguntar a receita, eu respondo a receita "
     "daquela categoria — não a do total.\n\n"
     "A **quebra** é outra coisa: ela não filtra nada, só faz cada gráfico "
     "mostrar os maiores segmentos da dimensão escolhida em vez do total. "
     "Filtro tira dado da conta; quebra reparte o mesmo dado."),

    (["alerta", "como nasce um alerta", "quando dispara", "trashold",
      "threshold", "limite de negocio"],
     "Como um alerta nasce",
     "De duas origens diferentes, e as duas aparecem misturadas na lista com a "
     "origem escrita no cartão:\n\n"
     "- **desvio do histórico** — o dia está fora do que essa métrica costuma "
     "ser (é o z robusto);\n"
     "- **limite de negócio** — um patamar fixo combinado com a área, que "
     "dispara mesmo quando o histórico já se acostumou com o problema.\n\n"
     "O segundo existe porque o primeiro sozinho tem um ponto cego: métrica que "
     "piora devagar e sempre nunca fica 'estranha', porque o normal foi "
     "descendo junto."),
]


def explicar(texto: str,
             aceitar_fracos: bool = True) -> Optional[tuple[str, str]]:
    """
    Devolve (título, explicação) se a pergunta for sobre um conceito.

    Com `aceitar_fracos=False` só os gatilhos inequívocos contam. É o modo
    usado quando a frase NÃO soa como dúvida: aí "tem alerta hoje?" continua
    sendo uma consulta de alertas, e não um pedido de aula sobre alertas.
    """
    t = _normalizar(texto)
    melhor: Optional[tuple[int, str, str]] = None
    for gatilhos, titulo, corpo in CONCEITOS:
        fracos = {_normalizar(x) for x in FRACOS.get(titulo, [])}
        for gat in gatilhos:
            g = _normalizar(gat)
            if not aceitar_fracos and g in fracos:
                continue
            if g in t:
                # O gatilho mais longo ganha: "quao relevante" é mais
                # específico do que "alerta" e descreve melhor a pergunta.
                if melhor is None or len(g) > melhor[0]:
                    melhor = (len(g), titulo, corpo)
    if melhor is None:
        return None
    return melhor[1], melhor[2]


def definir_metrica(dom: Dominio, chave: str) -> str:
    """Texto de 'o que é essa métrica', com a fórmula quando existe."""
    m = dom.metrica(chave)
    partes = [f"**{m.rotulo}** — {m.descricao}"]
    if getattr(m, "formula", None):
        partes.append(f"A conta é: `{m.formula}`.")
    partes.append(
        "Nesta métrica, "
        + ("subir é bom." if m.bom_quando_sobe else "**subir é ruim** — "
           "então uma alta aparece em vermelho no painel.")
    )
    return " ".join(partes)


# --------------------------------------------------------------------------- #
# 3. A saída elegante
# --------------------------------------------------------------------------- #

def pergunta_de_conceito(texto: str) -> bool:
    """Cheira a 'o que é' / 'como funciona' em vez de 'quanto foi'."""
    t = _normalizar(texto)
    return bool(re.search(
        r"\b(o que e|oq e|que e|o que sao|como funciona|como voce|como vc|"
        r"por que voce|por que vc|significa|quer dizer|explica|explique|"
        r"me explica|como assim|qual a diferenca|diferenca entre|como nasce|"
        r"como surge|como e calculad|como sao calculad|como e feit|"
        r"para que serve|pra que serve|por que existe|qual a logica|"
        r"como se calcula|de onde vem|de onde sai|como voces|em que consiste)\b",
        t))


def social(texto: str) -> Optional[str]:
    """Classifica a conversa social. None quando não é isso."""
    t = _normalizar(texto)
    if re.search(r"\b(tudo bem|tudo bom|como vai|como voce esta|como vc esta|"
                 r"beleza)\b", t):
        return "como_esta"
    if _tem(t, ["obrigad", "valeu", "brigad", "agradec"]):
        return "agradecimento"
    if _tem(t, ["muito bom", "otimo", "perfeito", "adorei", "gostei", "show",
                "massa", "top", "excelente", "boa"]):
        return "elogio"
    if re.search(r"\b(tchau|ate mais|ate logo|falou|abraco|por hoje e so|"
                 r"ate amanha)\b", t):
        return "despedida"
    if re.search(r"\b(oi|ola|opa|e ai|eai|hey|hi|bom dia|boa tarde|"
                 r"boa noite)\b", t):
        return "saudacao"
    return None


def responder_social(dom: Dominio, texto: str, tom: str) -> list[str]:
    """As linhas da conversa social, na voz do agente do domínio."""
    v = voz(dom)
    dominio = dom.nome
    exemplos = "*" + "* · *".join(dom.perguntas_exemplo[:3]) + "*"

    if tom == "agradecimento":
        return [_escolher(v.agradecimento, texto),
                f"Se quiser puxar outro fio de {dominio}, é só falar."]
    if tom == "elogio":
        return [_escolher(v.elogio, texto)]
    if tom == "despedida":
        return [_escolher(v.despedida, texto)]
    if tom == "como_esta":
        return [_escolher(v.como_esta, texto),
                f"Enquanto isso: quer que eu dê uma varrida geral em "
                f"{dominio} e te conte o que mudou?"]
    if tom == "identidade":
        return [
            f"{_artigo(dom)} {dom.agente_nome}. {dom.agente_papel}",
            "Leio a mesma camada semântica que desenha os gráficos desta tela "
            "e respeito os mesmos filtros — então o número que eu falo é o "
            "número que você vê. Se divergir, é bug meu, pode cobrar.",
            f"Dá para começar por: {exemplos}",
        ]
    return [
        _escolher(v.saudacao, texto, dominio=dominio),
        v.convite,
        f"Se quiser um ponto de partida: {exemplos}",
    ]


def nao_entendi(dom: Dominio, texto: str) -> list[str]:
    """
    O que dizer quando não deu para entender.

    Errar em silêncio é pior do que não responder: se eu chutar uma métrica e
    devolver um número, a pessoa leva esse número para a reunião. Então aqui o
    agente admite, mostra o que ele sabe fazer e devolve a bola -- sem soar
    como mensagem de erro.
    """
    metricas = ", ".join(x.rotulo.lower() for x in
                         list(dom.metricas.values())[:6])
    dims = ", ".join(x.rotulo.lower() for x in
                     list(dom.dimensoes.values())[:5])
    exemplos = "\n".join(f"- *{p}*" for p in dom.perguntas_exemplo[:4])
    return [
        voz(dom).admissao,
        f"Neste painel eu sei falar de {metricas}, quebrando por {dims}. "
        "Também explico como o produto funciona por dentro, se a dúvida for "
        "essa: como o alerta nasce, o que é z robusto, por que a cascata tem "
        "resíduo.",
        "Se quiser, tente por um destes caminhos:",
        exemplos,
    ]
