from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import env


LOG_LEVEL = env("LOG_LEVEL", "INFO") or "INFO"
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("assistant")


app = FastAPI(title="AI Assistant", version="1.0.0")


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    meta: Dict[str, Any] = {}


def _disable_automation() -> bool:
    # Default to disabled in production hosting (Render has no GUI/desktop apps).
    raw = env("DISABLE_AUTOMATION", "1")
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def process_query(query: str) -> str:
    """Core web handler that reuses existing assistant logic safely."""
    query = (query or "").strip()
    if not query:
        return "Please provide a query."

    # Lazy imports so the server can boot even if optional desktop-only deps are missing.
    from Backend.Chatbot import ChatBot
    from Backend.Model import FirstLayerDMM
    from Backend.RealtimeSearchEngine import realtime_search_engine
    from Backend.realtime_search.intent_local import upgrade_general_to_realtime
    from Backend.SIE import try_society_intelligence

    try:
        sie_reply = try_society_intelligence(query)
        if sie_reply is not None:
            return str(sie_reply)
    except Exception as exc:
        logger.warning("SIE error: %s", exc, exc_info=True)

    try:
        decision = FirstLayerDMM(query) or []
    except Exception as exc:
        logger.error("Intent parsing error: %s", exc, exc_info=True)
        return "Sorry, I couldn't understand that request. Please try again."

    try:
        decision = upgrade_general_to_realtime(list(decision), query) if decision else []
    except Exception as exc:
        logger.warning("Realtime upgrade error: %s", exc, exc_info=True)

    if not decision:
        return str(ChatBot(query))

    # Exit is a CLI concept; for web we just acknowledge.
    if any(str(task).startswith("exit") for task in decision):
        return "Okay."

    # Automation/image generation may be desktop-specific; keep logic but guard in production.
    if any(str(task).startswith(("open ", "close ", "play ", "system ", "content ", "google search ", "youtube search ")) for task in decision):
        if _disable_automation():
            return "Automation features are disabled in hosted mode."
        try:
            from asyncio import run
            from Backend.Automation import Automation

            run(Automation(list(decision)))
            return "Done."
        except Exception as exc:
            logger.error("Automation error: %s", exc, exc_info=True)
            return "Automation failed."

    if any(str(task).startswith("generate image") for task in decision):
        if _disable_automation():
            return "Image generation is disabled in hosted mode."
        try:
            from Backend.ImageGeneration import GenerateImages

            for task in decision:
                if str(task).startswith("generate image"):
                    prompt = str(task).replace("generate image", "", 1).strip() or query
                    GenerateImages(prompt)
            return "Image generation started."
        except Exception as exc:
            logger.error("Image generation error: %s", exc, exc_info=True)
            return "Image generation failed."

    general_or_realtime = [
        str(task) for task in decision if str(task).startswith("general") or str(task).startswith("realtime")
    ]
    if any(task.startswith("realtime") for task in general_or_realtime):
        merged_query = " and ".join(" ".join(task.split()[1:]).strip() for task in general_or_realtime).strip()
        try:
            return str(realtime_search_engine(merged_query or query))
        except Exception as exc:
            logger.error("Realtime search error: %s", exc, exc_info=True)
            return str(ChatBot(query))

    for task in general_or_realtime:
        if task.startswith("general"):
            pure_query = task.replace("general", "", 1).strip()
            return str(ChatBot(pure_query or query))

    return str(ChatBot(query))


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "time": int(time.time())}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        answer = process_query(req.query)
        return ChatResponse(answer=answer, meta={"automation_disabled": _disable_automation()})
    except Exception as exc:
        logger.error("Unhandled error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


if __name__ == "__main__":
    # Local debug only. Render uses gunicorn/uvicorn via start.sh.
    import uvicorn

    port = int(os.environ.get("PORT", "10000"))
    uvicorn.run("app.server:app", host="0.0.0.0", port=port, log_level=LOG_LEVEL.lower())

