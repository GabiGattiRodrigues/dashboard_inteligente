"""
Dias úteis.

Os dois prazos do monitoramento contam de jeitos diferentes, e confundir os
dois é o erro que faz uma comunicação chegar atrasada:

- **Análise**: até 45 dias **corridos** contados da seleção
  (Circular 3.978, art. 43, § 1º).
- **Comunicação ao Coaf**: até o **dia útil** seguinte ao da decisão de
  comunicar (art. 48, § 2º). Decisão tomada na sexta vai na segunda; decisão
  tomada na véspera de feriado pula o feriado.

Os feriados abaixo são os nacionais e os dias sem expediente bancário no
período simulado. Uma operação real leria o calendário da própria instituição.
"""

from __future__ import annotations

from datetime import date, timedelta

FERIADOS = {
    date(2025, 9, 7), date(2025, 10, 12), date(2025, 11, 2),
    date(2025, 11, 15), date(2025, 11, 20), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3),
    date(2026, 4, 21), date(2026, 5, 1), date(2026, 6, 4), date(2026, 9, 7),
    date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 20),
    date(2026, 12, 25),
}

PRAZO_ANALISE_DIAS = 45


def eh_dia_util(d: date) -> bool:
    return d.weekday() < 5 and d not in FERIADOS


def proximo_dia_util(d: date) -> date:
    """O primeiro dia útil DEPOIS de `d` — o prazo do art. 48, § 2º."""
    x = d + timedelta(days=1)
    while not eh_dia_util(x):
        x += timedelta(days=1)
    return x


def somar_dias_uteis(d: date, n: int) -> date:
    x = d
    for _ in range(n):
        x = proximo_dia_util(x)
    return x


def prazo_analise(selecao: date) -> date:
    """Último dia para concluir a análise (art. 43, § 1º): dias corridos."""
    return selecao + timedelta(days=PRAZO_ANALISE_DIAS)
