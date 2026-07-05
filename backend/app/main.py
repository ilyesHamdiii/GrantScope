from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models.case_activity  # noqa: F401
import app.models.entities  # noqa: F401
import app.models.finding_evidence  # noqa: F401
import app.models.suppression  # noqa: F401
from app.api.router import api_router
from app.db.base import Base
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="GrantScope API",
    version="0.10.0",
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

app.include_router(api_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "grantscope-api",
        "mode": "development",
    }