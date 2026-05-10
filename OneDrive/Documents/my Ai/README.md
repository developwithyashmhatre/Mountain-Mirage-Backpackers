# Python AI Assistant (Render-ready)

This project contains a local CLI assistant (`Main.py`) plus a production web wrapper for hosting (`app/server.py`).

## Local installation

```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

Create your local env file:

```bash
copy .env.example .env
```

## Local run

### CLI (original behavior)

```bash
python Main.py
```

### Web API (recommended for production parity)

```bash
set PORT=10000
python -m uvicorn app.server:app --host 0.0.0.0 --port %PORT%
```

Endpoints:

- `GET /health`
- `POST /chat` with JSON: `{ "query": "hello" }`

## Environment variables

Required for most AI features:

- `GROQ_API_KEY`
- `COHERE_API_KEY`

Optional:

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `SECRET_KEY`

Hosting toggles:

- `DISABLE_AUTOMATION` (default `1` in hosted mode)

## Render deployment

### GitHub push

```bash
git add .
git commit -m "Prepare Render deployment"
git push
```

### Render settings (exact)

- **Service type**: Web Service
- **Environment**: Python
- **Build command**: `pip install -r requirements.txt`
- **Start command**: `bash start.sh`
- **Health check path**: `/health`
- **Runtime**: from `runtime.txt` (Python 3.11.9)

Add Environment Variables in Render Dashboard:

- `GROQ_API_KEY`: your key
- `COHERE_API_KEY`: your key
- `LOG_LEVEL`: `INFO`
- `DISABLE_AUTOMATION`: `1`
- (optional) `OPENAI_API_KEY`, `DATABASE_URL`, `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`

### Deploy via `render.yaml` (recommended)

If you connect this repo to Render, it can read `render.yaml` automatically.

## Notes for cloud hosting

- Desktop automation features (opening apps, keyboard control, screenshots/webcam) are **disabled by default** in hosted mode.
- The hosted web server binds to `0.0.0.0` and uses Render’s `PORT`.

