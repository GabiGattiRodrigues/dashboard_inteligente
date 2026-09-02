#!/usr/bin/env bash
# ===================================================================
#  Analytics com agente - abre o painel no navegador (macOS e Linux)
#
#  No macOS, dois cliques neste arquivo. Se o Mac reclamar que não pode
#  abrir, rode uma vez no Terminal:  chmod +x iniciar.command
#
#  Faz o mesmo que o iniciar.bat do Windows: acha o Python, cria um
#  ambiente isolado só na primeira vez, instala as bibliotecas e sobe
#  o app. Para fechar, Ctrl+C nesta janela.
# ===================================================================
set -euo pipefail

cd "$(dirname "$0")"

echo
echo "  =========================================================="
echo "    Analytics com agente - três painéis, um motor"
echo "  =========================================================="
echo

# --- 1. Python -------------------------------------------------------
PY=""
for cand in python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done

if [ -z "$PY" ]; then
  echo "  [ X ]  Não encontrei o Python nesta máquina."
  echo
  echo "         macOS:  brew install python   (ou python.org/downloads)"
  echo "         Linux:  sudo apt install python3 python3-venv"
  echo
  read -r -p "  Enter para fechar. " _
  exit 1
fi
echo "  [ 1/4 ]  Python encontrado: $($PY --version 2>&1)"

# --- 2. Ambiente isolado ---------------------------------------------
VPY=".venv/bin/python"
if [ ! -x "$VPY" ]; then
  echo "  [ 2/4 ]  Criando o ambiente isolado (só na primeira vez)..."
  "$PY" -m venv .venv
else
  echo "  [ 2/4 ]  Ambiente isolado já existe."
fi

# --- 3. Dependências --------------------------------------------------
if [ ! -f ".venv/instalado.txt" ]; then
  echo "  [ 3/4 ]  Instalando as bibliotecas. Leva alguns minutos na"
  echo "           primeira vez; nas próximas é instantâneo."
  echo "           (o progresso aparece abaixo — é normal demorar)"
  echo
  # Sem --quiet de propósito: uma instalação de vários minutos sem nenhum
  # sinal na tela parece travamento, e a pessoa fecha a janela no meio.
  # --retries/--timeout evitam que um soluço de rede derrube tudo.
  if ! "$VPY" -m pip install --upgrade pip \
        --disable-pip-version-check --retries 5 --timeout 60; then
    echo
    echo "  [ ! ]  Não consegui atualizar o pip. Seguindo assim mesmo."
  fi
  if ! "$VPY" -m pip install -r requirements.txt \
        --disable-pip-version-check --retries 5 --timeout 60; then
    echo
    echo "  [ X ]  A instalação falhou — quase sempre é conexão."
    echo "         Rode este arquivo de novo; ele continua de onde parou."
    echo
    read -r -p "  Enter para fechar. " _
    exit 1
  fi
  echo pronto > ".venv/instalado.txt"
  echo
  echo "           Bibliotecas instaladas."
else
  echo "  [ 3/4 ]  Bibliotecas já instaladas."
fi

# --- 4. Dados ---------------------------------------------------------
if [ ! -f "data/fato_olist.parquet" ]; then
  echo
  echo "  [ ! ]  Falta o arquivo data/fato_olist.parquet"
  echo "         Ele vem pronto no zip. Se você clonou do GitHub:"
  echo "             bash scripts/baixar_olist.sh"
  echo "             .venv/bin/python scripts/build_fact.py"
  echo
  read -r -p "  Enter para fechar. " _
  exit 1
fi

[ -f "data/fato_credito.parquet" ] || {
  echo "  [ ! ]  Gerando a carteira de crédito simulada..."
  "$VPY" scripts/build_credito.py
}

# Evita o Streamlit parar pedindo e-mail na primeira execução.
mkdir -p "$HOME/.streamlit"
[ -f "$HOME/.streamlit/credentials.toml" ] || printf '[general]\nemail = ""\n' \
  > "$HOME/.streamlit/credentials.toml"

# --- Chave da OpenAI (opcional) ---------------------------------------
if [ -f "chave-openai.txt" ]; then
  OPENAI_API_KEY="$(tr -d '[:space:]' < chave-openai.txt)"
  export OPENAI_API_KEY
  echo "  [ 4/4 ]  Chave da OpenAI lida de chave-openai.txt"
elif [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "  [ 4/4 ]  Chave da OpenAI encontrada no ambiente."
else
  echo "  [ 4/4 ]  Sem chave da OpenAI: o agente roda no modo determinístico."
  echo "           Tudo funciona; só a linguagem fica menos flexível. Para"
  echo "           ligar o modelo, crie um arquivo chave-openai.txt nesta"
  echo "           pasta com a chave dentro e abra este arquivo de novo."
fi

echo
echo "  ----------------------------------------------------------"
echo "   Abrindo no navegador. Se não abrir sozinho, entre em:"
echo "   http://localhost:8501"
echo
echo "   Para fechar: Ctrl+C aqui."
echo "  ----------------------------------------------------------"
echo

exec "$VPY" -m streamlit run app.py
