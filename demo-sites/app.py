"""demo-sites: controllable fake websites for the uptime monitor.

Each named "site" answers according to its current mode; modes are switched
at runtime via POST /mode/{name} (used by the frontend Demo page and by the
e2e proof script). State lives in process memory — restarting the emulator
resets modes to "ok".

Modes: ok | error | dead | slow | flaky
  ok    → 200 "OK from {name}"
  error → 500
  dead  → hangs (client-side timeout)
  slow  → sleeps delay_ms (default 10000), then 200
  flaky → every 2nd request 500
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="demo-sites", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

VALID_MODES = {"ok", "error", "dead", "slow", "flaky"}

MODES: dict[str, dict] = {
    "main": {"mode": "ok"},
    "slow": {"mode": "ok"},
    "flaky": {"mode": "ok"},
    "dead": {"mode": "ok"},
}
COUNTERS: dict[str, int] = {}


class ModeIn(BaseModel):
    mode: str
    delay_ms: int = 10_000


def _state(name: str) -> dict:
    if name not in MODES:
        MODES[name] = {"mode": "ok"}
        COUNTERS[name] = 0
    return MODES[name]


async def _respond(name: str) -> tuple[int, str]:
    state = _state(name)
    mode = state["mode"]
    if mode == "error":
        return 500, "Internal Server Error"
    if mode == "dead":
        await asyncio.sleep(3600)  # never answers in practice
        return 200, "OK"
    if mode == "slow":
        await asyncio.sleep(state.get("delay_ms", 10_000) / 1000)
        return 200, f"OK from {name}"
    if mode == "flaky":
        COUNTERS[name] = COUNTERS.get(name, 0) + 1
        if COUNTERS[name] % 2 == 0:
            return 500, "Flaky failure"
        return 200, f"OK from {name}"
    return 200, f"OK from {name}"


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "modes": MODES}


@app.get("/modes")
async def modes() -> dict:
    return dict(MODES)


@app.post("/mode/{name}")
async def set_mode(name: str, payload: ModeIn) -> dict:
    if payload.mode not in VALID_MODES:
        raise HTTPException(422, f"mode must be one of {sorted(VALID_MODES)}")
    MODES[name] = {"mode": payload.mode, "delay_ms": payload.delay_ms}
    return {"name": name, **MODES[name]}


@app.get("/site/{name}")
async def site(name: str):
    status, body = await _respond(name)
    return Response(content=body, status_code=status, media_type="text/plain")


# Convenience endpoints (CONTRACT §6)

@app.get("/ok")
async def ok() -> str:
    return "OK"


@app.get("/error")
async def error():
    return Response(content="Internal Server Error", status_code=500, media_type="text/plain")


@app.get("/hang")
async def hang():
    await asyncio.sleep(3600)
    return "OK"


@app.get("/slow/{ms}")
async def slow(ms: int):
    await asyncio.sleep(ms / 1000)
    return "OK"


@app.get("/flaky/{n}")
async def flaky(n: int):
    COUNTERS["__flaky"] = COUNTERS.get("__flaky", 0) + 1
    if COUNTERS["__flaky"] % n == 0:
        return Response(content="Flaky failure", status_code=500, media_type="text/plain")
    return "OK"
