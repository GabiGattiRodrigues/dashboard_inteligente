"""
Os trechos de norma que o painel cita.

Duas normas do Banco Central organizam o monitoramento de PLD/FT de uma
instituição de pagamento:

- **Circular BCB nº 3.978/2020** — o QUE a instituição precisa ter: política,
  avaliação interna de risco, conheça seu cliente, monitoramento, seleção,
  análise, dossiê, comunicação ao Coaf, prazos.
- **Carta Circular BCB nº 4.001/2020** — uma lista EXEMPLIFICATIVA de
  operações e situações que podem configurar indício de suspeita, para
  orientar o monitoramento e a seleção previstos na 3.978.

A 4.001 não é uma lista de regras prontas. Ela diz "isto é indício"; quem
decide o limiar, a janela e a combinação de sinais é a instituição, na sua
avaliação interna de risco. É exatamente essa tradução — de situação descrita
em português para regra com parâmetro — que o catálogo em `regras.py` faz, e
cada regra aponta de volta para o trecho que a justifica.

Os textos abaixo são resumos fiéis para uso no painel, não a transcrição
integral. A referência oficial é sempre o normativo publicado pelo BCB.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Trecho:
    chave: str
    norma: str          # "Circular 3.978" | "Carta Circular 4.001" | "Lei"
    dispositivo: str    # "art. 43, § 1º"
    resumo: str
    curto: str = ""     # nome curto para filtro e tabela

    @property
    def rotulo(self) -> str:
        """"IV, a · Incompatível com renda ou atividade" — para dimensão."""
        return f"{self.dispositivo.replace('art. 1º, ', '')} · {self.curto}"

    @property
    def citacao(self) -> str:
        return f"{self.norma}, {self.dispositivo}"


TRECHOS: dict[str, Trecho] = {t.chave: t for t in [
    # ---------------- Circular 3.978 -------------------------------------- #
    Trecho("3978_art10", "Circular 3.978", "art. 10",
           "Avaliação interna de risco: a instituição identifica e mensura o "
           "risco de uso dos seus produtos para LD/FT, considerando perfis de "
           "clientes, da própria instituição, das operações e dos "
           "funcionários, parceiros e terceirizados."),
    Trecho("3978_art20", "Circular 3.978", "art. 20",
           "Os clientes são classificados nas categorias de risco definidas na "
           "avaliação interna de risco, com base nas informações de "
           "qualificação."),
    Trecho("3978_art27", "Circular 3.978", "art. 27",
           "Pessoas expostas politicamente (PEP): definição e procedimentos "
           "de identificação e de atenção especial à relação de negócio."),
    Trecho("3978_art38", "Circular 3.978", "art. 38",
           "A instituição implementa procedimentos de monitoramento, seleção e "
           "análise de operações e situações, para identificar e dispensar "
           "especial atenção às suspeitas de LD/FT."),
    Trecho("3978_art39", "Circular 3.978", "art. 39",
           "O monitoramento e a seleção consideram, entre outras, operações "
           "cujos valores ou partes se mostrem incompatíveis com a capacidade "
           "financeira do cliente (inciso I, alínea c). O período para "
           "monitorar e selecionar não pode passar de 45 dias (parágrafo "
           "único)."),
    Trecho("3978_art43_1", "Circular 3.978", "art. 43, § 1º",
           "A análise das operações e situações selecionadas não pode passar "
           "de 45 dias, contados da data da seleção."),
    Trecho("3978_art43_2", "Circular 3.978", "art. 43, § 2º",
           "A análise deve ser formalizada em dossiê, independentemente de "
           "haver comunicação ao Coaf."),
    Trecho("3978_art48_2", "Circular 3.978", "art. 48, § 2º",
           "A comunicação da operação ou situação suspeita ao Coaf deve ser "
           "feita até o dia útil seguinte ao da decisão de comunicar."),
    Trecho("3978_art49", "Circular 3.978", "art. 49",
           "Comunicação ao Coaf de depósito, aporte ou saque em espécie de "
           "valor igual ou superior a R$ 50 mil."),
    Trecho("3978_art54", "Circular 3.978", "art. 54",
           "A instituição que não tiver feito comunicação no ano presta "
           "declaração de não ocorrência até dez dias úteis após o fim do "
           "ano."),
    # ---------------- Carta Circular 4.001 -------------------------------- #
    Trecho("4001_III_e", "Carta Circular 4.001", "art. 1º, III, e",
           "Irregularidades nos procedimentos de identificação e registro do "
           "cliente.", curto="Irregularidade na identificação"),
    Trecho("4001_III_f", "Carta Circular 4.001", "art. 1º, III, f",
           "Cadastramento de várias contas numa mesma data, ou em curto "
           "período, com depósitos de valores idênticos ou aproximados, ou "
           "com elementos em comum.", curto="Contas abertas em lote"),
    Trecho("4001_III_j", "Carta Circular 4.001", "art. 1º, III, j",
           "Incompatibilidade da atividade econômica ou do faturamento "
           "informados com o padrão apresentado.", curto="Faturamento incompatível"),
    Trecho("4001_III_l", "Carta Circular 4.001", "art. 1º, III, l",
           "Registro de mesmo e-mail ou IP por pessoas naturais, sem "
           "justificativa razoável.", curto="Mesmo IP ou dispositivo"),
    Trecho("4001_IV_a", "Carta Circular 4.001", "art. 1º, IV, a",
           "Movimentação de recursos incompatível com o patrimônio, a "
           "atividade econômica ou a ocupação profissional e a capacidade "
           "financeira do cliente.", curto="Incompatível com renda ou atividade"),
    Trecho("4001_IV_b", "Carta Circular 4.001", "art. 1º, IV, b",
           "Transferências de valores arredondados na unidade de milhar ou "
           "um pouco abaixo do limite para notificação de operações.", curto="Valores logo abaixo do limite"),
    Trecho("4001_IV_c", "Carta Circular 4.001", "art. 1º, IV, c",
           "Movimentação de recursos de alto valor, de forma contumaz, em "
           "benefício de terceiros.", curto="Alto valor em benefício de terceiros"),
    Trecho("4001_IV_e", "Carta Circular 4.001", "art. 1º, IV, e",
           "Movimentação de quantia significativa por meio de conta até então "
           "pouco movimentada.", curto="Conta pouco movimentada"),
    Trecho("4001_IV_i", "Carta Circular 4.001", "art. 1º, IV, i",
           "Mudança repentina e injustificada na forma de movimentação de "
           "recursos ou nos tipos de transação.", curto="Mudança repentina de padrão"),
    Trecho("4001_IV_l", "Carta Circular 4.001", "art. 1º, IV, l",
           "Operações que, por habitualidade, valor e forma, configurem "
           "artifício para burlar a identificação da origem, do destino ou "
           "dos responsáveis.", curto="Artifício para burlar identificação"),
    Trecho("4001_IV_n", "Carta Circular 4.001", "art. 1º, IV, n",
           "Recebimento de depósitos de diversas origens, sem fundamentação "
           "econômico-financeira.", curto="Depósitos de diversas origens"),
    Trecho("4001_IV_s", "Carta Circular 4.001", "art. 1º, IV, s",
           "Movimentação habitual de recursos de ou para PEP, sem "
           "fundamentação econômico-financeira.", curto="Movimentação habitual de PEP"),
    Trecho("4001_IV_w", "Carta Circular 4.001", "art. 1º, IV, w",
           "Recebimentos relevantes no mesmo terminal de pagamento (POS), "
           "incompatíveis com a capacidade financeira do estabelecimento.", curto="POS incompatível com o estabelecimento"),
    Trecho("4001_IV_y", "Carta Circular 4.001", "art. 1º, IV, y",
           "Transações em horário incompatível com a atividade do "
           "estabelecimento comercial.", curto="Horário incompatível"),
    Trecho("4001_IV_ac", "Carta Circular 4.001", "art. 1º, IV, ac",
           "Movimentação de valores incompatíveis com o faturamento mensal "
           "da pessoa jurídica.", curto="Incompatível com faturamento da PJ"),
    Trecho("4001_XVII_a", "Carta Circular 4.001", "art. 1º, XVII, a",
           "Operação atípica em municípios localizados em regiões de "
           "fronteira.", curto="Operação atípica em fronteira"),
    # ---------------- Lei -------------------------------------------------- #
    Trecho("lei9613_art11", "Lei 9.613/1998", "art. 11",
           "A comunicação ao Coaf é feita sem dar ciência dela a qualquer "
           "pessoa, inclusive ao cliente a quem se refere."),
]}


def trecho(chave: str) -> Trecho:
    return TRECHOS[chave]


def citar(chaves: list[str] | tuple[str, ...]) -> str:
    """"Carta Circular 4.001, art. 1º, IV, a; IV, n" — agrupando por norma."""
    por_norma: dict[str, list[str]] = {}
    for c in chaves:
        t = TRECHOS[c]
        por_norma.setdefault(t.norma, []).append(t.dispositivo)
    partes = []
    for norma, disp in por_norma.items():
        # "art. 1º, IV, a" e "art. 1º, IV, n" viram "art. 1º, IV, a e IV, n"
        if all(d.startswith("art. 1º, ") for d in disp) and len(disp) > 1:
            miolo = " e ".join(d.replace("art. 1º, ", "") for d in disp)
            partes.append(f"{norma}, art. 1º, {miolo}")
        else:
            partes.append(f"{norma}, " + "; ".join(disp))
    return " · ".join(partes)
