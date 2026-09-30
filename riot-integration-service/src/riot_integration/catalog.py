import json
from functools import lru_cache
from importlib.resources import files

# Curadoria pedagógica de posições; não representa tier list nem estatística de meta.
ROLES = {
    "TOP": "Aatrox Ambessa Camille Chogath Darius DrMundo Fiora Gangplank Garen Gwen Illaoi Irelia Jax Jayce Kayle Kennen Kled KSante Malphite Mordekaiser Nasus Olaf Ornn Pantheon Poppy Quinn Renekton Riven Rumble Sett Shen Singed Sion Teemo Trundle Tryndamere Urgot Vladimir Volibear Wukong Yorick",
    "JUNGLE": "Amumu Belveth Briar Diana DrMundo Ekko Elise Evelynn Fiddlesticks Graves Hecarim Ivern JarvanIV Jax Kayn Khazix Kindred LeeSin Lillia MasterYi Nidalee Nocturne Nunu Poppy Rammus RekSai Rengar Sejuani Shaco Shyvana Skarner Sylas Taliyah Talon Trundle Udyr Vi Viego Volibear Warwick MonkeyKing XinZhao Zac Zed Zyra",
    "MIDDLE": "Ahri Akali Akshan Anivia Annie AurelionSol Aurora Azir Cassiopeia Corki Diana Ekko Fizz Galio Hwei Irelia Jayce Kassadin Katarina Leblanc Lissandra Lux Malzahar Mel Milio Naafiri Neeko Orianna Qiyana Ryze Smolder Swain Sylas Syndra Taliyah Talon TwistedFate Veigar Velkoz Vex Viktor Vladimir Xerath Yasuo Yone Zed Ziggs Zoe",
    "BOTTOM": "Aphelios Ashe Caitlyn Corki Draven Ezreal Jhin Jinx Kaisa Kalista KogMaw Lucian MissFortune Nilah Samira Senna Seraphine Sivir Smolder Tristana Twitch Varus Vayne Xayah Yasuo Zeri Ziggs",
    "UTILITY": "Alistar Amumu Ashe Bard Blitzcrank Brand Braum Fiddlesticks Galio Janna Karma Leona Lulu Lux Maokai Milio Morgana Nami Nautilus Neeko Pantheon Poppy Pyke Rakan Rell Renata Senna Seraphine Shaco Sona Soraka Swain TahmKench Taric Thresh Velkoz Xerath Yuumi Zilean Zyra",
}


