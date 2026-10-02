from contextlib import asynccontextmanager
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from riot_integration.catalog import catalog
from riot_integration.client import RiotClient, RiotError
from riot_integration.config import Settings
from riot_integration.models import Account


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Reutiliza conexões e fecha os recursos ao encerrar a aplicação.
        async with httpx.AsyncClient(
            base_url=f"https://{settings.region}.api.riotgames.com",
            headers={"X-Riot-Token": settings.api_key.get_secret_value()},
            timeout=settings.timeout_seconds,
            transport=transport,
            follow_redirects=False,
        ) as http:
            app.state.riot = RiotClient(http, settings)
            yield

    app = FastAPI(
        title="LoL Portfolio — Riot Integration",
        version="0.1.0",
        description="Etapa 1: conta Riot por gameName e tagLine. Região definida no servidor.",
        lifespan=lifespan,
    )

    @app.exception_handler(RiotError)
    async def handle_riot_error(request: Request, error: RiotError):
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after else {}
        return JSONResponse({"detail": error.detail}, status_code=error.status, headers=headers)

    @app.get("/health", tags=["Operação"])
    async def health():
        """Liveness local; não consome a API nem comprova validade da chave."""
        return {"status": "ok"}

    @app.get(
        "/api/v1/accounts/by-riot-id",
        response_model=Account,
        tags=["Contas"],
        responses={
            code: {"description": description}
            for code, description in {
                404: "Conta não encontrada",
                429: "Cooldown da Riot (Retry-After)",
                502: "Falha externa",
                503: "Chave ausente ou acesso recusado",
                504: "Timeout",
            }.items()
        },
    )
    async def account(
        request: Request,
        game_name: Annotated[
            str, Query(alias="gameName", min_length=1, max_length=100, pattern=r"\S")
        ],
        tag_line: Annotated[
            str, Query(alias="tagLine", min_length=1, max_length=100, pattern=r"\S")
        ],
        region: Literal["americas", "europe", "asia", "sea"] | None = None,
    ):
        return await request.app.state.riot.account(game_name, tag_line, region)

    @app.get("/api/v1/summoners/by-puuid/{puuid}", tags=["Contas"])
    async def summoner(request: Request, puuid: str, platform: str = "br1"):
        return await request.app.state.riot.summoner(puuid, platform)

    @app.get("/api/v1/champions", tags=["Catálogo"])
    async def champions():
        return catalog()

    @app.get("/api/v1/matches/by-puuid/{puuid}", tags=["Partidas"])
    async def match_ids(
        request: Request,
        puuid: str,
        region: Literal["americas", "europe", "asia", "sea"] = "americas",
        count: int = Query(20, ge=1, le=50),
        queue: int = Query(420),
    ):
        if queue not in (420, 440):
            raise RiotError(422, "Fila inválida; use 420 ou 440.")
        result = await request.app.state.riot.get_json(
            f"/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids",
            region=region,
            params={"start": 0, "count": count, "queue": queue},
            ttl=60,
        )
        if not isinstance(result, list) or not all(isinstance(x, str) for x in result):
            raise RiotError(502, "Lista de partidas inválida.")
        return result

    @app.get("/api/v1/matches/{match_id}", tags=["Partidas"])
    async def match(
        request: Request,
        match_id: str,
        region: Literal["americas", "europe", "asia", "sea"] = "americas",
    ):
        result = await request.app.state.riot.get_json(
            f"/lol/match/v5/matches/{quote(match_id, safe='')}", region=region, ttl=3600
        )
        if not isinstance(result, dict) or "info" not in result or "metadata" not in result:
            raise RiotError(502, "Partida inválida.")
        return result

    return app


app = create_app()
