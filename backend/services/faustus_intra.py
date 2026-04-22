"""Faustus intra-NPC arbitrage engine.

Questo modulo rileva cicli di arbitraggio usando *solo* i rate di scambio
forniti da Faustus (A→B, B→A, ...), indipendentemente dal mercato player.

L'idea è semplice:

- ogni edge A→B ha un rate `r = units_B_per_1_A`;
- costruiamo un grafo diretto con peso `-log(r)` per ogni edge;
- se esiste un ciclo con somma dei pesi < 0, il prodotto dei rate lungo il
  ciclo è > 1 → arbitraggio teorico (round trip profittevole nella valuta
  di partenza).

Questo rieusa la stessa tecnica di Bellman-Ford già usata nel motore
chaos-bridge, ma si applica a una matrice di rate fornita dall'NPC.

Nota: l'engine è puro (no I/O, no DB). Il chiamante è responsabile di
raccogliere i rate reali di Faustus e trasformarli in `FaustusRate`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FaustusRate:
    """Rate diretto A→B di Faustus.

    `rate` è quante unità di `target_trade_id` ottieni scambiando 1 unità di
    `source_trade_id` presso l'NPC.
    """

    source_trade_id: str
    target_trade_id: str
    rate: float  # units of target per 1 unit of source


@dataclass(frozen=True)
class FaustusCycle:
    """Un ciclo di arbitraggio intra-Faustus.

    `path` è la sequenza ciclica di trade_id (primo == ultimo).
    `step_rates[i]` è il rate applicato per passare da path[i] a path[i+1].
    """

    path: tuple[str, ...]
    profit_pct: float
    step_rates: tuple[float, ...]

    @property
    def length(self) -> int:
        """Numero di hop (len(path) - 1, perché il ciclo chiude su sé stesso)."""

        return len(self.path) - 1


@dataclass
class _Edge:
    """Arco del grafo per Bellman-Ford.

    Separato dalla dataclass pubblica per poter essere mutato internamente.
    """

    source: str
    target: str
    weight: float  # = -log(rate)
    rate: float


def _detect_negative_cycle(
    nodes: list[str], edges: list[_Edge]
) -> Optional[tuple[str, dict[str, Optional[str]]]]:
    """Bellman-Ford con sorgente virtuale per rilevare cicli negativi.

    Ritorna `(start_node, predecessor_map)` se un ciclo negativo esiste,
    altrimenti None.
    """

    dist: dict[str, float] = {n: 0.0 for n in nodes}
    pred: dict[str, Optional[str]] = {n: None for n in nodes}

    # |V|-1 rilassamenti standard.
    for _ in range(len(nodes) - 1):
        updated = False
        for e in edges:
            new_d = dist[e.source] + e.weight
            if new_d < dist[e.target]:
                dist[e.target] = new_d
                pred[e.target] = e.source
                updated = True
        if not updated:
            return None  # nessun ciclo negativo

    # Pass addizionale: se c'è ancora un arco rilassabile, siamo dopo un ciclo negativo.
    for e in edges:
        if dist[e.source] + e.weight < dist[e.target]:
            return e.target, pred
    return None


def _extract_cycle(start: str, pred: dict[str, Optional[str]]) -> list[str]:
    """Dalla predecessor map, estrae il ciclo che contiene `start`.

    Tecnica classica: fai |V| step all'indietro per "cadere" dentro il ciclo,
    poi cammini finché non ritorni al nodo di partenza.
    """

    v = start
    for _ in range(len(pred)):
        prev = pred[v]
        if prev is None:
            break
        v = prev

    cycle = [v]
    u = pred[v]
    while u is not None and u != v:
        cycle.append(u)
        u = pred[u]
    cycle.append(v)
    cycle.reverse()
    return cycle


def find_faustus_cycles(
    rates: Iterable[FaustusRate],
    *,
    min_profit_pct: float = 1.0,
    max_cycles: int = 20,
) -> list[FaustusCycle]:
    """Trova cicli di arbitraggio intra-Faustus.

    Args:
        rates: lista di rate diretti A→B dell'NPC.
        min_profit_pct: scarta cicli con profit < X%.
        max_cycles: limite di sicurezza sul numero di cicli da riportare.

    Returns:
        Lista di `FaustusCycle` ordinati per profit decrescente.
    """

    rates_list = list(rates)
    if not rates_list:
        return []

    # Nodi = unione di tutte le currency viste come sorgente o target.
    nodes = sorted({r.source_trade_id for r in rates_list} | {r.target_trade_id for r in rates_list})

    # Costruisci gli archi con peso -log(rate).
    edges: list[_Edge] = []
    for r in rates_list:
        if r.rate <= 0:
            continue
        edges.append(
            _Edge(
                source=r.source_trade_id,
                target=r.target_trade_id,
                weight=-math.log(r.rate),
                rate=r.rate,
            )
        )

    if not edges:
        return []

    edges_by_key: dict[tuple[str, str], _Edge] = {
        (e.source, e.target): e for e in edges
    }

    found: list[FaustusCycle] = []
    remaining_edges = edges.copy()

    for _ in range(max_cycles):
        result = _detect_negative_cycle(nodes, remaining_edges)
        if result is None:
            break
        start, pred = result
        path = _extract_cycle(start, pred)
        if len(path) < 3:  # almeno 2 hop A→B→A
            break

        # Ricostruisci i rate lungo il path.
        step_rates: list[float] = []
        valid = True
        for i in range(len(path) - 1):
            edge = edges_by_key.get((path[i], path[i + 1]))
            if edge is None:
                valid = False
                break
            step_rates.append(edge.rate)
        if not valid:
            break

        product = 1.0
        for r in step_rates:
            product *= r
        profit_pct = (product - 1.0) * 100.0

        if profit_pct >= min_profit_pct:
            found.append(
                FaustusCycle(
                    path=tuple(path),
                    profit_pct=profit_pct,
                    step_rates=tuple(step_rates),
                )
            )

        # Rimuovi l'arco "più debole" del ciclo e ri-cerca altri cicli distinti.
        weakest_idx = max(
            range(len(path) - 1),
            key=lambda i: edges_by_key[(path[i], path[i + 1])].weight,
        )
        weakest_key = (path[weakest_idx], path[weakest_idx + 1])
        remaining_edges = [
            e for e in remaining_edges if (e.source, e.target) != weakest_key
        ]

    found.sort(key=lambda c: c.profit_pct, reverse=True)
    return found
