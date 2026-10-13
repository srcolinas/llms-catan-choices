from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from simulation import Board, Edge, RandomPlayer, Report, Simulator, Vertex

if TYPE_CHECKING:
    from simulation import Chooser, Player


def test_vertex_hexes_match_the_origin_corner() -> None:
    hexes = sorted((item.q, item.r) for item in Vertex(0, 0, 0).hexes())
    assert hexes == [(0, -1), (0, 0), (1, -1)]


def test_edge_vertices_are_the_clockwise_endpoints() -> None:
    first, second = Edge(0, 0, 0).vertices()
    assert (first.q, first.r, first.index) == (0, -1, 2)
    assert (second.q, second.r, second.index) == (0, 0, 1)


def test_random_draft() -> None:
    board = Board.from_seed(1)
    players = [RandomPlayer.from_seed(seat) for seat in range(4)]
    report = Simulator(board, players).simulate(1)
    assert report.errors == [[], [], [], []]
    assert len(report.placements) == 4
    assert all(slot is not None for seat in report.placements for slot in seat)


def test_callable_mixed_with_random_player() -> None:
    def first(
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[tuple[int, Vertex, Edge]],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, prior, errors
        return available[0]

    report = play(2, first)
    assert report.errors == [[], [], []]
    assert all(slot is not None for seat in report.placements for slot in seat)


def test_choose_method_is_a_player() -> None:
    class Picker:
        def choose(
            self,
            board: Board,
            available: list[tuple[Vertex, Edge]],
            prior: list[tuple[int, Vertex, Edge]],
            errors: list[str],
        ) -> tuple[Vertex, Edge]:
            del board, prior, errors
            return available[0]

    report = play(2, Picker())
    assert report.errors == [[], [], []]


def test_choose_receives_prior_placements_in_draft_order() -> None:
    seen: list[list[tuple[int, Vertex, Edge]]] = []

    def first(
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[tuple[int, Vertex, Edge]],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, errors
        seen.append(list(prior))
        return available[0]

    report = play(2, first)

    assert len(seen) == 2
    assert seen[0] == []
    assert [seat for seat, _, _ in seen[1]] == [0, 1, 2, 2, 1]
    assert seen[1][0][1:] == report.placements[0][0]


def test_illegal_choice_is_corrected() -> None:
    seen: list[list[str]] = []

    def player(
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[tuple[int, Vertex, Edge]],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, prior
        seen.append(list(errors))
        if not errors:
            return (Vertex(5, 5, 0), Edge(9, 9, 3))
        return available[0]

    report = play(3, player)
    assert len(report.errors[0]) == 1
    assert "not on the board" in report.errors[0][0]
    assert seen[1] == report.errors[0]
    assert report.placements[0][0] is not None


def test_bad_return_is_counted() -> None:
    def player(
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[tuple[int, Vertex, Edge]],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, prior
        if not errors:
            return cast(tuple[Vertex, Edge], "nope")
        return available[0]

    report = play(4, player)
    assert len(report.errors[0]) == 1
    assert report.errors[0][0]
    assert report.placements[0][0] is not None


def test_exception_is_retried() -> None:
    def player(
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[tuple[int, Vertex, Edge]],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, prior
        if not errors:
            raise ValueError("bad choice")
        return available[0]

    report = play(5, player)
    assert report.errors[0] == ["bad choice"]
    assert report.placements[0][0] is not None


def test_player_count_must_be_three_or_four() -> None:
    with pytest.raises(ValueError, match="expected 3 or 4 players"):
        Simulator(Board.from_seed(0), [RandomPlayer.from_seed(0)])


def test_board_exposes_tiles_desert_and_harbours() -> None:
    board = Board.from_seed(0)
    assert len(board.tiles) == 18
    assert {tile.terrain for tile in board.tiles} == {
        "forest",
        "pasture",
        "fields",
        "hills",
        "mountains",
    }
    assert isinstance(board.desert.q, int)
    assert len(board.harbours) == 9
    assert "generic" in {harbour.kind for harbour in board.harbours}


def play(seed: int, first: RandomPlayer | Player | Chooser) -> Report:
    players = [first, RandomPlayer.from_seed(1), RandomPlayer.from_seed(2)]
    return Simulator(Board.from_seed(seed), players).simulate(2)
