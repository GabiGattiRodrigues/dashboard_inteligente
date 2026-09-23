"""
Catálogo de regras de monitoramento PLD.

Cada regra é a tradução de uma situação da Carta Circular 4.001 em algo que um
job consegue rodar: um **indicador**, um **parâmetro** que decide o corte e
**condições fixas** que evitam que o indicador sozinho dispare por bobagem.

    situação descrita na norma  →  indicador + parâmetro + condições  →  alerta

Por que um parâmetro só por regra
---------------------------------
Regra com cinco limiares ajustáveis é regra que ninguém consegue calibrar: não
dá para saber qual deles gerou o falso positivo. Aqui cada regra tem UM
parâmetro que se discute com a área (o múltiplo da renda, o número de
origens), e as demais condições ficam fixas e escritas. É o que permite a aba
de calibração responder "se eu subir este corte, quantos alertas somem e
quantas comunicações eu perco" sem ambiguidade.

Por que a supressão é por competência mensal
--------------------------------------------
Uma conta de passagem continua sendo conta de passagem no dia seguinte. Sem
supressão, a mesma situação gera um alerta por dia e a fila enche de
repetição. A regra aqui é **um alerta por cliente, por regra, por mês**: o
primeiro dia do mês em que o indicador passa do corte. O efeito colateral bom
é que o volume de alertas a qualquer parâmetro vira uma conta exata sobre o
máximo mensal do indicador — e a calibração deixa de ser estimativa.

As funções `avaliar_*` recebem as janelas já agregadas (matrizes entidade ×
dia) e devolvem o indicador e a máscara das condições fixas. São as mesmas
funções que o gerador da base simulada chama: o que a tela explica é o que o
job rodou.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

import numpy as np


@dataclass(frozen=True)
class Parametro:
    nome: str                 # "Múltiplo da renda mensal"
    valor: float              # vigente
    unidade: str              # "×", "origens", "%", "R$"
    minimo: float
    maximo: float
    passo: float
    # (início da vigência, valor). O mais recente vale. Mudança de parâmetro
    # é decisão de política, e fica registrada com data — senão uma quebra
    # de série no volume de alertas parece mudança de comportamento.
    historico: tuple[tuple[date, float], ...] = ()

    def vigente_em(self, d: date) -> float:
        v = self.historico[0][1] if self.historico else self.valor
        for inicio, valor in self.historico:
            if d >= inicio:
                v = valor
        return v

    def formatar(self, v: Optional[float] = None) -> str:
        from .. import i18n
        v = self.valor if v is None else v
        if self.unidade == "R$":
            return i18n.brl(v)
        if self.unidade == "%":
            return f"{v * 100:.0f}%"
        if self.unidade == "×":
            return f"{v:g}×" if i18n.en() else f"{v:g}×".replace(".", ",")
        return f"{v:g} {self.unidade}".strip()


@dataclass(frozen=True)
class Regra:
    id: str
    nome: str
    tipo: str                  # Volumétrica | Comportamental | Cadastral
    entidade: str              # titular | empresa | estabelecimento
    frequencia: str            # Diária | Ciclo mensal
    produto: str               # onde o sinal nasce
    indicador: str             # o que é medido, em português
    parametro: Parametro
    condicoes: tuple[str, ...]
    enquadramento: tuple[str, ...]   # chaves de normas.TRECHOS (4.001)
    base_3978: tuple[str, ...]       # chaves de normas.TRECHOS (3.978)
    racional: str
    gravidade: int                   # pontos na prioridade (0–35)
    calibravel: bool = True

    @property
    def rotulo(self) -> str:
        return f"{self.id} · {self.nome}"

    @property
    def rotulo_enquadramento(self) -> str:
        from .normas import TRECHOS
        t = TRECHOS[self.enquadramento[0]]
        return t.dispositivo.replace("art. 1º, ", "")

    @property
    def local(self) -> "Regra":
        """A regra na língua ativa (nome, indicador, condições, racional)."""
        from .en import regra
        return regra(self)


LIMITE_PIX = 5_000.0   # limite interno por transação Pix da conta simulada

REGRAS: dict[str, Regra] = {r.id: r for r in [
    Regra(
        "R01", "Movimentação incompatível com a renda", "Volumétrica",
        "titular", "Ciclo mensal", "Conta digital (Pix)",
        "Pix recebidos + enviados em 30 dias, em múltiplos da renda mensal "
        "declarada",
        Parametro("Múltiplo da renda mensal", 3.0, "×", 2.0, 8.0, 0.5,
                  historico=((date(2025, 1, 1), 4.0),
                             (date(2026, 3, 1), 3.0))),
        ("movimentação de 30 dias de pelo menos R$ 8.000",),
        ("4001_IV_a",), ("3978_art39",),
        "É a situação mais citada da 4.001 e a mais barata de medir: renda "
        "declarada contra o que passa pela conta. O piso em reais existe "
        "porque renda baixa estoura o múltiplo com qualquer transferência de "
        "família. O corte caiu de 4× para 3× em mar/2026, na revisão da "
        "avaliação interna de risco — e o volume de alertas subiu junto.",
        gravidade=20),
    Regra(
        "R02", "Muitas origens e saída rápida", "Comportamental",
        "titular", "Diária", "Conta digital (Pix)",
        "Pagadores distintos que mandaram Pix para a conta em 7 dias",
        Parametro("Origens distintas em 7 dias", 10, "origens", 5, 40, 1),
        ("pelo menos R$ 3.000 recebidos em 7 dias",
         "80% ou mais do valor recebido saiu da conta na mesma janela"),
        ("4001_IV_n", "4001_IV_c"), ("3978_art38",),
        "O desenho clássico de conta de passagem: dinheiro de muita gente que "
        "não fica. As duas condições fixas são o que separa isso de uma "
        "vaquinha — vaquinha recebe de muitos, mas o dinheiro fica parado até "
        "o evento.",
        gravidade=35),
    Regra(
        "R03", "Transferências logo abaixo do limite", "Comportamental",
        "titular", "Diária", "Conta digital (Pix)",
        "Pix enviados entre 90% e 100% do limite por transação, em 7 dias",
        Parametro("Transferências perto do limite em 7 dias", 3, "Pix",
                  2, 10, 1),
        (f"limite por transação de R$ {LIMITE_PIX:,.0f}".replace(",", "."),),
        ("4001_IV_b", "4001_IV_l"), ("3978_art38",),
        "Quem precisa mandar R$ 14 mil e manda três de R$ 4.900 está "
        "desenhando a operação em volta do limite. Um Pix perto do teto não "
        "diz nada; a repetição na mesma semana é que é o sinal.",
        gravidade=25),
    Regra(
        "R04", "Conta pouco movimentada que acorda", "Volumétrica",
        "titular", "Ciclo mensal", "Conta digital (Pix)",
        "Movimentação de 30 dias em múltiplos da média mensal dos 3 meses "
        "anteriores",
        Parametro("Múltiplo da média anterior", 10.0, "×", 4.0, 30.0, 1.0),
        ("movimentação de 30 dias de pelo menos R$ 10.000",
         "média anterior com piso de R$ 200, para conta nova não dividir por "
         "zero"),
        ("4001_IV_e", "4001_IV_i"), ("3978_art38",),
        "Conta dormente que de repente movimenta dezenas de milhares é o "
        "padrão de conta emprestada ou vendida. É uma regra ruidosa de "
        "propósito — pega também o 13º que caiu na conta errada — e por isso "
        "tem gravidade baixa na prioridade.",
        gravidade=15),
    Regra(
        "R05", "Recebimento incompatível com o estabelecimento", "Volumétrica",
        "estabelecimento", "Diária", "Cartão de benefícios",
        "Recebimentos no POS em 7 dias, em múltiplos da receita semanal "
        "esperada para o porte",
        Parametro("Múltiplo da receita esperada", 3.0, "×", 1.5, 10.0, 0.5),
        ("pelo menos R$ 15.000 recebidos em 7 dias",),
        ("4001_IV_w",), ("3978_art39",),
        "Em cartão de benefício, o esquema típico é a troca: o titular "
        "\"gasta\" o saldo inteiro numa mercearia parceira e recebe parte em "
        "dinheiro. Do lado do estabelecimento isso aparece como uma padaria "
        "de bairro faturando como supermercado.",
        gravidade=30),
    Regra(
        "R06", "Transações em horário incompatível", "Comportamental",
        "estabelecimento", "Diária", "Cartão de benefícios",
        "Parcela das transações entre 23h e 5h, em 7 dias",
        Parametro("Parcela noturna", 0.25, "%", 0.05, 0.60, 0.05),
        ("pelo menos 30 transações em 7 dias",
         "só estabelecimentos de horário comercial (padaria, mercado, "
         "farmácia)"),
        ("4001_IV_y",), ("3978_art38",),
        "Mercearia que vende de madrugada, com cartão de refeição, é "
        "transação que não aconteceu no balcão. Restaurante e posto 24h ficam "
        "de fora da regra — para eles a madrugada é expediente.",
        gravidade=15),
    Regra(
        "R07", "Recarga incompatível com o porte da empresa", "Volumétrica",
        "empresa", "Ciclo mensal", "Recarga de benefícios",
        "Recarga de benefícios dos últimos 30 dias por colaborador ativo",
        Parametro("Recarga por colaborador", 2_500, "R$", 1_000, 8_000, 250),
        ("recarga total de pelo menos R$ 20.000 em 30 dias",),
        ("4001_IV_ac", "4001_III_j"), ("3978_art39",),
        "Benefício de alimentação e refeição tem ordem de grandeza conhecida. "
        "Empresa recém-cadastrada carregando cinco mil reais por cabeça, "
        "todo mês, está usando o cartão como meio de pagamento de outra "
        "coisa. O pico de 13º e PLR em dezembro é o falso positivo esperado.",
        gravidade=30),
    Regra(
        "R08", "Contas abertas em lote no mesmo dispositivo", "Cadastral",
        "titular", "Diária", "Cadastro",
        "Contas abertas no mesmo dia, pelo app, a partir do mesmo dispositivo",
        Parametro("Contas no mesmo dispositivo e dia", 5, "contas", 3, 20, 1),
        ("cadastro feito pelo app pessoal — o cadastro em lote pelo portal do "
         "RH da empresa é esperado e fica de fora",),
        ("4001_III_f", "4001_III_l"), ("3978_art38",),
        "Cinco pessoas abrindo conta do mesmo celular no mesmo dia não é "
        "família: é alguém cadastrando laranjas. O portal do RH fica de fora "
        "porque ali o cadastro em lote é o processo normal — sem essa "
        "exceção, todo cliente novo viraria alerta.",
        gravidade=25),
    Regra(
        "R09", "PEP com movimentação relevante", "Cadastral",
        "titular", "Ciclo mensal", "Conta digital (Pix)",
        "Movimentação de 30 dias de titular qualificado como PEP",
        Parametro("Movimentação de PEP em 30 dias", 10_000, "R$", 2_000,
                  50_000, 1_000),
        ("titular qualificado como pessoa exposta politicamente",),
        ("4001_IV_s",), ("3978_art27",),
        "PEP não é suspeito por ser PEP; a norma pede atenção especial. A "
        "regra garante que a movimentação relevante de PEP passe por olho "
        "humano todo mês — e a maior parte termina, corretamente, em "
        "monitoramento reforçado.",
        gravidade=20),
    Regra(
        "R10", "CPF irregular na checagem mensal", "Cadastral",
        "titular", "Ciclo mensal", "Cadastro",
        "Situação do CPF na base oficial: suspenso, cancelado ou titular "
        "falecido",
        Parametro("Situação irregular", 1, "", 1, 1, 1),
        ("CPF com movimentação nos 30 dias anteriores à checagem",),
        ("4001_III_e",), ("3978_art20",),
        "É o ciclo mensal de checagem de CPFs: a base é dividida em 28 lotes "
        "e cada lote é checado num dia do mês. Quase todo alerta aqui acaba "
        "em atualização cadastral. O que não acaba é conta de titular "
        "falecido que continua movimentando.",
        gravidade=20, calibravel=False),
]}

ORDEM = list(REGRAS.keys())


def por_rotulo(rotulo: str) -> Regra:
    for r in REGRAS.values():
        if r.rotulo == rotulo or r.id == rotulo:
            return r
    raise KeyError(rotulo)


# --------------------------------------------------------------------------- #
# Avaliação
# --------------------------------------------------------------------------- #
#
# `J` é um dicionário de matrizes (entidade × dia) já em janela móvel, montado
# pelo job. Cada função devolve (indicador, condicoes_fixas). O alerta nasce
# onde  condicoes & (indicador >= parametro).

def _div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, a / np.where(b > 0, b, 1), 0.0)


def avaliar_R01(J):
    vol30 = J["in30"] + J["out30"]
    return _div(vol30, J["renda"][:, None]), vol30 >= 8_000


def avaliar_R02(J):
    cond = (J["in7"] >= 3_000) & (J["out7"] >= 0.8 * J["in7"])
    return J["origens7"].astype(float), cond


def avaliar_R03(J):
    return J["perto_limite7"].astype(float), J["perto_limite7"] > 0


def avaliar_R04(J):
    vol30 = J["in30"] + J["out30"]
    base = np.maximum(J["media_mensal_ant"], 200.0)
    return _div(vol30, base), vol30 >= 10_000


def avaliar_R05(J):
    return _div(J["rec7"], J["receita_semanal"][:, None]), J["rec7"] >= 15_000


def avaliar_R06(J):
    parcela = _div(J["noturno7"], J["qtd7"])
    return parcela, (J["qtd7"] >= 30) & J["horario_comercial"][:, None]


def avaliar_R07(J):
    por_colab = _div(J["recarga30"], J["colaboradores"])
    return por_colab, J["recarga30"] >= 20_000


def avaliar_R08(J):
    return J["lote_dispositivo"].astype(float), J["lote_dispositivo"] > 0


def avaliar_R09(J):
    vol30 = J["in30"] + J["out30"]
    return vol30, J["pep"][:, None] & (vol30 > 0)


def avaliar_R10(J):
    irregular = J["cpf_irregular"]
    return irregular.astype(float), irregular & ((J["in30"] + J["out30"]) > 0)


AVALIADORES: dict[str, Callable] = {
    "R01": avaliar_R01, "R02": avaliar_R02, "R03": avaliar_R03,
    "R04": avaliar_R04, "R05": avaliar_R05, "R06": avaliar_R06,
    "R07": avaliar_R07, "R08": avaliar_R08, "R09": avaliar_R09,
    "R10": avaliar_R10,
}
