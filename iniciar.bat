@echo off
rem ===================================================================
rem  Analytics com agente - abre o painel no navegador (Windows)
rem
rem  Basta dar dois cliques neste arquivo. Ele cuida de tudo:
rem   1. acha o Python instalado na maquina
rem   2. cria um ambiente isolado (.venv) so na primeira vez, para nao
rem      baguncar as bibliotecas que voce ja tem
rem   3. instala as dependencias, tambem so na primeira vez
rem   4. sobe o app e abre o navegador
rem
rem  Para fechar: volte nesta janela preta e aperte Ctrl+C, ou
rem  simplesmente feche a janela.
rem ===================================================================

setlocal enableextensions
chcp 65001 >nul 2>&1
title Analytics com agente - tres paineis, um motor
cd /d "%~dp0"

echo.
echo  ==========================================================
echo    Analytics com agente - tres paineis, um motor
echo  ==========================================================
echo.

rem --- 1. Onde esta o Python? ----------------------------------------
rem O launcher "py" e o jeito recomendado no Windows; "python" e o plano B.
rem
rem Nota para quem for mexer: a checagem NAO pode ficar dentro de um bloco
rem "if (...)" usando %errorlevel%. Dentro de parenteses o cmd expande a
rem variavel na hora em que LE o bloco, e nao na hora em que executa -- entao
rem o teste leria o errorlevel anterior ao "where" e daria o resultado errado.
rem Por isso os desvios abaixo, em vez de aninhamento.
set "PY="
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto python_ok
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
:python_ok

if not defined PY (
  echo  [ X ]  Nao encontrei o Python nesta maquina.
  echo.
  echo         Instale em https://www.python.org/downloads/
  echo         IMPORTANTE: na primeira tela do instalador, marque
  echo         "Add Python to PATH" antes de clicar em Install.
  echo.
  echo         Depois de instalar, rode este arquivo de novo.
  echo.
  pause
  exit /b 1
)

echo  [ 1/4 ]  Python encontrado.

rem --- 2. Ambiente isolado -------------------------------------------
set "VPY=.venv\Scripts\python.exe"

if not exist "%VPY%" (
  echo  [ 2/4 ]  Criando o ambiente isolado ^(so na primeira vez^)...
  %PY% -m venv .venv
  if not exist "%VPY%" (
    echo.
    echo  [ X ]  Nao consegui criar o ambiente .venv
    echo         Tente rodar na mao:  %PY% -m venv .venv
    echo.
    pause
    exit /b 1
  )
) else (
  echo  [ 2/4 ]  Ambiente isolado ja existe.
)

rem --- 3. Dependencias ------------------------------------------------
rem O arquivo-marca evita reinstalar tudo a cada abertura.
if not exist ".venv\instalado.txt" (
  echo  [ 3/4 ]  Instalando as bibliotecas. Isso leva alguns minutos
  echo           na primeira vez; nas proximas e instantaneo.
  echo           O progresso aparece abaixo - e normal demorar.
  echo.
  rem Sem --quiet de proposito: uma instalacao de varios minutos sem nenhum
  rem sinal na tela parece travamento, e a pessoa fecha a janela no meio.
  rem --retries/--timeout evitam que um solucos de rede derrube tudo.
  "%VPY%" -m pip install --upgrade pip --disable-pip-version-check --retries 5 --timeout 60
  "%VPY%" -m pip install -r requirements.txt --disable-pip-version-check --retries 5 --timeout 60
  if errorlevel 1 (
    echo.
    echo  [ X ]  A instalacao falhou - quase sempre e conexao.
    echo         Rode este arquivo de novo; ele continua de onde parou.
    echo.
    pause
    exit /b 1
  )
  echo pronto> ".venv\instalado.txt"
  echo.
  echo           Bibliotecas instaladas.
) else (
  echo  [ 3/4 ]  Bibliotecas ja instaladas.
)

rem --- 4. Dados -------------------------------------------------------
if not exist "data\fato_olist.parquet" (
  echo.
  echo  [ ! ]  Falta o arquivo data\fato_olist.parquet
  echo         Ele vem pronto no zip. Se voce clonou do GitHub, rode:
  echo             scripts\baixar_olist.sh   ^(ou baixe os CSVs do Olist^)
  echo             .venv\Scripts\python scripts\build_fact.py
  echo.
  pause
  exit /b 1
)

if not exist "data\fato_credito.parquet" (
  echo  [ ! ]  Gerando a carteira de credito simulada...
  "%VPY%" scripts\build_credito.py
)

rem --- Evita o Streamlit parar pedindo e-mail na primeira execucao ----
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit" >nul 2>&1
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  >"%USERPROFILE%\.streamlit\credentials.toml" echo [general]
  >>"%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

rem --- Chave da OpenAI (opcional) -------------------------------------
rem Sem chave o app roda igual, com o interpretador deterministico.
rem
rem Aqui tambem sem aninhar em "if (...)": o "set /p" com redirecionamento
rem dentro de um bloco e outro ponto onde o cmd tropeca. Desvios de novo.
if not exist "chave-openai.txt" goto sem_arquivo_chave
<chave-openai.txt set /p OPENAI_API_KEY=
echo  [ 4/4 ]  Chave da OpenAI lida de chave-openai.txt
goto chave_ok

:sem_arquivo_chave
if not defined OPENAI_API_KEY goto sem_chave
echo  [ 4/4 ]  Chave da OpenAI encontrada no sistema.
goto chave_ok

:sem_chave
echo  [ 4/4 ]  Sem chave da OpenAI: o agente vai rodar no modo
echo           deterministico. Tudo funciona, so a linguagem fica
echo           menos flexivel. Para ligar o modelo, crie um arquivo
echo           chamado  chave-openai.txt  nesta pasta, com a chave
echo           numa linha so, sem aspas e sem espacos sobrando.

:chave_ok

echo.
echo  ----------------------------------------------------------
echo   Abrindo no navegador. Se nao abrir sozinho, entre em:
echo   http://localhost:8501
echo.
echo   Para fechar: Ctrl+C aqui, ou feche esta janela.
echo  ----------------------------------------------------------
echo.

"%VPY%" -m streamlit run app.py

rem Se o Streamlit sair com erro, a janela fica aberta para dar tempo de ler.
if errorlevel 1 (
  echo.
  echo  [ X ]  O app encerrou com erro. A mensagem esta acima.
  echo.
  pause
)

endlocal
