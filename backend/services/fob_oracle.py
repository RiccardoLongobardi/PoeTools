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
