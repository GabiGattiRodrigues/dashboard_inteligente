"""
Resolução de períodos e escolha da base de comparação.

Comparar período com período é a operação que o produto inteiro repete, então
ela mora num lugar só.

Uma base de comparação pode ser DUAS coisas
-------------------------------------------
Na maioria dos casos é uma janela: "o mês passado", "os 28 dias anteriores".
Mas "d vs média dos últimos 3 mesmos dias da semana" não é uma janela — é a
média de três janelas separadas. Comparar uma terça contra a média das três
terças anteriores é mais estável que comparar contra uma terça só, que pode ter
sido feriado ou promoção.

Por isso `Comparacao.anteriores` é uma lista. Quando tem um item, é a
comparação simples de sempre; quando tem vários, o valor da base é a **média
dos valores** de cada janela — e não a razão agregada. A diferença importa em
métrica de razão: a pessoa que pede "a média das últimas 3 terças" quer a média
dos três tickets médios, não o ticket médio dos três dias somados.

Duas regras que não são óbvias
------------------------------
- **Dia contra dia** em varejo compara com o MESMO DIA DA SEMANA (D-7), e não
  com ontem. Segunda contra domingo não é queda, é calendário. As duas opções
  existem, com D-7 em destaque.
- **Mês até aqui** compara com o mesmo NÚMERO DE DIAS do mês anterior. Comparar
  12 dias contra 31 é o erro clássico de MTD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Optional

DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]


@dataclass(frozen=True)
class Janela:
    inicio: date
    fim: date
    rotulo: str = ""

    @property
    def dias(self) -> int:
        return (self.fim - self.inicio).days + 1

    @property
    def eh_dia(self) -> bool:
        return self.inicio == self.fim

    def __str__(self) -> str:
        if self.eh_dia:
            return self.inicio.strftime("%d/%m/%Y")
        return f"{self.inicio.strftime('%d/%m/%Y')} a {self.fim.strftime('%d/%m/%Y')}"

    def curto(self) -> str:
        if self.eh_dia:
            return self.inicio.strftime("%d/%m")
        return f"{self.inicio.strftime('%d/%m')}–{self.fim.strftime('%d/%m')}"


@dataclass(frozen=True)
class Comparacao:
    atual: Janela
    anteriores: tuple[Janela, ...]
    descricao: str
    # Como ler a base: uma janela só, ou a média de várias.
    modo: Literal["janela", "media"] = "janela"

    @property
    def anterior(self) -> Janela:
        """A primeira janela da base. Existe para o código que só sabe lidar
        com comparação simples (a decomposição de causa raiz, por exemplo)."""
        return self.anteriores[0]

    @property
    def composta(self) -> bool:
        return len(self.anteriores) > 1

    def rotulo_base(self) -> str:
        if not self.composta:
            return str(self.anterior)
        return "média de " + ", ".join(j.curto() for j in self.anteriores)


# --------------------------------------------------------------------------- #
# Construtores de janela
# --------------------------------------------------------------------------- #

def _mes_anterior(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def _ultimo_dia_do_mes(d: date) -> date:
    prox = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return prox - timedelta(days=1)


def dia(d: date) -> Janela:
    return Janela(d, d)


def ultimos_dias(fim: date, n: int) -> Janela:
    return Janela(fim - timedelta(days=n - 1), fim)


def mes_ate_aqui(ref: date) -> Janela:
    return Janela(ref.replace(day=1), ref)


def mes_fechado(ref: date) -> Janela:
    ini = ref.replace(day=1)
    return Janela(ini, _ultimo_dia_do_mes(ini))


def semana_de(ref: date) -> Janela:
    """Semana de segunda a domingo que contém `ref`."""
    ini = ref - timedelta(days=ref.weekday())
    return Janela(ini, ini + timedelta(days=6))


def semana_ate_aqui(ref: date) -> Janela:
    """Semana corrente acumulada: de segunda até `ref`."""
    return Janela(ref - timedelta(days=ref.weekday()), ref)


def mesmos_dias_da_semana(ref: date, quantos: int = 3) -> tuple[Janela, ...]:
    """As `quantos` ocorrências anteriores do mesmo dia da semana."""
    return tuple(dia(ref - timedelta(days=7 * (i + 1))) for i in range(quantos))


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #

PRESETS: dict[str, str] = {
    "dia_d1": "Dia vs dia anterior (D-1)",
    "dia_d7": "Dia vs mesmo dia da semana anterior (D-7)",
    "dia_media3": "Dia vs média dos 3 últimos mesmos dias da semana",
    "mtd": "Mês acumulado vs mês anterior acumulado",
    "semana": "Semana acumulada vs semana anterior acumulada",
    "mes_fechado": "Mês fechado vs mês anterior",
    "ultimos_28": "Últimos 28 dias vs 28 anteriores",
    "ultimos_90": "Últimos 90 dias vs 90 anteriores",
}

# Os quatro níveis que o painel de comparação mostra sempre, lado a lado.
NIVEIS_COMPARACAO = ["dia_d1", "dia_d7", "mtd", "dia_media3"]


def montar_preset(chave: str, ref: date) -> Comparacao:
    """Traduz um preset da tela em janelas concretas."""
    if chave == "dia_d1":
        return Comparacao(dia(ref), (dia(ref - timedelta(days=1)),),
                          PRESETS[chave])

    if chave == "dia_d7":
        return Comparacao(dia(ref), (dia(ref - timedelta(days=7)),),
                          PRESETS[chave])

    if chave == "dia_media3":
        return Comparacao(dia(ref), mesmos_dias_da_semana(ref, 3),
                          PRESETS[chave], modo="media")

    if chave == "mtd":
        a = mes_ate_aqui(ref)
        ini_ant = _mes_anterior(a.inicio)
        fim_ant = min(ini_ant + timedelta(days=a.dias - 1),
                      _ultimo_dia_do_mes(ini_ant))
        return Comparacao(a, (Janela(ini_ant, fim_ant),), PRESETS[chave])

    if chave == "semana":
        a = semana_ate_aqui(ref)
        ini_ant = a.inicio - timedelta(days=7)
        return Comparacao(
            a, (Janela(ini_ant, ini_ant + timedelta(days=a.dias - 1)),),
            PRESETS[chave])

    if chave == "mes_fechado":
        a = mes_fechado(ref)
        ini_ant = _mes_anterior(a.inicio)
        return Comparacao(a, (Janela(ini_ant, _ultimo_dia_do_mes(ini_ant)),),
                          PRESETS[chave])

    if chave in ("ultimos_28", "ultimos_90"):
        n = int(chave.split("_")[1])
        a = ultimos_dias(ref, n)
        return Comparacao(
            a, (Janela(a.inicio - timedelta(days=n), a.inicio - timedelta(days=1)),),
            PRESETS[chave])

    raise KeyError(f"preset desconhecido: {chave}")


# --------------------------------------------------------------------------- #
# Comparações escolhidas pelo usuário (causa raiz)
# --------------------------------------------------------------------------- #

def contra_semana(ref: date, semana_alvo: date) -> Comparacao:
    """
    Semana corrente acumulada contra outra semana, no MESMO trecho.

    O corte no mesmo número de dias é o que torna a conta justa: comparar uma
    semana com 3 dias corridos contra outra com 7 mostraria uma queda que é só
    calendário.
    """
    a = semana_ate_aqui(ref)
    ini_b = semana_alvo - timedelta(days=semana_alvo.weekday())
    b = Janela(ini_b, ini_b + timedelta(days=a.dias - 1))
    return Comparacao(
        a, (b,),
        f"Semana acumulada ({a.dias} dia{'s' if a.dias > 1 else ''}) vs mesmo "
        f"trecho da semana de {ini_b.strftime('%d/%m/%Y')}")


def contra_mes(ref: date, mes_alvo: date) -> Comparacao:
    """Mês corrente acumulado contra outro mês, no mesmo número de dias."""
    a = mes_ate_aqui(ref)
    ini_b = mes_alvo.replace(day=1)
    fim_b = min(ini_b + timedelta(days=a.dias - 1), _ultimo_dia_do_mes(ini_b))
    return Comparacao(
        a, (Janela(ini_b, fim_b),),
        f"Mês acumulado ({a.dias} dia{'s' if a.dias > 1 else ''}) vs mesmo "
        f"trecho de {ini_b.strftime('%m/%Y')}")


def contra_dia(ref: date, dia_alvo: date) -> Comparacao:
    rot = "dia anterior" if dia_alvo == ref - timedelta(days=1) else \
          dia_alvo.strftime("%d/%m/%Y")
    return Comparacao(dia(ref), (dia(dia_alvo),), f"{ref.strftime('%d/%m/%Y')} vs {rot}")


def descrever_dia(d: date) -> str:
    return f"{d.strftime('%d/%m/%Y')} ({DIAS_SEMANA[d.weekday()]})"
