from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.requests import Request

from data_fetcher import ScreenerClient
from rule_engine import evaluate_checklist

app = FastAPI(title="Stock Rule Checklist")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

screener_client = ScreenerClient()


class EvaluateRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=100)


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/evaluate")
def evaluate_stock(payload: EvaluateRequest) -> dict:
    query = payload.query.strip()
    try:
        snapshot = screener_client.fetch_company_snapshot(query)
        report = evaluate_checklist(snapshot)
        return report
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Unable to evaluate stock due to an internal error: {exc}",
        ) from exc
