"""
Acentua o portugues do projeto, apenas onde e prosa.

Por que isto e um script e nao um sed
-------------------------------------
Os identificadores do codigo sao propositalmente sem acento (`variacao`,
`descricao`, `regiao`) para nao depender de encoding em import, chave de
dicionario e nome de coluna. So o TEXTO precisa de acento. Separar um do outro
exige olhar a sintaxe, e nao o texto puro.

Tres armadilhas, todas encontradas na pratica ao escrever este script:

1. **Chave nao e prosa.** `"regiao"` em `dims_filtro` e uma chave de dominio, e
   `Dimensao(..., coluna="regiao")` e o nome de uma coluna no Parquet.
   Acentuar qualquer um dos dois quebra a consulta em silencio.
2. **A f-string chega inteira.** O tokenizador entrega `f"...{dom.descricao}"`
   como um unico token STRING, incluindo o codigo dentro das chaves. Reescrever
   ali produz `{dom.descrição}` — um atributo que nao existe.
3. **SQL e codigo.** `"COUNT(DISTINCT order_id)"` tem espaco e parece prosa.

Regra final: so vira prosa o literal que tem espaco, nao parece SQL, e a troca
nunca entra no miolo de uma interpolacao.
"""

from __future__ import annotations

import io
import pathlib
import re
import tokenize
from typing import Iterable

