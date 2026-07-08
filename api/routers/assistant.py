"""Natural-language ask endpoint: POST /api/ask.

This is a public, billed endpoint (each call costs LLM tokens), so it is
guarded: a per-IP rate limit, input bounds, and the per-question tool-call
budget enforced inside llm.run_ask. The model can only reach verified tools —
there is no arbitrary SQL path — so the existing data-accuracy guarantees hold.
"""
import json

import anthropic
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from llm import read_gaps, run_ask, run_ask_stream
from rate_limit import RateLimiter
from schemas.assistant import AskRequest, AskResponse

router = APIRouter()

# Billed endpoint, so the per-IP window is tight.
_limiter = RateLimiter(max_hits=8)


def _guard(req: AskRequest, request: Request) -> str:
    """Shared per-IP rate limit + input validation. Returns the cleaned
    question, or raises an HTTPException."""
    ip = request.client.host if request.client else "unknown"
    if _limiter.limited(ip):
        raise HTTPException(status_code=429, detail="Too many questions — give it a minute.")
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Ask a question first.")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Question is too long (max 500 characters).")
    return question


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request):
    """Non-streaming answer (used by the eval and as a simple fallback)."""
    question = _guard(req, request)
    try:
        return run_ask(question)
    except anthropic.AuthenticationError:
        # No usable credentials (no API key and no logged-in profile).
        raise HTTPException(status_code=503, detail="The assistant isn't configured with API credentials.")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="The model is rate-limited right now — try again shortly.")
    except anthropic.APIStatusError:
        raise HTTPException(status_code=502, detail="The assistant had an upstream error — try again.")


@router.post("/ask/stream")
def ask_stream(req: AskRequest, request: Request):
    """Server-Sent Events: streams the tool-call chain and the answer tokens as
    the agent works. Validation + rate limit run before the stream opens; errors
    that surface mid-stream (auth, upstream) arrive as an `error` event, since
    the HTTP status is already committed once streaming starts."""
    question = _guard(req, request)

    def sse():
        def ev(d: dict) -> str:
            return f"data: {json.dumps(d)}\n\n"
        try:
            for e in run_ask_stream(question):
                yield ev(e)
        except anthropic.AuthenticationError:
            yield ev({"type": "error", "detail": "The assistant isn't configured with API credentials."})
        except anthropic.RateLimitError:
            yield ev({"type": "error", "detail": "The model is rate-limited right now — try again shortly."})
        except anthropic.APIStatusError:
            yield ev({"type": "error", "detail": "The assistant had an upstream error — try again."})
        except Exception:
            yield ev({"type": "error", "detail": "The assistant hit an unexpected error — try again."})

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/gaps")
def gaps(response: Response, limit: int = 50):
    """Review the data gaps the assistant has logged — questions it couldn't
    fully answer because the platform is missing that stat/split/season."""
    response.headers["Cache-Control"] = "no-store"  # review data, never cache
    return read_gaps(max(1, min(limit, 500)))
