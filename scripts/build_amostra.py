"""Monta amostra/amostra.html injetando dados.json no template.

A amostra e um HTML unico, sem rede: os numeros ja vem calculados pelo mesmo
motor do app (exportar_amostra.py) e ficam embutidos como JSON.
"""

import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PASTA = RAIZ / "amostra"


def main() -> None:
    template = (PASTA / "template.html").read_text(encoding="utf-8")
    dados = (PASTA / "dados.json").read_text(encoding="utf-8")
    # O conteudo vai dentro de <script type="application/json">; a unica
    # sequencia que fecharia a tag antes da hora e "</".
    dados = dados.replace("</", "<\\/")
    saida = template.replace("__DADOS__", dados)
    destino = PASTA / "amostra.html"
    destino.write_text(saida, encoding="utf-8")
    print(f"amostra: {len(saida.encode('utf-8')) // 1024} KB -> {destino}")


if __name__ == "__main__":
    main()
