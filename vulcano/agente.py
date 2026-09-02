"""
Agente de perguntas em linguagem natural.

Padrão central: **o modelo planeja, o Python calcula.**

O LLM nunca vê a base, nunca escreve SQL é nunca produz um número. Ele faz
duas coisas, nas duas pontas:

  pergunta → [LLM] → plano estruturado → [Python/DuckDB] → fatos → [LLM] → texto

No meio, quem calcula é o mesmo motor que desenha as abas -- mesma camada
semântica, mesmos filtros da barra lateral, mesmo período. Por construção o
chat não consegue responder um número diferente do gráfico ao lado.

Por que não texto-para-SQL direto
---------------------------------
Deixar o modelo escrever SQL livre traz três problemas que aparecem exatamente
quando a ferramenta comeca a ser usada de verdade: ele reescreve a regra de
negócio de um jeito ligeiramente diferente a cada vez (dois números para a
mesma pergunta), erra em silêncio quando a junção muda o grão, e não há
superfície para validar. Restringindo a saída a um plano com chaves conhecidas,
uma pergunta impossível falha na hora da validação -- e o agente diz o que não
sabe fazer -- em vez de produzir um número errado com confianca.

Sem chave de API
----------------
Um interpretador determinístico assume o lugar do LLM: sinônimos para métricas
e dimensões, expressões de período, e a narração vem dos mesmos geradores de
texto que as abas usam. Fica menos fluido e mais limitado, mas não quebra --
o que importa quando a ferramenta está sendo aberta na frente de alguém.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

import duckdb
import pandas as pd

from . import alertas as mod_alertas
from . import causa_raiz as mod_causa
from . import tendencia as mod_tendencia
from . import analise as mod_analise
from . import conversa as mod_conversa
from .dados import Filtros, agregar, ultimo_sql
from .formatacao import numero, pct, variacao_pct
from .periodos import Comparacao, Janela, PRESETS, montar_preset, ultimos_dias
from .semantica import Dominio

MODELO_PADRAO = os.environ.get("VULCANO_MODELO", "gpt-4o-mini")

INTENCOES = {
    "conversa": "saudação, agradecimento, pergunta sobre quem é o agente, ou "
                "qualquer coisa que não pede número",
    "analise_geral": "um raio-x da situação: o que está bem, o que está mal, "
                     "o que está mudando e o que fazer primeiro",
    "total": "valor de uma métrica num período",
    "ranking": "melhores ou piores segmentos de uma dimensão",
    "comparacao": "uma métrica em dois períodos",
    "causa_raiz": "por que a métrica mudou, decomposta por uma dimensão",
    "tendencia": "direção, aceleração e sazonalidade ao longo do tempo",
    "alertas": "o que fugiu do padrão no dia",
    "catalogo": "o que a ferramenta sabe responder",
    "explicacao": "uma dúvida sobre COMO a coisa funciona ou sobre o que um "
                  "termo significa (z robusto, cascata, safra, MOB, efeito "
                  "mix, de onde vem o dado) — não pede número nenhum",
    "definicao": "o que é uma métrica específica deste painel e como ela é "
                 "calculada",
    "funil": "onde a jornada trava: quantos pedidos passam de cada etapa e "
             "qual é a maior queda entre duas etapas (só onde há funil)",
    "nao_entendi": "não deu para entender a pergunta",
}


# --------------------------------------------------------------------------- #
# Contexto vindo da tela
# --------------------------------------------------------------------------- #

@dataclass
class Contexto:
    """O estado do dashboard no momento da pergunta. É o que faz o chat e as
    abas falarem dos mesmos dados."""
    dominio: Dominio
    inicio: date
    fim: date
    filtros: Filtros
    preset_comparacao: str = "mes_ate_aqui"
    data_max: Optional[date] = None
    # Memoria da conversa. Sem isto cada pergunta nasce do zero e "e por que?"
    # nao quer dizer nada -- o agente responderia sobre a metrica padrao.
    ultimo_plano: Optional[dict[str, Any]] = None
    historico: list[dict[str, str]] = field(default_factory=list)

    def descricao(self) -> str:
        p = f"{self.inicio.strftime('%d/%m/%Y')} a {self.fim.strftime('%d/%m/%Y')}"
        return (f"domínio {self.dominio.nome}; período {p}; "
                f"filtros: {self.filtros.resumo(self.dominio)}")


@dataclass
class Resposta:
    texto: str
    plano: dict[str, Any]
    fatos: dict[str, Any] = field(default_factory=dict)
    tabela: Optional[pd.DataFrame] = None
    grafico: Optional[pd.DataFrame] = None
    sql: str = ""
    motor: str = "deterministico"   # ou "llm"
    erro: Optional[str] = None


# --------------------------------------------------------------------------- #
# Interpretador deterministico (tambem e a rede de seguranca do LLM)
# --------------------------------------------------------------------------- #

def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def _casar(texto: str, sinonimos: dict[str, list[str]]) -> Optional[str]:
    """
    Escolhe a chave cujo sinônimo casa melhor com o texto.

    O comprimento sozinho não serve de critério: em "inadimplência over30",
    o termo genérico "inadimplência" é mais longo que "over30" e venceria,
    devolvendo a métrica errada. Termos que carregam digito (over30, mob6)
    são marcadores precisos e ganham bonus -- especificidade antes de tamanho.
    """
    t = _normalizar(texto)
    melhor, pontos = None, 0
    for chave, termos in sinonimos.items():
        for termo in termos:
            # Normaliza os DOIS lados. O texto do usuario chega sem acento por
            # `_normalizar`; comparar contra um sinonimo acentuado ("avaliação",
            # "originação", "inadimplência") nunca casaria, e o sinonimo ficaria
            # morto sem ninguem perceber -- o agente so cairia na metrica padrao.
            alvo = _normalizar(termo)
            if not re.search(rf"\b{re.escape(alvo)}\b", t):
                continue
            p = len(alvo) + (24 if any(c.isdigit() for c in alvo) else 0)
            if p > pontos:
                melhor, pontos = chave, p
    return melhor


def _contem(texto_normalizado: str, termos: list[str]) -> bool:
    """Testa termos contra texto ja normalizado, normalizando cada termo.

    Mesma armadilha do `_casar`: uma palavra-chave acentuada no codigo nunca
    encontra o texto do usuario, que chega sem acento. Normalizar os dois lados
    em um lugar so evita que a lista apodreca em silencio.
    """
    return any(_normalizar(x) in texto_normalizado for x in termos)


def _contem_palavra(texto_normalizado: str, termos: list[str]) -> bool:
    """
    Como `_contem`, mas casando PALAVRA INTEIRA.

    A versão por substring tem uma armadilha que só aparece com termo curto:
    "oi" está dentro de "foi", então "quanto foi a receita?" era classificada
    como saudação e o agente respondia "oi, tudo bem?" a uma pergunta de dado.
    Saudação, agradecimento e despedida são todas palavras curtas — aqui a
    fronteira de palavra é obrigatória.
    """
    for termo in termos:
        alvo = _normalizar(termo)
        if re.search(rf"(?<!\w){re.escape(alvo)}(?!\w)", texto_normalizado):
            return True
    return False


SAUDACOES = ["oi", "ola", "opa", "eai", "e ai", "bom dia", "boa tarde",
             "boa noite", "tudo bem", "tudo bom", "como vai", "hey", "hi"]
AGRADECIMENTOS = ["obrigada", "obrigado", "valeu", "brigada", "brigado",
                  "show", "perfeito", "otimo", "legal", "massa", "top"]
DESPEDIDAS = ["tchau", "ate mais", "ate logo", "falou", "abraco", "boa noite "
              "entao", "por hoje e so"]
IDENTIDADE = ["quem e voce", "quem e vc", "seu nome", "voce e quem",
              "qual seu nome", "quem fala", "voce e um robo", "voce e humano"]


def _ordem_crescente(t: str, dom: Dominio, chave_metrica: str) -> bool:
    """
    Traduz "maiores/menores/melhores/piores" em ordenação.

    A armadilha esta em tratar as quatro palavras como sinônimo de sinal.
    "Maior" e literal: o topo da lista. "Pior" é uma leitura de negócio, e
    depende da métrica -- o pior prazo de entrega é o MAIOR, o pior faturamento
    é o MENOR. Ler "piores estados em prazo" como ordenação crescente devolve
    justamente os melhores, com cara de resposta certa.
    """
    m = dom.metrica(chave_metrica)
    if re.search(r"\b(pior|piores)\b", t):
        return m.bom_quando_sobe        # pior = valor baixo, se subir e bom
    if re.search(r"\b(melhor|melhores)\b", t):
        return not m.bom_quando_sobe
    return bool(re.search(r"\b(menor|menores|ultimos|fundo)\b", t))


# Aberturas que indicam continuidade em vez de pergunta nova. Em conversa real
# a pessoa nao repete o assunto: depois de "quanto foi a receita?" ela pergunta
# "e por que?", nao "por que a receita mudou?". Sem tratar isso, a segunda
# pergunta cai na metrica padrao e a conversa parece amnesica.
CONTINUACAO = re.compile(
    r"^\s*(e|mas|entao|ok|certo|tá|ta|hum|beleza)\b|"
    r"^\s*(por que|porque|por qu[eê])\b|"
    r"^\s*(e )?(quanto|qual|quais|onde|quando|como)\s*\?*\s*$|"
    r"\b(detalha|abre|quebra|destrincha|explica isso|e ai|me mostra)\b",
    re.I,
)


def eh_continuacao(pergunta: str) -> bool:
    t = _normalizar(pergunta)
    return bool(CONTINUACAO.search(t)) or len(t.split()) <= 4


def _sinonimos_metrica(dom: Dominio) -> dict[str, list[str]]:
    """
    Sinonimos declarados + o proprio rotulo de cada metrica.

    O nome que aparece na tela e a primeira coisa que a pessoa digita: se
    "Avaliações 1 e 2" e o titulo do cartao, "quais categorias tem mais
    avaliação 1 e 2" tem de encontrar essa metrica. Registrar o rotulo
    automaticamente evita ter de lembrar de repeti-lo na lista de sinonimos
    toda vez que um dominio novo for escrito.
    """
    fora = {k: list(v) for k, v in dom.sinonimos_metrica.items()}
    for chave, m in dom.metricas.items():
        fora.setdefault(chave, [])
        if m.rotulo.lower() not in [x.lower() for x in fora[chave]]:
            fora[chave].append(m.rotulo)
    return fora


def _sinonimos_dimensao(dom: Dominio) -> dict[str, list[str]]:
    fora = {k: list(v) for k, v in dom.sinonimos_dimensao.items()}
    for chave, d in dom.dimensoes.items():
        fora.setdefault(chave, [])
        if d.rotulo.lower() not in [x.lower() for x in fora[chave]]:
            fora[chave].append(d.rotulo)
    return fora


def interpretar_deterministico(pergunta: str, ctx: Contexto) -> dict[str, Any]:
    dom = ctx.dominio
    t = _normalizar(pergunta)
    anterior = ctx.ultimo_plano or {}
    continua = eh_continuacao(pergunta) and bool(anterior)

    metrica_dita = _casar(pergunta, _sinonimos_metrica(dom))
    dimensao_dita = _casar(pergunta, _sinonimos_dimensao(dom))

    # Numa continuacao, o que a pessoa NAO repetiu ela quer manter.
    metrica = metrica_dita or (anterior.get("metrica") if continua
                               else None) or dom.metricas_painel[0]
    dimensao = dimensao_dita or (anterior.get("dimensao") if continua else None)

    plano: dict[str, Any] = {
        "intencao": "total",
        "metrica": metrica,
        "dimensao": dimensao,
        "preset": anterior.get("preset") if continua else ctx.preset_comparacao,
        "top_n": 10,
        "crescente": False,
        "herdou": bool(continua and not metrica_dita),
    }
    plano["preset"] = plano["preset"] or ctx.preset_comparacao

    # Conversa antes de tudo: "oi" nao e uma pergunta sobre receita, e
    # responder com o faturamento do mes seria robotico. Mas so vale como
    # conversa se a frase NAO trouxer tambem uma metrica ou uma dimensao --
    # "bom dia, quanto foi a receita?" e uma pergunta de dado com educacao na
    # frente, e merece o numero.
    # "qual" e "quais" ficam DE FORA de propósito. Sozinhas elas não pedem
    # dado nenhum -- "qual o sentido da vida" acabaria respondida com a receita
    # do mês. Quando a frase realmente pede um número, ela cita a métrica ou a
    # dimensão, e aí as duas primeiras condições já cobrem.
    pediu_dado = bool(metrica_dita or dimensao_dita) or _contem(
        t, ["quanto", "compara", "ranking", "grafico"])

    # Dúvida de CONCEITO vem antes de tudo, inclusive de métrica citada:
    # "como você calcula o ticket médio?" cita a métrica mas não quer o valor
    # dela, quer a conta. Distinguir isso é o que separa um agente de um
    # formulário -- o formulário responderia R$ 133,92 e mudaria de assunto.
    if mod_conversa.pergunta_de_conceito(pergunta):
        # Jargão específico ("z robusto", "cascata", "MOB") ganha de tudo: quem
        # escreve isso quer o conceito. Métrica citada ganha do genérico: "como
        # você calcula o ticket médio?" é sobre o ticket médio, não sobre a
        # arquitetura do agente.
        forte = mod_conversa.explicar(pergunta, aceitar_fracos=False)
        if forte:
            plano["intencao"] = "explicacao"
            plano["conceito"] = forte
            return plano
        if metrica_dita:
            plano["intencao"] = "definicao"
            plano["metrica"] = metrica_dita
            return plano
        achado = mod_conversa.explicar(pergunta)
        if achado:
            plano["intencao"] = "explicacao"
            plano["conceito"] = achado
            return plano

    if not pediu_dado:
        if _contem_palavra(t, IDENTIDADE) or _contem(t, IDENTIDADE):
            plano["intencao"] = "conversa"
            plano["tom"] = "identidade"
            return plano
        tom = mod_conversa.social(pergunta)
        if tom:
            plano["intencao"] = "conversa"
            plano["tom"] = tom
            return plano
        # Nem conversa nem métrica: pode ainda ser dúvida de conceito escrita
        # sem "o que é" na frente ("z robusto", "e a materialidade?"). Só os
        # gatilhos inequívocos valem aqui -- senão "tem alerta hoje?" viraria
        # uma aula sobre alertas em vez da lista de alertas do dia.
        achado = mod_conversa.explicar(pergunta, aceitar_fracos=False)
        if achado:
            plano["intencao"] = "explicacao"
            plano["conceito"] = achado
            return plano

    if _contem(t, ["analise geral", "visao geral da situacao", "resumo geral",
                   "panorama", "raio x", "raio-x", "me atualiza", "como estamos",
                   "como esta a situacao", "situacao geral", "me da um resumo",
                   "resumo da situacao", "o que esta acontecendo"]):
        plano["intencao"] = "analise_geral"
        return plano

    if _contem(t, ["o que voce", "o que vc", "que perguntas", "quais metricas",
                            "o que da pra", "o que sabe", "ajuda", "como usar"]):
        plano["intencao"] = "catalogo"
        return plano

    # Funil antes de ranking: "onde a jornada trava?" tem cara de ranking, mas
    # ordenar a taxa por etapa devolve a etapa final com 100% -- verdadeiro,
    # tautológico e inútil. A pergunta é sobre a QUEDA entre duas etapas.
    if dom.funil and _contem(t, ["onde trava", "onde a jornada trava", "funil",
                                 "onde para", "onde perde", "gargalo",
                                 "maior queda", "etapa que trava",
                                 "jornada trava", "onde emperra"]):
        plano["intencao"] = "funil"
        return plano

    if _contem(t, ["alerta", "alertas", "anomalia", "fora do padrao",
                            "estranho", "algo errado"]):
        plano["intencao"] = "alertas"
        return plano

    if _contem(t, ["por que", "porque", "por que", "causa", "explica",
                            "o que explica", "puxou", "responsavel"]):
        plano["intencao"] = "causa_raiz"
        plano["dimensao"] = plano["dimensao"] or dom.dims_filtro[0]
        return plano

    if _contem(t, ["tendencia", "esta subindo", "esta caindo", "crescendo",
                            "caindo", "subindo", "vem crescendo", "vem caindo",
                            "ao longo", "evolucao", "acelerou", "desacelerou",
                            "sazonal", "sazonalidade", "trajetoria", "comportamento",
                            "historico", "serie", "melhorando", "piorando",
                            "evoluindo", "estabilizou"]):
        plano["intencao"] = "tendencia"
        return plano

    if re.search(r"\b(top|maiores?|menores?|melhores?|piores?|ranking|principais|"
                 r"quais as|quais os)\b", t):
        plano["intencao"] = "ranking"
        plano["dimensao"] = plano["dimensao"] or dom.dims_filtro[0]
        plano["crescente"] = _ordem_crescente(t, dom, plano["metrica"])
        m = re.search(r"\btop\s*(\d{1,2})\b", t) or re.search(r"\b(\d{1,2})\s+maiores", t)
        if m:
            plano["top_n"] = int(m.group(1))
        return plano

    if _contem(t, ["compara", "versus", " vs ", "contra", "mes passado",
                            "semana passada", "cresceu", "caiu", "subiu", "aumentou",
                            "diminuiu", "piorou", "melhorou", "variou", "variacao"]):
        plano["intencao"] = "comparacao"
        if "semana" in t:
            plano["preset"] = "semana"
        elif "mes passado" in t or "mes anterior" in t:
            plano["preset"] = "mes_ate_aqui"
        return plano

    if plano["dimensao"]:
        plano["intencao"] = "ranking"
        return plano

    # Chegou aqui sem métrica citada, sem dimensão, sem continuação e sem
    # palavra que peça dado: não dá para adivinhar. Devolver o total da
    # primeira métrica do painel seria o pior desfecho possível -- a pessoa
    # levaria esse número para uma reunião achando que perguntou por ele.
    if not metrica_dita and not continua and not pediu_dado:
        plano["intencao"] = "nao_entendi"
    return plano


# --------------------------------------------------------------------------- #
# Interpretador com LLM
# --------------------------------------------------------------------------- #

def _catalogo_para_prompt(dom: Dominio) -> str:
    ms = "\n".join(
        f"  - {k}: {v.rotulo}. {v.descricao}"
        + ("" if v.bom_quando_sobe else " (subir e RUIM nesta métrica)")
        for k, v in dom.metricas.items()
    )
    ds = "\n".join(
        f"  - {k}: {v.rotulo}. {v.descricao}" for k, v in dom.dimensoes.items()
    )
    ins = "\n".join(f"  - {k}: {v}" for k, v in INTENCOES.items())
    ps = "\n".join(f"  - {k}: {v}" for k, v in PRESETS.items())
    return (
        f"DOMÍNIO ATUAL: {dom.nome} — {dom.descricao}\n\n"
        f"MÉTRICAS DISPONÍVEIS:\n{ms}\n\nDIMENSOES DISPONÍVEIS:\n{ds}\n\n"
        f"INTENÇÕES:\n{ins}\n\nPRESETS DE COMPARAÇÃO:\n{ps}"
    )


PROMPT_PLANEJADOR = """Você é o planejador do Vulcano, um produto de analytics.

