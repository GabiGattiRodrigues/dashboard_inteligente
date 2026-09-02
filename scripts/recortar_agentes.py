"""
Recorta os rostos dos agentes em avatares PNG com fundo transparente.

As fotos originais vem em tres fundos diferentes -- branco, preto e um xadrez
de "transparencia" que ficou achatado dentro do JPEG. Nenhum deles pode
aparecer no painel: o avatar assenta sobre cartao claro, sobre fundo escuro e
sobre a barra de abas, e um retangulo branco em volta do bicho denuncia
recorte malfeito.

Entao a remocao de fundo e feita de verdade, por segmentacao (rembg/u2net),
e nao por chave de cor. Chave de cor nao serviria aqui por um motivo simples:
o R2 e um cachorro PRETO fotografado sobre fundo PRETO, e o Bailey tem peito
BRANCO sobre fundo BRANCO -- em ambos os casos o fundo e a cor do bicho sao a
mesma cor, e qualquer limiar come parte do animal.

Cada agente tem duas caras, sempre do mesmo bicho para a pessoa reconhecer
quem esta falando:

  <prefixo>-animada.png   sorrindo, na aba de conversa
  <prefixo>-alerta.png    atento, na aba de alertas

Rodar:  python scripts/recortar_agentes.py
(precisa de `pip install rembg onnxruntime`; o modelo e baixado na primeira vez)
"""

import pathlib

import numpy as np
from PIL import Image

SRC = pathlib.Path("/mnt/user-data/uploads/imagens vulcano")
OUT = pathlib.Path(__file__).resolve().parents[1] / "assets"

# (arquivo, saida, cx, cy, r) -- centro e raio da JANELA de corte, em fracao da
# largura da imagem. A janela so enquadra; quem decide o que e bicho e o que e
# fundo e a segmentacao.
CORTES = [
    # Bailey: as duas poses estao na mesma foto -- sentado sorrindo a esquerda,
    # de pe e atento a direita.
    ("WhatsApp Image 2026-09-02 at 07.55.22.jpeg", "bailey-animada", .252, .352, .208),
    ("WhatsApp Image 2026-09-02 at 07.55.22.jpeg", "bailey-alerta",  .680, .236, .200),
    # Abigail: idem, gatinha sorrindo a esquerda e atenta a direita.
    ("WhatsApp Image 2026-09-02 at 07.55.23 (2).jpeg", "abigail-animada", .212, .292, .202),
    ("WhatsApp Image 2026-09-02 at 07.55.23 (2).jpeg", "abigail-alerta",  .632, .272, .168),
    # R2: duas fotos separadas.
    ("WhatsApp Image 2026-09-02 at 07.55.23 (1).jpeg", "r2-animada", .515, .310, .405),
    ("WhatsApp Image 2026-09-02 at 07.55.23.jpeg",     "r2-alerta",  .489, .248, .285),
]

LADO = 320   # 2x do maior uso na tela (160 px na capa)


def _segmentar(caminho: pathlib.Path) -> Image.Image:
    """Remove o fundo da foto inteira, uma vez por arquivo."""
    from rembg import new_session, remove
    if not hasattr(_segmentar, "_sessao"):
        _segmentar._sessao = new_session("u2net")
    im = Image.open(caminho).convert("RGB")
    return remove(im, session=_segmentar._sessao).convert("RGBA")


def _limpar_franja(im: Image.Image) -> Image.Image:
    """
    Tira a franja clara que a segmentacao deixa na borda.

    O recorte devolve pixels semitransparentes que ainda carregam a cor do
    fundo antigo. Sobre fundo escuro isso vira um halo branco em volta da
    orelha. Desconta-se a cor de fundo desses pixels dividindo pelo alfa
    (unpremultiply aproximado) e endurece-se um pouco o alfa nas pontas.
    """
    a = np.asarray(im).astype(np.float32)
    alfa = a[..., 3:4] / 255.0
    # Alfa muito baixo e franja pura: some com ela. Alfa alto vira opaco.
    duro = np.clip((alfa - 0.35) / 0.45, 0, 1)
    a[..., 3:4] = duro * 255.0
    return Image.fromarray(a.astype("uint8"), "RGBA")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cache: dict[str, Image.Image] = {}
    for arq, nome, fx, fy, fr in CORTES:
        if arq not in cache:
            cache[arq] = _limpar_franja(_segmentar(SRC / arq))
        im = cache[arq]
        W, H = im.size
        cx, cy, r = fx * W, fy * H, fr * W
        rosto = im.crop((round(cx - r), round(cy - r),
                         round(cx + r), round(cy + r)))
        rosto = rosto.resize((LADO, LADO), Image.LANCZOS)
        rosto.save(OUT / f"{nome}.png")
        opaco = (np.asarray(rosto)[..., 3] > 128).mean()
        print(f"{nome}.png  ({opaco:.0%} do quadro e bicho)")


if __name__ == "__main__":
    main()
