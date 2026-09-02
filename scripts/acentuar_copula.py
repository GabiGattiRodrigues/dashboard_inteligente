"""
Segunda passada da acentuacao: rotulos de uma palavra e o "e" copulativo.

Sobraram dois casos, e os dois exigem contexto que um dicionario de palavras
nao tem:

1. **Rotulos de uma palavra.** A guarda "so acentua se tiver espaco" protege
   chaves e nomes de coluna, mas junto barra rotulos legitimos como "Regiao"
   e "Credito". Aqui eles sao tratados por lista explicita, pequena e revisada.

2. **O "e" copulativo.** "e" pode ser conjuncao (mantem) ou o verbo ser
   (vira "é"), e a diferenca nao esta na palavra, esta na frase. Trocar tudo
   estragaria as conjuncoes; nao trocar nada deixa o texto errado. A saida e
   uma lista de padroes em que a leitura copulativa e praticamente certa
   ("nao e", "isso e", "que e", "e o que"), e depois uma conferencia manual
   do que sobrar.
"""

from __future__ import annotations

import io
import pathlib
import re
import tokenize

# Rotulos de uma palavra que aparecem na tela e precisam de acento.
# Aplicados so quando o literal e EXATAMENTE um destes, para nunca atingir
# uma chave de dicionario ou nome de coluna homonimo.
ROTULOS = {
    "Regiao": "Região",
    "Credito": "Crédito",
    "Operacao": "Operação",
    "Media": "Média",
    "Periodo": "Período",
    "Metrica": "Métrica",
    "Dimensao": "Dimensão",
    "Segmentos": "Segmentos",
    "Tendencia": "Tendência",
    "Variacao": "Variação",
    "Contribuicao": "Contribuição",
    "Comparacao": "Comparação",
    "Antes": "Antes",
    "Depois": "Depois",
    "Anterior": "Anterior",
    "Atual": "Atual",
    "Leitura": "Leitura",
    "Sev.": "Sev.",
    "Terca": "Terça",
    "Sabado": "Sábado",
    "Nao identificado": "Não identificado",
    "Cartao de credito": "Cartão de crédito",
    "Cartao de debito": "Cartão de débito",
    "A vista": "À vista",
    "Credito pessoal": "Crédito pessoal",
    "CDC veiculo": "CDC veículo",
    "Cartao consignado": "Cartão consignado",
    "Ate 2 SM": "Até 2 SM",
    "Ultimos N dias": "Últimos N dias",
    "Mes": "Mês",
    "Intervalo livre": "Intervalo livre",
    "Visao geral": "Visão geral",
    "Comparacao de periodos": "Comparação de períodos",
    "Sobre os dados": "Sobre os dados",
    "Sudeste": "Sudeste",
    "Producao": "Produção",
}

