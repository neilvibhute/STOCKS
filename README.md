# Stock Rule Checklist (Screener.in)

A lightweight web app that:

1. Accepts a stock name or ticker.
2. Finds the company page on Screener dynamically.
3. Pulls key financial data from Screener.
4. Evaluates a 34-rule checklist and returns a structured report.

## Project Structure

- `app.py` - FastAPI server and endpoints
- `data_fetcher.py` - Screener search + HTML parsing
- `rule_engine.py` - Rule checklist evaluation logic
- `templates/index.html` - Single page UI
- `static/styles.css` - Styles

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app:app --reload
```

Open `http://127.0.0.1:8000`.

## Deployment

### Deploy to Render (Free)

1. Push to GitHub
2. Go to [render.com](https://render.com) and sign in
3. Click "New +" → "Web Service"
4. Connect your GitHub repo
5. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3

### Deploy to Railway (Free)

1. Push to GitHub
2. Go to [railway.app](https://railway.app) and sign in
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your repo
5. Railway auto-detects Python and uses Procfile

## Notes

- The app intentionally has no auth or DB, suitable for personal use (2-3 users max).
- Rules marked as **N/A** indicate missing data or require manual context (portfolio, technical indicators, DCF models). Score is calculated only from evaluated rules.
- The scraper extracts metrics from Screener's top-ratios section and financial tables. If Screener changes HTML structure, selectors may need updates.
- Debug logs print extracted ratio count and page size to help troubleshoot scraping issues.
