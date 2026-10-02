import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException
from portfolio_core.database import open_database
from portfolio_core.http import fetch
from portfolio_core.schemas import AnalysisRequest
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, Column, MetaData, String, Table, select
from sqlalchemy.orm import Session

from match_history.demo import demo_analysis
from match_history.stats import extract_match, summarize

metadata = MetaData()
analyses = Table(
    "analyses", metadata, Column("id", String(36), primary_key=True), Column("payload", JSON)
)
matches = Table(
    "matches", metadata, Column("key", String(400), primary_key=True), Column("payload", JSON)
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HISTORY_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///history.db"
    riot_url: str = "http://127.0.0.1:8001"


def create_app(settings=None, transport=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = open_database(
            settings.database_url, Path(__file__).parent / "migrations"
        )
        # Serializa sincronizações: previne duplicações e rajadas contra a Riot.
        app.state.lock = asyncio.Lock()
        async with httpx.AsyncClient(timeout=25, transport=transport) as http:
            app.state.http = http
            yield
        app.state.engine.dispose()

    app = FastAPI(title="LoL Match History", lifespan=lifespan)

    @app.get("/health")
    def health():
        with app.state.engine.connect() as connection:
            connection.execute(select(1))
        return {"status": "ok"}

    async def get_catalog():
        return await fetch(app.state.http, "GET", settings.riot_url + "/api/v1/champions")

    @app.get("/api/v1/analyses/demo")
    async def demo():
        return demo_analysis(await get_catalog())

    @app.get("/api/v1/analyses/{analysis_id}")
    def read_analysis(analysis_id: UUID):
        with Session(app.state.engine) as session:
            payload = session.execute(
                select(analyses.c.payload).where(analyses.c.id == str(analysis_id))
            ).scalar_one_or_none()
        if payload is None:
            raise HTTPException(404, "Análise não encontrada. Consulte o jogador novamente.")
        return payload

    @app.post("/api/v1/analyses", status_code=201)
    async def analyze(body: AnalysisRequest):
        if app.state.lock.locked():
            raise HTTPException(
                429,
                "Há uma análise em andamento. Aguarde alguns segundos.",
                headers={"Retry-After": "10"},
            )
        async with app.state.lock:
            http = app.state.http
            base = settings.riot_url + "/api/v1"
            account = await fetch(
                http,
                "GET",
                base + "/accounts/by-riot-id",
                params={"gameName": body.gameName, "tagLine": body.tagLine, "region": body.region},
            )
            ids = await fetch(
                http,
                "GET",
                base + "/matches/by-puuid/" + quote(account["puuid"], safe=""),
                params={"region": body.region, "count": body.count, "queue": body.queue},
            )
            # Duplicatas externas não contam duas vezes.
            ids = list(dict.fromkeys(ids))
            catalog = await get_catalog()
            rows = []
            for match_id in ids:
                key = f"{body.region}:{account['puuid']}:{match_id}"
                with Session(app.state.engine) as session:
                    row = session.execute(
                        select(matches.c.payload).where(matches.c.key == key)
                    ).scalar_one_or_none()
                if row is None:
                    raw = await fetch(
                        http,
                        "GET",
                        base + "/matches/" + quote(match_id, safe=""),
                        params={"region": body.region},
                    )
                    try:
                        row = extract_match(raw, account["puuid"], body.queue)
                    except (KeyError, TypeError, ValueError):
                        raise HTTPException(502, "Dados de partida incompletos na Riot.") from None
                    if row is not None:
                        # Cada partida concluída fica salva mesmo se a seguinte sofrer rate limit.
                        with Session(app.state.engine) as session, session.begin():
                            session.execute(matches.insert().values(key=key, payload=row))
                if row is not None and row["queue"] == body.queue:
                    rows.append(row)
            rows.sort(key=lambda x: x["timestamp"], reverse=True)
            profile_icon_id = (rows[0].get("profileIcon") if rows else 29)
            payload = {
                "id": str(uuid4()),
                "account": {
                    "gameName": account.get("gameName") or body.gameName,
                    "tagLine": account.get("tagLine") or body.tagLine,
                    "profileIconId": profile_icon_id,
                },
                "region": body.region,
                "queue": body.queue,
                "requested": body.count,
                "fetched": len(ids),
                "skipped": len(ids) - len(rows),
                "demo": False,
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "matches": rows,
                "stats": summarize(rows),
                "catalog": catalog,
            }
            with Session(app.state.engine) as session, session.begin():
                session.execute(analyses.insert().values(id=payload["id"], payload=payload))
            return payload

    return app


app = create_app()
