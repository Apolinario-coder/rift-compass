import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from riot_integration.client import RiotClient, RiotError
from riot_integration.config import Settings
from riot_integration.main import create_app

URL = "/api/v1/accounts/by-riot-id"
PARAMS = {"gameName": "Meu Jogador", "tagLine": "BR1"}


def settings(**kwargs):
    return Settings(_env_file=None, api_key="test-secret", **kwargs)


def test_success_encodes_name_and_uses_header():
    def handler(request):
        assert request.url.host == "americas.api.riotgames.com"
        assert request.url.raw_path.endswith(b"/Meu%20Jogador/BR1")
        assert request.headers["X-Riot-Token"] == "test-secret"
        assert "test-secret" not in str(request.url)
        return httpx.Response(200, json={"puuid": "abc", **PARAMS})

    with TestClient(create_app(settings(), httpx.MockTransport(handler))) as client:
        response = client.get(URL, params=PARAMS)
        assert response.status_code == 200
        assert response.json() == {"puuid": "abc", **PARAMS}


@pytest.mark.parametrize("status,expected", [(404, 404), (401, 503), (403, 503), (400, 502)])
def test_errors_are_sanitized_without_retry(status, expected):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="upstream details test-secret")

    with TestClient(create_app(settings(), httpx.MockTransport(handler))) as client:
        response = client.get(URL, params=PARAMS)
        assert response.status_code == expected
        assert "test-secret" not in response.text
        assert len(calls) == 1


@pytest.mark.parametrize("payload", [{}, {"puuid": ""}, {"puuid": 12}])
def test_malformed_success(payload):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with TestClient(create_app(settings(), transport)) as client:
        assert client.get(URL, params=PARAMS).status_code == 502


def test_missing_key_health_and_input_validation():
    def forbidden(request):
        pytest.fail("Não deve chamar a Riot")

    app = create_app(Settings(_env_file=None, api_key=""), httpx.MockTransport(forbidden))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get(URL, params=PARAMS).status_code == 503
        assert client.get(URL).status_code == 422
        assert client.get(URL, params={**PARAMS, "gameName": "   "}).status_code == 422
        assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize("retry_after,expected", [("30", 30), ("bad", 120), ("nan", 120)])
def test_rate_limit_blocks_subsequent_calls_and_recovers(retry_after, expected):
    async def scenario():
        now = [1000.0]
        calls = []

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": retry_after})
            return httpx.Response(200, json={"puuid": "abc"})

        async with httpx.AsyncClient(
            base_url="https://americas.api.riotgames.com", transport=httpx.MockTransport(handler)
        ) as http:
            riot = RiotClient(http, settings(), clock=lambda: now[0])
            for _ in range(2):
                with pytest.raises(RiotError) as error:
                    await riot.account("Name", "BR1")
                assert error.value.status == 429
                assert error.value.retry_after == expected
            assert len(calls) == 1
            now[0] += expected
            assert (await riot.account("Name", "BR1")).puuid == "abc"
            assert len(calls) == 2

    asyncio.run(scenario())


def test_retry_after_is_exposed_to_api_caller():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(429, headers={"Retry-After": "20"})
    )
    with TestClient(create_app(settings(), transport)) as client:
        response = client.get(URL, params=PARAMS)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "20"


@pytest.mark.parametrize("failure,expected", [("timeout", 504), ("network", 502), ("500", 502)])
@pytest.mark.parametrize("recover", [True, False])
def test_transient_retries_are_bounded(failure, expected, recover):
    async def scenario():
        calls, sleeps = [], []

        async def sleep(delay):
            sleeps.append(delay)

        def handler(request):
            calls.append(request)
            if recover and len(calls) == 3:
                return httpx.Response(200, json={"puuid": "abc"})
            if failure == "timeout":
                raise httpx.ReadTimeout("secret", request=request)
            if failure == "network":
                raise httpx.ConnectError("secret", request=request)
            return httpx.Response(500)

        async with httpx.AsyncClient(
            base_url="https://americas.api.riotgames.com", transport=httpx.MockTransport(handler)
        ) as http:
            riot = RiotClient(http, settings(), sleep=sleep)
            if recover:
                assert (await riot.account("Name", "BR1")).puuid == "abc"
            else:
                with pytest.raises(RiotError) as error:
                    await riot.account("Name", "BR1")
                assert error.value.status == expected
                assert "secret" not in error.value.detail
            assert len(calls) == 3
    asyncio.run(scenario())


def test_catalog_mastery_calculation():
    from riot_integration.catalog import catalog

    data = catalog()
    assert "champions" in data
    assert len(data["champions"]) > 100
    for champ in data["champions"]:
        assert "winrateCurve" in champ
        c = champ["winrateCurve"]
        assert 4 <= c["inflectionGames"] <= 40
        assert 35.0 <= c["initialWinrate"] <= 50.0
        assert 54.0 <= c["tacticalWinrate"] <= 58.0
        assert 60.0 <= c["masteryWinrate"] <= 66.0
        assert c["winrateDelta"] > 0
        assert len(c["trajectory"]) >= 5
