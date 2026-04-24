"""Base adapter interface per tutte le fonti build."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BuildRecord:
    """Schema unico build per la cache."""
    id: str
    league: str
    source: str                          # ladder | pobbin | maxroll | mobalytics
    category: str                        # meta | guide
    name: str
    url: Optional[str] = None
    author: Optional[str] = None
    ascendancy: Optional[str] = None
    class_name: Optional[str] = None
    main_skill: Optional[str] = None
    tags: dict = field(default_factory=lambda: {
        "element": [], "damage_type": [], "playstyle": [], "weapon_pref": []
    })
    guide: dict = field(default_factory=lambda: {
        "summary": "", "pros": [], "cons": [], "levelling": [], "gear": [], "notes": ""
    })
    raw: dict = field(default_factory=lambda: {"raw_text": "", "raw_html": ""})
    signals: dict = field(default_factory=lambda: {
        "is_ladder_build": False,
        "is_guide_build": False,
        "confidence": 0.0,
        "popularity_rank": None,
    })

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "league": self.league,
            "source": self.source,
            "category": self.category,
            "name": self.name,
            "url": self.url,
            "author": self.author,
            "ascendancy": self.ascendancy,
            "class_name": self.class_name,
            "main_skill": self.main_skill,
            "tags": self.tags,
            "guide": self.guide,
            "raw": self.raw,
            "signals": self.signals,
        }


class BuildAdapter(ABC):
    """Interfaccia comune per tutti gli adapter."""

    source_name: str = "unknown"

    @abstractmethod
    async def fetch(self, league: str, limit: int = 100) -> list[BuildRecord]:
        """Fetcha e normalizza build dalla fonte. Deve sempre restituire lista (vuota se errore)."""
        ...
