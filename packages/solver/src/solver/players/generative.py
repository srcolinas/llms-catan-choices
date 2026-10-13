from __future__ import annotations

import json
import random

import pydantic
import pydantic_ai
from pydantic_ai.models import Model

from simulation import Board, Edge, PriorPlacement, Vertex
from solver.dataset import board_record
from solver.players.calls import CallLog, timed
from solver.settings import Settings


class Coordinate(pydantic.BaseModel):
    q: int
    r: int
    index: int = pydantic.Field(ge=0, le=5)


class Placement(pydantic.BaseModel):
    vertex: Coordinate
    edge: Coordinate


class GenerativePlayer:
    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> None:
        del rng
        self.kind = "generative"
        self.name = settings.llm_model
        self._model: Model | str = settings.llm_model
        self._heuristics = settings.heuristics.read_text()
        self._agent: pydantic_ai.Agent[None, Placement] | None = None
        self._calls = CallLog()

    def choose(
        self,
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[PriorPlacement],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        self._calls.start_turn(errors)
        with timed(self._calls):
            result = self._agent_for(board).run_sync(
                user_message(available, prior, errors)
            )
        choice = result.output
        placed = (
            Vertex(choice.vertex.q, choice.vertex.r, choice.vertex.index),
            Edge(choice.edge.q, choice.edge.r, choice.edge.index),
        )
        self._calls.end_turn()
        return placed

    def accepted_calls(self, count: int) -> list[dict[str, int] | None]:
        return self._calls.finish(count)

    def _agent_for(self, board: Board) -> pydantic_ai.Agent[None, Placement]:
        if self._agent is None:
            self._agent = pydantic_ai.Agent(
                self._model,
                output_type=Placement,
                instructions=instructions(board, self._heuristics),
            )
        return self._agent


def instructions(board: Board, heuristics: str) -> str:
    board_json = json.dumps(board_record(board), indent=2)
    return (
        "You are choosing a settlement and a connected road during Catan setup.\n\n"
        "Heuristics:\n"
        f"{heuristics.strip()}\n\n"
        "Board:\n"
        f"{board_json}"
    )


def user_message(
    available: list[tuple[Vertex, Edge]],
    prior: list[PriorPlacement],
    errors: list[str],
) -> str:
    options = [
        {"vertex": _coordinate(vertex), "edge": _coordinate(edge)}
        for vertex, edge in available
    ]
    lines = [
        "Choose one legal settlement vertex and the road edge connected to it.",
        "Return that vertex and edge.",
        "Prior placements in chronological order:",
        json.dumps(
            [
                {
                    "seat": seat,
                    "vertex": _coordinate(vertex),
                    "edge": _coordinate(edge),
                }
                for seat, vertex, edge in prior
            ]
        ),
        "Options:",
        json.dumps(options),
    ]
    if errors:
        lines.append("Earlier choices were rejected:")
        lines.extend(errors)
    return "\n".join(lines)


def _coordinate(point: Vertex | Edge) -> dict[str, int]:
    return {"q": point.q, "r": point.r, "index": point.index}