# Padroes em que "e" e o verbo ser. Revisados um a um.
COPULA = [
    (r"\bnão e\b", "não é"),
    (r"\bisso e\b", "isso é"),
    (r"\bisto e\b", "isto é"),
    (r"\bque e\b", "que é"),
    (r"\be o que\b", "é o que"),
    (r"\be por isso\b", "é por isso"),
    (r"\be exatamente\b", "é exatamente"),
    (r"\be sempre\b", "é sempre"),
    (r"\be nunca\b", "é nunca"),
    (r"\be apenas\b", "é apenas"),
    (r"\be requisito\b", "é requisito"),
    (r"\be enfeite\b", "é enfeite"),
    (r"\be possível\b", "é possível"),
    (r"\be impossível\b", "é impossível"),
    (r"\be necessário\b", "é necessário"),
    (r"\be material\b", "é material"),
    (r"\be um erro\b", "é um erro"),
    (r"\be uma leitura\b", "é uma leitura"),
    (r"\be a única\b", "é a única"),
    (r"\be o único\b", "é o único"),
    (r"\be a ação\b", "é a ação"),
    (r"\be o painel\b", "é o painel"),
    (r"\be o MAIOR\b", "é o MAIOR"),
    (r"\be o erro\b", "é o erro"),
    (r"\be o nome\b", "é o nome"),
    (r"\be o arquivo\b", "é o arquivo"),
    (r"\be o negócio\b", "é o negócio"),
    (r"\be o que separa\b", "é o que separa"),
    (r"\be o que permite\b", "é o que permite"),
    (r"\be o que faz\b", "é o que faz"),
    (r"\be o que importa\b", "é o que importa"),
    (r"\be o que garante\b", "é o que garante"),
    (r"\be censura\b", "é censura"),
    (r"\be calendário\b", "é calendário"),
    (r"\be ruído\b", "é ruído"),
    (r"\be bug\b", "é bug"),
    (r"\be informação\b", "é informação"),
    (r"\be prosa\b", "é prosa"),
    (r"\bAqui e\b", "Aqui é"),
    (r"\bE por isso\b", "É por isso"),
    (r"\bE o painel\b", "É o painel"),
    (r"\bE o que\b", "É o que"),
    (r"\bE a\b(?= (única|conta|ação|regra|saída|leitura|diferença|forma))", "É a"),
    (r"\bE assim\b", "É assim"),
    (r"\bE o\b(?= (único|erro|caso|sinal|que|painel|motor|dado))", "É o"),
    (r"\bsubir e bom\b", "subir é bom"),
    (r"\bmenor e melhor\b", "menor é melhor"),
    (r"\bmaior e melhor\b", "maior é melhor"),
    (r"\bpior e o\b", "pior é o"),
    (r"\be um plugin\b", "é um plugin"),
    (r"\be escrever\b", "é escrever"),
    (r"\be uma dimensão\b", "é uma dimensão"),
    (r"\be um atributo\b", "é um atributo"),
    (r"\be entrega atrasada\b", "é entrega atrasada"),
    (r"\be o limiar\b", "é o limiar"),
    (r"\be quanto entrou\b", "é quanto entrou"),
    (r"\be se a promessa\b", "é se a promessa"),
    (r"\be real\b", "é real"),
    (r"\be uma consulta\b", "é uma consulta"),
    (r"\be enorme\b", "é enorme"),
    (r"\be contagem distinta\b", "é contagem distinta"),
    (r"\be uma contagem distinta\b", "é uma contagem distinta"),
    (r"\be declarada\b", "é declarada"),
    (r"\be feito\b", "é feito"),
    (r"\bComo e feito\b", "Como é feito"),
    (r"\be o verbo\b", "é o verbo"),
    (r"\be identificador\b", "é identificador"),
    (r"\be código\b", "é código"),
    (r"\be razão\b", "é razão"),
    (r"\be aditiva\b", "é aditiva"),
    (r"\bo residual e\b", "o residual é"),
    (r"\bA regra e\b", "A regra é"),
    (r"\ba saída e\b", "a saída é"),
    (r"\bA saída e\b", "A saída é"),
    (r"\bo baseline e\b", "o baseline é"),
    (r"\bo corte e\b", "o corte é"),
    (r"\bo padrão e\b", "o padrão é"),
    (r"\bo ponto e\b", "o ponto é"),
    (r"\bo grão e\b", "o grão é"),
    (r"\ba pergunta e\b", "a pergunta é"),
    (r"\bo dado e\b", "o dado é"),
    (r"\bo dado não e\b", "o dado não é"),
    (r"\bnada e\b", "nada é"),
    (r"\bmas e\b", "mas é"),
    (r"\be legal\b", "é legal"),
    (r"\be mais compatível\b", "é mais compatível"),
    (r"\be mais forte\b", "é mais forte"),
]

SQL_MARCAS = re.compile(
    r"\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|SUM|COUNT|DISTINCT|CASE|WHEN|"
    r"THEN|END|CAST|DOUBLE|LIMIT|CREATE|VIEW|read_parquet)\b"
)
ABERTURA = re.compile(r"""(?is)^([A-Za-z]*)('''|\"\"\"|'|")(.*)\2$""", re.S)


def _reescrever(bruto: str) -> str:
    m = ABERTURA.match(bruto)
    if not m:
        return bruto
    prefixo, aspas, miolo = m.group(1), m.group(2), m.group(3)
    if "b" in prefixo.lower():
        return bruto

    # 1) Rotulo exato de uma palavra.
    if miolo in ROTULOS:
        return f"{prefixo}{aspas}{ROTULOS[miolo]}{aspas}"

    if " " not in miolo.strip() or SQL_MARCAS.search(miolo):
        return bruto

    # 2) Copula, so fora das interpolacoes.
    def aplica(t: str) -> str:
        for padrao, troca in COPULA:
            t = re.sub(padrao, troca, t)
        return t

    saida, i = [], 0
    for mm in re.finditer(r"\{[^{}]*\}", miolo):
        saida.append(aplica(miolo[i:mm.start()]))
        saida.append(mm.group(0))
        i = mm.end()
    saida.append(aplica(miolo[i:]))
    novo = "".join(saida)
    return f"{prefixo}{aspas}{novo}{aspas}" if novo != miolo else bruto


def processar(caminho: pathlib.Path) -> bool:
    fonte = caminho.read_text(encoding="utf-8")
    tokens = list(tokenize.generate_tokens(io.StringIO(fonte).readline))
    edicoes = []
    for tok in tokens:
        if tok.type != tokenize.STRING:
            continue
        novo = _reescrever(tok.string)
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
            cabeca, cauda = linhas[l0 - 1][:c0], linhas[l1 - 1][c1:]
            linhas[l0 - 1:l1] = [cabeca + novo + cauda]
    caminho.write_text("".join(linhas), encoding="utf-8")
    return True


if __name__ == "__main__":
    raiz = pathlib.Path(__file__).resolve().parents[1]
    for p in [raiz / "app.py"] + sorted((raiz / "vulcano").rglob("*.py")):
        if processar(p):
            print(f"segunda passada: {p}")
