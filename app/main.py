from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import Base, engine
from .routers import records, telegram, wechat

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return RedirectResponse(url="/app/")


@app.get("/health")
def health():
    return {"ok": True}


app.include_router(records.router)
app.include_router(telegram.router)
app.include_router(wechat.router)

static_dir = Path(__file__).parent / "static"
app.mount("/app", StaticFiles(directory=static_dir, html=True), name="app")

