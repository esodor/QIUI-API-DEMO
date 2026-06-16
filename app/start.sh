#!/bin/bash
# Script di avvio per Mac/Linux

cd "$(dirname "$0")"

# Crea .env se non esiste
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Prima di avviare, apri app/.env e inserisci la tua ANTHROPIC_API_KEY"
  echo "   Ottienila su: https://console.anthropic.com"
  echo ""
  read -p "Premi INVIO per aprire .env oppure CTRL+C per uscire..."
  ${EDITOR:-nano} .env
fi

# Crea venv se non esiste
if [ ! -d .venv ]; then
  echo "Creo ambiente virtuale Python..."
  python3 -m venv .venv
fi

# Attiva venv e installa dipendenze
source .venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "🧠 Secondo Cervello in avvio..."
echo "   Apri http://localhost:8000 nel browser"
echo ""

python main.py
