"""Intent tagger IT/EN per FOB.

Parsing keyword-based della query utente:
- element   : cold, fire, lightning, chaos, physical
- damage_type: spell, attack, dot, minion, slam
- weapon_pref: bow, 2h_mace, 1h, wand, staff, claw, dagger
- playstyle  : mapping, bossing, tanky, aoe, fast, dot, melee, ranged
- ascendancy : Occultist, Juggernaut, Raider, ...
- budget_div : float estratto da "20 div" / "medio" / "alto"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntentTags:
    element: list[str] = field(default_factory=list)
    damage_type: list[str] = field(default_factory=list)
    weapon_pref: list[str] = field(default_factory=list)
    playstyle: list[str] = field(default_factory=list)
    ascendancy: list[str] = field(default_factory=list)
    budget_div: Optional[float] = None
    content_target: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Budget testuale -> div approssimativo
# ---------------------------------------------------------------------------
_BUDGET_TEXT = {
    "bassissimo": 5.0, "povero": 5.0, "scarso": 5.0, "zero": 3.0,
    "basso": 10.0, "low": 10.0, "economico": 10.0, "cheap": 10.0,
    "medio": 25.0, "medium": 25.0, "mid": 25.0,
    "medio-alto": 40.0, "medio alto": 40.0,
    "alto": 60.0, "high": 60.0, "caro": 60.0, "expensive": 60.0,
    "altissimo": 100.0, "very high": 100.0, "meta": 100.0,
    "illimitato": 200.0, "no budget": 200.0, "no limits": 200.0,
}


class IntentTagger:
    """Tagger keyword-based per query PoE in italiano e inglese."""

    def tag(self, description: str) -> IntentTags:
        t = description.lower()
        tags = IntentTags()

        # ------------------------------------------------------------------
        # ELEMENT
        # ------------------------------------------------------------------
        if any(k in t for k in [
            "ghiaccio", "gelo", "cold", "ice", "frost", "freeze",
            "congela", "ghiaccia", "glacial",
        ]):
            tags.element.append("cold")

        if any(k in t for k in [
            "fuoco", "fiamma", "fire", "flame", "burn", "ignite",
            "brucia", "incendia", "combustion",
        ]):
            tags.element.append("fire")

        if any(k in t for k in [
            "fulmine", "fulmina", "fulmin", "elettrico", "lampo",
            "lightning", "shock", "thunder", "electr",
        ]):
            tags.element.append("lightning")
            if "lightning" not in tags.damage_type and "spell" not in tags.damage_type:
                tags.damage_type.append("lightning")

        if any(k in t for k in [
            "caos", "veleno", "chaos", "poison", "corrupt",
        ]):
            tags.element.append("chaos")

        if any(k in t for k in [
            "fisico", "physical", "phys",
        ]):
            tags.element.append("physical")

        # ------------------------------------------------------------------
        # DAMAGE TYPE
        # ------------------------------------------------------------------
        if any(k in t for k in [
            "spell", "magia", "incantesimo", "cast", "caster",
            "fulmin", "lightning", "ghiaccia", "ice nova", "fireball",
        ]):
            if "spell" not in tags.damage_type:
                tags.damage_type.append("spell")

        if any(k in t for k in [
            "attack", "attacco", "hit", "strike", "colpo",
            "slam", "slamm", "martell", "mace",
        ]):
            if "attack" not in tags.damage_type:
                tags.damage_type.append("attack")

        if any(k in t for k in [
            "dot", "damage over time", "degen", "veleno",
            "poison", "burn", "rf", "righteous fire",
            "toxic", "bleed", "sanguina",
        ]):
            if "dot" not in tags.damage_type:
                tags.damage_type.append("dot")

        if any(k in t for k in [
            "minion", "minioni", "zombie", "golem",
            "skeleton", "scheletro", "spettro", "spectre",
        ]):
            if "minion" not in tags.damage_type:
                tags.damage_type.append("minion")

        if any(k in t for k in [
            "slam", "slamm", "martellone", "earthquake",
            "ground slam", "warchief",
        ]):
            if "slam" not in tags.damage_type:
                tags.damage_type.append("slam")

        # ------------------------------------------------------------------
        # WEAPON PREF
        # ------------------------------------------------------------------
        if any(k in t for k in ["martellone", "2h mace", "mace", "maul", "mazza"]):
            tags.weapon_pref.append("2h_mace")
        if any(k in t for k in ["arco", "bow", "frecce"]):
            tags.weapon_pref.append("bow")
        if any(k in t for k in ["bacchetta", "wand"]):
            tags.weapon_pref.append("wand")
        if any(k in t for k in ["bastone", "staff"]):
            tags.weapon_pref.append("staff")
        if any(k in t for k in ["artiglio", "claw"]):
            tags.weapon_pref.append("claw")
        if any(k in t for k in ["pugnale", "dagger"]):
            tags.weapon_pref.append("dagger")

        # ------------------------------------------------------------------
        # PLAYSTYLE
        # ------------------------------------------------------------------
        if any(k in t for k in [
            "mapping", "farm", "mappe", "mappa", "maps",
            "veloce in mappa", "clear speed",
        ]):
            tags.playstyle.append("mapping")

        if any(k in t for k in [
            "boss", "bossing", "uber", "pinnacle", "endgame boss",
            "uccidere boss", "kill boss",
        ]):
            tags.playstyle.append("bossing")

        if any(k in t for k in [
            "tanky", "tank", "sopravvivenza", "survivability",
            "immortal", "non muoio", "tough", "resistente",
        ]):
            tags.playstyle.append("tanky")

        if any(k in t for k in [
            "aoe", "area", "schermo", "screen", "tutto lo schermo",
            "clearspeed", "clear",
        ]):
            tags.playstyle.append("aoe")

        if any(k in t for k in [
            "veloce", "fast", "speed", "rapido", "movimento",
        ]):
            tags.playstyle.append("fast")

        if any(k in t for k in [
            "melee", "corpo a corpo", "cac", "mischia",
        ]):
            tags.playstyle.append("melee")

        if any(k in t for k in [
            "ranged", "distanza", "a distanza",
        ]):
            tags.playstyle.append("ranged")

        # ------------------------------------------------------------------
        # ASCENDANCY hints
        # ------------------------------------------------------------------
        asc_hints = {
            "occultist": "Occultist",
            "juggernaut": "Juggernaut", "jug": "Juggernaut",
            "raider": "Raider",
            "pathfinder": "Pathfinder",
            "elementalist": "Elementalist",
            "champion": "Champion",
            "gladiator": "Gladiator",
            "berserker": "Berserker",
            "slayer": "Slayer",
            "necromancer": "Necromancer",
            "inquisitor": "Inquisitor",
            "hierophant": "Hierophant",
            "guardian": "Guardian",
            "deadeye": "Deadeye",
            "trickster": "Trickster",
            "saboteur": "Saboteur",
            "assassin": "Assassin",
            "chieftain": "Chieftain",
            "warden": "Warden",
        }
        for kw, asc in asc_hints.items():
            if kw in t:
                tags.ascendancy.append(asc)

        # ------------------------------------------------------------------
        # BUDGET
        # ------------------------------------------------------------------
        # 1) numero esplicito: "20 div", "50divine"
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:div|divine|divini)", t)
        if m:
            tags.budget_div = float(m.group(1).replace(",", "."))
        else:
            # 2) testo: "budget medio", "medio-alto", ecc.
            for phrase, val in _BUDGET_TEXT.items():
                if phrase in t:
                    tags.budget_div = val
                    break

        return tags
