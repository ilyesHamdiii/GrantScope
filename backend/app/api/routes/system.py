from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db


router = APIRouter(tags=["system"])


@router.get("/system/database")
def database_status(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))

    return {
        "status": "connected",
        "database": "postgresql",
    }