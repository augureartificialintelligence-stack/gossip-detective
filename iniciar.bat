@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GOSSIP DETECTIVE - Central de Comando

if not exist ".venv\Scripts\python.exe" (
  echo Preparando ambiente Python pela primeira vez...
  python -m venv .venv || goto :erro
  ".venv\Scripts\python.exe" -m pip install --use-feature=truststore -r requirements.txt || goto :erro
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo  Arquivo .env criado. Para ativar a pesquisa por IA, abra o .env
  echo  e preencha ANTHROPIC_API_KEY. Sem a chave, so os arquivos verificados funcionam.
  echo.
)

".venv\Scripts\python.exe" server.py --abrir
goto :eof

:erro
echo.
echo  Nao foi possivel preparar o ambiente. Verifique se o Python 3.11+ esta instalado.
pause
