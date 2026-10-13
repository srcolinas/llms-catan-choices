# /// script
# requires-python = ">=3.12"
# dependencies = ["simulation"]
#
# [tool.uv.sources]
# simulation = { path = "../packages/simulation" }
# ///

"""Count legal Catan setup drafts.

A draft is an ordered sequence of town-and-road placements under the distance
rule. Tile numbers, terrain, and harbours do not change which placements are
legal, so every board seed has the same count.
"""

from __future__ import annotations

import argparse
from time import perf_counter

from simulation import Board, Edge

# mask -> (settlement sequences, settlement-and-road drafts)
Layer = dict[int, tuple[int, int]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Count legal Catan setup drafts")
    parser.add_argument(
        "--players",
        type=int,
        choices=(3, 4),
        help="Count only this table size. The default counts 3 and 4.",
    )
    args = parser.parse_args()
    closed, degrees = board_graph()
    count_drafts(closed, degrees, args.players)


def board_graph() -> tuple[list[int], list[int]]:
    """Closed neighborhood and degree of each vertex, in a stable order."""
    board = Board.from_seed(0)
    hexes = [(tile.q, tile.r) for tile in board.tiles]
    hexes.append((board.desert.q, board.desert.r))

    neighbors: dict[tuple[int, int, int], set[tuple[int, int, int]]] = {}
    for q, r in hexes:
        for index in range(6):
            first, second = Edge(q, r, index).vertices()
            left = (first.q, first.r, first.index)
            right = (second.q, second.r, second.index)
            neighbors.setdefault(left, set()).add(right)
            neighbors.setdefault(right, set()).add(left)

    vertices = sorted(neighbors)
    index_of = {vertex: index for index, vertex in enumerate(vertices)}
    closed: list[int] = []
    degrees: list[int] = []
    for vertex in vertices:
        adjacent = neighbors[vertex]
        mask = 1 << index_of[vertex]
        for neighbor in adjacent:
            mask |= 1 << index_of[neighbor]
        closed.append(mask)
        degrees.append(len(adjacent))

    if len(closed) != 54:
        raise RuntimeError(f"expected 54 vertices, found {len(closed)}")
    openings = sum(degrees)
    if openings != 144:
        raise RuntimeError(f"expected 144 opening pairs, found {openings}")
    if any(degree not in (2, 3) for degree in degrees):
        raise RuntimeError("every vertex must have degree 2 or 3")
    return closed, degrees


def count_drafts(closed: list[int], degrees: list[int], players: int | None) -> None:
    """Print the draft tree ply by ply, then the requested table totals."""
    layer: Layer = {0: (1, 1)}
    for ply in range(1, 7):
        started = perf_counter()
        layer = _extend(layer, closed, degrees)
        sequences, drafts = _totals(layer)
        _report_ply(ply, len(layer), sequences, drafts, perf_counter() - started)

    if players in (None, 3):
        sequences, drafts = _totals(layer)
        print(f"3 players: sequences={sequences} drafts={drafts}", flush=True)

    if players in (None, 4):
        started = perf_counter()
        ply7_sequences, ply7_drafts, ply8_sequences, ply8_drafts = _finish(
            layer, closed, degrees
        )
        elapsed = perf_counter() - started
        _report_ply(7, None, ply7_sequences, ply7_drafts, None)
        _report_ply(8, None, ply8_sequences, ply8_drafts, elapsed)
        print(f"4 players: sequences={ply8_sequences} drafts={ply8_drafts}", flush=True)


def _extend(layer: Layer, closed: list[int], degrees: list[int]) -> Layer:
    """One more settlement. Roads multiply by the vertex degree.

    A placed road's endpoints are both forbidden by the distance rule, so a
    later legal vertex still has every incident edge available.
    """
    nxt: Layer = {}
    for mask, (sequences, drafts) in layer.items():
        for index, neighborhood in enumerate(closed):
            if mask & (1 << index):
                continue
            updated = mask | neighborhood
            added_drafts = drafts * degrees[index]
            previous = nxt.get(updated)
            if previous is None:
                nxt[updated] = (sequences, added_drafts)
            else:
                nxt[updated] = (previous[0] + sequences, previous[1] + added_drafts)
    return nxt


def _finish(
    layer: Layer,
    closed: list[int],
    degrees: list[int],
) -> tuple[int, int, int, int]:
    """Count plies 7 and 8 from the ply-6 masks without storing them."""
    vertex_count = len(closed)
    full = (1 << vertex_count) - 1
    degree_two = 0
    degree_three = 0
    for index, degree in enumerate(degrees):
        if degree == 2:
            degree_two |= 1 << index
        else:
            degree_three |= 1 << index

    ply7_sequences = 0
    ply7_drafts = 0
    ply8_sequences = 0
    ply8_drafts = 0
    for mask, (sequences, drafts) in layer.items():
        for index, neighborhood in enumerate(closed):
            if mask & (1 << index):
                continue
            blocked = mask | neighborhood
            free = full ^ blocked
            ply7_sequences += sequences
            ply7_drafts += drafts * degrees[index]
            ply8_sequences += sequences * free.bit_count()
            road_choices = (
                2 * (free & degree_two).bit_count()
                + 3 * (free & degree_three).bit_count()
            )
            ply8_drafts += drafts * degrees[index] * road_choices
    return ply7_sequences, ply7_drafts, ply8_sequences, ply8_drafts


def _totals(layer: Layer) -> tuple[int, int]:
    sequences = 0
    drafts = 0
    for count, weight in layer.values():
        sequences += count
        drafts += weight
    return sequences, drafts


def _report_ply(
    ply: int,
    states: int | None,
    sequences: int,
    drafts: int,
    seconds: float | None,
) -> None:
    parts = [f"ply {ply}:"]
    if states is not None:
        parts.append(f"states={states}")
    parts.append(f"sequences={sequences}")
    parts.append(f"drafts={drafts}")
    if seconds is not None:
        parts.append(f"seconds={seconds:.3f}")
    print(" ".join(parts), flush=True)


if __name__ == "__main__":
    main()
