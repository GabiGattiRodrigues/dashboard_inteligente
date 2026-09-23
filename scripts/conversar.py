"""
Conversa de linha de comando com os agentes, sem abrir o Streamlit.

Serve para conferir roteiro de conversa (as perguntas do guia de cada agente)
nas duas línguas:

    python scripts/conversar.py marketing en "what was revenue?" "and why?"
    python scripts/conversar.py credito pt "qual a originação?" "e por quê?"

Cada pergunta herda o plano da anterior, como na tela. O período é o dos
últimos 90 dias da base e a comparação é a padrão da barra lateral.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vulcano import i18n  # noqa: E402
from vulcano.agente import Contexto, perguntar  # noqa: E402
from vulcano.dados import Filtros, conectar, periodo_disponivel  # noqa: E402
from vulcano.dominios import obter  # noqa: E402


def conversa(chave: str, idioma: str, perguntas: list[str],
             mostrar: bool = True) -> list:
    i18n.definir(idioma)
    dom = obter(chave)
    con = conectar(dom)
    dmin, dmax = periodo_disponivel(con)
    ctx = Contexto(dominio=dom, inicio=max(dmin, dmax - timedelta(days=89)),
                   fim=dmax, filtros=Filtros(),
                   preset_comparacao="ultimos_90" if chave == "pld"
                   else "mes_fechado")
    saida = []
    for p in perguntas:
        r = perguntar(con, p, ctx, usar_llm=False)
        ctx.ultimo_plano = r.plano
        ctx.historico += [{"papel": "user", "texto": p},
                          {"papel": "assistant", "texto": r.texto}]
        saida.append(r)
        if mostrar:
            print(f"\n>>> {p}\n[{r.plano['intencao']} · {r.plano.get('metrica')}"
                  f" · {r.plano.get('dimensao')}]\n{r.texto[:900]}")
    return saida


if __name__ == "__main__":
    conversa(sys.argv[1], sys.argv[2], sys.argv[3:])
