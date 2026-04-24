"""CLI entry point per refresh manuale della cache.

Uso:
    python -m backend.jobs.refresh_builds --league Mirage
    python -m backend.jobs.refresh_builds --league Mirage --sources ladder pobbin
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="FOB Cache Refresh CLI")
    parser.add_argument("--league", default="Mirage", help="League name (default: Mirage)")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Sources da refreshare (default: tutte). Es: ladder pobbin maxroll",
    )
    parser.add_argument("--limit", type=int, default=100, help="Limite record per source")
    args = parser.parse_args()

    from backend.services.refresh_service import refresh_cache

    print(f"[FOB] Refresh cache — league={args.league} sources={args.sources or 'all'} limit={args.limit}")
    report = asyncio.run(refresh_cache(
        league=args.league,
        sources=args.sources,
        limit_per_source=args.limit,
    ))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    warnings = [s for s, v in report["sources"].items() if v["status"] == "error"]
    if warnings:
        print(f"\n[WARNING] Source fallite: {', '.join(warnings)}", file=sys.stderr)
    print(f"\n[OK] +{report['new_builds_added']} build aggiunte. Totale: {report['total_builds']}")


if __name__ == "__main__":
    main()
