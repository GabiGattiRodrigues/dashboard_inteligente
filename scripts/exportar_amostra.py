"""
Exporta um retrato do app para uma amostra estatica (JSON).

Todo numero da amostra sai dos motores de verdade -- mesma camada semantica,
mesmo SQL, mesma decomposicao. A amostra e estatica; os numeros nao sao
inventados. E o unico jeito honesto de mostrar o produto em um link que abre
no celular sem servidor.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vulcano import alertas as mod_alertas
from vulcano import causa_raiz as mod_causa
from vulcano import tendencia as mod_tendencia
from vulcano import analise as mod_analise
from vulcano.agente import Contexto, perguntar
from vulcano.dados import (Filtros, agregar, comparar, conectar,
                           periodo_disponivel, serie_diaria)
from vulcano.dominios import listar
from vulcano.estilo import PASTA_ASSETS, descrever_janela
from vulcano.formatacao import julgar, numero, pct, variacao_pct
from vulcano.periodos import NIVEIS_COMPARACAO, PRESETS, montar_preset, descrever_dia

SAIDA = Path(__file__).resolve().parents[1] / "amostra" / "dados.json"

# Preset por dominio, escolhido para a amostra cair num trecho com movimento.
CENARIO = {
    "marketing": dict(preset="mes_fechado", ref=date(2017, 11, 30),
                      metrica_causa="receita", dim_causa="categoria",
                      dia_alerta=date(2017, 11, 24),
                      conversa=["Oi!", "Quanto foi a receita?", "e por quê?",
                                "e por região?", "e o ticket médio?",
                                "como você calcula o ticket médio?"]),
    # Setembro/2017 e onde o afrouxamento de politica embutido no gerador
    # aparece: a safra sai de 3,91% para 5,85% de over30. E o mes em que a
    # analise de causa raiz tem o que encontrar.
    "credito": dict(preset="mes_fechado", ref=date(2017, 9, 30),
                    metrica_causa="over30_mob3", dim_causa="canal",
                    dia_alerta=date(2018, 1, 3),
                    conversa=["Qual a originação?",
                              "e a inadimplência over30?",
                              "quais os piores canais?", "e por quê?",
                              "o que é MOB?"]),
    "produto": dict(preset="mes_fechado", ref=date(2017, 11, 30),
                    metrica_causa="prazo_entrega", dim_causa="regiao",
                    dia_alerta=date(2017, 11, 24),
                    conversa=["Onde a jornada trava?", "Qual a nota média?",
                              "quais os piores estados em prazo?",
                              "e por quê?", "está melhorando?",
                              "de onde vem esse dado?"]),
}


def _avatar(prefixo: str, variante: str, lado: int = 128):
    """
    O PNG do agente como data URI, reduzido para o tamanho de tela.

    A amostra e um arquivo unico que a pessoa abre no celular, entao cada KB
    conta. Os originais tem 320 px (o dobro do maior uso no app); aqui a maior
    aparicao e 52 px, e 128 px ja da nitidez de sobra em tela retina -- levar
    os 320 px multiplicaria o arquivo por seis sem diferenca visivel.
    """
    import base64
    import io

    from PIL import Image

    caminho = PASTA_ASSETS / f"{prefixo}-{variante}.png"
    if not prefixo or not caminho.exists():
        return None
    im = Image.open(caminho).convert("RGBA").resize((lado, lado), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _kpis(con, dom, comp):
    a = agregar(con, dom, dom.metricas_painel, comp.anterior.inicio,
                comp.anterior.fim)
    b = agregar(con, dom, dom.metricas_painel, comp.atual.inicio, comp.atual.fim)

    def _v(df, k):
        if df.empty or pd.isna(df.iloc[0][k]):
            return float("nan")
        return float(df.iloc[0][k])

    saida = []
    for mk in dom.metricas_painel:
        m = dom.metrica(mk)
        va, vb = _v(a, mk), _v(b, mk)
        dp = variacao_pct(vb, va)
        saida.append({
            "rotulo": m.rotulo,
            "valor": numero(vb, m),
            "anterior": numero(va, m),
            "delta": pct(dp) if dp is not None else None,
            "melhorou": julgar(dp, m.bom_quando_sobe),
            "sentido": None if dp is None else ("sobe" if dp > 0 else "desce"),
            "definicao": m.descricao,
        })
    return saida


def _serie(con, dom, mk, fim, dias=70):
    m = dom.metrica(mk)
    s = serie_diaria(con, dom, [mk], fim - timedelta(days=dias - 1), fim)
    s = s.dropna(subset=[mk])
    if s.empty:
        return None
    s["mm"] = s[mk].rolling(7, min_periods=2).mean()
    return {
        "metrica": m.rotulo,
        "datas": [d.strftime("%d/%m") for d in s["data"]],
        "valores": [round(float(v), 4) for v in s[mk]],
        "media_movel": [None if pd.isna(v) else round(float(v), 4) for v in s["mm"]],
        "rotulos": [numero(float(v), m) for v in s[mk]],
    }


def _segmentos(con, dom, mk, dk, ini, fim, n=6):
    m, d = dom.metrica(mk), dom.dimensao(dk)
    df = agregar(con, dom, [mk], ini, fim, dims=[dk], ordenar_por=mk, limite=n)
    df = df.dropna(subset=[mk])
    if df.empty:
        return None
    return {
        "metrica": m.rotulo, "dimensao": d.rotulo,
        "itens": [{"nome": str(r[d.coluna]),
                   "valor": float(r[mk]),
                   "rotulo": numero(float(r[mk]), m)} for _, r in df.iterrows()],
    }


def _causa(con, dom, mk, dk, comp):
    m = dom.metrica(mk)
    dec = mod_causa.decompor(con, dom, mk, dk, comp, Filtros(), top_n=6)
    casc = mod_causa.dados_cascata(dec)
    return {
        "metrica": m.rotulo,
        "dimensao": dom.dimensao(dk).rotulo,
        "de": numero(dec.total_a, m),
        "para": numero(dec.total_b, m),
        "delta": numero(dec.delta, m, sinal=True),
        "delta_pct": pct(dec.delta_pct),
        "fecha": bool(dec.fecha),
        "residuo": numero(dec.residuo, m, sinal=True),
        "explicacao": mod_causa.explicar(dec, quantos=3),
        "aviso": dec.aviso,
        "cascata": [{"rotulo": r["rotulo"], "valor": float(r["valor"]),
                     "tipo": r["tipo"],
                     "rotulo_valor": numero(float(r["valor"]), m,
                                            sinal=(r["tipo"] != "total"))}
                    for _, r in casc.iterrows()],
    }


def _alertas(con, dom, dia):
    al = mod_alertas.varrer(con, dom, dia, Filtros())
    return {
        "dia": dia.strftime("%d/%m/%Y"),
        "resumo": mod_alertas.resumir(al, dia),
        "itens": [{"severidade": a.severidade, "tipo": a.tipo,
                   "texto": a.texto, "acao": a.acao,
                   "motivo": mod_alertas.motivo_provavel(con, dom, a, Filtros())}
                  for a in al[:5]],
    }


def _tendencia(con, dom, mk, ini, fim):
    t = mod_tendencia.analisar(con, dom, mk, ini, fim, Filtros())
    if t is None:
        return None
    return {"metrica": dom.metrica(mk).rotulo,
            "linhas": mod_tendencia.descrever(t)}


def _conversa(con, dom, perguntas, ini, fim, preset):
    ctx = Contexto(dominio=dom, inicio=ini, fim=fim, filtros=Filtros(),
                   preset_comparacao=preset)
    turnos = []
    for q in perguntas:
        r = perguntar(con, q, ctx, usar_llm=False)
        ctx.ultimo_plano = r.plano
        ctx.historico += [{"papel": "user", "texto": q},
                          {"papel": "assistant", "texto": r.texto}]
        turnos.append({
            "pergunta": q,
            "resposta": r.texto,
            "plano": {k: r.plano.get(k) for k in
                      ("intencao", "metrica", "dimensao", "preset")},
            "herdou": bool(r.plano.get("herdou")),
            "sql": r.sql,
        })
    return turnos


ROTULOS_NIVEL = {"dia_d1": "Contra ontem", "dia_d7": "Contra D-7",
                 "mtd": "Mês acumulado", "dia_media3": "Contra 3 dias iguais"}


def _niveis(con, dom, ref):
    """Os quatro níveis de comparação, no mesmo dia de referência."""
    fora = []
    for nivel in NIVEIS_COMPARACAO:
        c = montar_preset(nivel, ref)
        r = comparar(con, dom, dom.metricas_painel, c, Filtros())
        fora.append({
            "chave": nivel, "rotulo": ROTULOS_NIVEL[nivel],
            "regra": PRESETS[nivel], "base": c.rotulo_base(),
            "metricas": [
                {"rotulo": dom.metrica(mk).rotulo,
                 "atual": numero(r[mk]["atual"], dom.metrica(mk)),
                 "variacao": (pct(r[mk]["delta_pct"])
                              if r[mk]["delta_pct"] is not None else None),
                 "melhorou": julgar(r[mk]["delta_pct"],
                                    dom.metrica(mk).bom_quando_sobe)}
                for mk in dom.metricas_painel],
        })
    return fora


def _funil(con, dom, ini, fim):
    if dom.chave != "produto":
        return None
    from vulcano.dominios.produto import FUNIL
    passos, base = [], None
    for coluna, rotulo, _ in FUNIL:
        n = con.execute(
            f"SELECT COUNT(DISTINCT CASE WHEN {coluna} = 1 THEN order_id END) "
            f"FROM fato WHERE data BETWEEN DATE '{ini}' AND DATE '{fim}'"
        ).fetchone()[0] or 0
        base = base or n or 1
        passos.append({"etapa": rotulo, "valor": int(n),
                       "rotulo": f"{n:,}".replace(",", "."),
                       "fatia": f"{n / base * 100:.1f}".replace(".", ",") + "%"})
    return passos


def montar() -> dict:
    fora = {"dominios": [], "gerado_em": date.today().isoformat()}
    for dom in listar():
        cen = CENARIO[dom.chave]
        con = conectar(dom)
        dmin, dmax = periodo_disponivel(con)
        comp = montar_preset(cen["preset"], cen["ref"])
        ini, fim = comp.atual.inicio, comp.atual.fim

        a_datas, a_det = descrever_janela(comp.atual)
        b_datas, b_det = descrever_janela(comp.anterior)

        fora["dominios"].append({
            "chave": dom.chave,
            "nome": dom.nome,
            "subtitulo": dom.subtitulo,
            "descricao": dom.descricao,
            "fonte": dom.fonte,
            "simulado": dom.simulado,
            # As duas caras vao embutidas como data URI: a amostra e um
            # arquivo unico que precisa abrir no celular sem servidor e sem
            # rede, entao nao pode referenciar PNG nenhum de fora.
            "agente": {"nome": dom.agente_nome, "rosto": dom.agente_rosto,
                       "papel": dom.agente_papel,
                       "animada": _avatar(dom.agente_imagem, "animada"),
                       "alerta": _avatar(dom.agente_imagem, "alerta")},
            "notas": dom.notas,
            "comparacao": {"atual": a_datas, "atual_det": a_det,
                           "anterior": b_datas, "anterior_det": b_det,
                           "regra": comp.descricao},
            "kpis": _kpis(con, dom, comp),
            "serie": _serie(con, dom, dom.metricas_painel[0], fim),
            "segmentos": _segmentos(con, dom, dom.metricas_painel[0],
                                    dom.dims_filtro[0], ini, fim),
            "causa": _causa(con, dom, cen["metrica_causa"], cen["dim_causa"],
                            comp),
            "alertas": _alertas(con, dom, cen["dia_alerta"]),
            "tendencia": _tendencia(con, dom, dom.metricas_painel[0],
                                    max(dmin, fim - timedelta(days=120)), fim),
            "conversa": _conversa(con, dom, cen["conversa"], ini, fim,
                                  cen["preset"]),
            "niveis": _niveis(con, dom, fim),
            "funil": _funil(con, dom, ini, fim),
            "analise_geral": mod_analise.narrar_analise_geral(
                dom, mod_analise.analise_geral(con, dom, ini, fim, comp,
                                               Filtros())),
            "dia_referencia": descrever_dia(fim),
        })
    return fora


if __name__ == "__main__":
    dados = montar()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    print(f"{SAIDA} ({SAIDA.stat().st_size/1024:.0f} KB)")
    for d in dados["dominios"]:
        print(f"  {d['nome']}: {len(d['kpis'])} kpis, "
              f"{len(d['causa']['cascata'])} barras, "
              f"{len(d['alertas']['itens'])} alertas, "
              f"{len(d['conversa'])} turnos")
