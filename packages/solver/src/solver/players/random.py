from __future__ import annotations

import random

from simulation import Board, Edge, PriorPlacement, Vertex
from solver.settings import Settings


class RandomPlayer:
    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> None:
        self.kind = "random"
        self.name = "random"
        self._rng = random.Random((rng or random.Random()).getrandbits(64))

    def choose(
        self,
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[PriorPlacement],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, prior, errors
        return self._rng.choice(available)