MAPA = {
    # -cao / -oes
    "variacao": "variação", "variacoes": "variações",
    "comparacao": "comparação", "comparacoes": "comparações",
    "descricao": "descrição", "descricoes": "descrições",
    "decomposicao": "decomposição", "aquisicao": "aquisição",
    "satisfacao": "satisfação", "operacao": "operação", "operacoes": "operações",
    "originacao": "originação", "aprovacao": "aprovação",
    "interacao": "interação", "participacao": "participação",
    "informacao": "informação", "informacoes": "informações",
    "maturacao": "maturação", "transicao": "transição", "provisao": "provisão",
    "projecao": "projeção", "execucao": "execução", "validacao": "validação",
    "degradacao": "degradação", "narracao": "narração",
    "formatacao": "formatação", "agregacao": "agregação",
    "sobreposicao": "sobreposição", "atencao": "atenção",
    "acao": "ação", "acoes": "ações", "decisao": "decisão", "decisoes": "decisões",
    "versao": "versão", "razao": "razão", "razoes": "razões",
    "opcao": "opção", "opcoes": "opções", "selecao": "seleção",
    "funcao": "função", "relacao": "relação", "situacao": "situação",
    "condicao": "condição", "construcao": "construção", "producao": "produção",
    "distribuicao": "distribuição", "contribuicao": "contribuição",
    "contribuicoes": "contribuições", "correcao": "correção",
    "direcao": "direção", "conversao": "conversão", "extracao": "extração",
    "reclamacao": "reclamação", "avaliacao": "avaliação",
    "avaliacoes": "avaliações", "definicao": "definição",
    "aceleracao": "aceleração", "oscilacao": "oscilação",
    "explicacao": "explicação", "conclusao": "conclusão",
    "sugestao": "sugestão", "sugestoes": "sugestões",
    "intencao": "intenção", "intencoes": "intenções",
    "concessao": "concessão", "declaracao": "declaração",
    "interpretacao": "interpretação", "redistribuicao": "redistribuição",
    "ligacao": "ligação", "juncao": "junção", "posicao": "posição",
    "composicao": "composição", "proporcao": "proporção",
    # -encia / -ancia
    "procedencia": "procedência", "consequencia": "consequência",
    "consequencias": "consequências", "referencia": "referência",
    "experiencia": "experiência", "frequencia": "frequência",
    "inadimplencia": "inadimplência", "tendencia": "tendência",
    "tendencias": "tendências", "eficiencia": "eficiência",
    "antecedencia": "antecedência", "existencia": "existência",
    "evidencia": "evidência", "resistencia": "resistência",
    "consistencia": "consistência", "urgencia": "urgência",
    "diferenca": "diferença", "presenca": "presença", "sentenca": "sentença",
    # -ao / -oes
    "regiao": "região", "regioes": "regiões",
    "dimensao": "dimensão", "dimensoes": "dimensões",
    "cartao": "cartão", "padrao": "padrão", "padroes": "padrões",
    "sao": "são", "nao": "não", "entao": "então",
    "gestao": "gestão", "questao": "questão", "questoes": "questões",
    "grao": "grão", "chao": "chão", "mao": "mão",
    # acentos agudos e circunflexos
    "metrica": "métrica", "metricas": "métricas",
    "periodo": "período", "periodos": "períodos",
    "historico": "histórico", "historicos": "históricos",
    "estatistico": "estatístico", "estatistica": "estatística",
    "estatisticas": "estatísticas",
    "analise": "análise", "analises": "análises",
    "media": "média", "medias": "médias", "medio": "médio", "medios": "médios",
    "mes": "mês", "numero": "número", "numeros": "números",
    "unico": "único", "unica": "única", "unicos": "únicos", "unicas": "únicas",
    "tres": "três", "ja": "já", "voce": "você", "vc": "vc",
    "portugues": "português", "saida": "saída", "saidas": "saídas",
    "credito": "crédito", "debito": "débito",
    "politica": "política", "politicas": "políticas",
    "publico": "público", "publica": "pública", "publicos": "públicos",
    "publicas": "públicas",
    "minimo": "mínimo", "minima": "mínima", "minimos": "mínimos",
    "maximo": "máximo", "maxima": "máxima",
    "proprio": "próprio", "propria": "própria", "proprios": "próprios",
    "alem": "além", "atras": "atrás", "apos": "após", "ate": "até",
    "tambem": "também", "ninguem": "ninguém", "alguem": "alguém",
    "porem": "porém", "sera": "será", "havera": "haverá", "tera": "terá",
    "possivel": "possível", "impossivel": "impossível",
    "disponivel": "disponível", "disponiveis": "disponíveis",
    "indisponivel": "indisponível", "indisponiveis": "indisponíveis",
    "distinguivel": "distinguível", "legivel": "legível",
    "auditavel": "auditável", "agnostico": "agnóstico",
    "semantica": "semântica", "semantico": "semântico",
    "logica": "lógica", "logico": "lógico",
    "grafico": "gráfico", "graficos": "gráficos",
    "tecnica": "técnica", "tecnicas": "técnicas",
    "tecnico": "técnico", "tecnicos": "técnicos",
    "pratica": "prática", "praticas": "práticas",
    "residuo": "resíduo", "residuos": "resíduos",
    "calculo": "cálculo", "calculos": "cálculos",
    "matematica": "matemática", "aritmetica": "aritmética",
    "veiculo": "veículo", "salario": "salário", "salarios": "salários",
    "usuario": "usuário", "usuarios": "usuários",
    "relatorio": "relatório", "diario": "diário", "diaria": "diária",
    "necessario": "necessário", "necessaria": "necessária",
    "aleatorio": "aleatório", "trajetoria": "trajetória",
    "criterio": "critério", "criterios": "critérios",
    "proximo": "próximo", "proxima": "próxima",
    "ultimo": "último", "ultima": "última", "ultimos": "últimos",
    "ultimas": "últimas", "otima": "ótima", "otimo": "ótimo",
    "otica": "ótica", "pessimo": "péssimo",
    "facil": "fácil", "dificil": "difícil", "util": "útil", "uteis": "úteis",
    "nivel": "nível", "niveis": "níveis", "vies": "viés",
    "so": "só", "la": "lá", "ai": "aí",
    "duvida": "dúvida", "duvidas": "dúvidas",
    "ambiguo": "ambíguo", "ambigua": "ambígua",
    "silencio": "silêncio", "codigo": "código", "codigos": "códigos",
    "area": "área", "areas": "áreas", "ve": "vê", "le": "lê", "tem": "tem",
    "transito": "trânsito", "hipotese": "hipótese",
    "estavel": "estável", "instavel": "instável",
    "confiavel": "confiável", "razoavel": "razoável",
    "responsavel": "responsável", "variavel": "variável",
    "variaveis": "variáveis", "comparavel": "comparável",
    "concluida": "concluída", "concluido": "concluído",
    "expoe": "expõe", "poe": "põe", "compoe": "compõe",
    "decompoe": "decompõe", "reconstroi": "reconstrói",
    "constroi": "constrói", "sozinho": "sozinho",
    "consulta": "consulta", "metodologicas": "metodológicas",
    "metodologica": "metodológica", "junior": "júnior",
    "dominio": "domínio", "dominios": "domínios",
    "dicionario": "dicionário", "parametro": "parâmetro",
    "parametros": "parâmetros", "sintaxe": "sintaxe",
    "obvio": "óbvio", "obvia": "óbvia",
}