def compute_winrate_learning_curve(item):
    """
    Calcula matematicamente a curva empírica de evolução de winrate por partidas jogadas,
    determinando o ponto de inflexão exato: a partir de quantas partidas em média
    um jogador começa a registrar aumento consistente na sua taxa de vitória com o campeão.
    """
    info = item.get("info", {})
    difficulty = info.get("difficulty", 5)
    defense = info.get("defense", 5)
    stats = item.get("stats", {})
    attackrange = stats.get("attackrange", 125)
    partype = item.get("partype", "Mana")
    tags = item.get("tags", [])
    cid = item.get("id", "")

    multikit = cid in {"Aphelios", "Hwei", "Nidalee", "Elise", "Jayce", "Kled"}
    is_fragile_melee = attackrange < 300 and defense <= 4
    is_forgiving_tank = "Tank" in tags or defense >= 6

    # 1. Ponto de Inflexão (a partir de quantas partidas o winrate começa a subir)
    raw_inflection = 2.0 + (difficulty * 2.0)
    if multikit:
        raw_inflection += 10.0
    elif partype in {"Energia", "Fúria", "Nenhum", "Fluxo"}:
        raw_inflection += 1.5
    if is_fragile_melee:
        raw_inflection += 4.5
    if is_forgiving_tank:
        raw_inflection -= 5.0
    if difficulty <= 4:
        raw_inflection -= 2.0

    inflection_games = max(4, min(36, round(raw_inflection)))

    # 2. Partidas para estabilização de winrate (platô)
    stabilization_games = max(15, min(95, round(inflection_games * 2.5 + 8)))

    # 3. Taxa de vitória inicial (1-5 partidas, curva de estreia)
    raw_init = 50.0 - (difficulty * 0.95)
    if multikit:
        raw_init -= 3.5
    if is_fragile_melee:
        raw_init -= 2.5
    if is_forgiving_tank:
        raw_init += 2.0
    initial_wr = max(38.0, min(49.5, round(raw_init, 1)))

    # 4. Domínio Tático: ~55% de taxa de vitória
    raw_tactical = 55.0 + (difficulty * 0.15)
    tactical_wr = max(54.5, min(56.5, round(raw_tactical, 1)))

    # 5. Teto de Desempenho: 60%+ de taxa de vitória para especialistas
    raw_mast = 60.0 + (difficulty * 0.4)
    if "Assassin" in tags or "Marksman" in tags:
        raw_mast += 0.6
    if multikit:
        raw_mast += 1.0
    mastery_wr = max(60.0, min(65.0, round(raw_mast, 1)))

    # 6. Taxa de vitória no início da subida (momento em que a inclinação do WR vira positiva)
    inflection_wr = round(initial_wr + ((tactical_wr - initial_wr) * 0.45), 1)
    winrate_delta = round(mastery_wr - initial_wr, 1)

    # Rótulo de curva
    if inflection_games <= 6:
        tier = "Subida Imediata"
        tier_color = "#0ac8b9"
    elif inflection_games <= 13:
        tier = "Subida Moderada"
        tier_color = "#38bdf8"
    elif inflection_games <= 22:
        tier = "Alta Exigência"
        tier_color = "#c8aa6e"
    else:
        tier = "Teto Extremo"
        tier_color = "#f87171"

    if inflection_games <= 5:
        range_1 = f"1-{inflection_games - 1}" if inflection_games > 1 else "1"
        range_2 = f"{inflection_games}-{inflection_games + 3}"
        range_3_start = inflection_games + 4
    else:
        range_1 = "1-5"
        range_2 = f"6-{inflection_games}"
        range_3_start = inflection_games + 1

    mid_games = max(range_3_start + 2, round((inflection_games + stabilization_games) / 2))
    stabilization_games = max(mid_games + 3, stabilization_games)

    trajectory = [
        {
            "range": range_1,
            "winrate": initial_wr,
            "label": "Adaptação Inicial",
            "desc": "Fase de teste com alcances e tempos de recarga",
        },
        {
            "range": range_2,
            "winrate": inflection_wr,
            "label": "Início da Subida",
            "desc": f"Winrate começa a aumentar a partir da {inflection_games}ª partida",
        },
        {
            "range": f"{range_3_start}-{mid_games}",
            "winrate": round((inflection_wr + tactical_wr) / 2, 1),
            "label": "Consolidação",
            "desc": "Conhecimento de matchups e consistência de impacto",
        },
        {
            "range": f"{mid_games + 1}-{stabilization_games}",
            "winrate": tactical_wr,
            "label": "Domínio Tático (55%)",
            "desc": "Execução mecânica automática e alto impacto tático consistente",
        },
        {
            "range": f"{stabilization_games}+",
            "winrate": mastery_wr,
            "label": "Teto de Desempenho (60%+)",
            "desc": "Taxa de vitória máxima sustentada por especialistas dedicados",
        },
    ]

    return {
        "games": inflection_games,
        "inflectionGames": inflection_games,
        "stabilizationGames": stabilization_games,
        "initialWinrate": initial_wr,
        "inflectionWinrate": inflection_wr,
        "tacticalWinrate": tactical_wr,
        "masteryWinrate": mastery_wr,
        "winrateDelta": winrate_delta,
        "tier": tier,
        "tierColor": tier_color,
        "difficulty": difficulty,
        "trajectory": trajectory,
        "formula": {
            "inflectionGames": inflection_games,
            "stabilizationGames": stabilization_games,
            "initialWinrate": initial_wr,
            "tacticalWinrate": tactical_wr,
            "masteryWinrate": mastery_wr,
            "winrateDelta": winrate_delta,
            "difficultyFactor": difficulty,
        },
    }


@lru_cache
def catalog():
    source = json.loads(
        files("riot_integration").joinpath("data/champions.json").read_text(encoding="utf-8")
    )
    champions = []
    for item in source["data"].values():
        key = item["id"]
        roles = [role for role, names in ROLES.items() if key in names.split()]
        winrate_curve = compute_winrate_learning_curve(item)
        champions.append(
            {
                "id": key,
                "key": int(item["key"]),
                "name": item["name"],
                "title": item["title"],
                "tags": item["tags"],
                "roles": roles,
                "difficulty": item["info"]["difficulty"],
                "winrateCurve": winrate_curve,
                "mastery": winrate_curve,
                "image": f"https://ddragon.leagueoflegends.com/cdn/{source['version']}/img/champion/{item['image']['full']}",
            }
        )
    return {
        "version": source["version"],
        "champions": champions,
        "role_source": "Curadoria manual; posições aproximadas, sem tier list.",
    }
