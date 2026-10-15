from __future__ import annotations

import random

from simulation import Board, Edge, PriorPlacement, Vertex
from solver.players.human import active_table, game_seed
from solver.settings import Settings


class RandomPlayer:
    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
    ) -> None:
        self.kind = "random"
        self.name = "random"
        self._seat: int | None = None
        self._rng = random.Random((rng or random.Random()).getrandbits(64))

    def bind_seat(self, seat: int) -> None:
        self._seat = seat

    def choose(
        self,
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[PriorPlacement],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, prior, errors
        table = active_table()
        seed = game_seed.get()
        if table is not None and seed is not None:
            table.note_waiting_random(seed)
        choice = self._rng.choice(available)
        if table is not None and seed is not None and self._seat is not None:
            table.note_placement(seed, self._seat, choice[0], choice[1], self.kind)
        return choice
