"""
Base de conhecimento dos agentes -- o "R" do RAG.

Divisão de trabalho
-------------------
O número continua vindo do motor (camada semântica + DuckDB), igual ao
gráfico ao lado. O que esta camada traz é o repertório de quem cuida do
assunto: o que fazer quando a situação é esta, o que não fazer, com quem
falar e como medir depois. Ela nunca devolve número de resultado. Os trechos
dizem O QUE fazer, nunca QUANTO -- o "quanto" é sempre do motor.

Por isso o RAG entra só na terceira camada da resposta (o que fazer) e no
cartão de alerta, e não no número. Recuperar número por similaridade de texto
é o jeito mais curto de o chat responder um valor diferente do gráfico.

O corpus
--------
Um arquivo markdown por domínio em `conhecimento/`. Cada `## Título` é um
trecho recuperável, com metadados e o texto em pt e en:

    ## Título em português | Title in English
    - id: log-regiao-fora
    - metricas: pct_no_prazo, pct_atraso_grave
    - quando: piora            (piora | melhora | ambos)
    - dimensoes: regiao_destino, origem
    - sinais: alerta           (concentrado, espalhado, efeito_taxa,
                                efeito_mix, tendencia, sazonal, alerta)
    - tipo: playbook           (playbook | criterio | armadilha)

    ### pt
    texto...

    ### en
    text...

Quem escreve playbook não precisa saber Python: editar o .md muda o que o
agente recomenda na próxima execução.

A busca
-------
São dezenas de trechos por domínio. Banco vetorial aqui seria infraestrutura
sem problema para resolver, então a busca é simples e auditável:

1. **Filtro duro.** Só o domínio do agente; trecho de "piora" não entra
   quando a métrica melhorou; trecho que declara métricas só entra para elas;
   trecho que declara sinais só entra quando algum desses sinais apareceu
   (o de "efeito mix" não serve quando foi efeito taxa).
2. **BM25** sobre o texto do trecho, com a consulta montada a partir da
   situação calculada (métrica, segmento, efeito, tendência) + a pergunta.
3. **Bônus de metadado** para métrica, dimensão e sinal declarados.
4. **Com chave da OpenAI**, embeddings entram como segundo ranking e os dois
   são fundidos por RRF (reciprocal rank fusion). Sem chave, fica só o BM25
   -- a mesma regra do resto do agente: degrada, não quebra. E sem chave a
   busca é determinística: mesma situação, mesmo trecho.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .i18n import L

PASTA = Path(__file__).resolve().parents[1] / "conhecimento"

QUANDO = {"piora", "melhora", "ambos"}
SINAIS = {"concentrado", "espalhado", "efeito_taxa", "efeito_mix",
          "tendencia", "sazonal", "alerta"}
TIPOS = {"playbook", "criterio", "armadilha"}

MODELO_EMBEDDING = "text-embedding-3-small"

# Palavras que aparecem em todo trecho e não ajudam a separar um do outro.
_PARADAS = set("""
a o as os um uma uns umas de do da dos das no na nos nas em por para pra com
sem e ou que se ao aos à às é ser foi são está esta isso isto esse essa ele
ela eles elas mais menos muito pouco já não nao sim antes depois quando como
qual quais quem onde porque pois mas também tambem só so cada todo toda todos
the an of to in on for with without and or that if is are was be it this
these those as at by from not more less than then when how which who where
""".split())

# Palavras de direção entram na consulta para casar com o vocabulário do
# trecho ("caindo", "subindo", "pior"), não para filtrar -- quem filtra
# direção é o metadado `quando`.
_DIRECAO = {
    True: "piora piorou pior queda caindo subindo worse falling rising",
    False: "melhora melhorou melhor better improving",
}

_SINAL_TEXTO = {
    "concentrado": "concentrado segmento específico concentrated segment",
    "espalhado": "espalhado geral todos spread general all",
    "efeito_taxa": "efeito taxa patamar rate effect",
    "efeito_mix": "efeito mix composição público mix effect composition",
    "tendencia": "tendência sustentada semana após semana sustained trend",
    "sazonal": "sazonalidade calendário dia da semana seasonality weekday",
    "alerta": "alerta fora do controle limite alert out of control",
}


# --------------------------------------------------------------------------- #
# O corpus
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Trecho:
    id: str
    dominio: str
    titulo_pt: str
    titulo_en: str
    texto_pt: str
    texto_en: str
    metricas: tuple[str, ...] = ()
    quando: str = "ambos"
    dimensoes: tuple[str, ...] = ()
    sinais: tuple[str, ...] = ()
    tipo: str = "playbook"

    @property
    def titulo(self) -> str:
        return L(self.titulo_pt, self.titulo_en)

    @property
    def texto(self) -> str:
        return L(self.texto_pt, self.texto_en)

    def texto_indexado(self) -> str:
        """O que a busca enxerga: as duas línguas, para a pergunta em inglês
        casar com o mesmo trecho que a pergunta em português."""
        return " ".join([self.titulo_pt, self.titulo_en, self.texto_pt,
                         self.texto_en, " ".join(self.metricas),
                         " ".join(self.dimensoes)])


def _lista(valor: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in valor.split(",") if x.strip())


def _juntar(linhas: list[str]) -> str:
    """Parágrafos do markdown viram uma frase corrida só."""
    return " ".join(x.strip() for x in linhas if x.strip())


def ler_arquivo(caminho: Path) -> list[Trecho]:
    """Lê um arquivo de playbook. Erro de formato quebra na hora, com o nome
    do trecho: playbook mal escrito que passa em silêncio vira recomendação
    sumida em produção."""
    dominio = caminho.stem
    conteudo = caminho.read_text(encoding="utf-8")
    trechos = []
    for bloco in re.split(r"^## ", conteudo, flags=re.M)[1:]:
        linhas = bloco.splitlines()
        titulo = linhas[0].strip()
        titulo_pt, _, titulo_en = titulo.partition(" | ")
        meta: dict[str, str] = {}
        corpo: dict[str, list[str]] = {"pt": [], "en": []}
        atual = None
        for ln in linhas[1:]:
            s = ln.strip()
            if s.lower() in ("### pt", "### en"):
                atual = s[-2:].lower()
                continue
            if atual is None:
                m = re.match(r"-\s*(\w+)\s*:\s*(.*)", s)
                if m:
                    meta[m.group(1).lower()] = m.group(2).strip()
                continue
            corpo[atual].append(ln)

        onde = f"{caminho.name} › {titulo}"
        if "id" not in meta:
            raise ValueError(f"trecho sem id: {onde}")
        if not corpo["pt"] or not corpo["en"]:
            raise ValueError(f"trecho sem texto em pt e en: {onde}")
        quando = meta.get("quando", "ambos")
        sinais = _lista(meta.get("sinais", ""))
        tipo = meta.get("tipo", "playbook")
        if quando not in QUANDO:
            raise ValueError(f"'quando' inválido ({quando}): {onde}")
        if set(sinais) - SINAIS:
            raise ValueError(f"sinal desconhecido {set(sinais) - SINAIS}: {onde}")
        if tipo not in TIPOS:
            raise ValueError(f"tipo inválido ({tipo}): {onde}")

        trechos.append(Trecho(
            id=meta["id"], dominio=dominio,
            titulo_pt=titulo_pt.strip(),
            titulo_en=(titulo_en or titulo_pt).strip(),
            texto_pt=_juntar(corpo["pt"]), texto_en=_juntar(corpo["en"]),
            metricas=_lista(meta.get("metricas", "")), quando=quando,
            dimensoes=_lista(meta.get("dimensoes", "")), sinais=sinais,
            tipo=tipo,
        ))
    return trechos


@lru_cache(maxsize=None)
def trechos(dominio: str) -> tuple[Trecho, ...]:
    caminho = PASTA / f"{dominio}.md"
    if not caminho.exists():
        return ()
    return tuple(ler_arquivo(caminho))


# --------------------------------------------------------------------------- #
# BM25
# --------------------------------------------------------------------------- #

def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


_PARADAS_N = {_normalizar(p) for p in _PARADAS}


def _radical(t: str) -> str:
    """Radical bem grosseiro: tira plural e algumas terminações, o bastante
    para "safras" casar com "safra" e "caindo" com "caiu"."""
    for suf in ("mente", "ando", "endo", "indo", "ados", "idas", "idos",
                "ing", "ou", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def tokens(texto: str) -> list[str]:
    bruto = re.findall(r"[a-z0-9]+", _normalizar(texto.replace("_", " ")))
    return [_radical(t) for t in bruto if t not in _PARADAS_N and len(t) > 1]


class _Indice:
    def __init__(self, docs: list[str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.freq = [Counter(tokens(d)) for d in docs]
        self.tam = [sum(f.values()) for f in self.freq]
        self.media = (sum(self.tam) / len(self.tam)) if self.tam else 0.0
        df: Counter = Counter()
        for f in self.freq:
            df.update(f.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - q + 0.5) / (q + 0.5))
                    for t, q in df.items()}

    def pontuar(self, consulta: str) -> list[float]:
        q = set(tokens(consulta))
        saida = []
        for f, tam in zip(self.freq, self.tam):
            s = 0.0
            for t in q:
                tf = f.get(t, 0)
                if not tf:
                    continue
                norm = self.k1 * (1 - self.b + self.b * tam / (self.media or 1))
                s += self.idf[t] * tf * (self.k1 + 1) / (tf + norm)
            saida.append(s)
        return saida


@lru_cache(maxsize=None)
def _indice(dominio: str) -> _Indice:
    return _Indice([t.texto_indexado() for t in trechos(dominio)])


# --------------------------------------------------------------------------- #
# Embeddings (opcionais)
# --------------------------------------------------------------------------- #

def _cliente():
    # Import tardio: agente importa analise, que importa este módulo.
    from .agente import _cliente_openai
    return _cliente_openai()


@lru_cache(maxsize=None)
def _vetores_corpus(dominio: str) -> Optional[tuple[tuple[float, ...], ...]]:
    """Embeddings do corpus, uma chamada por domínio por processo. Falhou,
    fica None e a busca segue só com BM25 -- sem tentar de novo a cada
    pergunta, para não pagar a latência do erro toda vez."""
    cli = _cliente()
    ts = trechos(dominio)
    if cli is None or not ts:
        return None
    try:
        r = cli.embeddings.create(
            model=MODELO_EMBEDDING,
            input=[f"{t.titulo_pt}. {t.texto_pt}" for t in ts])
        return tuple(tuple(d.embedding) for d in r.data)
    except Exception:
        return None


def _vetor_consulta(texto: str) -> Optional[tuple[float, ...]]:
    cli = _cliente()
    if cli is None:
        return None
    try:
        r = cli.embeddings.create(model=MODELO_EMBEDDING, input=[texto])
        return tuple(r.data[0].embedding)
    except Exception:
        return None


def _cosseno(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


# --------------------------------------------------------------------------- #
# A busca
# --------------------------------------------------------------------------- #

@dataclass
class Situacao:
    """O que o motor já calculou sobre a métrica. É isso que vira consulta --
    a pergunta da pessoa entra junto, mas a situação é o que manda."""
    metrica: Optional[str] = None
    rotulo_metrica: str = ""
    piorou: Optional[bool] = None
    dimensao: Optional[str] = None
    rotulo_dimensao: str = ""
    segmento: str = ""
    sinais: tuple[str, ...] = ()
    pergunta: str = ""

    def consulta(self) -> str:
        partes = [self.pergunta, self.rotulo_metrica, self.metrica or "",
                  self.rotulo_dimensao, self.segmento]
        if self.piorou is not None:
            partes.append(_DIRECAO[self.piorou])
        partes += [_SINAL_TEXTO[s] for s in self.sinais if s in _SINAL_TEXTO]
        return " ".join(p for p in partes if p)


@dataclass
class Achado:
    trecho: Trecho
    pontos: float
    motivos: list[str] = field(default_factory=list)


def _cabe(t: Trecho, sit: Situacao) -> bool:
    if sit.piorou is not None and t.quando != "ambos":
        if (t.quando == "piora") != sit.piorou:
            return False
    if t.metricas and sit.metrica and sit.metrica not in t.metricas:
        return False
    if t.metricas and not sit.metrica and not sit.pergunta:
        return False
    if t.sinais and not set(t.sinais) & set(sit.sinais):
        return False
    return True


def buscar(dominio: str, sit: Situacao, k: int = 2,
           usar_embeddings: bool = False, minimo: float = 1.0) -> list[Achado]:
    """Os `k` trechos que mais servem para a situação, do mais ao menos útil.

    `minimo` corta o trecho que só passou no filtro mas não conversa com nada
    da situação: melhor não recomendar do que recomendar fora de assunto.
    """
    ts = trechos(dominio)
    if not ts:
        return []
    lex = _indice(dominio).pontuar(sit.consulta())

    candidatos: list[Achado] = []
    for i, t in enumerate(ts):
        if not _cabe(t, sit):
            continue
        a = Achado(t, lex[i])
        if sit.metrica and sit.metrica in t.metricas:
            a.pontos += 3.0
            a.motivos.append(f"métrica {sit.metrica}")
        if sit.dimensao and sit.dimensao in t.dimensoes:
            a.pontos += 1.0
            a.motivos.append(f"dimensão {sit.dimensao}")
        comuns = set(t.sinais) & set(sit.sinais)
        if comuns:
            a.pontos += 1.5 * len(comuns)
            a.motivos.append("sinal " + ", ".join(sorted(comuns)))
        if a.pontos >= minimo:
            candidatos.append(a)
    if not candidatos:
        return []

    # Trecho escrito para a métrica vem antes do trecho geral de situação:
    # "como ler o lift" diz mais sobre lift do que "queda concentrada".
    def _especifico(a: Achado) -> bool:
        return bool(sit.metrica and sit.metrica in a.trecho.metricas)

    candidatos.sort(key=lambda a: (not _especifico(a), -a.pontos, a.trecho.id))

    # Fusão com embeddings: só quando há pergunta de verdade (no cartão de
    # alerta a consulta é toda estruturada e o BM25 com metadado já acerta).
    if usar_embeddings and sit.pergunta:
        vetores = _vetores_corpus(dominio)
        vq = _vetor_consulta(sit.consulta()) if vetores else None
        if vetores and vq:
            pos = {t.id: i for i, t in enumerate(ts)}
            por_sem = sorted(candidatos, key=lambda a: -_cosseno(
                vq, vetores[pos[a.trecho.id]]))
            rank_lex = {a.trecho.id: r for r, a in enumerate(candidatos)}
            rank_sem = {a.trecho.id: r for r, a in enumerate(por_sem)}
            candidatos.sort(key=lambda a: -(
                1 / (60 + rank_lex[a.trecho.id])
                + 1 / (60 + rank_sem[a.trecho.id])))
    return candidatos[:k]


# --------------------------------------------------------------------------- #
# Saída para o agente e para a tela
# --------------------------------------------------------------------------- #

def fonte(t: Trecho, agente: str) -> str:
    return L(f"playbook {agente} › {t.titulo_pt}",
             f"{agente}'s playbook › {t.titulo_en}")


def para_fatos(achados: list[Achado], agente: str) -> list[dict[str, str]]:
    """O formato que vai para o bloco FATOS do narrador."""
    return [{"fonte": fonte(a.trecho, agente), "texto": a.trecho.texto,
             "tipo": a.trecho.tipo} for a in achados]


def linha(item: dict[str, str]) -> str:
    """A frase da resposta sem LLM."""
    return (L("**No playbook:** ", "**From the playbook:** ")
            + item["texto"] + f" *({item['fonte']})*")


def situacao_do_alerta(dom: Any, alerta: Any) -> Situacao:
    m = dom.metrica(alerta.chave_metrica)
    piorou = (alerta.observado > alerta.esperado) != m.bom_quando_sobe
    sinais = ["alerta"]
    if alerta.segmento:
        sinais.append("concentrado")
    rot_dim = ""
    if alerta.dimensao:
        try:
            rot_dim = dom.dimensao(alerta.dimensao).rotulo
        except Exception:
            rot_dim = ""
    return Situacao(metrica=alerta.chave_metrica, rotulo_metrica=m.rotulo,
                    piorou=piorou, dimensao=alerta.dimensao,
                    rotulo_dimensao=rot_dim,
                    segmento=str(alerta.segmento or ""), sinais=tuple(sinais))


def para_alerta(dom: Any, alerta: Any) -> Optional[dict[str, str]]:
    """O trecho do playbook que acompanha o cartão de alerta, ou None."""
    try:
        achados = buscar(dom.chave, situacao_do_alerta(dom, alerta), k=1)
    except Exception:
        return None
    return para_fatos(achados, dom.agente_nome)[0] if achados else None