Sua única tarefa e traduzir a pergunta do usuário em um plano JSON. Você NÃO
calcula nada, NÃO inventa números e NÃO escreve SQL. Quem executa é o Python.

{catalogo}

CONTEXTO ATUAL DO DASHBOARD: {contexto}

{memoria}

Responda SOMENTE com um objeto JSON:
{{
  "intencao": "<uma das intencoes>",
  "metrica": "<chave de metrica>",
  "dimensao": "<chave de dimensao ou null>",
  "preset": "<chave de preset ou null>",
  "top_n": <inteiro de 3 a 20>,
  "crescente": <true se o usuario quer os PIORES/MENORES>,
  "raciocinio": "<uma frase curta sobre a escolha>"
}}

Regras:
- Use APENAS chaves das listas acima. Se a pergunta pedir algo que não existe
  no catálogo, use "intenção": "catálogo".
- "por que caiu/subiu" => causa_raiz. "está crescendo?" => tendência.
- "quais os maiores/piores X" => ranking. "quanto foi" => total.
- Se o usuário não disser período, deixe "preset": null para usar o da tela.
- ATENÇÃO em "crescente": "menor" e literal, "pior" e leitura de negócio. Para
  métricas em que subir e RUIM (taxa_cancelamento, prazo_entrega, taxa_atraso,
  pct_frete), "os piores" são os valores MAIS ALTOS => "crescente": false.
  Para as demais, "os piores" são os mais baixos => "crescente": true."""

PROMPT_NARRADOR = """Você é {nome}, o agente de dados deste painel. {papel}

