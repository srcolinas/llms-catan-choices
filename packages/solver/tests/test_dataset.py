import json
from pathlib import Path

import pytest
from solver.__main__ import play
from solver.dataset import (
    append_lines,
    completed_seeds,
    game_line,
    pending_seeds,
    recorded_name,
    write_lines,
)
from solver.settings import Settings

from simulation import Board, Edge, RandomPlayer, Simulator, Vertex

ROSTER = ["random", "random", "random", "random"]


def test_write_lines_flushes_each_line(tmp_path: Path) -> None:
    output = tmp_path / "choices.jsonl"
    seen: list[str] = []

    def lines():
        yield "one"
        seen.append(output.read_text())
        yield "two"

    write_lines(lines(), output)
    assert seen == ["one\n"]
    assert output.read_text() == "one\ntwo\n"


def test_recorded_name_marks_how_the_model_chose() -> None:
    assert (
        recorded_name("generative", "gateway/openai:gpt-6-luna")
        == "gpt-6-luna(generative)"
    )
    assert recorded_name("openai-decision", "gpt-6-luna") == "gpt-6-luna(decision)"
    assert recorded_name("jev", "jev-latest") == "jev-latest"
    assert recorded_name("system-one", "nimble") == "nimble"
    assert recorded_name("random", "random") == "random"


def test_dataset_schema_and_replay(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "choices.jsonl"
    loaded = Settings(llm_model="test:model", heuristics=tmp_path / "heuristics.md")
    write_lines(play(range(2), ROSTER, loaded), output)
    first = output.read_text()
    write_lines(play(range(2), ROSTER, loaded), output)
    assert output.read_text() == first

    rows = [json.loads(line) for line in first.splitlines()]
    assert len(rows) == 2
    assert all(set(row) == {"seed", "ok", "board", "choices"} for row in rows)
    assert [(row["seed"], row["ok"]) for row in rows] == [(0, True), (1, True)]
    assert rows[0]["board"] != rows[1]["board"]
    for row in rows:
        board = row["board"]
        assert len(board["tiles"]) == 18
        assert set(board["desert"]) == {"q", "r"}
        assert len(board["harbours"]) == 9
        assert len(row["choices"]) == 4
        for seat in row["choices"]:
            assert len(seat) == 2
            for choice in seat:
                assert choice["kind"] == "random"
                assert choice["player"] == "random"
                assert "metadata" not in choice
                assert set(choice["vertex"]) == {"q", "r", "index"}
                assert set(choice["edge"]) == {"q", "r", "index"}


def test_unfinished_draft_writes_null_slots() -> None:
    def stop(
        board: Board,
        available: list[tuple[Vertex, Edge]],
        prior: list[tuple[int, Vertex, Edge]],
        errors: list[str],
    ) -> tuple[Vertex, Edge]:
        del board, available, prior, errors
        raise RuntimeError("stop")

    board = Board.from_seed(1)
    report = Simulator(board, [stop, stop, stop]).simulate(1)
    row = json.loads(
        game_line(
            1,
            board,
            [
                ("generative", "gateway/model"),
                ("random", "random"),
                ("random", "random"),
            ],
            report,
        )
    )
    assert row["seed"] == 1
    assert row["ok"] is False
    assert row["error"] == "stop"
    assert row["choices"] == [[None, None], [None, None], [None, None]]


def test_game_line_records_call_metadata() -> None:
    board = Board.from_seed(1)
    report = Simulator(
        board,
        [
            RandomPlayer.from_seed(1),
            RandomPlayer.from_seed(2),
            RandomPlayer.from_seed(3),
        ],
    ).simulate(1)
    row = json.loads(
        game_line(
            1,
            board,
            [
                ("generative", "gateway/openai:gpt-6-luna"),
                ("random", "random"),
                ("random", "random"),
            ],
            report,
            [
                [{"latency_ms": 842}, None],
                [None, None],
                [None, None],
            ],
        )
    )
    assert row["seed"] == 1
    assert row["ok"] is True
    assert "error" not in row
    first, second = row["choices"][0]
    assert first["metadata"] == {"latency_ms": 842}
    assert first["player"] == "gpt-6-luna(generative)"
    assert "metadata" not in second
    for seat in row["choices"][1:]:
        for choice in seat:
            assert choice["player"] == "random"
            assert "metadata" not in choice


def test_append_lines_keeps_existing_rows_and_flushes(tmp_path: Path) -> None:
    output = tmp_path / "choices.jsonl"
    output.write_text("kept\n")
    seen: list[str] = []

    def lines():
        yield "added"
        seen.append(output.read_text())

    append_lines(lines(), output)
    assert seen == ["kept\nadded\n"]
    assert output.read_text() == "kept\nadded\n"


def test_completed_seeds_uses_ok_and_legacy_rows(tmp_path: Path) -> None:
    path = tmp_path / "choices.jsonl"
    filled = {"choices": [[{"kind": "random"}, {"kind": "random"}]]}
    partial = {"choices": [[{"kind": "random"}, None]]}
    marked = {"seed": 4, "ok": True, "choices": [[None, None]]}
    failed = {"seed": 5, "ok": False, "error": "rate limit"}
    path.write_text(
        "\n".join(
            [
                json.dumps(filled),
                json.dumps(partial),
                "{truncated",
                json.dumps(marked),
                json.dumps(failed),
                "",
            ]
        )
        + "\n"
    )
    assert completed_seeds(path) == {0, 4}
    assert pending_seeds(path, 6) == [1, 2, 3, 5]
    assert completed_seeds(tmp_path / "missing.jsonl") == set()


def test_resume_appends_only_missing_seeds(tmp_path: Path) -> None:
    output = tmp_path / "choices.jsonl"
    loaded = Settings(llm_model="test:model", heuristics=tmp_path / "heuristics.md")
    finished = next(play([0], ROSTER, loaded))
    failed = {
        "seed": 1,
        "ok": False,
        "error": "rate limit",
        "board": json.loads(finished)["board"],
        "choices": [[None, None], [None, None], [None, None], [None, None]],
    }
    output.write_text(finished + "\n" + json.dumps(failed) + "\n")
    before = output.read_text()

    pending = pending_seeds(output, 3)
    assert pending == [1, 2]
    append_lines(play(pending, ROSTER, loaded), output)

    text = output.read_text()
    assert text.startswith(before)
    rows = [json.loads(line) for line in text.splitlines()]
    assert [(row["seed"], row["ok"]) for row in rows] == [
        (0, True),
        (1, False),
        (1, True),
        (2, True),
    ]
    assert rows[0] == json.loads(finished)
    assert pending_seeds(output, 3) == []
    unchanged = output.read_text()
    append_lines(play(pending_seeds(output, 3), ROSTER, loaded), output)
    assert output.read_text() == unchanged


def test_worker_exception_still_yields_other_seeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import solver.__main__ as entry

    real = entry.Board.from_seed

    def flaky(seed: int) -> Board:
        if seed == 1:
            raise RuntimeError("rate limit")
        return real(seed)

    monkeypatch.setattr(
        entry,
        "Board",
        type("FlakyBoard", (), {"from_seed": staticmethod(flaky)}),
    )
    loaded = Settings(llm_model="test:model", heuristics=tmp_path / "heuristics.md")
    rows = [json.loads(line) for line in play([0, 1, 2], ROSTER, loaded, workers=2)]
    assert [row["seed"] for row in rows] == [0, 1, 2]
    assert rows[0]["ok"] is True
    assert rows[1]["ok"] is False
    assert rows[1]["error"] == "rate limit"
    assert rows[1]["choices"] == [[None, None]] * 4
    assert rows[2]["ok"] is True
