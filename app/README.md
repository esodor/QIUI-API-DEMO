# App — Secondo Cervello

Interfaccia web per il tuo Secondo Cervello.

## Avvio rapido

### 1. Ottieni la API key di Anthropic (gratis per iniziare)

1. Vai su [console.anthropic.com](https://console.anthropic.com)
2. Crea un account
3. Vai su "API Keys" → "Create Key"
4. Copia la chiave (inizia con `sk-ant-...`)

### 2. Configura la chiave

```bash
# Copia il file di esempio
cp app/.env.example app/.env

# Apri e inserisci la tua chiave
# ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Avvia l'app

**Mac/Linux:**
```bash
chmod +x app/start.sh
./app/start.sh
```

**Windows:**
```
Doppio click su app\start.bat
```

**Manuale (se preferisci):**
```bash
cd app
pip install -r requirements.txt
python main.py
```

### 4. Apri nel browser

→ [http://localhost:8000](http://localhost:8000)

---

## Funzionalità

- **Chat con Claude** con tutto il contesto del tuo Secondo Cervello
- **Upload file**: immagini (JPG, PNG, GIF, WebP), PDF, documenti di testo
- **3 modalità rapide**: Analisi Profonda, Aggiorna Sistema, Revisione Settimanale
- **Salva note** direttamente nelle aree del Secondo Cervello
- **Visualizza file** del Secondo Cervello dalla sidebar
- **Drag & drop** file nell'area chat

## Deployment online (opzionale, dopo)

Per mettere online l'app puoi usare Railway, Render, o Fly.io.
In tutti i casi, imposta la variabile d'ambiente `ANTHROPIC_API_KEY` sul server.

**Railway:**
```bash
railway up
railway variables set ANTHROPIC_API_KEY=sk-ant-...
```