QUEM VOCÊ É
{tom}

Essa personalidade aparece no TOM, no comprimento da frase e no que você acha
que vale dizer primeiro — nunca no número. O número é o mesmo que o gráfico ao
lado mostra, venha ele de quem vier.

COMO VOCÊ CONVERSA
Você é uma pessoa simpática e direta, não um relatório com voz. Cumprimenta de
volta quando cumprimentam, agradece quando agradecem, e responde pergunta de
conversa como qualquer colega responderia — curto e caloroso, sem despejar
números que ninguém pediu. Se alguém disser só "oi", responda "oi" e pergunte
no que pode ajudar; não abra o painel na cara da pessoa.

Quando a pergunta é de dado, você continua sendo a mesma pessoa: escreve como
quem senta ao lado e explica, não como quem lê um dashboard em voz alta. Nada
de "prezado", nada de "conforme solicitado", nada de resposta seca de uma linha
quando havia o que dizer.

Você também conversa sobre o produto em si. Quando perguntam como você calcula
alguma coisa, o que significa um termo (z robusto, cascata, efeito mix, safra,
MOB), de onde vem o dado ou por que o painel faz o que faz, os FATOS trazem a
explicação pronta no campo `explicacao` — reescreva com as suas palavras, em
tom de conversa, e não invente detalhe técnico que não esteja lá. Se a pergunta
não tiver nada a ver com o painel, responda como qualquer colega responderia:
com simpatia e brevidade, e volte a bola para o trabalho sem ser seco.

