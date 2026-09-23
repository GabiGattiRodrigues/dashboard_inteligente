"""
Português e inglês no mesmo produto.

O painel inteiro -- tela, agentes, alertas, dossiê -- fala as duas línguas, e
a troca é um botão. Três decisões moldam este módulo:

1. **O texto em inglês mora ao lado do português**, e não num arquivo de
   chaves à parte. `L("Receita", "Revenue")` deixa as duas versões lado a lado
   no código; quem mexe numa frase vê na hora que a outra também precisa
   mudar. Catálogo de chaves (`t("home.title")`) esconde isso e as duas
   versões se descolam em silêncio.

2. **O número não muda de língua, só de roupa.** O motor calcula igual; o que
   muda é o separador (1.234,5 vira 1,234.5), a data (18/08/2018 vira
   Aug 18, 2018) e o rótulo. Número de aba e número de agente continuam
   sendo o mesmo número nas duas línguas.

3. **O dado é gravado em português e continua assim.** Filtro, SQL e regra
   de negócio comparam contra "Cartão de crédito", "Feminino",
   "Comunicado ao COAF". A tradução dos valores acontece só na hora de
   mostrar (`V`), nunca na hora de filtrar -- senão trocar de língua mudaria
   o resultado da consulta.

A língua ativa é por execução do script. O Streamlit roda cada sessão numa
thread própria, então a escolha de uma pessoa não vaza para a tela de outra.
Fora do Streamlit (testes, scripts) o padrão é português.
"""

from __future__ import annotations

import math
import re
import threading
from datetime import date
from typing import Optional

_estado = threading.local()

IDIOMAS = {"pt": "Português", "en": "English"}


def definir(idioma: str) -> None:
    _estado.idioma = idioma if idioma in IDIOMAS else "pt"


def idioma() -> str:
    return getattr(_estado, "idioma", "pt")


def en() -> bool:
    return idioma() == "en"


def L(pt: str, en_: str) -> str:
    """A frase na língua ativa. As duas versões ficam lado a lado no código."""
    return en_ if en() else pt


# --------------------------------------------------------------------------- #
# Números
# --------------------------------------------------------------------------- #

def num(x: float, casas: int = 0) -> str:
    """1.234,5 em português, 1,234.5 em inglês."""
    s = f"{x:,.{casas}f}"
    if en():
        return s
    return s.replace(",", "@").replace(".", ",").replace("@", ".")


