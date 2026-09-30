from collections import Counter, defaultdict

ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}


def extract_match(raw, puuid, queue):
    info = raw.get("info", {})
    # Remakes e partidas de outras filas não entram na amostra.
    if info.get("queueId") != queue or info.get("mapId") != 11 or info.get("gameDuration", 0) < 300:
        return None
    p = next((p for p in info.get("participants", []) if p.get("puuid") == puuid), None)
    if p is None:
        return None
    duration = info["gameDuration"]
    return {
        "id": raw["metadata"]["matchId"],
        "championId": p["championId"],
        "championName": p.get("championName", ""),
        "role": p.get("teamPosition", ""),
        "win": bool(p.get("win", False)),
        "kills": p.get("kills", 0),
        "deaths": p.get("deaths", 0),
        "assists": p.get("assists", 0),
        "cs": p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
        "vision": p.get("visionScore", 0),
        "damage": p.get("totalDamageDealtToChampions", 0),
        "duration": duration,
        "timestamp": info.get("gameStartTimestamp", info.get("gameCreation", 0)),
        "queue": queue,
    }


def summarize(matches):
    groups = defaultdict(list)
    for match in matches:
        groups[match["championId"]].append(match)

    def metrics(rows):
        count = len(rows)
        wins = sum(m["win"] for m in rows)
        minutes = sum(m["duration"] for m in rows) / 60
        kills = sum(m["kills"] for m in rows)
        deaths = sum(m["deaths"] for m in rows)
        assists = sum(m["assists"] for m in rows)
        return {
            "games": count,
            "wins": wins,
            "winrate": round(100 * wins / count, 1) if count else 0,
            "kda": round((kills + assists) / max(1, deaths), 2),
            "csPerMinute": round(sum(m["cs"] for m in rows) / minutes, 1) if minutes else 0,
            "visionPerMinute": round(sum(m["vision"] for m in rows) / minutes, 2) if minutes else 0,
        }

    roles = Counter(m["role"] for m in matches if m["role"] in ROLES)
    champions = [{"championId": key, **metrics(rows)} for key, rows in groups.items()]
    champions.sort(key=lambda x: (-x["games"], -x["winrate"], x["championId"]))
    return {
        **metrics(matches),
        "roles": dict(roles),
        "preferredRole": roles.most_common(1)[0][0] if roles else None,
        "champions": champions,
    }
