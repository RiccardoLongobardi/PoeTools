"""Ranking engine: score-a build dalla cache contro i tag di intent."""
from __future__ import annotations

from typing import Any


def score_build(build: dict, tags: dict) -> tuple[float, dict]:
    """
    Ritorna (score, match_detail) dove match_detail spiega su cosa ha matchato.
    Tags atteso: {element, damage_type, playstyle, weapon_pref, ascendancy, budget_div}
    """
    score = 0.0
    detail: dict[str, Any] = {}
    build_tags = build.get("tags", {})

    # Element match (+2)
    q_elem = tags.get("element", [])
    b_elem = build_tags.get("element", [])
    elem_hits = [e for e in q_elem if e in b_elem]
    if elem_hits:
        score += 2.0 * len(elem_hits)
        detail["element"] = elem_hits

    # Damage type match (+2)
    q_dmg = tags.get("damage_type", [])
    b_dmg = build_tags.get("damage_type", [])
    dmg_hits = [d for d in q_dmg if d in b_dmg]
    if dmg_hits:
        score += 2.0 * len(dmg_hits)
        detail["damage_type"] = dmg_hits

    # Playstyle match (+1.5)
    q_style = tags.get("playstyle", [])
    b_style = build_tags.get("playstyle", [])
    style_hits = [p for p in q_style if p in b_style]
    if style_hits:
        score += 1.5 * len(style_hits)
        detail["playstyle"] = style_hits

    # Weapon pref match (+1)
    q_wpn = tags.get("weapon_pref", [])
    b_wpn = build_tags.get("weapon_pref", [])
    wpn_hits = [w for w in q_wpn if w in b_wpn]
    if wpn_hits:
        score += 1.0 * len(wpn_hits)
        detail["weapon_pref"] = wpn_hits

    # Ascendancy match (+3 — forte segnale)
    q_asc = tags.get("ascendancy", [])
    b_asc = build.get("ascendancy", "")
    if q_asc and b_asc and b_asc in q_asc:
        score += 3.0
        detail["ascendancy"] = b_asc

    # Popularity boost (ladder rank) — bonus leggero
    rank = build.get("signals", {}).get("popularity_rank")
    if isinstance(rank, int) and rank <= 50:
        score += max(0.0, (50 - rank) / 50)  # max +1.0 per rank 1
        detail["popularity_boost"] = round((50 - rank) / 50, 2)

    return round(score, 3), detail


def rank_builds(
    builds: list[dict],
    tags: dict,
    category: str | None = None,
    top_n: int = 10,
) -> list[dict]:
    """
    Filtra per category se specificata, applica score, ritorna top N.
    Ogni item output ha campi extra: score, match_detail.
    """
    filtered = [b for b in builds if category is None or b.get("category") == category]
    scored = []
    for b in filtered:
        score, detail = score_build(b, tags)
        scored.append({**b, "score": score, "match_detail": detail})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]
