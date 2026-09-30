import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from riot_integration.config import Settings
from riot_integration.models import Account


class RiotError(Exception):
    def __init__(self, status: int, detail: str, retry_after: int | None = None):
        self.status = status
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(detail)


class RiotClient:
    """Adapter: concentra HTTP e erros externos, sem depender do FastAPI."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.http = http
        self.settings = settings
        self.sleep = sleep
        self.clock = clock
        self.blocked_until = 0.0
        self.failures = 0
        self.circuit_until = 0.0
        self.cache = {}
        # Uma chamada por vez nesta etapa: novas chamadas observam o cooldown
        # antes de atingir a Riot. Estado local; executar com um único worker.
        self.lock = asyncio.Lock()

    async def account(self, game_name: str, tag_line: str, region: str | None = None) -> Account:
        path = (
            "/riot/account/v1/accounts/by-riot-id/"
            f"{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
        )
        try:
            return Account.model_validate(await self.get_json(path, region=region, ttl=60))
        except ValidationError:
            raise RiotError(502, "Resposta inválida da Riot.") from None

    async def get_json(self, path: str, *, region: str | None = None, params=None, ttl=0):
        if not self.settings.api_key.get_secret_value().strip():
            raise RiotError(503, "Configure RIOT_API_KEY no servidor.")
        region = region or self.settings.region
        if region not in {"americas", "europe", "asia", "sea"}:
            raise RiotError(422, "Região inválida.")
        url = f"https://{region}.api.riotgames.com{path}"
        key = (url, str(params))
        async with self.lock:
            cached = self.cache.get(key)
            if cached and cached[0] > self.clock():
                return cached[1]
            for attempt in range(self.settings.max_attempts):
                if self.circuit_until > self.clock():
                    raise RiotError(
                        503,
                        "Riot indisponível. Circuito aberto por 30 segundos.",
                        math.ceil(self.circuit_until - self.clock()),
                    )
                remaining = math.ceil(self.blocked_until - self.clock())
                if remaining > 0:
                    raise RiotError(429, "Limite da Riot atingido. Aguarde.", remaining)
                try:
                    response = await self.http.get(url, params=params)
                except httpx.TimeoutException:
                    failure = RiotError(504, "A Riot demorou para responder.")
                except httpx.RequestError:
                    failure = RiotError(502, "Não foi possível conectar à Riot.")
                else:
                    if response.status_code == 200:
                        try:
                            data = response.json()
                        except (ValueError, ValidationError):
                            raise RiotError(502, "Resposta inválida da Riot.") from None
                        self.failures = 0
                        if ttl:
                            if len(self.cache) >= 500:
                                self.cache.clear()
                            self.cache[key] = (self.clock() + ttl, data)
                        return data
                    if response.status_code == 404:
                        raise RiotError(404, "Riot ID não encontrado nesta região.")
                    if response.status_code in (401, 403):
                        raise RiotError(
                            503, "A Riot recusou o acesso. Verifique a chave no servidor."
                        )
                    if response.status_code == 429:
                        try:
                            delay = max(1, math.ceil(float(response.headers["Retry-After"])))
                        except (KeyError, ValueError, OverflowError):
                            delay = 120
                        self.blocked_until = self.clock() + delay
                        raise RiotError(429, "Limite da Riot atingido. Aguarde.", delay)
                    if response.status_code < 500:
                        raise RiotError(502, "A Riot retornou uma resposta inesperada.")
                    failure = RiotError(502, "A Riot está temporariamente indisponível.")
                if attempt + 1 < self.settings.max_attempts:
                    await self.sleep(0.5 * 2**attempt)
            self.failures += 1
            if self.failures >= 3:
                self.circuit_until = self.clock() + 30
            raise failure