SQL_MARCAS = re.compile(
    r"\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|SUM|COUNT|DISTINCT|CASE|WHEN|"
    r"THEN|END|CAST|DOUBLE|LIMIT|CREATE|VIEW|read_parquet|IS\s+NULL|"
    r"NOT\s+NULL|NULLS)\b"
)

PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]+")


def _troca(texto: str) -> str:
    def sub(m: re.Match) -> str:
        p = m.group(0)
        novo = MAPA.get(p.lower())
        if novo is None:
            return p
        if p.isupper():
            return novo.upper()
        if p[0].isupper():
            return novo[0].upper() + novo[1:]
        return novo

    return PALAVRA.sub(sub, texto)


# --------------------------------------------------------------------------- #
# Guardas
# --------------------------------------------------------------------------- #

def _eh_prosa(miolo: str) -> bool:
    """Prosa tem espaco e nao e SQL. Literal de um token so e identificador."""
    limpo = miolo.strip()
    if " " not in limpo:
        return False
    if SQL_MARCAS.search(limpo):
        return False
    return True


def _troca_fora_da_interpolacao(miolo: str) -> str:
    """Aplica a troca apenas fora dos blocos {...} de uma f-string."""
    saida: list[str] = []
    i = 0
    for m in re.finditer(r"\{[^{}]*\}", miolo):
        saida.append(_troca(miolo[i:m.start()]))
        saida.append(m.group(0))          # a interpolacao passa intacta
        i = m.end()
    saida.append(_troca(miolo[i:]))
    return "".join(saida)


ABERTURA = re.compile(r"""(?is)^([A-Za-z]*)('''|\"\"\"|'|")(.*)\2$""", re.S)


def _reescrever_literal(bruto: str) -> str:
    """Recebe o literal com aspas e prefixo; devolve reescrito ou intacto."""
    m = ABERTURA.match(bruto)
    if not m:
        return bruto
    prefixo, aspas, miolo = m.group(1), m.group(2), m.group(3)
    if "b" in prefixo.lower():
        return bruto
    if not _eh_prosa(miolo):
        return bruto
    return f"{prefixo}{aspas}{_troca_fora_da_interpolacao(miolo)}{aspas}"


# --------------------------------------------------------------------------- #

def acentuar_arquivo(caminho: pathlib.Path) -> bool:
    fonte = caminho.read_text(encoding="utf-8")
    tokens = list(tokenize.generate_tokens(io.StringIO(fonte).readline))

    edicoes = []
    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        novo = _reescrever_literal(tok.string)
        if novo != tok.string:
            edicoes.append((tok.start, tok.end, novo))

    if not edicoes:
        return False

    linhas = fonte.splitlines(keepends=True)
    for (l0, c0), (l1, c1), novo in sorted(edicoes, reverse=True):
        if l0 == l1:
            linha = linhas[l0 - 1]
            linhas[l0 - 1] = linha[:c0] + novo + linha[c1:]
        else:
            cabeca = linhas[l0 - 1][:c0]
            cauda = linhas[l1 - 1][c1:]
            linhas[l0 - 1:l1] = [cabeca + novo + cauda]

    caminho.write_text("".join(linhas), encoding="utf-8")
    return True


def main(alvos: Iterable[pathlib.Path]) -> None:
    for p in alvos:
        if acentuar_arquivo(p):
            print(f"acentuado: {p}")


if __name__ == "__main__":
    raiz = pathlib.Path(__file__).resolve().parents[1]
    alvos = [raiz / "app.py"] + sorted((raiz / "vulcano").rglob("*.py"))
    main(alvos)
