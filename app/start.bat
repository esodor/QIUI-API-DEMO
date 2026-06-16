@echo off
cd /d "%~dp0"

if not exist .env (
  copy .env.example .env
  echo.
  echo Apri app\.env e inserisci la tua ANTHROPIC_API_KEY
  echo Ottienila su: https://console.anthropic.com
  echo.
  pause
  notepad .env
)

if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate
pip install -q -r requirements.txt

echo.
echo Secondo Cervello in avvio...
echo Apri http://localhost:8000 nel browser
echo.

python main.py
pause