def brl(v: float, casas: int = 0) -> str:
    """Valor em reais. A moeda é a mesma nas duas línguas; muda o separador."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return ("-" if v < 0 else "") + "R$ " + num(abs(v), casas)


# --------------------------------------------------------------------------- #
# Datas
# --------------------------------------------------------------------------- #

MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
            "jul", "ago", "set", "out", "nov", "dez"]
MESES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DIAS_SEMANA_PT = ["segunda-feira", "terça-feira", "quarta-feira",
                  "quinta-feira", "sexta-feira", "sábado", "domingo"]
DIAS_SEMANA_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                  "Saturday", "Sunday"]
DIAS_CURTOS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado",
                  "Domingo"]


def data(d: date) -> str:
    """18/08/2018 · Aug 18, 2018"""
    if en():
        return f"{MESES_EN[d.month - 1]} {d.day}, {d.year}"
    return d.strftime("%d/%m/%Y")


def data_curta(d: date) -> str:
    """18/08 · Aug 18"""
    if en():
        return f"{MESES_EN[d.month - 1]} {d.day}"
    return d.strftime("%d/%m")


def mes(d: date) -> str:
    """08/2018 · Aug 2018"""
    if en():
        return f"{MESES_EN[d.month - 1]} {d.year}"
    return d.strftime("%m/%Y")


def mes_ano(texto: str) -> str:
    """'2026-07' → 'jul/2026' · 'Jul 2026'"""
    ano, m = texto.split("-")[:2]
    if en():
        return f"{MESES_EN[int(m) - 1]} {ano}"
    return f"{MESES_PT[int(m) - 1]}/{ano}"


def dia_semana(d: date) -> str:
    return (DIAS_SEMANA_EN if en() else DIAS_SEMANA_PT)[d.weekday()]


def formato_data_widget() -> str:
    """O formato do st.date_input."""
    return "MM/DD/YYYY" if en() else "DD/MM/YYYY"


def formato_data_plotly() -> str:
    return "%b %d, %Y" if en() else "%d/%m/%Y"


# --------------------------------------------------------------------------- #
# Valores do dado
# --------------------------------------------------------------------------- #
#
# Os valores das dimensões são gravados em português. Aqui está como cada um
# aparece em inglês. Valor que não está na lista aparece como veio -- sigla de
# UF, código de cliente, nome próprio -- e é isso que se quer.

VALORES_EN: dict[str, str] = {
    # --- comuns
    "Centro-Oeste": "Center-West", "Nordeste": "Northeast", "Norte": "North",
    "Sudeste": "Southeast", "Sul": "South",
    "Segunda": "Monday", "Terça": "Tuesday", "Quarta": "Wednesday",
    "Quinta": "Thursday", "Sexta": "Friday", "Sábado": "Saturday",
    "Domingo": "Sunday",
    "Dia útil": "Weekday", "Fim de semana": "Weekend",
    # --- marketing / produto (Olist)
    "Boleto": "Boleto (bank slip)", "Cartão de crédito": "Credit card",
    "Cartão de débito": "Debit card", "Voucher": "Voucher",
    "2 a 3x": "2–3 installments", "4 a 6x": "4–6 installments",
    "7 a 12x": "7–12 installments", "Acima de 12x": "Over 12 installments",
    "À vista": "Single payment",
    "Primeira compra": "First purchase", "Recorrente": "Returning",
    "Acima de R$ 500": "Over R$ 500", "Até R$ 50": "Up to R$ 50",
    "R$ 100 a 250": "R$ 100–250", "R$ 250 a 500": "R$ 250–500",
    "R$ 50 a 100": "R$ 50–100",
    "1. Criado, não aprovado": "1. Created, not approved",
    "2. Aprovado, não postado": "2. Approved, not shipped",
    "3. Postado, não entregue": "3. Shipped, not delivered",
    "4. Entregue": "4. Delivered",
    "Ainda não entregue": "Not delivered yet",
    "Entregou atrasado": "Delivered late",
    "Entregou no prazo": "Delivered on time",
    "Dentro do estado": "Same state", "Entre estados": "Interstate",
    "Não identificado": "Unidentified",
    "1 a 2 (ruim)": "1–2 (poor)", "3 (neutra)": "3 (neutral)",
    "4 a 5 (boa)": "4–5 (good)",
    # categorias do Olist
    "Agro indústria e comércio": "Agro industry & commerce",
    "Alimentos": "Food", "Alimentos bebidas": "Food & drinks",
    "Artes": "Art", "Artes e artesanato": "Arts & crafts",
    "Artigos de festas": "Party supplies",
    "Artigos de natal": "Christmas supplies", "Automotivo": "Auto",
    "Bebidas": "Drinks", "Bebês": "Baby", "Beleza saúde": "Health & beauty",
    "Brinquedos": "Toys", "CDs DVDs musicais": "CDs, DVDs & musicals",
    "Cama mesa banho": "Bed, bath & table",
    "Casa conforto": "Home comfort", "Casa conforto 2": "Home comfort 2",
    "Casa construção": "Home construction", "Cine foto": "Cine & photo",
    "Climatização": "Air conditioning", "Consoles games": "Consoles & games",
    "Construção ferramentas construção": "Construction tools",
    "Construção ferramentas ferramentas": "Construction tools & tools",
    "Construção ferramentas iluminação": "Construction tools & lighting",
    "Construção ferramentas jardim": "Construction tools & garden",
    "Construção ferramentas segurança": "Construction tools & safety",
    "Cool stuff": "Cool stuff", "DVDs blu ray": "DVDs & Blu-ray",
    "Eletrodomésticos": "Home appliances",
    "Eletrodomésticos 2": "Home appliances 2",
    "Eletroportáteis": "Small appliances", "Eletrônicos": "Electronics",
    "Esporte lazer": "Sports & leisure",
    "Fashion bolsas e acessórios": "Fashion bags & accessories",
    "Fashion calçados": "Fashion shoes", "Fashion esporte": "Fashion sport",
    "Fashion roupa feminina": "Fashion women's clothing",
    "Fashion roupa infanto juvenil": "Fashion kids' clothing",
    "Fashion roupa masculina": "Fashion men's clothing",
    "Fashion underwear e moda praia": "Fashion underwear & beachwear",
    "Ferramentas jardim": "Garden tools", "Flores": "Flowers",
    "Fraldas higiene": "Diapers & hygiene",
    "Indústria comércio e negócios": "Industry, commerce & business",
    "Informática acessórios": "Computer accessories",
    "Instrumentos musicais": "Musical instruments",
    "La cuisine": "La cuisine", "Livros importados": "Imported books",
    "Livros interesse geral": "General-interest books",
    "Livros técnicos": "Technical books",
    "Malas acessórios": "Luggage & accessories",
    "Market place": "Marketplace",
    "Móveis colchão e estofado": "Furniture: mattresses & upholstery",
    "Móveis cozinha área de serviço jantar e jardim":
        "Furniture: kitchen, laundry, dining & garden",
    "Móveis decoração": "Furniture & decor",
    "Móveis escritório": "Office furniture",
    "Móveis quarto": "Bedroom furniture", "Móveis sala": "Living-room furniture",
    "Música": "Music", "PC gamer": "Gaming PC", "PCs": "PCs",
    "Papelaria": "Stationery", "Perfumaria": "Perfumery",
    "Pet shop": "Pet shop",
    "Portáteis casa forno e café": "Small appliances: oven & coffee",
    "Portáteis cozinha e preparadores de alimentos":
        "Small appliances: kitchen & food prep",
    "Relógios presentes": "Watches & gifts",
    "Seguros e serviços": "Insurance & services",
    "Sem categoria": "Uncategorized",
    "Sinalização e segurança": "Signage & safety",
    "Tablets impressão imagem": "Tablets, printing & imaging",
    "Telefonia": "Telephony", "Telefonia fixa": "Landline telephony",
    "Utilidades domésticas": "Housewares", "Áudio": "Audio",
    # --- crédito
    "Correspondente": "Banking agent", "Loja parceira": "Partner store",
    "Site": "Website", "Telemarketing": "Telemarketing", "App": "App",
    "CDC veículo": "Auto loan", "Capital de giro": "Working capital",
    "Cartão consignado": "Payroll-deductible card",
    "Crédito pessoal": "Personal loan",
    "2 a 5 SM": "2–5 min. wages", "5 a 10 SM": "5–10 min. wages",
    "Acima de 10 SM": "Over 10 min. wages", "Até 2 SM": "Up to 2 min. wages",
    "Aprovado": "Approved", "Recusado": "Declined",
    "13 a 24 meses": "13–24 months", "25 a 36 meses": "25–36 months",
    "Acima de 36 meses": "Over 36 months", "Até 12 meses": "Up to 12 months",
    "Não aprovado": "Not approved",
    "Acima de R$ 15 mil": "Over R$ 15k", "Até R$ 2 mil": "Up to R$ 2k",
    "R$ 2 a 5 mil": "R$ 2–5k", "R$ 5 a 15 mil": "R$ 5–15k",
    "1,8 a 2,6% a.m.": "1.8–2.6% per month",
    "2,6 a 3,6% a.m.": "2.6–3.6% per month",
    "Acima de 3,6% a.m.": "Over 3.6% per month",
    "Até 1,8% a.m.": "Up to 1.8% per month",
    # --- people
    "Atendimento": "Customer service",
    "Centro de distribuição": "Distribution center",
    "Comercial": "Sales", "Corporativo": "Corporate", "Lojas": "Stores",
    "Tecnologia": "Technology",
    "Júnior": "Junior", "Liderança": "Leadership", "Operacional": "Operational",
    "Pleno": "Mid-level", "Sênior": "Senior",
    "Feminino": "Female", "Masculino": "Male",
    "Híbrido": "Hybrid", "Presencial": "On-site", "Remoto": "Remote",
    "Consultoria": "Recruiting agency",
    "Contratação em massa": "Mass hiring", "Indicação": "Referral",
    "LinkedIn": "LinkedIn", "Portais de vagas": "Job boards",
    "1 a 3 anos": "1–3 years", "3 a 12 meses": "3–12 months",
    "Até 3 meses": "Up to 3 months", "Mais de 3 anos": "Over 3 years",
    "25 a 34 anos": "25–34", "35 a 44 anos": "35–44",
    "45 anos ou mais": "45 or older", "Até 24 anos": "Up to 24",
    "Antes de set/2024": "Before Sep 2024",
    # --- PLD
    "R01 · Movimentação incompatível com a renda":
        "R01 · Activity inconsistent with income",
    "R02 · Muitas origens e saída rápida": "R02 · Many sources, fast outflow",
    "R03 · Transferências logo abaixo do limite":
        "R03 · Transfers just below the limit",
    "R04 · Conta pouco movimentada que acorda": "R04 · Dormant account wakes up",
    "R05 · Recebimento incompatível com o estabelecimento":
        "R05 · Receipts inconsistent with the merchant",
    "R06 · Transações em horário incompatível":
        "R06 · Transactions at inconsistent hours",
    "R07 · Recarga incompatível com o porte da empresa":
        "R07 · Top-ups inconsistent with company size",
    "R08 · Contas abertas em lote no mesmo dispositivo":
        "R08 · Batch accounts on the same device",
    "R09 · PEP com movimentação relevante": "R09 · PEP with relevant activity",
    "R10 · CPF irregular na checagem mensal":
        "R10 · Irregular CPF in the monthly check",
    "III, e · Irregularidade na identificação":
        "III, e · Identification irregularity",
    "III, f · Contas abertas em lote": "III, f · Accounts opened in batch",
    "III, j · Faturamento incompatível": "III, j · Inconsistent revenue",
    "III, l · Mesmo IP ou dispositivo": "III, l · Same IP or device",
    "IV, a · Incompatível com renda ou atividade":
        "IV, a · Inconsistent with income or activity",
    "IV, ac · Incompatível com faturamento da PJ":
        "IV, ac · Inconsistent with company revenue",
    "IV, b · Valores logo abaixo do limite": "IV, b · Amounts just below the limit",
    "IV, c · Alto valor em benefício de terceiros":
        "IV, c · High value on behalf of third parties",
    "IV, e · Conta pouco movimentada": "IV, e · Low-activity account",
    "IV, i · Mudança repentina de padrão": "IV, i · Sudden change of pattern",
    "IV, l · Artifício para burlar identificação":
        "IV, l · Scheme to evade identification",
    "IV, n · Depósitos de diversas origens": "IV, n · Deposits from many sources",
    "IV, s · Movimentação habitual de PEP": "IV, s · Habitual PEP activity",
    "IV, w · POS incompatível com o estabelecimento":
        "IV, w · POS inconsistent with the merchant",
    "IV, y · Horário incompatível": "IV, y · Inconsistent hours",
    "XVII, a · Operação atípica em fronteira":
        "XVII, a · Atypical operation at the border",
    "Empresa cliente (PJ)": "Client company (legal entity)",
    "Estabelecimento (PJ)": "Merchant (legal entity)",
    "Titular (PF)": "Account holder (individual)",
    "Cadastro": "Onboarding", "Cartão de benefícios": "Benefits card",
    "Conta digital (Pix)": "Digital account (Pix)",
    "Recarga de benefícios": "Benefits top-up",
    "Demais áreas": "Other areas", "Fronteira": "Border",
    "Alto": "High", "Baixo": "Low", "Médio": "Medium",
    "Não PEP": "Not PEP", "PEP": "PEP",
    "Comunicado ao COAF": "Reported to COAF", "Descartado": "Dismissed",
    "Em análise": "Under review",
    "Monitoramento reforçado": "Enhanced monitoring",
    "Acima de R$ 100 mil": "Over R$ 100k", "Até R$ 5 mil": "Up to R$ 5k",
    "R$ 20 a 100 mil": "R$ 20–100k", "R$ 5 a 20 mil": "R$ 5–20k",
    "Cadastral": "Onboarding data", "Comportamental": "Behavioral",
    "Volumétrica": "Volume-based",
    "Ciclo mensal": "Monthly cycle", "Diária": "Daily",
    "Colaborador · empresa grande": "Employee · large company",
    "Colaborador · empresa mei": "Employee · micro-entrepreneur",
    "Colaborador · empresa média": "Employee · mid-size company",
    "Colaborador · empresa pequena": "Employee · small company",
    "Empresa grande": "Large company", "Empresa média": "Mid-size company",
    "Empresa pequena": "Small company",
    "Estabelecimento · farmácia": "Merchant · pharmacy",
    "Estabelecimento · outros": "Merchant · other",
    "Estabelecimento · padaria e mercearia": "Merchant · bakery & grocery",
    "Estabelecimento · posto e mobilidade": "Merchant · gas & mobility",
    "Estabelecimento · restaurante": "Merchant · restaurant",
    "Estabelecimento · supermercado": "Merchant · supermarket",
    "Crítica": "Critical", "Alta": "High", "Média": "Medium", "Baixa": "Low",
    "0 a 15 dias": "0–15 days", "16 a 30 dias": "16–30 days",
    "31 a 45 dias": "31–45 days", "Vencidos (mais de 45)": "Overdue (over 45)",
    "Falha do job": "Job failure", "Reprocessamento": "Reprocessing",
    "Ok": "OK", "Sem lote": "No batch",
    "Recebido de": "Received from", "Enviado para": "Sent to",
    "Cartões da empresa": "Company cards",
    "Gasto dos colaboradores em": "Employees spent at",
    "Pix recebidos": "Pix received", "Pix enviados": "Pix sent",
    "Valor recebido por Pix": "Amount received via Pix",
    "Valor enviado por Pix": "Amount sent via Pix",
    "Pix logo abaixo do limite": "Pix just below the limit",
    "Compras no cartão (POS)": "Card purchases (POS)",
    "Compras entre 23h e 5h": "Purchases between 11pm and 5am",
    "Valor recebido pelos estabelecimentos": "Amount received by merchants",
    "Contas abertas": "Accounts opened",
    "Contas que movimentaram": "Accounts with activity",
    "Pagadores distintos por conta (7 dias)":
        "Distinct payers per account (7 days)",
    "Recarga de benefício": "Benefits top-up",
    "Colaboradores ativos": "Active employees",
    "Recebido no POS": "Received at POS", "Transações": "Transactions",
    "Transações entre 23h e 5h": "Transactions between 11pm and 5am",
}

# Rótulos compostos ("Tecnologia · Pleno") se traduzem pedaço a pedaço.
_SEP = " · "


def V(valor) -> str:
    """Um valor do dado como ele aparece na língua ativa."""
    if valor is None:
        return ""
    s = str(valor)
    if not en():
        return s
    if s in VALORES_EN:
        return VALORES_EN[s]
    if _SEP in s:
        partes = s.split(_SEP)
        if any(p in VALORES_EN for p in partes):
            return _SEP.join(VALORES_EN.get(p, p) for p in partes)
    m = re.fullmatch(r"Outros \((\d+) segmentos\)", s)
    if m:
        return f"Others ({m.group(1)} segments)"
    if s.startswith("Conta ***"):
        return "Account" + s[5:]
    return s


def V_lista(valores) -> str:
    return ", ".join(V(v) for v in valores)


def rotulo_idioma(chave: str) -> str:
    return {"pt": "🇧🇷 Português", "en": "🇺🇸 English"}[chave]


def plural(n: int, pt_um: str, pt_varios: str, en_um: str,
           en_varios: Optional[str] = None) -> str:
    """Concordância de número nas duas línguas."""
    if en():
        return en_um if n == 1 else (en_varios or en_um + "s")
    return pt_um if n == 1 else pt_varios
