"""Adapter: Maxroll.gg build guides (HTML scraping, fragile — adapter isolato)."""
from __future__ import annotations

import hashlib
import logging
import re

import httpx
from bs4 import BeautifulSoup

from backend.datasource.adapters.base import BuildAdapter, BuildRecord

logger = logging.getLogger(__name__)

MAXROLL_INDEX_URL = "https://maxroll.gg/poe/build-guides"
USER_AGENT = "PoeTools/FOBOracle (contact: github.com/RiccardoLongobardi/PoeTools)"


class MaxrollAdapter(BuildAdapter):
    source_name = "maxroll"

    async def fetch(self, league: str, limit: int = 50) -> list[BuildRecord]:
        headers = {"User-Agent": USER_AGENT}
        records: list[BuildRecord] = []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(MAXROLL_INDEX_URL, headers=headers)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            logger.warning("Maxroll fetch failed: %s", exc)
            return []

        try:
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("a[href*='/poe/build-guides/']")[:limit]
            for card in cards:
                href = card.get("href", "")
                title = card.get_text(separator=" ", strip=True)
                if not title or not href:
                    continue
                url = f"https://maxroll.gg{href}" if href.startswith("/") else href
                slug = href.rstrip("/").split("/")[-1]
                build_id = hashlib.md5(f"maxroll:{slug}".encode()).hexdigest()[:12]

                rec = BuildRecord(
                    id=build_id,
                    league=league,
                    source="maxroll",
                    category="guide",
                    name=title,
                    url=url,
                    guide={"summary": "", "pros": [], "cons": [], "levelling": [], "gear": [], "notes": ""},
                    raw={"raw_text": title, "raw_html": ""},
                    signals={"is_ladder_build": False, "is_guide_build": True, "confidence": 0.5, "popularity_rank": None},
                )
                records.append(rec)
        except Exception as exc:
            logger.warning("Maxroll parse failed: %s", exc)

        logger.info("Maxroll: %d records fetched", len(records))
        return records
