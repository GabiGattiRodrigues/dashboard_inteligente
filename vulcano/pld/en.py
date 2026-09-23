"""
A Ravena em inglês: regras, normas, verificações e evidências.

As regras e os trechos de norma são declarados uma vez só, em português, em
`regras.py` e `normas.py` -- é o que o job roda e o que a tela cita. Aqui fica
a tradução, pelo mesmo `id`/`chave`, e as funções que devolvem a versão da
língua ativa. O id da regra (R01...R10) e o dispositivo (IV, a) são os mesmos
nas duas línguas, porque são eles que a analista procura na norma.

A evidência de cada alerta foi gravada no dado, em português, pelo job. Em
inglês ela é reescrita por padrão: são dez moldes fixos (um por regra), e os
números são reformatados no padrão americano. Evidência que não casa com o
molde aparece como veio -- melhor em português do que inventada.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .. import i18n

REGRAS_EN: dict[str, dict] = {
    "R01": dict(
        nome="Activity inconsistent with income",
        indicador="Pix received + sent over 30 days, in multiples of the "
                  "declared monthly income",
        parametro="Multiple of monthly income",
        condicoes=("30-day activity of at least R$ 8,000",),
        racional=(
            "It is the most cited situation in 4,001 and the cheapest to "
            "measure: declared income against what goes through the account. "
            "The floor in reais exists because low income blows the multiple "
            "with any family transfer. The threshold dropped from 4× to 3× in "
            "Mar 2026, in the internal risk assessment review — and alert "
            "volume rose with it."),
    ),
    "R02": dict(
        nome="Many sources, fast outflow",
        indicador="Distinct payers who sent Pix to the account in 7 days",
        parametro="Distinct sources in 7 days",
        condicoes=("at least R$ 3,000 received in 7 days",
                   "80% or more of the amount received left the account in "
                   "the same window"),
        racional=(
            "The classic pass-through account design: money from many people "
            "that doesn't stay. The two fixed conditions are what separate "
            "this from a group collection — a collection receives from many, "
            "but the money sits until the event."),
    ),
    "R03": dict(
        nome="Transfers just below the limit",
        indicador="Pix sent between 90% and 100% of the per-transaction "
                  "limit, in 7 days",
        parametro="Transfers near the limit in 7 days",
        condicoes=("per-transaction limit of R$ 5,000",),
        racional=(
            "Someone who needs to send R$ 14k and sends three of R$ 4,900 is "
            "designing the operation around the limit. One Pix near the cap "
            "says nothing; the repetition in the same week is the signal."),
    ),
    "R04": dict(
        nome="Dormant account wakes up",
        indicador="30-day activity in multiples of the monthly average of the "
                  "previous 3 months",
        parametro="Multiple of the previous average",
        condicoes=("30-day activity of at least R$ 10,000",
                   "previous average with a floor of R$ 200, so a new account "
                   "doesn't divide by zero"),
        racional=(
            "A dormant account that suddenly moves tens of thousands is the "
            "pattern of a lent or sold account. It's a noisy rule on purpose "
            "— it also catches the year-end bonus landing in the wrong "
            "account — which is why it has low severity in the priority."),
    ),
    "R05": dict(
        nome="Receipts inconsistent with the merchant",
        indicador="POS receipts in 7 days, in multiples of the weekly revenue "
                  "expected for the merchant's size",
        parametro="Multiple of expected revenue",
        condicoes=("at least R$ 15,000 received in 7 days",),
        racional=(
            "With benefit cards, the typical scheme is the swap: the holder "
            "\"spends\" the whole balance at a partner grocery store and "
            "gets part back in cash. On the merchant's side it shows up as a "
            "neighborhood bakery billing like a supermarket."),
    ),
    "R06": dict(
        nome="Transactions at inconsistent hours",
        indicador="Share of transactions between 11pm and 5am, in 7 days",
        parametro="Night-time share",
        condicoes=("at least 30 transactions in 7 days",
                   "only merchants with business hours (bakery, grocery, "
                   "pharmacy)"),
        racional=(
            "A grocery store selling at dawn, on a meal card, is a "
            "transaction that didn't happen at the counter. Restaurants and "
            "24h gas stations are out of the rule — for them the small hours "
            "are business hours."),
    ),
    "R07": dict(
        nome="Top-ups inconsistent with company size",
        indicador="Benefit top-ups over the last 30 days per active employee",
        parametro="Top-up per employee",
        condicoes=("total top-up of at least R$ 20,000 in 30 days",),
        racional=(
            "Food and meal benefits have a known order of magnitude. A newly "
            "registered company loading five thousand reais per head, every "
            "month, is using the card as a means of paying for something "
            "else. The December peak from year-end bonuses and profit sharing "
            "is the expected false positive."),
    ),
    "R08": dict(
        nome="Batch accounts on the same device",
        indicador="Accounts opened on the same day, through the app, from the "
                  "same device",
        parametro="Accounts on the same device and day",
        condicoes=("onboarding done through the personal app — batch "
                   "onboarding through the company's HR portal is expected and "
                   "stays out",),
        racional=(
            "Five people opening accounts from the same phone on the same day "
            "is not a family: it's someone registering mules. The HR portal "
            "stays out because batch onboarding is the normal process there "
            "— without that exception, every new client would become an "
            "alert."),
    ),
    "R09": dict(
        nome="PEP with relevant activity",
        indicador="30-day activity of an account holder qualified as a PEP",
        parametro="PEP activity in 30 days",
        condicoes=("account holder qualified as a politically exposed "
                   "person",),
        racional=(
            "A PEP is not suspicious for being a PEP; the regulation asks for "
            "special attention. The rule ensures relevant PEP activity goes "
            "past human eyes every month — and most of it ends, correctly, in "
            "enhanced monitoring."),
    ),
    "R10": dict(
        nome="Irregular CPF in the monthly check",
        indicador="CPF status in the official registry: suspended, canceled "
                  "or holder deceased",
        parametro="Irregular status",
        condicoes=("CPF with activity in the 30 days before the check",),
        racional=(
            "It's the monthly CPF check cycle: the base is split into 28 "
            "batches and each batch is checked on one day of the month. "
            "Almost every alert here ends in a registration update. What "
            "doesn't is a deceased holder's account that keeps moving money."),
    ),
}

TIPOS_EN = {"Volumétrica": "Volume-based", "Comportamental": "Behavioral",
            "Cadastral": "Onboarding data"}
FREQ_EN = {"Diária": "Daily", "Ciclo mensal": "Monthly cycle"}
UNIDADES_EN = {"origens": "sources", "contas": "accounts", "Pix": "Pix"}

TRECHOS_EN: dict[str, str] = {
    "3978_art10": "Internal risk assessment: the institution identifies and "
                  "measures the risk of its products being used for ML/TF, "
                  "considering the profiles of clients, of the institution "
                  "itself, of transactions and of employees, partners and "
                  "outsourced providers.",
    "3978_art20": "Clients are classified into the risk categories defined in "
                  "the internal risk assessment, based on their "
                  "qualification information.",
    "3978_art27": "Politically exposed persons (PEPs): definition and "
                  "procedures for identification and special attention to "
                  "the business relationship.",
    "3978_art38": "The institution implements procedures for monitoring, "
                  "selecting and analyzing transactions and situations, to "
                  "identify and pay special attention to suspected ML/TF.",
    "3978_art39": "Monitoring and selection consider, among others, "
                  "transactions whose amounts or parties appear inconsistent "
                  "with the client's financial capacity (item I, sub-item "
                  "c). The period to monitor and select cannot exceed 45 "
                  "days (sole paragraph).",
    "3978_art43_1": "The analysis of selected transactions and situations "
                    "cannot exceed 45 days from the selection date.",
    "3978_art43_2": "The analysis must be formalized in a case file, whether "
                    "or not a report is made to COAF.",
    "3978_art48_2": "The report of the suspicious transaction or situation to "
                    "COAF must be made by the business day after the decision "
                    "to report.",
    "3978_art49": "Report to COAF of cash deposits, contributions or "
                  "withdrawals of R$ 50k or more.",
    "3978_art54": "An institution that made no report during the year files a "
                  "declaration of non-occurrence within ten business days "
                  "after year end.",
    "4001_III_e": "Irregularities in client identification and registration "
                  "procedures.",
    "4001_III_f": "Registration of several accounts on the same date, or in a "
                  "short period, with deposits of identical or similar "
                  "amounts, or with elements in common.",
    "4001_III_j": "Economic activity or reported revenue inconsistent with "
                  "the observed pattern.",
    "4001_III_l": "The same e-mail or IP registered by individuals, without "
                  "reasonable justification.",
    "4001_IV_a": "Movement of funds inconsistent with the client's assets, "
                 "economic activity or occupation and financial capacity.",
    "4001_IV_b": "Transfers of amounts rounded to the thousand or slightly "
                 "below the reporting threshold.",
    "4001_IV_c": "Habitual movement of high-value funds on behalf of third "
                 "parties.",
    "4001_IV_e": "Movement of a significant amount through a previously "
                 "low-activity account.",
    "4001_IV_i": "Sudden, unjustified change in how funds are moved or in the "
                 "types of transaction.",
    "4001_IV_l": "Transactions that, by frequency, amount and form, amount to "
                 "a scheme to evade identification of the origin, destination "
                 "or those responsible.",
    "4001_IV_n": "Receipt of deposits from many sources, without economic or "
                 "financial grounds.",
    "4001_IV_s": "Habitual movement of funds to or from a PEP, without "
                 "economic or financial grounds.",
    "4001_IV_w": "Relevant receipts on the same payment terminal (POS), "
                 "inconsistent with the merchant's financial capacity.",
    "4001_IV_y": "Transactions at hours inconsistent with the merchant's "
                 "activity.",
    "4001_IV_ac": "Movement of amounts inconsistent with the legal entity's "
                  "monthly revenue.",
    "4001_XVII_a": "Atypical transaction in municipalities located in border "
                   "regions.",
    "lei9613_art11": "The report to COAF is made without informing anyone of "
                     "it, including the client it refers to.",
}

NORMAS_EN = {"Circular 3.978": "Circular 3,978",
             "Carta Circular 4.001": "Circular Letter 4,001",
             "Lei 9.613/1998": "Law 9,613/1998"}

VERIFICAR_EN = {
    "R01": "Ask for proof of the source of funds and check whether the "
           "declared income is outdated.",
    "R02": "Check whether the payers are related to each other and where the "
           "money went — a destination repeated in other accounts is the "
           "strong signal.",
    "R03": "Rebuild the total amount that was meant to be transferred and "
           "understand why it was split.",
    "R04": "Check for a recent change of phone, e-mail or ownership before "
           "the increase in activity.",
    "R05": "Compare receipts with the revenue and size declared at "
           "onboarding; see which companies the cards come from.",
    "R06": "Confirm the opening hours and whether the night-time "
           "transactions repeat on the same cards.",
    "R07": "Confirm the actual headcount and revenue, and where the loaded "
           "balance is being spent.",
    "R08": "Verify the holders' actual tie to the company and the document "
           "validation of the accounts in the same batch.",
    "R09": "Apply PEP enhanced due diligence: source of funds and "
           "relationship with the counterparties.",
    "R10": "Update the registration. If the holder is deceased and the "
           "account moves money, identify who is operating it.",
}


# --------------------------------------------------------------------------- #
# Versões localizadas
# --------------------------------------------------------------------------- #

def dispositivo(d: str) -> str:
    """'art. 43, § 1º' → 'art. 43, § 1'; 'art. 1º, IV, a' → 'art. 1, IV, a'."""
    if not i18n.en():
        return d
    return d.replace("º", "").replace(" e ", " and ")


def norma(n: str) -> str:
    return NORMAS_EN.get(n, n) if i18n.en() else n


def regra(r):
    """A regra na língua ativa. O id e o parâmetro numérico não mudam."""
    if not i18n.en():
        return r
    t = REGRAS_EN.get(r.id)
    if not t:
        return r
    p = replace(r.parametro, nome=t["parametro"],
                unidade=UNIDADES_EN.get(r.parametro.unidade,
                                        r.parametro.unidade))
    return replace(r, nome=t["nome"], indicador=t["indicador"],
                   condicoes=tuple(t["condicoes"]), racional=t["racional"],
                   tipo=TIPOS_EN.get(r.tipo, r.tipo),
                   frequencia=FREQ_EN.get(r.frequencia, r.frequencia),
                   produto=i18n.V(r.produto), parametro=p)


def verificar(rid: str, pt: str) -> str:
    return VERIFICAR_EN.get(rid, pt) if i18n.en() else pt


# --------------------------------------------------------------------------- #
# Evidência: dez moldes, um por regra
# --------------------------------------------------------------------------- #

_N = r"\d{1,3}(?:\.\d{3})*(?:,\d+)?"


def _num(txt: str) -> str:
    """'43.438' → '43,438'; '26,3' → '26.3'."""
    return txt.replace(".", "@").replace(",", ".").replace("@", ",")


def _brl(m: re.Match) -> str:
    return "R$ " + _num(m.group(1))


def _data_br(txt: str) -> str:
    dia, mes, ano = txt.split("/")
    return f"{i18n.MESES_EN[int(mes) - 1]} {int(dia)}, {ano}"


_SITUACAO = {"cancelado": "canceled", "suspenso": "suspended",
             "titular falecido": "holder deceased"}
_CATEG = {"farmácia": "pharmacy", "padaria e mercearia": "bakery & grocery"}

_MOLDES: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"(?P<a>R\$ {_N}) recebidos e (?P<b>R\$ {_N}) enviados por Pix "
                rf"em (?P<d>\d+) dias — (?P<x>{_N})× a renda mensal declarada "
                rf"de (?P<c>R\$ {_N})\.?"),
     "{a} received and {b} sent via Pix in {d} days — {x}× the declared "
     "monthly income of {c}."),
    (re.compile(rf"(?P<n>\d+) pagadores distintos mandaram (?P<a>R\$ {_N}) em "
                rf"(?P<d>\d+) dias; (?P<b>R\$ {_N}) \((?P<p>\d+)% do recebido\) "
                rf"saiu da conta na mesma janela\."),
     "{n} distinct payers sent {a} in {d} days; {b} ({p}% of the amount "
     "received) left the account in the same window."),
    (re.compile(rf"(?P<n>\d+) Pix enviados entre (?P<a>R\$ {_N}) e "
                rf"(?P<b>R\$ {_N}) em (?P<d>\d+) dias, somando (?P<c>R\$ {_N}) "
                rf"— o limite por transação é (?P<e>R\$ {_N})\.?"),
     "{n} Pix sent between {a} and {b} in {d} days, totaling {c} — the "
     "per-transaction limit is {e}."),
    (re.compile(rf"(?P<a>R\$ {_N}) movimentados em (?P<d>\d+) dias, contra "
                rf"média mensal de (?P<b>R\$ {_N}) nos (?P<m>\d+) meses "
                rf"anteriores \((?P<x>{_N})× a média, com piso de "
                rf"(?P<c>R\$ {_N})\)\."),
     "{a} moved in {d} days, against a monthly average of {b} over the "
     "previous {m} months ({x}× the average, with a floor of {c})."),
    (re.compile(rf"(?P<a>R\$ {_N}) recebidos no POS em (?P<d>\d+) dias, "
                rf"(?P<x>{_N})× a receita semanal esperada \((?P<b>R\$ {_N})\); "
                rf"(?P<p>\d+)% vieram de cartões de uma mesma empresa cliente\."),
     "{a} received at the POS in {d} days, {x}× the expected weekly revenue "
     "({b}); {p}% came from cards of a single client company."),
    (re.compile(rf"(?P<n>\d+) de (?P<t>\d+) transações \((?P<p>\d+)%\) entre "
                rf"(?P<h1>\d+)h e (?P<h2>\d+)h em (?P<d>\d+) dias, num "
                rf"estabelecimento de horário comercial \((?P<cat>[^)]+)\)\."),
     "{n} of {t} transactions ({p}%) between {h1}:00 and {h2}:00 in {d} "
     "days, at a merchant with business hours ({cat})."),
    (re.compile(rf"(?P<a>R\$ {_N}) em recargas de benefício em (?P<d>\d+) dias "
                rf"para (?P<n>\d+) colaboradores ativos — (?P<b>R\$ {_N}) por "
                rf"pessoa\. Faturamento mensal declarado de (?P<c>R\$ {_N}); "
                rf"cliente desde (?P<desde>\d+/\d+)\.?"),
     "{a} in benefit top-ups in {d} days for {n} active employees — {b} per "
     "person. Declared monthly revenue of {c}; client since {desde}."),
    (re.compile(r"Conta aberta pelo app em (?P<dt>\d+/\d+/\d+),? junto com "
                r"outras (?P<n>\d+) contas no mesmo dispositivo e no mesmo "
                r"dia\."),
     "Account opened through the app on {dt}, along with {n} other accounts "
     "on the same device on the same day."),
    (re.compile(rf"Titular PEP movimentou (?P<a>R\$ {_N}) em (?P<d>\d+) dias "
                rf"\((?P<b>R\$ {_N}) recebidos, (?P<c>R\$ {_N}) enviados\); "
                rf"renda mensal declarada de (?P<e>R\$ {_N})\.?"),
     "PEP account holder moved {a} in {d} days ({b} received, {c} sent); "
     "declared monthly income of {e}."),
    (re.compile(rf"Checagem mensal \(lote (?P<l>\d+) de (?P<t>\d+)\) encontrou o "
                rf"CPF com situação \"(?P<s>[^\"]+)\" desde (?P<dt>\d+/\d+/\d+); "
                rf"a conta movimentou (?P<a>R\$ {_N}) nos (?P<d>\d+) dias "
                rf"anteriores\."),
     "Monthly check (batch {l} of {t}) found the CPF with status \"{s}\" "
     "since {dt}; the account moved {a} in the previous {d} days."),
]


def evidencia(txt: str) -> str:
    """A evidência gravada pelo job, na língua ativa."""
    if not i18n.en() or not txt:
        return txt
    for molde, saida in _MOLDES:
        m = molde.fullmatch(txt.strip())
        if not m:
            continue
        g = {}
        for k, v in m.groupdict().items():
            if v is None:
                continue
            if v.startswith("R$ "):
                g[k] = "R$ " + _num(v[3:])
            elif k == "dt":
                g[k] = _data_br(v)
            elif k == "s":
                g[k] = _SITUACAO.get(v, v)
            elif k == "cat":
                g[k] = _CATEG.get(v, v)
            elif k == "desde":
                mes, ano = v.split("/")
                g[k] = f"{i18n.MESES_EN[int(mes) - 1]} {ano}"
            else:
                g[k] = _num(v) if ("," in v or "." in v) else v
        return saida.format(**g)
    return txt
