#!/usr/bin/env bash
# Baixa os CSVs publicos do Olist para data/raw/.
# A base original esta no Kaggle (olistbr/brazilian-ecommerce); este espelho
# no GitHub evita exigir credencial do Kaggle para reproduzir o projeto.
set -euo pipefail
DEST="$(dirname "$0")/../data/raw"
mkdir -p "$DEST"
TMP="$(mktemp -d)"
git clone --depth 1 -q \
  https://github.com/spdrio/Brazilian-E-Commerce-Public-Dataset-by-Olist.git "$TMP/olist"
cp "$TMP/olist/files/"*.csv "$DEST/"
rm -rf "$TMP"
echo "CSVs em $DEST:"
ls -1 "$DEST"
