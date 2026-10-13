from __future__ import annotations

import json
import logging
import random
from collections.abc import Sequence
from typing import Protocol

from openai import OpenAI
from openai.types.decision import AnswerAnswerResourceChoice, Decision
from openai.types.decision_create_params import Question

from simulation import Board, Edge, PriorPlacement, Vertex
from solver.players.calls import CallLog, timed
from solver.players.jev import placement_criteria
from solver.players.system_one import instructions, judged
from solver.settings import Settings

_MAX_CHOICES = 255

_LOGGER = logging.getLogger(__name__)


class _DecisionsAPI(Protocol):
    def create(
        self,
        *,
        input: str,
        model: str,
        questions: Sequence[Question],
    ) -> Decision: ...


class _DecisionClient(Protocol):
    @property
    def decisions(self) -> _DecisionsAPI: ...


class OpenAIDecisionPlayer:
    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
        *,
        client: _DecisionClient | None = None,
    ) -> None:
        del rng
        self.kind = "openai-decision"
        self.name = settings.openai_decision_model
        self._instructions = instructions(settings.heuristics.read_text())
        self._client = client
        self._calls = CallLog()

    def choose(
        self,
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[PriorPlacement],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        self._calls.start_turn(errors)
        if len(available) > _MAX_CHOICES:
            raise ValueError(
                f"choice accepts at most {_MAX_CHOICES} options, got {len(available)}"
            )
        if len(available) == 1:
            choice = available[0]
        else:
            criteria, options = placement_criteria(board, available)
            _LOGGER.debug(f"Asking openai decision model {self.name} for {criteria}")
            try:
                with timed(self._calls):
                    decision = self._client_for().decisions.create(
                        model=self.name,
                        input=judged(board, prior, errors),
                        questions=[
                            {
                                "type": "choice",
                                "name": "placement",
                                "instructions": self._instructions,
                                "choices": [
                                    {"value": key, "description": json.dumps(value)}
                                    for key, value in criteria.items()
                                ],
                            }
                        ],
                    )
            except Exception as e:
                _LOGGER.error(f"Error asking openai decision model {self.name}: {e}")
                raise
            _LOGGER.debug(f"Decision: {decision}")
            key = _placement_choice(decision)
            choice = options[key]
        self._calls.end_turn()
        return choice

    def accepted_calls(self, count: int) -> list[dict[str, int] | None]:
        return self._calls.finish(count)

    def _client_for(self) -> _DecisionClient:
        if self._client is None:
            self._client = OpenAI()
        return self._client


def _placement_choice(decision: Decision) -> str:
    for answer in decision.answers:
        if answer.name != "placement":
            continue
        if answer.type == "refusal":
            raise ValueError("decision refused placement")
        if not isinstance(answer, AnswerAnswerResourceChoice):
            raise TypeError(f"expected a choice answer, got {answer.type}")
        choice = answer.choice
        if isinstance(choice, str):
            return choice
        raise ValueError(f"unknown placement option {choice!r}")
    raise ValueError("decision response did not include a placement answer")