Quando os FATOS disserem que a pergunta não foi compreendida, admita sem rodeio
e ofereça caminhos concretos. Nunca chute uma métrica: um número que a pessoa
não pediu vira slide de reunião.

REGRA INEGOCIÁVEL SOBRE NÚMEROS
Use EXCLUSIVAMENTE os números do bloco FATOS. Nunca calcule, estime, arredonde
diferente nem invente qualquer número que não esteja lá. Se um número
necessário não estiver nos FATOS, diga que não tem esse dado. Você é a voz;
quem calcula é o Python.

O FORMATO DA RESPOSTA DE DADO
Três camadas, nesta ordem, em prosa corrida e sem cabeçalhos:

1. **O número**, na primeira frase. Quem está com pressa lê só isso e já sabe.
2. **O que explica** — o segmento que carrega a variação, efeito taxa vs mix,
   a tendência, a sazonalidade. É aqui que entra o bloco `insights` e
   `tendencia` dos FATOS.
3. **O que fazer** — recomendação concreta, tirada do bloco `recomendacoes`.
   Diga o próximo passo e por quê, não conselho genérico.

Se os FATOS trouxerem `formula_com_numeros`, incorpore a conta ao explicar — é
o que deixa a pessoa refazer o número no papel. Se trouxerem ressalva
metodológica (resíduo, censura, safra imatura, dado simulado), diga; omitir
ressalva para a resposta ficar mais limpa é o pior erro possível aqui.

