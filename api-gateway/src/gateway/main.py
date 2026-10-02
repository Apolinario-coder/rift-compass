import hmac
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from portfolio_core.http import fetch
from portfolio_core.schemas import AnalysisRequest, Role
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")
    riot_url: str = "http://127.0.0.1:8001"
    history_url: str = "http://127.0.0.1:8002"
    recommendation_url: str = "http://127.0.0.1:8003"
    username: str = "admin"
    password: SecretStr = SecretStr("")
    jwt_secret: SecretStr = SecretStr("")
    secure_cookie: bool = False


class Login(BaseModel):
    username: str
    password: SecretStr


def create_app(settings=None, transport=None):
    settings = settings or Settings()
    auth_enabled = bool(settings.password.get_secret_value())
    if auth_enabled and len(settings.jwt_secret.get_secret_value()) < 32:
        raise RuntimeError(
            "GATEWAY_JWT_SECRET precisa de pelo menos 32 caracteres quando o login está ativo."
        )
    attempts = {}

    @asynccontextmanager
    async def lifespan(app):
        # Uma consulta pode envolver 50 partidas. O timeout é maior no gateway.
        async with httpx.AsyncClient(timeout=900, transport=transport) as http:
            app.state.http = http
            yield

    app = FastAPI(title="Rift Compass — Gateway", lifespan=lifespan)

    @app.middleware("http")
    async def security(request: Request, call_next):
        path = request.url.path
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlparse
                origin_host = urlparse(origin).netloc.split(":")[0].lower()
                forwarded_host = request.headers.get("x-forwarded-host", "")
                host_header = request.headers.get("host", "")
                req_host = (forwarded_host or host_header).split(":")[0].lower()
                if origin_host and req_host:
                    is_local = origin_host in ["localhost", "127.0.0.1"] and req_host in ["localhost", "127.0.0.1"]
                    if not is_local and origin_host != req_host:
                        return JSONResponse({"detail": "Origem não permitida."}, status_code=403)
        if auth_enabled and path.startswith("/api/") and path not in {"/api/session", "/api/login"}:
            try:
                token = request.cookies.get("session", "")
                claims = jwt.decode(
                    token,
                    settings.jwt_secret.get_secret_value(),
                    algorithms=["HS256"],
                    options={"require": ["exp", "sub", "iat"]},
                    issuer="rift-compass",
                )
                if claims["sub"] != settings.username:
                    raise jwt.InvalidTokenError()
            except jwt.InvalidTokenError:
                return JSONResponse({"detail": "Faça login para continuar."}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self';"
            " img-src 'self' https://ddragon.leagueoflegends.com data:;"
            " style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;"
            " font-src 'self' https://fonts.gstatic.com;"
            " script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://static.cloudflareinsights.com;"
            " connect-src 'self' https://cloudflareinsights.com;"
            " frame-ancestors 'none';"
            " base-uri 'self';"
            " form-action 'self'"
        )
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/session")
    async def session(request: Request):
        authenticated = not auth_enabled
        if auth_enabled:
            try:
                claims = jwt.decode(
                    request.cookies.get("session", ""),
                    settings.jwt_secret.get_secret_value(),
                    algorithms=["HS256"],
                    issuer="rift-compass",
                    options={"require": ["exp", "sub", "iat"]},
                )
                authenticated = claims["sub"] == settings.username
            except jwt.InvalidTokenError:
                pass
        return {"authEnabled": auth_enabled, "authenticated": authenticated}

    @app.post("/api/login")
    async def login(body: Login, request: Request, response: Response):
        if not auth_enabled:
            raise HTTPException(400, "Login não está habilitado nesta instalação local.")
        host = request.client.host if request.client else "local"
        now = time.monotonic()
        recent = [t for t in attempts.get(host, []) if now - t < 60]
        if len(recent) >= 5:
            raise HTTPException(
                429, "Muitas tentativas. Aguarde um minuto.", headers={"Retry-After": "60"}
            )
        attempts[host] = recent + [now]
        if not (
            hmac.compare_digest(body.username.encode(), settings.username.encode())
            and hmac.compare_digest(
                body.password.get_secret_value().encode(),
                settings.password.get_secret_value().encode(),
            )
        ):
            raise HTTPException(401, "Usuário ou senha inválidos.")
        attempts.pop(host, None)
        issued = int(time.time())
        token = jwt.encode(
            {"sub": settings.username, "iat": issued, "exp": issued + 3600, "iss": "rift-compass"},
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        response.set_cookie(
            "session",
            token,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="strict",
            max_age=3600,
        )
        return {"authenticated": True}

    def get_http():
        http = getattr(app.state, "http", None)
        if http is None or http.is_closed:
            http = httpx.AsyncClient(timeout=900, transport=transport)
            app.state.http = http
        return http

    @app.post("/api/logout")
    async def logout(response: Response):
        response.delete_cookie("session")
        return {"authenticated": False}

    @app.get("/api/catalog")
    async def catalog():
        try:
            return await fetch(get_http(), "GET", settings.riot_url + "/api/v1/champions")
        except Exception:
            from riot_integration.catalog import catalog as get_catalog
            return get_catalog()

    @app.get("/api/analyses/demo")
    async def demo():
        try:
            return await fetch(get_http(), "GET", settings.history_url + "/api/v1/analyses/demo")
        except Exception:
            from match_history.demo import demo_analysis
            from riot_integration.catalog import catalog as get_catalog
            return demo_analysis(get_catalog())

    def get_inprocess_history():
        h = getattr(app.state, "inprocess_history", None)
        if h is not None:
            return h
        import asyncio
        from portfolio_core.database import open_database
        from riot_integration.config import Settings as RiotSettings
        from riot_integration.client import RiotClient
        from riot_integration.main import create_app as create_riot_app
        from match_history.main import create_app as create_history_app, Settings as HistorySettings
        import match_history

        r_settings = RiotSettings()
        riot_app = create_riot_app(settings=r_settings)
        r_http = httpx.AsyncClient(
            base_url=f"https://{r_settings.region}.api.riotgames.com",
            headers={"X-Riot-Token": r_settings.api_key.get_secret_value()},
            timeout=r_settings.timeout_seconds,
        )
        riot_app.state.riot = RiotClient(r_http, r_settings)

        h_settings = HistorySettings()
        h_app = create_history_app(settings=h_settings, transport=httpx.ASGITransport(app=riot_app))
        h_app.state.engine = open_database(
            h_settings.database_url, Path(match_history.__file__).parent / "migrations"
        )
        h_app.state.lock = asyncio.Lock()
        h_app.state.http = httpx.AsyncClient(timeout=25, transport=httpx.ASGITransport(app=riot_app))

        app.state.inprocess_history = h_app
        return h_app

    @app.post("/api/analyses", status_code=201)
    async def analyze(body: AnalysisRequest):
        try:
            return await fetch(
                get_http(),
                "POST",
                settings.history_url + "/api/v1/analyses",
                json=body.model_dump(),
            )
        except HTTPException as e:
            if e.status_code not in (502, 503, 504):
                raise
        except Exception:
            pass

        try:
            h_app = get_inprocess_history()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=h_app), timeout=90) as client:
                res = await client.post("http://test/api/v1/analyses", json=body.model_dump())
                if res.is_success:
                    return res.json()
                detail = res.json().get("detail", "Erro ao processar análise.") if "application/json" in res.headers.get("content-type", "") else res.text
                raise HTTPException(res.status_code, detail)
        except HTTPException:
            raise
        except Exception as err:
            import os
            if not os.environ.get("RIOT_API_KEY"):
                raise HTTPException(503, "RIOT_API_KEY não configurada no servidor. Cadastre a variável RIOT_API_KEY ou utilize o botão 'Carregar Demonstração'.")
            raise HTTPException(502, f"Falha na comunicação com a Riot Games: {err}")

    @app.get("/api/analyses/{analysis_id}")
    async def read_analysis(analysis_id: UUID):
        try:
            return await fetch(
                get_http(), "GET", settings.history_url + "/api/v1/analyses/" + str(analysis_id)
            )
        except Exception:
            try:
                h_app = get_inprocess_history()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=h_app), timeout=30) as client:
                    res = await client.get(f"http://test/api/v1/analyses/{analysis_id}")
                    if res.is_success:
                        return res.json()
            except Exception:
                pass
            raise HTTPException(404, "Análise não encontrada.")

    @app.get("/api/analyses", include_in_schema=False)
    async def list_analyses():
        return {"items": []}

    @app.get("/api/recommendations/{analysis_id}")
    async def recommendations(analysis_id: str, role: Role = "ALL"):
        if analysis_id != "demo":
            try:
                UUID(analysis_id)
            except ValueError:
                raise HTTPException(422, "Identificador inválido.") from None
        try:
            return await fetch(
                get_http(),
                "GET",
                settings.recommendation_url + "/api/v1/recommendations/" + analysis_id,
                params={"role": role},
            )
        except Exception:
            from recommendation.engine import recommend
            if analysis_id == "demo":
                from match_history.demo import demo_analysis
                from riot_integration.catalog import catalog as get_catalog
                cat = get_catalog()
                return recommend(demo_analysis(cat), role=role)
            try:
                # Gera recomendações in-process para o ID real recuperando a análise salva
                analysis = await read_analysis(UUID(analysis_id))
                return {
                    "analysisId": analysis_id,
                    "demo": analysis.get("demo", False),
                    **recommend(analysis, role=role),
                }
            except Exception:
                raise

    static_candidates = [
        Path(__file__).parent / "static",
        Path.cwd() / "static",
        Path.cwd() / "api-gateway" / "src" / "gateway" / "static",
        Path(__file__).resolve().parent.parent.parent.parent / "static",
    ]
    static = next((d for d in static_candidates if d.exists() and (d / "index.html").exists()), static_candidates[0])
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/api/index", include_in_schema=False)
    @app.get("/api/index.py", include_in_schema=False)
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(static / "index.html")

    return app


app = create_app()
