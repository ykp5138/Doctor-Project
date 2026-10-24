"""A feedback-only receiver; no recordings, transcription, or model endpoints."""
from contextlib import asynccontextmanager
import hmac
import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException

from feedback_store import FeedbackRequest, append_feedback


def _configured_token() -> str:
    return os.getenv("FEEDBACK_API_TOKEN", "").strip()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if not _configured_token():
        raise RuntimeError("Set FEEDBACK_API_TOKEN before starting the feedback receiver.")
    yield


app = FastAPI(
    title="Feedback receiver",
    lifespan=_lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _require_token(authorization: Optional[str] = Header(None)) -> None:
    expected = _configured_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Feedback receiver is not configured.")
    scheme, _, provided = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="A valid feedback token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/feedback", dependencies=[Depends(_require_token)])
def store_feedback(req: FeedbackRequest):
    try:
        return append_feedback(req)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not save feedback on the receiving computer. Check its feedback directory permissions.",
        ) from exc
