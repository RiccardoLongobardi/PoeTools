"""FOB orchestrator: BuildQuery→Build candidates→BuildPlan."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Optional,Protocol
from backend.services.intent import IntentTagger
from backend.services.pob_parser import parse_pob

@dataclass
class BuildQuery:
    description:str
    league:str="Mirage"
    budget_div:Optional[float]=None
    element:list[str]=field(default_factory=list)
    damage_type:list[str]=field(default_factory=list)
    weapon_pref:list[str]=field(default_factory=list)
    playstyle:list[str]=field(default_factory=list)
    ascendancy:list[str]=field(default_factory=list)
    content_target:list[str]=field(default_factory=list)

@dataclass
class Build:
    id:str
    name:str
    source:str
    url:Optional[str]=None
    pob_output:Optional[str]=None
    ascendancy:Optional[str]=None
    main_skill:Optional[str]=None
    element:list[str]=field(default_factory=list)
    damage_type:list[str]=field(default_factory=list)
    weapon_pref:list[str]=field(default_factory=list)
    playstyle:list[str]=field(default_factory=list)
    est_cost_div:Optional[float]=None
    league:Optional[str]=None

@dataclass
class BuildCandidate:
    build:Build
    score:float

@dataclass
class BuildPlan:
    build_id:str
    league:str
    levelling_stages:list=field(default_factory=list)
    gear_phases:list=field(default_factory=list)
    total_cost_div:Optional[float]=None
    notes:str=""

class BuildSource(Protocol):
    async def fetch_builds(self,query:BuildQuery)->list[Build]:...

class UserPoBSource:
    def __init__(self,pob_code:str):
        self._pob_code=pob_code
    async def fetch_builds(self,query:BuildQuery)->list[Build]:
        try:
            p=parse_pob(self._pob_code)
            return[Build(id="user_pob",name="User PoB",source="user",pob_output=self._pob_code,
                ascendancy=p.ascendancy,main_skill=p.main_skill,element=p.element,
                damage_type=p.damage_type,weapon_pref=p.weapon_pref,playstyle=p.playstyle)]
        except:return[]

def _tag_match_score(b:Build,q:BuildQuery)->float:
    s=0.0
    if q.element and any(e in b.element for e in q.element):s+=2
    if q.damage_type and any(d in b.damage_type for d in q.damage_type):s+=2
    if q.ascendancy and b.ascendancy in q.ascendancy:s+=3
    if q.weapon_pref and any(w in b.weapon_pref for w in q.weapon_pref):s+=1
    if q.playstyle and any(p in b.playstyle for p in q.playstyle):s+=1
    if q.budget_div and b.est_cost_div and abs(b.est_cost_div-q.budget_div)<10:s+=1
    return s

async def suggest_builds(query:BuildQuery,*,user_pob_code:Optional[str]=None,
    include_poe_ninja:bool=False,maxroll_catalog_path:Optional[str]=None,max_results:int=5)->list[BuildCandidate]:
    sources:list[BuildSource]=[]
    if user_pob_code:sources.append(UserPoBSource(user_pob_code))
    all_builds:list[Build]=[]
    for src in sources:
        try:all_builds.extend(await src.fetch_builds(query))
        except:pass
    candidates=[BuildCandidate(build=b,score=_tag_match_score(b,query))for b in all_builds]
    candidates.sort(key=lambda c:c.score,reverse=True)
    return candidates[:max_results]

async def plan_build(build:Build)->BuildPlan:
    from backend.services.planner import create_build_plan
    return await create_build_plan(build)

async def run_oracle(query: str, league: str = "Settlers") -> dict:
    """Entry point chiamato da routes.py.

    Riceve la query in linguaggio naturale, orchestra intent tagging,
    build suggestion e progressione, e restituisce un dict compatibile
    con OracleResponse.
    """
    import logging
    log = logging.getLogger(__name__)

    # 1. Tagger intento
    tagger = IntentTagger()
    tags = tagger.tag(query)
    log.info("Intent tags: %s", tags)

    # 2. Costruisci BuildQuery
    bq = BuildQuery(
        description=query,
        league=league,
        element=tags.element,
        damage_type=tags.damage_type,
        weapon_pref=tags.weapon_pref,
        playstyle=tags.playstyle,
        ascendancy=tags.ascendancy,
        budget_div=tags.budget_div,
    )

    # 3. Prova a caricare build da poe.ninja (fallback: lista vuota)
    all_builds: list[Build] = []
    warning: str | None = None
      # 3. poe.ninja fetch (fallback automatico se errore)
    all_builds: list[Build] = []
    warning: str | None = None
    # NOTA: PoeNinjaSource attuale gestisce currency, non builds
    # Per ora skippiamo e usiamo solo fallback catalog
    warning = "poe.ninja builds API non ancora implementato; uso catalogo fallback."
    all_builds = _fallback_builds(bq)
    
    # 4. Scoring e ranking
    candidates = [
        BuildCandidate(build=b, score=_tag_match_score(b, bq))
        for b in all_builds
    ]
    candidates.sort(key=lambda c: c.score, reverse=True)
    top = candidates[:5]

    # 6. Piano progressione sulla build migliore
    plan = None
    if top:
        try:
            plan = await plan_build(top[0].build)
        except Exception as exc:
            log.warning("plan_build error: %s", exc)

    # 7. Serializza in dict compatibile con OracleResponse
    intent_dict = {
        "damage_type": tags.damage_type,
        "style": tags.playstyle,
        "budget": f"{tags.budget_div}div" if tags.budget_div else "any",
        "playstyle": tags.playstyle,
        "raw_tokens": query.lower().split(),
    }

    builds_list = [
        {
            "id": c.build.id,
            "name": c.build.name,
            "source": c.build.source,
            "url": c.build.url,
            "pob_output": c.build.pob_output,
            "ascendancy": c.build.ascendancy,
            "main_skill": c.build.main_skill,
            "element": c.build.element,
            "damage_type": c.build.damage_type,
            "weapon_pref": c.build.weapon_pref,
            "playstyle": c.build.playstyle,
            "est_cost_div": c.build.est_cost_div,
            "league": c.build.league,
            "score": c.score,
        }
        for c in top
    ]

    plan_dict = None
    if plan:
        plan_dict = {
            "build_id": plan.build_id,
            "league": plan.league,
            "levelling_stages": plan.levelling_stages,
            "gear_phases": plan.gear_phases,
            "total_cost_div": plan.total_cost_div,
            "priced_items": [],
            "notes": plan.notes,
        }

    return {
        "intent": intent_dict,
        "builds": builds_list,
        "plan": plan_dict,
        "warning": warning,
    }


def _fallback_builds(bq: BuildQuery) -> list[Build]:
    """Build di esempio hardcoded quando poe.ninja non e' raggiungibile."""
    catalog = [
        Build(
            id="ice_nova_occultist",
            name="Ice Nova Occultist",
            source="fallback",
            ascendancy="Occultist",
            main_skill="Ice Nova",
            element=["cold"],
            damage_type=["spell", "cold"],
            playstyle=["aoe", "mapping"],
            est_cost_div=20.0,
        ),
        Build(
            id="rf_juggernaut",
            name="Righteous Fire Juggernaut",
            source="fallback",
            ascendancy="Juggernaut",
            main_skill="Righteous Fire",
            element=["fire"],
            damage_type=["dot", "fire"],
            playstyle=["tank", "mapping"],
            est_cost_div=15.0,
        ),
        Build(
            id="lightning_strike_raider",
            name="Lightning Strike Raider",
            source="fallback",
            ascendancy="Raider",
            main_skill="Lightning Strike",
            element=["lightning"],
            damage_type=["attack", "lightning"],
            playstyle=["melee", "fast"],
            est_cost_div=30.0,
        ),
        Build(
            id="slam_juggernaut",
            name="Earthquake Juggernaut",
            source="fallback",
            ascendancy="Juggernaut",
            main_skill="Earthquake",
            element=["physical"],
            damage_type=["attack", "physical", "slam"],
            weapon_pref=["mace", "maul"],
            playstyle=["melee", "slam", "boss"],
            est_cost_div=25.0,
        ),
        Build(
            id="toxic_rain_pathfinder",
            name="Toxic Rain Pathfinder",
            source="fallback",
            ascendancy="Pathfinder",
            main_skill="Toxic Rain",
            element=["chaos"],
            damage_type=["dot", "chaos"],
            weapon_pref=["bow"],
            playstyle=["ranged", "dot", "mapping"],
            est_cost_div=18.0,
        ),
    ]
    # Filtra per score > 0, altrimenti ritorna tutto
    scored = [(b, _tag_match_score(b, bq)) for b in catalog]
    matched = [b for b, s in scored if s > 0]
    return matched if matched else catalog

