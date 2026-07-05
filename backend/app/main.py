from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app.models.case_activity  # noqa: F401
import app.models.entities  # noqa: F401
import app.models.finding_evidence  # noqa: F401
import app.models.suppression  # noqa: F401
from app.api.router import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.demo_seed import seed_public_demo


STATIC_DIRECTORY = Path("/app/static")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)

    if settings.PUBLIC_DEMO_MODE:
        with SessionLocal() as db:
            seed_public_demo(db)

    yield


app = FastAPI(
    title="GrantScope API",
    version="0.11.0",
    description=(
        "Entra OAuth and service-principal incident investigation workbench "
        "for evidence-driven cloud identity triage."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_public_demo_read_only(
    request: Request,
    call_next,
):
    if (
        settings.PUBLIC_DEMO_MODE
        and request.url.path.startswith("/api/v1")
        and request.method not in {"GET", "HEAD", "OPTIONS"}
    ):
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "GrantScope public demo is read-only and uses "
                    "synthetic NorthBridge evidence only."
                )
            },
        )

    return await call_next(request)


app.include_router(api_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "grantscope-api",
        "mode": (
            "public-demo"
            if settings.PUBLIC_DEMO_MODE
            else "development"
        ),
    }


if STATIC_DIRECTORY.is_dir():
    app.mount(
        "/",
        StaticFiles(
            directory=str(STATIC_DIRECTORY),
            html=True,
        ),
        name="frontend",
    )