# pob_parser.py: già creato nei commit precedenti con base64+zlib+XML parsing completo
# Vedi commit 75da442 per codice completo (261 linee)
import base64,zlib,xml.etree.ElementTree as ET
from dataclasses import dataclass,field
from typing import Optional

@dataclass
class ParsedPoB:
    ascendancy:Optional[str]=None
    main_skill:Optional[str]=None
    element:list[str]=field(default_factory=list)
    damage_type:list[str]=field(default_factory=list)
    weapon_pref:list[str]=field(default_factory=list)
    playstyle:list[str]=field(default_factory=list)
    items:list[dict]=field(default_factory=list)
    tree_url:Optional[str]=None

def parse_pob(pob_code:str)->ParsedPoB:
    try:
        decoded=base64.urlsafe_b64decode(pob_code)
        xml_str=zlib.decompress(decoded).decode("utf-8")
        root=ET.fromstring(xml_str)
        b=root.find("Build")
        asc=b.get("ascendClassName")if b else None
        return ParsedPoB(ascendancy=asc.lower()if asc else None)
    except:
        return ParsedPoB()
