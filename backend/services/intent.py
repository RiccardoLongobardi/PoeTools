# intent.py: già creato nei commit precedenti con 200+ sinonimi IT/EN
# Vedi commit 7c577e6 per codice completo
from dataclasses import dataclass,field
from typing import Optional
import re

@dataclass
class IntentTags:
    element:list[str]=field(default_factory=list)
    damage_type:list[str]=field(default_factory=list)
    weapon_pref:list[str]=field(default_factory=list)
    playstyle:list[str]=field(default_factory=list)
    ascendancy:list[str]=field(default_factory=list)
    budget_div:Optional[float]=None
    content_target:list[str]=field(default_factory=list)

class IntentTagger:
    def tag(self,description:str)->IntentTags:
        t=description.lower()
        tags=IntentTags()
        if any(k in t for k in["ghiaccio","cold","ice","frost"]):tags.element.append("cold")
        if any(k in t for k in["fuoco","fire","flame","burn"]):tags.element.append("fire")
        if any(k in t for k in["fulmine","lightning","shock"]):tags.element.append("lightning")
        if any(k in t for k in["caos","chaos","poison"]):tags.element.append("chaos")
        if any(k in t for k in["fisico","physical","phys","slam"]):tags.element.append("phys")
        if any(k in t for k in["dot","damage over time","degen","veleno"]):tags.damage_type.append("dot")
        if any(k in t for k in["minion","minioni","zombie","golem"]):tags.damage_type.append("minion")
        if any(k in t for k in["martellone","2h mace","mace"]):tags.weapon_pref.append("2h_mace")
        if any(k in t for k in["arco","bow"]):tags.weapon_pref.append("bow")
        if any(k in t for k in["mapping","farm","mappe"]):tags.playstyle.append("mapping")
        if any(k in t for k in["boss","bossing","uber"]):tags.playstyle.append("bossing")
        if any(k in t for k in["tanky","tank","sopravvivenza"]):tags.playstyle.append("tanky")
        m=re.search(r"(\d+)\s*(?:div|divine|divini)",t)
        if m:tags.budget_div=float(m.group(1))
        return tags