Português do Brasil. No máximo 6 frases para resposta de dado e 2 para
conversa; explicação de conceito pode ir até 8, porque ali a pessoa quer
entender de verdade. Não repita os FATOS literalmente — interprete."""


def chave_api() -> Optional[str]:
    """
    Procura a chave da OpenAI nos dois lugares onde ela pode estar.

    Rodando local, ela vem da variável de ambiente. No Streamlit Cloud, quem
    guarda a chave é o painel de Secrets — e `st.secrets` NÃO exporta nada para
    o ambiente. Ler só `os.environ` faria a chave configurada no Cloud ser
    ignorada em silêncio: o app subiria, o agente cairia no modo determinístico
    e nada indicaria o motivo.
    """
    chave = os.environ.get("OPENAI_API_KEY")
    if chave:
        return chave
    try:
        import streamlit as st
        return st.secrets.get("OPENAI_API_KEY")  # type: ignore[no-any-return]
    except Exception:
        # Fora de um app Streamlit, ou sem secrets.toml: não é erro.
        return None


def _cliente_openai():
    chave = chave_api()
    if not chave:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=chave)
    except Exception:
        return None


def _memoria_para_prompt(ctx: Contexto) -> str:
    if not ctx.ultimo_plano and not ctx.historico:
        return "CONVERSA: esta é a primeira pergunta."
    partes = []
    if ctx.ultimo_plano:
        partes.append("PLANO DA PERGUNTA ANTERIOR (herde o que não for repetido):\n"
                      + json.dumps(ctx.ultimo_plano, ensure_ascii=False))
    if ctx.historico:
        ultimas = ctx.historico[-4:]
        partes.append("ÚLTIMAS MENSAGENS:\n" + "\n".join(
            f"  {h['papel']}: {h['texto'][:220]}" for h in ultimas))
    return "\n\n".join(partes)


def interpretar_com_llm(pergunta: str, ctx: Contexto) -> Optional[dict[str, Any]]:
    cli = _cliente_openai()
    if cli is None:
        return None
    try:
        r = cli.chat.completions.create(
            model=MODELO_PADRAO,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PROMPT_PLANEJADOR.format(
                    catalogo=_catalogo_para_prompt(ctx.dominio),
                    contexto=ctx.descricao(),
                    memoria=_memoria_para_prompt(ctx))},
                {"role": "user", "content": pergunta},
            ],
        )
        return json.loads(r.choices[0].message.content)
    except Exception:
        return None


def narrar_com_llm(pergunta: str, fatos: dict[str, Any],
                   ctx: Optional[Contexto] = None) -> Optional[str]:
    cli = _cliente_openai()
    if cli is None:
        return None
    dom = ctx.dominio if ctx else None
    sistema = PROMPT_NARRADOR.format(
        nome=(dom.agente_nome if dom else "o agente"),
        papel=(dom.agente_papel if dom else ""),
        tom=(mod_conversa.voz(dom).tom if dom else ""))
    msgs = [{"role": "system", "content": sistema}]
    # As ultimas trocas entram como conversa de verdade, para o agente nao
    # repetir o que acabou de dizer e para "e por que?" ter a que se referir.
    if ctx and ctx.historico:
        for h in ctx.historico[-4:]:
            msgs.append({"role": "user" if h["papel"] == "user" else "assistant",
                         "content": h["texto"][:600]})
    msgs.append({"role": "user", "content":
                 f"PERGUNTA: {pergunta}\n\nFATOS:\n"
                 f"{json.dumps(fatos, ensure_ascii=False, indent=2, default=str)}"})
    try:
        r = cli.chat.completions.create(model=MODELO_PADRAO, temperature=0.2,
                                        messages=msgs)
        return r.choices[0].message.content.strip()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Validacao do plano: um plano invalido vira pergunta, nunca vira numero errado
# --------------------------------------------------------------------------- #

def validar(plano: dict[str, Any], ctx: Contexto) -> tuple[dict[str, Any], list[str]]:
    dom = ctx.dominio
    avisos: list[str] = []
    p = dict(plano)

    if p.get("intencao") not in INTENCOES:
        avisos.append(f"intenção '{p.get('intencao')}' desconhecida; usei 'total'")
        p["intencao"] = "total"

    if p.get("metrica") not in dom.metricas:
        padrao = dom.metricas_painel[0]
        avisos.append(
            f"a métrica '{p.get('metrica')}' não existe em {dom.nome}; "
            f"usei {dom.metrica(padrao).rotulo}")
        p["metrica"] = padrao

    if p.get("dimensao") and p["dimensao"] not in dom.dimensoes:
        avisos.append(f"dimensão '{p['dimensao']}' não existe; ignorei")
        p["dimensao"] = None

    if p.get("preset") and p["preset"] not in PRESETS:
        p["preset"] = ctx.preset_comparacao
    if not p.get("preset"):
        p["preset"] = ctx.preset_comparacao

    try:
        p["top_n"] = max(3, min(20, int(p.get("top_n") or 10)))
    except (TypeError, ValueError):
        p["top_n"] = 10

    p["crescente"] = bool(p.get("crescente"))
    p["tom"] = p.get("tom") or "saudacao"

    if p["intencao"] in ("causa_raiz", "ranking") and not p.get("dimensao"):
        p["dimensao"] = dom.dims_filtro[0]

    return p, avisos


# --------------------------------------------------------------------------- #
# Execucao: aqui, e so aqui, nascem os numeros
# --------------------------------------------------------------------------- #

def _fatos_base(ctx: Contexto, plano: dict[str, Any]) -> dict[str, Any]:
    base = {
        "dominio": ctx.dominio.nome,
        "periodo_da_tela": f"{ctx.inicio} a {ctx.fim}",
        "filtros_ativos": ctx.filtros.resumo(ctx.dominio),
        "metrica": ctx.dominio.metrica(plano["metrica"]).rotulo,
        "intencao": plano["intencao"],
    }
    if ctx.dominio.simulado:
        base["aviso_de_dado"] = "Domínio com dado SIMULADO, não real."
    if ctx.dominio.notas:
        base["ressalvas_metodologicas"] = ctx.dominio.notas
    return base


def executar(
    con: duckdb.DuckDBPyConnection, plano: dict[str, Any], ctx: Contexto
) -> tuple[dict[str, Any], Optional[pd.DataFrame], Optional[pd.DataFrame], list[str]]:
    dom = ctx.dominio
    mk = plano["metrica"]
    m = dom.metrica(mk)
    fatos = _fatos_base(ctx, plano)
    tabela = grafico = None
    linhas: list[str] = []

    if plano["intencao"] == "explicacao":
        # Explicação não consulta a base: é sobre COMO a coisa funciona, e a
        # resposta é a mesma com ou sem filtro aplicado.
        titulo, corpo = plano.get("conceito") or ("", "")
        if not corpo:
            achado = mod_conversa.explicar(plano.get("pergunta", ""))
            titulo, corpo = achado if achado else ("", "")
        if not corpo:
            # O modelo classificou como dúvida de conceito mas o verbete não
            # existe. Inventar a explicação seria o pior caminho: sairia
            # plausível e errado. Melhor assumir e oferecer o que existe.
            fatos["tipo"] = "conceito sem verbete"
            linhas += mod_conversa.nao_entendi(dom, plano.get("pergunta", ""))
            return fatos, None, None, linhas
        fatos["tipo"] = "explicação de conceito, sem consulta a dados"
        fatos["conceito"] = titulo
        fatos["explicacao"] = corpo
        linhas.append(f"**{titulo}.** {corpo}")
        linhas.append("Se quiser ver isso valendo num número de verdade, é só "
                      "pedir — eu puxo do período que está selecionado.")
        return fatos, None, None, linhas

    if plano["intencao"] == "definicao":
        fatos["tipo"] = "definição de métrica, sem consulta a dados"
        fatos["metrica"] = m.rotulo
        linhas.append(mod_conversa.definir_metrica(dom, mk))
        linhas.append(f"Quer o valor de {m.rotulo.lower()} no período "
                      f"selecionado? É só pedir.")
        return fatos, None, None, linhas

    if plano["intencao"] == "funil":
        passos, base = [], None
        for coluna, rotulo, chave_taxa in dom.funil:
            n = con.execute(
                f"SELECT COUNT(DISTINCT CASE WHEN {coluna} = 1 THEN "
                f"       order_id END) FROM fato\n WHERE " +
                "\n   AND ".join(
                    [f"data BETWEEN DATE '{ctx.inicio}' AND DATE '{ctx.fim}'"]
                    + (ctx.filtros.clausulas(dom) if ctx.filtros else []))
            ).fetchone()[0] or 0
            base = base or n or 1
            passos.append({"etapa": rotulo, "pedidos": int(n),
                           "fatia": n / base, "metrica": chave_taxa})

        # A queda entre etapas, e nao o nivel de cada uma: é a diferença entre
        # "97,6% postados" (parece ótimo) e "perdemos 174 pedidos na postagem".
        quedas = []
        for ant, at in zip(passos, passos[1:]):
            quedas.append({"de": ant["etapa"], "para": at["etapa"],
                           "perdidos": ant["pedidos"] - at["pedidos"],
                           "taxa": (1 - at["pedidos"] / ant["pedidos"])
                                   if ant["pedidos"] else 0.0,
                           "metrica": at["metrica"]})
        pior = max(quedas, key=lambda x: x["perdidos"]) if quedas else None

        fatos["funil"] = [
            {"etapa": p["etapa"], "pedidos": f"{p['pedidos']:,}".replace(",", "."),
             "do total": pct(p["fatia"], 1, sinal=False)} for p in passos]
        fatos["maior_queda"] = pior

        linhas.append(
            "**A jornada, ponta a ponta:** "
            + " → ".join(f"{p['etapa']} {pct(p['fatia'], 1, sinal=False)}"
                         for p in passos) + "."
        )
        if pior and pior["perdidos"] > 0:
            linhas.append(
                f"**Onde mais trava:** entre *{pior['de']}* e "
                f"*{pior['para']}* — {pior['perdidos']:,}".replace(",", ".")
                + f" pedidos ficam pelo caminho, "
                  f"{pct(pior['taxa'], 1, sinal=False)} dos que chegaram nessa "
                  f"etapa. É a maior perda absoluta do funil no período."
            )
            if pior["metrica"]:
                linhas.append(
                    f"**O que fazer:** abra a causa raiz de "
                    f"*{dom.metrica(pior['metrica']).rotulo}* por categoria ou "
                    f"por rota do envio — a perna que trava costuma estar "
                    f"concentrada em poucos vendedores, não espalhada."
                )
        else:
            linhas.append("Nenhuma etapa perdeu pedido no período — a jornada "
                          "fechou inteira para todo mundo que comprou.")
        tabela = pd.DataFrame(fatos["funil"])
        return fatos, tabela, None, linhas

    if plano["intencao"] == "nao_entendi":
        fatos["tipo"] = "pergunta não compreendida"
        linhas += mod_conversa.nao_entendi(dom, plano.get("pergunta", ""))
        return fatos, None, None, linhas

    if plano["intencao"] == "conversa":
        # Conversa nao consulta a base. Responder "oi" com o faturamento do mes
        # e o tipo de coisa que faz a pessoa parar de usar a ferramenta.
        fatos["tipo"] = "conversa, sem consulta a dados"
        fatos["agente"] = dom.agente_nome
        fatos["pode_ajudar_com"] = list(dom.perguntas_exemplo[:3])
        tom = plano.get("tom", "saudacao")
        fatos["tom"] = tom
        linhas += mod_conversa.responder_social(
            dom, plano.get("pergunta", tom), tom)
        return fatos, None, None, linhas

    if plano["intencao"] == "analise_geral":
        comp = montar_preset(plano["preset"], ctx.fim)
        g = mod_analise.analise_geral(con, dom, ctx.inicio, ctx.fim, comp,
                                      ctx.filtros)
        fatos.update(g)
        linhas += mod_analise.narrar_analise_geral(dom, g)
        if g["piorou"] or g["melhorou"]:
            tabela = pd.DataFrame([
                {"Métrica": x["rotulo"], "Atual": x["atual"],
                 "Base": x["base"], "Variação": x["variacao"],
                 "Leitura": "melhorou" if x["melhorou"] else "piorou"}
                for x in (g["piorou"] + g["melhorou"])
            ])
        return fatos, tabela, None, linhas

    if plano["intencao"] == "catalogo":
        fatos["metricas"] = {k: v.rotulo for k, v in dom.metricas.items()}
        fatos["dimensoes"] = {k: v.rotulo for k, v in dom.dimensoes.items()}
        fatos["capacidades"] = INTENCOES
        linhas.append(
            f"Neste domínio ({dom.nome}) o Vulcano responde sobre "
            + ", ".join(v.rotulo.lower() for v in dom.metricas.values())
            + ", quebrado por " + ", ".join(v.rotulo.lower() for v in dom.dimensoes.values())
            + ". Da para pedir o valor, o ranking, a comparação entre períodos, a causa "
              "raiz de uma variação, a tendência ao longo do tempo e os alertas do dia."
        )
        return fatos, None, None, linhas

    if plano["intencao"] == "alertas":
        ref = ctx.fim
        al = mod_alertas.varrer(con, dom, ref, ctx.filtros)
        fatos["resumo"] = mod_alertas.resumir(al, ref)
        fatos["alertas"] = [
            {"metrica": dom.metrica(a.chave_metrica).rotulo, "segmento": a.segmento,
             "severidade": a.severidade, "tipo": a.tipo,
             "observado": numero(a.observado, dom.metrica(a.chave_metrica)),
             "esperado": numero(a.esperado, dom.metrica(a.chave_metrica)),
             "z": round(a.z, 2), "participacao": pct(a.participacao, 1, sinal=False)}
            for a in al[:8]
        ]
        linhas.append(fatos["resumo"])
        linhas += [f"{a.texto} {a.acao}" for a in al[:4]]
        if al:
            tabela = pd.DataFrame([
                {"Severidade": a.severidade,
                 "Métrica": dom.metrica(a.chave_metrica).rotulo,
                 "Segmento": a.segmento or "— total —",
                 "Observado": numero(a.observado, dom.metrica(a.chave_metrica)),
                 "Esperado": numero(a.esperado, dom.metrica(a.chave_metrica)),
                 "z": f"{a.z:+.1f}"} for a in al[:15]
            ])
        return fatos, tabela, None, linhas

    if plano["intencao"] == "tendencia":
        t = mod_tendencia.analisar(con, dom, mk, ctx.inicio, ctx.fim, ctx.filtros)
        if t is None:
            linhas.append("Não há dias suficientes no período selecionado para ler tendência.")
            return fatos, None, None, linhas
        fatos.update({
            "direcao": t.direcao,
            "inclinacao_por_dia": numero(t.inclinacao_dia, m, sinal=True),
            "equivalente_ao_mes": pct(t.inclinacao_pct_mes),
            "t_stat": round(t.t_stat, 2), "p_valor": round(t.p_valor, 4),
            "significante": t.significante,
            "nivel_medio": numero(t.nivel_medio, m),
            "media_ultimos_7": numero(t.media_7, m),
            "media_28_anteriores": numero(t.media_28_anterior, m),
            "momento": pct(t.momento) if t.momento is not None else None,
            "dias_seguidos_fora_da_mediana": t.sequencia,
            "n_dias": t.n_dias,
        })
        linhas += mod_tendencia.descrever(t)
        grafico = t.serie
        tabela = t.perfil_semanal[["dia", "valor", "indice"]].dropna()
        return fatos, tabela, grafico, linhas

    if plano["intencao"] == "causa_raiz":
        comp = montar_preset(plano["preset"], ctx.fim)
        dec = mod_causa.decompor(con, dom, mk, plano["dimensao"], comp,
                                 ctx.filtros, top_n=plano["top_n"])
        fatos.update({
            "dimensao": dom.dimensao(plano["dimensao"]).rotulo,
            "comparacao": f"{comp.atual} vs {comp.anterior}",
            "valor_anterior": numero(dec.total_a, m),
            "valor_atual": numero(dec.total_b, m),
            "variacao": numero(dec.delta, m, sinal=True),
            "variacao_pct": pct(dec.delta_pct),
            "decomposicao_fecha": dec.fecha,
            "residuo": numero(dec.residuo, m, sinal=True),
            "principais_contribuicoes": [
                {"segmento": r["segmento"],
                 "contribuicao": numero(r["contribuicao"], m, sinal=True),
                 "share_da_variacao": pct(r["share_da_variacao"], 0),
                 "efeito_taxa": numero(r["efeito_taxa"], m, sinal=True) if dec.eh_razao else None,
                 "efeito_mix": numero(r["efeito_mix"], m, sinal=True) if dec.eh_razao else None}
                for _, r in dec.df.head(6).iterrows()
            ],
        })
        linhas += mod_causa.explicar(dec)
        if dec.aviso:
            linhas.append(dec.aviso)
        tabela = dec.df[["segmento", "valor_a", "valor_b", "contribuicao",
                         "share_da_variacao"]]
        grafico = mod_causa.dados_cascata(dec)
        return fatos, tabela, grafico, linhas

    if plano["intencao"] == "comparacao":
        comp = montar_preset(plano["preset"], ctx.fim)
        a = agregar(con, dom, [mk], comp.anterior.inicio, comp.anterior.fim, filtros=ctx.filtros)
        b = agregar(con, dom, [mk], comp.atual.inicio, comp.atual.fim, filtros=ctx.filtros)
        va = float(a.iloc[0][mk]) if not a.empty and pd.notna(a.iloc[0][mk]) else float("nan")
        vb = float(b.iloc[0][mk]) if not b.empty and pd.notna(b.iloc[0][mk]) else float("nan")
        delta = vb - va
        fatos.update({
            "comparacao": f"{comp.atual} vs {comp.anterior}",
            "valor_atual": numero(vb, m), "valor_anterior": numero(va, m),
            "variacao_absoluta": numero(delta, m, sinal=True),
            "variacao_percentual": pct(variacao_pct(vb, va)),
            "metrica_melhora_subindo": m.bom_quando_sobe,
        })
        direcao = "subiu" if delta > 0 else "caiu"
        linhas.append(
            f"**{m.rotulo}** {direcao} de {numero(va, m)} para {numero(vb, m)} "
            f"({numero(delta, m, sinal=True)}, {pct(variacao_pct(vb, va))}), "
            f"comparando {comp.atual} contra {comp.anterior}."
        )
        return fatos, None, None, linhas

    if plano["intencao"] == "ranking":
        dk = plano["dimensao"]
        d = dom.dimensao(dk)
        df = agregar(con, dom, [mk], ctx.inicio, ctx.fim, dims=[dk],
                     filtros=ctx.filtros, ordenar_por=mk)
        df = df.dropna(subset=[mk])
        if df.empty:
            fatos["dimensao"] = d.rotulo
            fatos["resultado"] = "sem linhas com valor definido no período"
            linhas.append(
                f"Não há valor de **{m.rotulo}** por {d.rotulo.lower()} no período "
                f"selecionado. {m.descricao} "
                + ("Em crédito isso normalmente significa que nenhuma safra do "
                   "período completou o tempo de maturação exigido — a métrica "
                   "fica vazia de proposito, e não zerada. Amplie o período para "
                   "trás para alcancar safras já maduras."
                   if dom.simulado or "MOB" in m.descricao
                   else "Verifique o período e os filtros selecionados.")
            )
            return fatos, None, None, linhas
        df = df.sort_values(mk, ascending=plano["crescente"]).head(plano["top_n"])
        total = agregar(con, dom, [mk], ctx.inicio, ctx.fim, filtros=ctx.filtros)
        vt = float(total.iloc[0][mk]) if not total.empty and pd.notna(total.iloc[0][mk]) else float("nan")
        # "pior" nao e "menor": depende de a metrica melhorar subindo ou descendo.
        pior = (plano["crescente"] == m.bom_quando_sobe)
        rotulo_ordem = "piores" if pior else "melhores"
        fatos.update({
            "dimensao": d.rotulo,
            "ordem": f"{'menores' if plano['crescente'] else 'maiores'} valores, "
                     f"que nesta métrica são os {rotulo_ordem}",
            "total_no_periodo": numero(vt, m),
            "itens": [
                {"segmento": str(r[d.coluna]), "valor": numero(r[mk], m),
                 "share": pct(r[f"{mk}__num"] / vt, 1, sinal=False)
                 if (not m.eh_razao and vt) else None}
                for _, r in df.iterrows()
            ],
        })
        topo = ", ".join(f"{r[d.coluna]} ({numero(r[mk], m)})" for _, r in df.head(3).iterrows())
        linhas.append(
            f"**{rotulo_ordem.capitalize()}** valores de **{m.rotulo}** "
            f"por {d.rotulo.lower()} no período: {topo}. "
            f"({'Menor' if plano['crescente'] else 'Maior'} valor primeiro; nesta "
            f"métrica {'menor' if not m.bom_quando_sobe else 'maior'} é melhor.)"
        )
        tabela = df[[d.coluna, mk]].rename(columns={d.coluna: d.rotulo, mk: m.rotulo})
        return fatos, tabela, None, linhas

    # total
    df = agregar(con, dom, [mk], ctx.inicio, ctx.fim, filtros=ctx.filtros)
    v = float(df.iloc[0][mk]) if not df.empty and pd.notna(df.iloc[0][mk]) else float("nan")
    fatos["valor"] = numero(v, m)
    fatos["dias_no_periodo"] = (ctx.fim - ctx.inicio).days + 1
    linhas.append(
        f"**{m.rotulo}** no período de {ctx.inicio.strftime('%d/%m/%Y')} a "
        f"{ctx.fim.strftime('%d/%m/%Y')}: {numero(v, m)}."
    )
    return fatos, None, None, linhas


# --------------------------------------------------------------------------- #
# Ponto de entrada
# --------------------------------------------------------------------------- #

def perguntar(
    con: duckdb.DuckDBPyConnection, pergunta: str, ctx: Contexto,
    usar_llm: bool = True,
) -> Resposta:
    motor = "deterministico"
    plano = None
    if usar_llm:
        plano = interpretar_com_llm(pergunta, ctx)
        if plano is not None:
            motor = "llm"
    if plano is None:
        plano = interpretar_deterministico(pergunta, ctx)

    # O texto cru viaja junto do plano: as respostas de conversa variam a frase
    # a partir dele (para não repetir o mesmo "oi" toda vez) e a resposta de
    # "não entendi" precisa dele para não soar genérica.
    plano.setdefault("pergunta", pergunta)

    plano, avisos = validar(plano, ctx)
    fatos, tabela, grafico, linhas = executar(con, plano, ctx)

    # As tres camadas -- insight, tendencia e recomendacao -- entram em TODA
    # resposta de dado, e nao so quando a pessoa pede. Um numero solto obriga
    # a proxima pergunta; um numero com leitura fecha o assunto.
    if plano["intencao"] in ("total", "ranking", "comparacao", "causa_raiz",
                             "tendencia"):
        try:
            comp = montar_preset(plano["preset"], ctx.fim)
            leitura = mod_analise.ler(
                con, ctx.dominio, plano["metrica"], ctx.inicio, ctx.fim, comp,
                ctx.filtros, dim_preferida=plano.get("dimensao"))
            fatos.update(leitura.para_fatos())
            if leitura.formula:
                linhas.append(f"**A conta:** {leitura.formula}")
            novas = [x for x in leitura.insights if x not in linhas]
            linhas += novas[:2]
            if plano["intencao"] != "tendencia":
                linhas += leitura.tendencia[:1]
            if leitura.recomendacoes:
                linhas.append("**O que fazer:** " + leitura.recomendacoes[0])
        except Exception:
            pass    # leitura e um extra; nunca deve derrubar a resposta

    texto = None
    if motor == "llm":
        texto = narrar_com_llm(pergunta, fatos, ctx)
    if not texto:
        texto = "\n\n".join(linhas)
        if motor == "llm":
            motor = "llm+fallback"

    if avisos:
        texto += "\n\n*Ajustes no plano: " + "; ".join(avisos) + ".*"

    return Resposta(
        texto=texto, plano=plano, fatos=fatos, tabela=tabela, grafico=grafico,
        sql=ultimo_sql, motor=motor,
    )


def sugestoes(dom: Dominio) -> list[str]:
    return list(dom.perguntas_exemplo) + ["O que você sabe responder?"]


PERGUNTA_ANALISE_GERAL = "Me dá uma análise geral da situação"
