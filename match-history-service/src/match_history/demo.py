from datetime import datetime, timezone

from match_history.stats import summarize


def demo_analysis(catalog):
    champions = [
        (103, "Ahri", "MIDDLE"),
        (61, "Orianna", "MIDDLE"),
        (134, "Syndra", "MIDDLE"),
        (99, "Lux", "UTILITY"),
        (22, "Ashe", "BOTTOM"),
    ]
    matches = []
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    for i in range(20):
        cid, name, role = champions[i % 5 if i % 4 == 0 else i % 3]
        matches.append(
            {
                "id": f"DEMO_{i:02}",
                "championId": cid,
                "championName": name,
                "role": role,
                "win": i % 5 < 3,
                "kills": 4 + i % 8,
                "deaths": 2 + i % 5,
                "assists": 5 + i % 9,
                "cs": 130 + i * 5,
                "vision": 12 + i,
                "damage": 14000 + i * 700,
                "duration": 1600 + i * 30,
                "timestamp": now - i * 3600000,
                "queue": 420,
            }
        )
    return {
        "id": "demo",
        "account": {"gameName": "Invocador", "tagLine": "DEMO", "profileIconId": 588},
        "region": "americas",
        "queue": 420,
        "requested": 20,
        "fetched": 20,
        "skipped": 0,
        "demo": True,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "matches": matches,
        "stats": summarize(matches),
        "catalog": catalog,
    }
