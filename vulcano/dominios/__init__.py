"""
Registro de domínios.

Acrescentar um domínio ao Vulcano é escrever um arquivo neste pacote e
inclui-lo na lista abaixo. Nenhum motor precisa ser tocado.

Cada arquivo de domínio também declara um dicionário `EN` com o mesmo
catálogo em inglês: nome, rótulos, descrições, fórmulas, sinônimos e as
perguntas de exemplo. `obter` e `listar` devolvem a versão da língua ativa --
o motor não sabe em que língua está, só lê `m.rotulo` como sempre leu. As
chaves (métrica, dimensão, coluna) e o SQL são os mesmos nas duas línguas: é
o que garante que o número em inglês seja o mesmo número em português.

Os sinônimos em inglês SE SOMAM aos em português. O agente entende as duas
línguas o tempo todo -- quem escreve "qual a receita by region?" não precisa
escolher.
"""

from dataclasses import replace
from typing import Any

from .. import i18n
from ..semantica import Dominio
from . import credito, marketing, people, pld, produto

_MODULOS = (marketing, credito, produto, pld, people)

DOMINIOS: dict[str, Dominio] = {m.DOMINIO.chave: m.DOMINIO for m in _MODULOS}
_EN: dict[str, dict[str, Any]] = {m.DOMINIO.chave: getattr(m, "EN", {})
                                  for m in _MODULOS}

ORDEM = ["marketing", "credito", "produto", "pld", "people"]

_CACHE_EN: dict[str, Dominio] = {}


def _somar(pt: dict[str, list[str]], en: dict[str, list[str]]
           ) -> dict[str, list[str]]:
    fora = {k: list(v) for k, v in pt.items()}
    for k, v in en.items():
        fora.setdefault(k, [])
        fora[k] += [x for x in v if x not in fora[k]]
    return fora


def _em_ingles(dom: Dominio) -> Dominio:
    """O mesmo domínio, com o texto em inglês e os sinônimos das duas línguas."""
    if dom.chave in _CACHE_EN:
        return _CACHE_EN[dom.chave]
    en = _EN.get(dom.chave) or {}
    if not en:
        return dom

    metricas = {}
    for k, m in dom.metricas.items():
        t = en.get("metricas", {}).get(k)
        if t:
            rotulo, descricao, *resto = t
            formula = resto[0] if resto else m.formula
            m = replace(m, rotulo=rotulo, descricao=descricao,
                        formula=formula if m.formula else "")
        metricas[k] = m

    dimensoes = {}
    for k, d in dom.dimensoes.items():
        t = en.get("dimensoes", {}).get(k)
        if t:
            d = replace(d, rotulo=t[0], descricao=t[1])
        dimensoes[k] = d

    limites = list(dom.limites)
    just = en.get("limites", [])
    if len(just) == len(limites):
        limites = [replace(lim, justificativa=j)
                   for lim, j in zip(limites, just)]

    funil = list(dom.funil)
    rot_funil = en.get("funil", [])
    if len(rot_funil) == len(funil):
        funil = [(c, r, t) for (c, _, t), r in zip(funil, rot_funil)]

    # Os sinônimos em português ficam: o rótulo em português de cada métrica
    # e dimensão entra aqui para o agente continuar entendendo "receita"
    # depois que a tela passou a dizer "Revenue".
    sin_m = _somar(dom.sinonimos_metrica, en.get("sinonimos_metrica", {}))
    for k, m in dom.metricas.items():
        sin_m.setdefault(k, [])
        if m.rotulo not in sin_m[k]:
            sin_m[k].append(m.rotulo)
    sin_d = _somar(dom.sinonimos_dimensao, en.get("sinonimos_dimensao", {}))
    for k, d in dom.dimensoes.items():
        sin_d.setdefault(k, [])
        if d.rotulo not in sin_d[k]:
            sin_d[k].append(d.rotulo)

    novo = replace(
        dom,
        nome=en.get("nome", dom.nome),
        subtitulo=en.get("subtitulo", dom.subtitulo),
        descricao=en.get("descricao", dom.descricao),
        fonte=en.get("fonte", dom.fonte),
        metricas=metricas, dimensoes=dimensoes, limites=limites,
        funil=funil,
        sinonimos_metrica=sin_m, sinonimos_dimensao=sin_d,
        perguntas_exemplo=list(en.get("perguntas_exemplo",
                                      dom.perguntas_exemplo)),
        notas=list(en.get("notas", dom.notas)),
        agente_papel=en.get("agente_papel", dom.agente_papel),
        guia_conversa=tuple(en.get("guia_conversa", dom.guia_conversa)),
        dica_conversa=en.get("dica_conversa", dom.dica_conversa),
    )
    _CACHE_EN[dom.chave] = novo
    return novo


def localizar(dom: Dominio) -> Dominio:
    """O domínio na língua ativa."""
    base = DOMINIOS.get(dom.chave, dom)
    return _em_ingles(base) if i18n.en() else base


def obter(chave: str) -> Dominio:
    if chave not in DOMINIOS:
        raise KeyError(f"domínio desconhecido: {chave}")
    return localizar(DOMINIOS[chave])


def listar() -> list[Dominio]:
    return [obter(c) for c in ORDEM if c in DOMINIOS]
