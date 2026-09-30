from collections import Counter

ROLE_NAMES = {
    "TOP": "Topo",
    "JUNGLE": "Selva",
    "MIDDLE": "Meio",
    "BOTTOM": "Atirador",
    "UTILITY": "Suporte",
}
VERSION = "affinity-v1"


def recommend(analysis, role="ALL"):
    catalog = analysis["catalog"]["champions"]
    by_id = {c["key"]: c for c in catalog}
    rows = [m for m in analysis["matches"] if role == "ALL" or m["role"] == role]
    if not rows:
        return {
            "items": [],
            "sampleSize": 0,
            "role": role,
            "version": VERSION,
            "explanation": "Sem partidas nesta posição. Escolha outra posição ou amplie a amostra.",
        }
    roles = Counter(m["role"] for m in rows if m["role"] in ROLE_NAMES)
    tags = Counter()
    for m in rows:
        for tag in by_id.get(m["championId"], {}).get("tags", []):
            tags[tag] += 1
    max_tag = max(tags.values(), default=1)
    items = []
    for champion in catalog:
        if not champion["roles"] or (role != "ALL" and role not in champion["roles"]):
            continue
        personal = [m for m in rows if m["championId"] == champion["key"]]
        games = len(personal)
        wins = sum(m["win"] for m in personal)
        # Prior Beta(2,2): reduz a influência de 1 vitória em 1 partida.
        adjusted_wr = (wins + 2) / (games + 4)
        kda = sum(m["kills"] + m["assists"] for m in personal) / max(
            1, sum(m["deaths"] for m in personal)
        )
        role_affinity = 1 if role != "ALL" else sum(roles[r] for r in champion["roles"]) / len(rows)
        style = sum(tags[t] / max_tag for t in champion["tags"]) / max(1, len(champion["tags"]))
        # Confiabilidade limita também o peso do KDA em amostras pequenas.
        reliability = games / (games + 4)
        performance = 0.7 * adjusted_wr + 0.3 * (0.5 + reliability * (min(kda / 5, 1) - 0.5))
        score = round(100 * (0.45 * role_affinity + 0.25 * style + 0.30 * performance), 1)
        preferred = max(champion["roles"], key=lambda r: roles[r])
        reasons = [f"Compatível com {ROLE_NAMES[role if role != 'ALL' else preferred]}."]
        if style > 0:
            reasons.append("Classes semelhantes às dos campeões da sua amostra.")
        if games:
            reasons.append(
                f"{wins} vitórias em {games} partidas; resultado suavizado para reduzir efeito de amostras pequenas."
            )
        else:
            reasons.append(
                "Novo na amostra: sugestão por posição e classe, sem desempenho pessoal observado."
            )
        items.append(
            {
                "champion": champion,
                "score": score,
                "games": games,
                "winrate": round(100 * wins / games, 1) if games else None,
                "kda": round(kda, 2) if games else None,
                "confidence": "moderada" if games >= 10 else "baixa",
                "kind": "known" if games else "explore",
                "reasons": reasons,
                "components": {
                    "role": round(45 * role_affinity, 1),
                    "style": round(25 * style, 1),
                    "performance": round(30 * performance, 1),
                },
            }
        )
    items.sort(key=lambda c: (-c["score"], -c["games"], c["champion"]["name"]))
    return {
        "items": items,
        "sampleSize": len(rows),
        "role": role,
        "version": VERSION,
        "explanation": "Afinidade combina posição (45%), classes jogadas (25%) e desempenho suavizado (30%). É uma heurística, não uma probabilidade de vitória nem uma tier list.",
    }
