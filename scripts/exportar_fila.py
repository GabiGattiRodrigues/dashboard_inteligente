"""
Exporta a fila de alertas abertos para a planilha do Apps Script.

Uma linha por alerta aberto na data-base, com a prioridade do cliente já
calculada por `vulcano/pld/fila.py` — a planilha não reimplementa a regra de
prioridade, para as duas nunca divergirem. Importar o CSV na aba "alertas" e
rodar `montarFila()` (ver automacoes/apps_script/fila_pld.gs).

    python scripts/exportar_fila.py            # posição na data-base
    python scripts/exportar_fila.py 2026-06-30 # posição em outra data
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from vulcano.dados import conectar  # noqa: E402
from vulcano.dominios import obter  # noqa: E402
from vulcano.pld import dados as pld_dados  # noqa: E402
from vulcano.pld import fila as mod_fila  # noqa: E402
from vulcano.pld.regras import REGRAS  # noqa: E402

SAIDA = RAIZ / "automacoes" / "apps_script" / "alertas_exemplo.csv"


def main() -> None:
    ref = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else pld_dados.data_base()
    dom = obter("pld")
    con = conectar(dom)
    al = mod_fila.alertas_abertos(con, dom, ref)
    clientes = mod_fila.posicao(con, dom, ref).set_index("cliente_id")
    al["prioridade"] = al["cliente_id"].map(clientes["prioridade"])
    al["enquadramento"] = al["regra_id"].map(lambda r: REGRAS[r].rotulo_enquadramento)
    colunas = ["alerta_id", "codigo", "tipo_cliente", "regra_id", "regra",
               "enquadramento", "valor_envolvido", "data", "prioridade",
               "evidencia"]
    al[colunas].to_csv(SAIDA, index=False, encoding="utf-8")
    print(f"{len(al)} alertas abertos em {ref} -> {SAIDA}")


if __name__ == "__main__":
    main()
