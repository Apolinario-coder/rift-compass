import copy
import time
from contextlib import ExitStack

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from gateway.main import Settings as GatewaySettings
from gateway.main import create_app as gateway_app
from match_history.demo import demo_analysis
from match_history.main import Settings as HistorySettings
from match_history.main import create_app as history_app
from match_history.main import matches
from match_history.stats import extract_match, summarize
from recommendation.engine import recommend
from recommendation.main import Settings as RecommendationSettings
from recommendation.main import create_app as recommendation_app
from riot_integration.catalog import catalog
from riot_integration.config import Settings as RiotSettings
from riot_integration.main import create_app as riot_app
from sqlalchemy import func, select


def transport_to(client):
    def handle(request):
        response = client.request(
            request.method,
            request.url.raw_path.decode(),
            content=request.content,
            headers={"Content-Type": "application/json"},
        )
        return httpx.Response(
            response.status_code, content=response.content, headers=response.headers
        )

    return httpx.MockTransport(handle)


def raw_match(index=0, queue=420):
    return {
        "metadata": {"matchId": f"BR1_{index}"},
        "info": {
            "queueId": queue,
            "mapId": 11,
            "gameDuration": 1800,
            "gameStartTimestamp": 1700000000000 + index * 1000,
            "participants": [
                {
                    "puuid": "player",
                    "championId": 103,
                    "championName": "Ahri",
                    "teamPosition": "MIDDLE",
                    "win": index % 2 == 0,
                    "kills": 5,
                    "deaths": 0,
                    "assists": 5,
                    "totalMinionsKilled": 150,
                }
            ],
        },
    }


@pytest.fixture
def stack(tmp_path):
    calls = []

    def riot_mock(request):
        calls.append(str(request.url))
        if "/accounts/" in request.url.path:
            return httpx.Response(
                200, json={"puuid": "player", "gameName": "Teste", "tagLine": "BR1"}
            )
        if request.url.path.endswith("/ids"):
            return httpx.Response(200, json=["BR1_0", "BR1_1", "BR1_1"])
        return httpx.Response(200, json=raw_match(int(request.url.path.rsplit("_", 1)[-1])))

    with ExitStack() as context:
        riot = context.enter_context(
            TestClient(
                riot_app(
                    RiotSettings(_env_file=None, api_key="test"), httpx.MockTransport(riot_mock)
                )
            )
        )
        history = context.enter_context(
            TestClient(
                history_app(
                    HistorySettings(
                        _env_file=None, database_url=f"sqlite:///{tmp_path}/history.db"
                    ),
                    transport_to(riot),
                )
            )
        )
        rec = context.enter_context(
            TestClient(
                recommendation_app(
                    RecommendationSettings(
                        _env_file=None, database_url=f"sqlite:///{tmp_path}/rec.db"
                    ),
                    transport_to(history),
                )
            )
        )

        def route(request):
            port = request.url.port
            client = {8001: riot, 8002: history, 8003: rec}[port]
            return transport_to(client).handle_request(request)

        gateway = context.enter_context(
            TestClient(
                gateway_app(
                    GatewaySettings(_env_file=None, password=""), httpx.MockTransport(route)
                )
            )
        )
        yield gateway, history, rec, calls


def test_pipeline_persists_deduplicates_and_recommends(stack):
    gateway, history, rec, calls = stack
    body = {"gameName": "Teste", "tagLine": "BR1", "count": 20}
    first = gateway.post("/api/analyses", json=body)
    assert first.status_code == 201, first.text
    result = first.json()
    assert result["demo"] is False
    assert result["stats"]["games"] == 2
    assert result["stats"]["winrate"] == 50
    assert result["stats"]["kda"] == 20
    assert gateway.get("/api/analyses/" + result["id"]).json() == result
    recommendations = gateway.get("/api/recommendations/" + result["id"] + "?role=MIDDLE")
    assert recommendations.status_code == 200, recommendations.text
    items = recommendations.json()["items"]
    assert items and all("MIDDLE" in i["champion"]["roles"] for i in items)
    assert all(0 <= i["score"] <= 100 for i in items)
    assert any(i["kind"] == "known" for i in items)
    assert any(i["kind"] == "explore" for i in items)
    assert len(calls) == 4
    second = gateway.post("/api/analyses", json=body)
    assert second.status_code == 201
    assert len(calls) == 4  # conta/IDs em cache; partidas no banco
    with history.app.state.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(matches)).scalar_one() == 2
    again = gateway.get("/api/recommendations/" + result["id"] + "?role=MIDDLE")
    assert again.json() == recommendations.json()


def test_demo_never_calls_riot_and_is_labeled(stack):
    gateway, _, _, calls = stack
    response = gateway.get("/api/analyses/demo")
    assert response.status_code == 200
    assert response.json()["demo"] is True
    assert response.json()["stats"]["games"] == 20
    recs = gateway.get("/api/recommendations/demo").json()
    assert recs["demo"] is True and recs["items"]
    assert calls == []
    assert gateway.get("/").status_code == 200
    assert gateway.get("/static/app.js").status_code == 200


