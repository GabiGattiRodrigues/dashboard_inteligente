"""
Camada semântica do Vulcano.

Um **domínio** é um plugin: ele declara suas métricas, suas dimensões, seus
limites de alerta e o arquivo de dados. O motor -- causa raiz, alertas,
tendência, agente -- não sabe se está olhando marketing, crédito ou produto.
Recebe um `Dominio` e trabalha.

É por isso que os três dashboards deste app compartilham código em vez de serem
três apps parecidos. Adicionar um quarto domínio é escrever um arquivo de
declaração; não se toca em nenhum motor.

Toda métrica é declarada uma única vez, e as abas E o agente leem daqui. Duas
consequências práticas:

1. Número de tela e número de agente são o mesmo número, por construção.
2. O agente não inventa SQL: ele escolhe entre chaves deste dicionário, e quem
   escreve o SQL é o Python.

Quando uma decomposição fecha
-----------------------------
Métrica cujo numerador é uma SOMA sempre pode ser quebrada por qualquer
dimensão: a soma dos segmentos reconstrói o total. Métrica cujo numerador é uma
CONTAGEM DISTINTA só fecha quando a dimensão assume um valor único por entidade
contada.

    pedidos  por região    fecha      — um pedido tem uma região só
    pedidos  por categoria não fecha  — um pedido pode ter duas categorias
    clientes por região    não fecha  — uma pessoa pode comprar para duas

O terceiro caso é o que engana: região é uma dimensão "grossa" e parece segura,
mas a entidade contada mudou de pedido para pessoa, e com ela mudou a regra.
Por isso a métrica declara QUE entidade conta (`entidade`) e a dimensão declara
para quais entidades ela é única (`unica_por`) — em vez de um "grão" único que
não distingue os dois casos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Grao = Literal["fino", "grosso"]


@dataclass(frozen=True)
class Metrica:
    chave: str
    rotulo: str
    num_sql: str
    den_sql: Optional[str] = None      # None => metrica aditiva
    formato: Literal["moeda", "inteiro", "percentual", "decimal"] = "inteiro"
    grao: Grao = "fino"
    bom_quando_sobe: bool = True
    descricao: str = ""
    casas: int = 0
    # False quando o numerador e contagem distinta: a soma dos segmentos nao
    # reconstroi o total, a menos que a dimensao seja unica por entidade.
    num_aditivo: bool = True
    # QUE entidade a contagem distinta conta ("pedido", "cliente", "contrato").
    # So faz sentido quando num_aditivo e False.
    entidade: Optional[str] = None
    # A conta por tras da metrica, em portugues: "Receita ÷ Pedidos".
    # Serve para o agente mostrar formula + exemplo numerico quando ha conta --
    # e para nao mostrar nada quando a metrica e so uma soma.
    formula: str = ""

    @property
    def eh_razao(self) -> bool:
        return self.den_sql is not None


@dataclass(frozen=True)
class Dimensao:
    chave: str
    rotulo: str
    coluna: str
    nivel: Grao = "grosso"
    descricao: str = ""
    # Entidades para as quais esta dimensao assume UM UNICO valor.
    #
    # E o que decide se uma contagem distinta pode ser decomposta por ela. Um
    # pedido tem uma regiao so, entao contar pedidos por regiao fecha. Uma
    # pessoa pode comprar para duas regioes ao longo do tempo, entao contar
    # CLIENTES por regiao nao fecha -- o mesmo cliente entra nos dois
    # segmentos. Sem declarar isso, a diferenca entre os dois casos e
    # invisivel, e a segunda conta e apresentada como se fechasse.
    unica_por: tuple[str, ...] = ()


@dataclass(frozen=True)
class Limite:
    """Patamar combinado com a área. Independe do histórico -- é o que separa
    'está fora do normal' de 'passou do que foi acordado'."""
    chave_metrica: str
    operador: str   # ">" dispara acima, "<" dispara abaixo
    valor: float
    justificativa: str


@dataclass(frozen=True)
class Dominio:
    chave: str
    nome: str
    subtitulo: str
    descricao: str
    fonte: str                       # procedencia do dado, dita sem rodeio
    simulado: bool
    arquivo: str                     # nome do parquet em data/
    metricas: dict[str, Metrica]
    dimensoes: dict[str, Dimensao]
    metricas_painel: list[str]
    dims_filtro: list[str]
    limites: list[Limite] = field(default_factory=list)
    sinonimos_metrica: dict[str, list[str]] = field(default_factory=dict)
    sinonimos_dimensao: dict[str, list[str]] = field(default_factory=dict)
    perguntas_exemplo: list[str] = field(default_factory=list)
    metricas_alerta: list[str] = field(default_factory=list)
    dims_alerta: list[str] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)   # ressalvas metodologicas

    # Funil da jornada, quando o dominio tem um. Cada passo e
    # (coluna do evento no fato, rotulo, chave da metrica de taxa ou None).
    # Fica declarado aqui, e nao no motor, porque nem todo dominio tem funil --
    # e os que tem, tem etapas diferentes. Vazio significa "sem funil", e o
    # agente simplesmente nao oferece essa resposta.
    funil: list[tuple[str, str, Optional[str]]] = field(default_factory=list)

    # --- identidade do agente deste dominio ------------------------------- #
    # Cada dominio tem seu proprio agente, com nome e rosto: quem responde
    # sobre credito nao e quem responde sobre marketing, porque o vocabulario,
    # as ressalvas e o que conta como resposta boa sao outros. Trocar um agente
    # e editar estas tres linhas no arquivo do dominio -- nada mais.
    agente_nome: str = "Agente"
    agente_rosto: str = "🤖"       # emoji, usado onde nao cabe imagem
    agente_papel: str = ""
    agente_genero: str = "m"       # "f" ou "m" -- so para concordancia
    # Chave da personalidade em vulcano/conversa.py VOZES. E o que faz cada
    # agente falar do seu jeito sem duplicar o texto em tres arquivos.
    agente_voz: str = ""
    # Prefixo dos avatares em assets/: "<prefixo>-animada.png" na aba de
    # conversa e "<prefixo>-alerta.png" na aba de alertas. Vazio = so emoji.
    agente_imagem: str = ""

    # -- consultas ao catalogo --------------------------------------------- #

    # -- concordancia com o nome do agente --------------------------------- #
    #
    # "Pergunte ao Abigail" e o tipo de erro que estraga a personagem em uma
    # palavra. Ficar escrevendo "ao"/"a" na mao em cada tela garante que um
    # agente novo nasca errado em algum canto, entao a conjugacao mora aqui,
    # ao lado do genero declarado.

    @property
    def agente_artigo(self) -> str:
        """"a" ou "o" -- para "conheca A Abigail"."""
        return "a" if self.agente_genero == "f" else "o"

    @property
    def agente_ao(self) -> str:
        """"à" ou "ao" -- para "pergunte À Abigail"."""
        return "à" if self.agente_genero == "f" else "ao"

    @property
    def agente_pronome(self) -> str:
        """"ela" ou "ele" -- para o texto que fala DO agente na terceira
        pessoa ("o que ela faz", "ele mantém o contexto")."""
        return "ela" if self.agente_genero == "f" else "ele"

    @property
    def agente_do(self) -> str:
        """"da" ou "do" -- para "a leitura DA Abigail"."""
        return "da" if self.agente_genero == "f" else "do"

    def metrica(self, chave: str) -> Metrica:
        if chave not in self.metricas:
            raise KeyError(f"métrica desconhecida em {self.chave}: {chave}")
        return self.metricas[chave]

    def dimensao(self, chave: str) -> Dimensao:
        if chave not in self.dimensoes:
            raise KeyError(f"dimensão desconhecida em {self.chave}: {chave}")
        return self.dimensoes[chave]

    def decomposicao_fecha(self, chave_metrica: str, chave_dimensao: str) -> bool:
        """
        Diz se a soma dos segmentos reconstrói o total.

        Numerador aditivo (uma soma) sempre fecha. Contagem distinta só fecha
        quando a dimensão assume um único valor por entidade contada:

        - pedidos por região **fecha** — um pedido tem uma região só;
        - pedidos por categoria **não fecha** — um pedido pode ter itens de
          duas categorias e entra nas duas;
        - clientes por região **não fecha** — a mesma pessoa pode comprar para
          duas regiões ao longo do tempo.

        O terceiro caso é o traiçoeiro: região é uma dimensão "grossa" e parece
        segura, mas a entidade contada mudou de pedido para pessoa, e com ela
        mudou a regra.
        """
        m, d = self.metrica(chave_metrica), self.dimensao(chave_dimensao)
        if m.num_aditivo:
            return True
        return bool(m.entidade and m.entidade in d.unica_por)

    @property
    def alertar_metricas(self) -> list[str]:
        return self.metricas_alerta or self.metricas_painel

    @property
    def alertar_dims(self) -> list[str]:
        return self.dims_alerta or self.dims_filtro[:3]


def indexar(itens: list) -> dict:
    return {i.chave: i for i in itens}
