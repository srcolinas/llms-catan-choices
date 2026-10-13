from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

from typesafe_sdk import Choice, JSONContent, TypeSafeClient

from simulation import Board, Edge, PriorPlacement, Vertex
from solver.dataset import board_record
from solver.players.calls import CallLog, timed
from solver.settings import Settings

Ask = Callable[[dict[str, Any], dict[str, JSONContent]], str]


class JevPlayer:
    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> None:
        del rng
        self.kind = "jev"
        self.name = settings.llm_model
        self._heuristics = settings.heuristics.read_text()
        self._calls = CallLog()

    def choose(
        self,
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[PriorPlacement],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        self._calls.start_turn(errors)
        if len(available) > 255:
            raise ValueError(
                f"choice accepts at most 255 options, got {len(available)}"
            )
        state = placement_state(board, self._heuristics, prior, errors)
        criteria, options = placement_criteria(board, available)
        key = self._ask_typesafe(state, criteria)
        try:
            choice = options[key]
        except KeyError as err:
            raise ValueError(f"unknown placement option {key!r}") from err
        self._calls.end_turn()
        return choice

    def accepted_calls(self, count: int) -> list[dict[str, int] | None]:
        return self._calls.finish(count)

    def _ask_typesafe(
        self,
        state: dict[str, Any],
        criteria: dict[str, JSONContent],
    ) -> str:
        with TypeSafeClient() as client, timed(self._calls):
            response = client.system_one(
                model=self.name,
                state=state,
                questions={
                    "placement": Choice(
                        instructions=(
                            "Choose the settlement vertex and the road edge connected to it "
                            "that best follows the heuristics."
                        ),
                        criteria=criteria,
                    ),
                },
            )
        return response.choices["placement"].choice


def placement_state(
    board: Board,
    heuristics: str,
    prior: list[PriorPlacement],
    errors: list[str],
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "heuristics": heuristics.strip(),
        "board": board_record(board),
        "prior_placements": [
            {
                "seat": seat,
                "vertex": _coordinate(vertex),
                "edge": _coordinate(edge),
            }
            for seat, vertex, edge in prior
        ],
    }
    if errors:
        state["rejected_choices"] = errors
    return state


def placement_criteria(
    board: Board,
    available: list[tuple[Vertex, Edge]],
) -> tuple[dict[str, JSONContent], dict[str, tuple[Vertex, Edge]]]:
    harbours = _harbours_by_vertex(board)
    criteria: dict[str, JSONContent] = {}
    options: dict[str, tuple[Vertex, Edge]] = {}
    for offset, (vertex, edge) in enumerate(available):
        key = f"o{offset}"
        option: dict[str, JSONContent] = {
            "vertex": _coordinate(vertex),
            "edge": _coordinate(edge),
            "resources": _resources(board, vertex),
        }
        kind = harbours.get(_corner(vertex))
        if kind is not None:
            option["harbour"] = kind
        criteria[key] = option
        options[key] = (vertex, edge)
    return criteria, options


def _harbours_by_vertex(board: Board) -> dict[frozenset[tuple[int, int]], str]:
    harbours: dict[frozenset[tuple[int, int]], str] = {}
    for harbour in board.harbours:
        for vertex in harbour.edge.vertices():
            harbours[_corner(vertex)] = harbour.kind
    return harbours


def _corner(vertex: Vertex) -> frozenset[tuple[int, int]]:
    return frozenset((item.q, item.r) for item in vertex.hexes())


def _resources(board: Board, vertex: Vertex) -> list[dict[str, int | str]]:
    tiles = {(tile.q, tile.r): tile for tile in board.tiles}
    desert = (board.desert.q, board.desert.r)
    described: list[dict[str, int | str]] = []
    for item in vertex.hexes():
        tile = tiles.get((item.q, item.r))
        if tile is not None:
            described.append({"terrain": tile.terrain, "number": tile.number})
        elif (item.q, item.r) == desert:
            described.append({"terrain": "desert"})
        else:
            described.append({"terrain": "water"})
    return described


def _coordinate(point: Vertex | Edge) -> dict[str, int]:
    return {"q": point.q, "r": point.r, "index": point.index}
