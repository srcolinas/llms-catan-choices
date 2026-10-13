from __future__ import annotations

import json
import logging
import random
from typing import Annotated, Any, Literal

import pydantic
import pydantic_ai
from pydantic_ai.models import Model
from pydantic_ai.models.system_one import SystemOneModel
from pydantic_ai.profiles.decision import DecisionModelProfile
from typesafe_sdk import JSONContent

from simulation import Board, Edge, PriorPlacement, Vertex
from solver.players.calls import CallLog, timed
from solver.players.jev import placement_criteria, placement_state
from solver.settings import Settings

_LOGGER = logging.getLogger(__name__)


class SystemOnePlayer:
    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> None:
        del rng
        if settings.system_one_max_options < 2:
            raise ValueError(
                "system_one_max_options must be at least 2, "
                f"got {settings.system_one_max_options}"
            )
        self.kind = "system-one"
        self.name = settings.llm_model
        self._max_options = settings.system_one_max_options
        self._instructions = instructions(settings.heuristics.read_text())
        self._model: Model | None = None
        self._calls = CallLog()

    def choose(
        self,
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[PriorPlacement],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        self._calls.start_turn(errors)
        criteria, options = placement_criteria(board, available)
        keys = list(criteria)
        prompt = judged(board, prior, errors)
        # A decision model accepts a limited number of options, so pick a winner
        # from each group and compare those winners until one remains.
        while len(keys) > self._max_options:
            winners: list[str] = []
            for start in range(0, len(keys), self._max_options):
                chunk = keys[start : start + self._max_options]
                if len(chunk) == 1:
                    winners.append(chunk[0])
                else:
                    winners.append(self._ask(chunk, criteria, prompt))
            keys = winners
        key = keys[0] if len(keys) == 1 else self._ask(keys, criteria, prompt)
        choice = options[key]
        self._calls.end_turn()
        return choice

    def accepted_calls(self, count: int) -> list[dict[str, int] | None]:
        return self._calls.finish(count)

    def _ask(
        self,
        keys: list[str],
        criteria: dict[str, JSONContent],
        prompt: str,
    ) -> str:
        subset = {key: criteria[key] for key in keys}
        agent: pydantic_ai.Agent[None, Any] = pydantic_ai.Agent(
            self._model_for(),
            output_type=_choice_model(subset),
            instructions=self._instructions,
        )
        _LOGGER.debug(f"Asking system-one model {self.name} for {subset}")
        try:
            with timed(self._calls):
                result = agent.run_sync(prompt)
        except Exception as e:
            _LOGGER.error(f"Error asking system-one model {self.name}: {e}")
            raise
        _LOGGER.debug(f"Result: {result}")
        key = _placement_key(result.output)
        if key not in subset:
            raise ValueError(f"unknown placement option {key!r}")
        return key

    def _model_for(self) -> Model:
        if self._model is None:
            self._model = SystemOneModel(
                self.name,
                profile=DecisionModelProfile(
                    decision_max_choice_options=self._max_options,
                    decision_max_score_levels=self._max_options,
                ),
            )
        return self._model


def instructions(heuristics: str) -> str:
    return (
        "You are choosing a settlement and a connected road during Catan setup.\n"
        "Choose the offered placement that best follows the heuristics.\n\n"
        "Heuristics:\n"
        f"{heuristics.strip()}"
    )


def judged(
    board: Board,
    prior: list[PriorPlacement],
    errors: list[str],
) -> str:
    state = placement_state(board, "", prior, errors)
    del state["heuristics"]
    return json.dumps(state)


def _choice_model(criteria: dict[str, JSONContent]) -> type[pydantic.BaseModel]:
    options = [
        Annotated[Literal[key], pydantic.Field(description=json.dumps(value))]
        for key, value in criteria.items()
    ]
    placement: Any = options[0]
    for option in options[1:]:
        placement |= option
    return pydantic.create_model(
        "PlacementChoice",
        __doc__="Choose the settlement and road that best follows the heuristics.",
        placement=(placement, pydantic.Field(description="One offered placement.")),
    )


def _placement_key(output: object) -> str:
    key = getattr(output, "placement", None)
    if not isinstance(key, str):
        raise TypeError(f"expected a placement choice, got {output!r}")
    return key
