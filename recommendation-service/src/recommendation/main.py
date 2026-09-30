import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from portfolio_core.database import open_database
from portfolio_core.http import fetch
from portfolio_core.schemas import Role
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, Column, MetaData, String, Table, select
from sqlalchemy.orm import Session

from recommendation.engine import VERSION, recommend

metadata = MetaData()
snapshots = Table(
    "recommendations", metadata, Column("id", String(80), primary_key=True), Column("payload", JSON)
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECOMMENDATION_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///recommendations.db"
    history_url: str = "http://127.0.0.1:8002"


def create_app(settings=None, transport=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = open_database(
            settings.database_url, Path(__file__).parent / "migrations"
        )
        app.state.lock = asyncio.Lock()
        async with httpx.AsyncClient(timeout=30, transport=transport) as http:
            app.state.http = http
            yield
        app.state.engine.dispose()

    app = FastAPI(title="LoL Recommendations", lifespan=lifespan)

    @app.get("/health")
    def health():
        with app.state.engine.connect() as connection:
            connection.execute(select(1))
        return {"status": "ok"}

    @app.get("/api/v1/recommendations/{analysis_id}")
    async def recommendations(analysis_id: str, role: Role = "ALL"):
        if analysis_id != "demo":
            try:
                UUID(analysis_id)
            except ValueError:
                raise HTTPException(422, "Identificador inválido.") from None
        key = f"{analysis_id}:{role}:{VERSION}"
        async with app.state.lock:
            if analysis_id != "demo":
                with Session(app.state.engine) as session:
                    existing = session.execute(
                        select(snapshots.c.payload).where(snapshots.c.id == key)
                    ).scalar_one_or_none()
                if existing:
                    return existing
            analysis = await fetch(
                app.state.http, "GET", settings.history_url + "/api/v1/analyses/" + analysis_id
            )
            result = {
                "analysisId": analysis_id,
                "demo": analysis["demo"],
                **recommend(analysis, role),
            }
            if analysis_id != "demo":
                with Session(app.state.engine) as session, session.begin():
                    session.execute(snapshots.insert().values(id=key, payload=result))
            return result

    return app


app = create_app()
