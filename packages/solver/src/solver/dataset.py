from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TypeGuard

from simulation import Board, Edge, Harbour, Report, Tile, Vertex


def recorded_name(kind: str, player: str) -> str:
    """Label stored for a seat. Model ids stay on the player; this is the record."""
    if kind == "generative":
        return f"{player.rsplit(':', 1)[-1]}(generative)"
    if kind == "openai-decision":
        return f"{player.rsplit(':', 1)[-1]}(decision)"
    return player


def game_line(
    seed: int,
    board: Board,
    players: Sequence[tuple[str, str]],
    report: Report,
    calls: Sequence[Sequence[dict[str, Any] | None]] | None = None,
) -> str:
    if calls is None:
        calls = [
            [None] * sum(slot is not None for slot in seat)
            for seat in report.placements
        ]
    choices = [
        _seat_choices(kind, name, slots, seat_calls)
        for (kind, name), slots, seat_calls in zip(
            players, report.placements, calls, strict=True
        )
    ]
    ok = bool(choices) and all(
        choice is not None for seat in choices for choice in seat
    )
    row: dict[str, Any] = {
        "seed": seed,
        "ok": ok,
        "board": board_record(board),
        "choices": choices,
    }
    if not ok:
        row["error"] = _draft_error(report)
    return json.dumps(row)


def failure_line(seed: int, seats: int, error: str) -> str:
    """A row for a seed whose worker raised before the draft returned."""
    row = {
        "seed": seed,
        "ok": False,
        "error": error,
        "board": board_record(Board.from_seed(seed)),
        "choices": [[None, None] for _ in range(seats)],
    }
    return json.dumps(row)


def completed_seeds(path: Path) -> set[int]:
    """Seeds that already have a successful row in ``path``.

    ``ok: true`` counts. Rows written before that field existed count when
    every placement slot is filled, using the non-empty line index as the seed.
    Any successful row for a seed is enough, so an earlier failure stays in the
    file without hiding a later success. Missing files and unreadable lines
    contribute no seeds.
    """
    if not path.is_file():
        return set()
    done: set[int] = set()
    for index, line in enumerate(_nonempty_lines(path)):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        raw_seed = row.get("seed", index)
        seed = raw_seed if _is_seed(raw_seed) else index
        if _row_succeeded(row):
            done.add(seed)
    return done


def pending_seeds(path: Path, count: int) -> list[int]:
    """Seeds in ``0 .. count - 1`` that do not yet have a successful row."""
    done = completed_seeds(path)
    return [seed for seed in range(count) if seed not in done]


def write_lines(lines: Iterable[str], output: Path) -> None:
    _emit_lines(lines, output, truncate=True)


def append_lines(lines: Iterable[str], output: Path) -> None:
    _emit_lines(lines, output, truncate=False)


def _emit_lines(lines: Iterable[str], output: Path, *, truncate: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w" if truncate else "a") as file:
        for line in lines:
            file.write(line)
            file.write("\n")
            file.flush()


def _draft_error(report: Report) -> str:
    messages = [message for seat in report.errors for message in seat if message]
    if not messages:
        return "draft stopped before every settlement was placed"
    return "; ".join(messages)


def _nonempty_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


def _is_seed(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _row_succeeded(row: dict[Any, Any]) -> bool:
    if "ok" in row:
        return row["ok"] is True
    choices = row.get("choices")
    if not isinstance(choices, list) or not choices:
        return False
    return all(_seat_filled(seat) for seat in choices)


def _seat_filled(seat: object) -> bool:
    return (
        isinstance(seat, list)
        and bool(seat)
        and all(choice is not None for choice in seat)
    )


def board_record(board: Board) -> dict[str, Any]:
    return {
        "tiles": [_tile_record(tile) for tile in board.tiles],
        "desert": {"q": board.desert.q, "r": board.desert.r},
        "harbours": [_harbour_record(harbour) for harbour in board.harbours],
    }


def _tile_record(tile: Tile) -> dict[str, int | str]:
    return {
        "q": tile.q,
        "r": tile.r,
        "number": tile.number,
        "terrain": tile.terrain,
    }


def _harbour_record(harbour: Harbour) -> dict[str, Any]:
    return {"edge": _coordinate(harbour.edge), "kind": harbour.kind}


def _seat_choices(
    kind: str,
    player: str,
    seat: tuple[tuple[Vertex, Edge] | None, tuple[Vertex, Edge] | None],
    calls: Sequence[dict[str, Any] | None],
) -> list[dict[str, Any] | None]:
    recorded: list[dict[str, Any] | None] = []
    pending = iter(calls)
    for slot in seat:
        if slot is None:
            recorded.append(None)
            continue
        recorded.append(_placement_record(kind, player, slot, next(pending, None)))
    return recorded


def _placement_record(
    kind: str,
    player: str,
    slot: tuple[Vertex, Edge],
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    vertex, edge = slot
    record = {
        "kind": kind,
        "player": recorded_name(kind, player),
        "vertex": _coordinate(vertex),
        "edge": _coordinate(edge),
    }
    if metadata is not None:
        record["metadata"] = metadata
    return record


def _coordinate(point: Vertex | Edge) -> dict[str, int]:
    return {"q": point.q, "r": point.r, "index": point.index}