def test_empty_history_and_role_do_not_invent_recommendations():
    demo = demo_analysis(catalog())
    assert recommend(demo, "JUNGLE")["items"] == []
    demo["matches"] = []
    assert recommend(demo)["items"] == []
    assert summarize([])["games"] == 0
    assert summarize([])["preferredRole"] is None


def test_small_sample_is_smoothed_and_scoring_explainable():
    demo = demo_analysis(catalog())
    demo["matches"] = [dict(demo["matches"][0], win=True)]
    result = recommend(demo, "MIDDLE")
    personal = next(i for i in result["items"] if i["games"])
    assert personal["winrate"] == 100
    assert personal["score"] < 100
    assert personal["confidence"] == "baixa"
    assert abs(sum(personal["components"].values()) - personal["score"]) <= 0.2
    assert result == recommend(demo, "MIDDLE")


@pytest.mark.parametrize("change", [{"gameDuration": 200}, {"queueId": 450}, {"mapId": 12}])
def test_excludes_remakes_and_other_modes(change):
    raw = raw_match()
    raw["info"].update(change)
    assert extract_match(raw, "player", 420) is None


def test_aggregates_weight_by_games_not_champion_averages():
    rows = [extract_match(raw_match(i), "player", 420) for i in range(4)]
    rows[0]["championId"] = 99
    rows[0]["win"] = True
    rows[1]["win"] = rows[2]["win"] = rows[3]["win"] = False
    stats = summarize(rows)
    assert stats["winrate"] == 25
    assert stats["csPerMinute"] == 5


def test_invalid_requests_do_not_reach_upstream(stack):
    client, _, _, calls = stack
    assert client.post("/api/analyses", json={"gameName": " ", "tagLine": "BR1"}).status_code == 422
    assert (
        client.post(
            "/api/analyses", json={"gameName": "ok", "tagLine": "BR1", "queue": 450}
        ).status_code
        == 422
    )
    assert client.get("/api/recommendations/not-an-id").status_code == 422
    assert client.get("/api/recommendations/demo?role=unknown").status_code == 422
    assert calls == []


def test_gateway_propagates_rate_limit():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(429, json={"detail": "Aguarde"}, headers={"Retry-After": "45"})
    )
    with TestClient(gateway_app(GatewaySettings(_env_file=None, password=""), transport)) as client:
        response = client.post("/api/analyses", json={"gameName": "ok", "tagLine": "BR1"})
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "45"


def test_jwt_login_logout_expiration_and_origin():
    config = GatewaySettings(
        _env_file=None, username="tester", password="test-pass", jwt_secret="x" * 40
    )
    upstream = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))
    with TestClient(gateway_app(config, upstream)) as client:
        assert client.get("/api/catalog").status_code == 401
        assert client.get("/api/session").json()["authenticated"] is False
        assert (
            client.post("/api/login", json={"username": "tester", "password": "bad"}).status_code
            == 401
        )
        response = client.post("/api/login", json={"username": "tester", "password": "test-pass"})
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/catalog").status_code == 200
        assert (
            client.post("/api/logout", headers={"Origin": "https://evil.example"}).status_code
            == 403
        )
        assert client.post("/api/logout").status_code == 200
        assert client.get("/api/catalog").status_code == 401
        expired = jwt.encode(
            {
                "sub": "tester",
                "iat": int(time.time()) - 100,
                "exp": int(time.time()) - 1,
                "iss": "rift-compass",
            },
            "x" * 40,
            algorithm="HS256",
        )
        client.cookies.set("session", expired)
        assert client.get("/api/catalog").status_code == 401


def test_secret_required_and_login_rate_limited():
    with pytest.raises(RuntimeError):
        gateway_app(GatewaySettings(_env_file=None, password="test", jwt_secret="short"))
    app = gateway_app(GatewaySettings(_env_file=None, password="test", jwt_secret="x" * 40))
    with TestClient(app) as client:
        for _ in range(5):
            assert (
                client.post(
                    "/api/login", json={"username": "admin", "password": "wrong"}
                ).status_code
                == 401
            )
        assert (
            client.post("/api/login", json={"username": "admin", "password": "wrong"}).status_code
            == 429
        )


def test_role_filter_uses_only_selected_role_stats():
    demo = demo_analysis(catalog())
    other = copy.deepcopy(demo["matches"][0])
    other.update(role="UTILITY", win=False, kills=0, deaths=30)
    demo["matches"] = [demo["matches"][0], other]
    item = next(i for i in recommend(demo, "MIDDLE")["items"] if i["games"])
    assert item["games"] == 1
    assert item["winrate"] == 100
