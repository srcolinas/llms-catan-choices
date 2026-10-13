import json
from pathlib import Path

import pytest
from solver.view import (
    PAGE,
    attach_evaluations,
    latency_histograms,
    load_directory,
    load_evaluations,
    load_games,
    performance_by_metric,
    performance_by_seat,
    render_page,
)


def _placement(seat: int, which: int, player: str = "random") -> dict[str, object]:
    return {
        "kind": "random" if player == "random" else "generative",
        "player": player,
        "vertex": {"q": seat, "r": which, "index": 0},
        "edge": {"q": seat, "r": which, "index": 1},
    }


def _choices_row(
    players: tuple[str, str, str, str] = ("random", "random", "random", "random"),
) -> dict[str, object]:
    return {
        "board": {"tiles": [], "desert": {"q": 0, "r": 0}, "harbours": []},
        "choices": [
            [_placement(seat, 0, player), _placement(seat, 1, player)]
            for seat, player in enumerate(players)
        ],
    }


def test_load_games_attaches_snake_steps(tmp_path: Path) -> None:
    row = _choices_row()
    path = tmp_path / "choices.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for _ in range(2)))

    games = load_games(path)

    assert len(games) == 2
    for game in games:
        assert [step["seat"] for step in game["steps"]] == [0, 1, 2, 3, 3, 2, 1, 0]
        used = [0, 0, 0, 0]
        for step in game["steps"]:
            seat = step["seat"]
            expected = game["choices"][seat][used[seat]]
            used[seat] += 1
            assert step["vertex"] == expected["vertex"]
            assert step["edge"] == expected["edge"]
            assert step["kind"] == expected["kind"]
            assert step["player"] == expected["player"]
            assert step["placement"] == used[seat]


def test_attach_evaluations_merges_by_line(tmp_path: Path) -> None:
    choices_path = tmp_path / "choices.jsonl"
    eval_path = tmp_path / "evaluation.jsonl"
    choices_path.write_text(
        "".join(json.dumps(_choices_row()) + "\n" for _ in range(2))
    )
    evaluations = [
        {
            "players": ["random", "random", "random", "random"],
            "metrics": {
                "resource_combos": [True, False, True, False],
                "diversity": [True, True, False, False],
            },
        },
        {
            "players": ["gateway/model", "random", "random", "random"],
            "metrics": {
                "resource_combos": [False, True, False, True],
                "diversity": [False, False, True, True],
            },
        },
    ]
    eval_path.write_text("".join(json.dumps(row) + "\n" for row in evaluations))

    games = attach_evaluations(load_games(choices_path), load_evaluations(eval_path))

    assert len(games) == 2
    assert games[0]["evaluation"]["metrics"]["resource_combos"] == [
        True,
        False,
        True,
        False,
    ]
    assert games[1]["evaluation"]["players"][0] == "gateway/model"
    assert "steps" in games[0]


def test_load_games_skips_failed_and_malformed_rows(tmp_path: Path) -> None:
    ok = _choices_row()
    failed = {**ok, "seed": 1, "ok": False, "error": "rate limit"}
    path = tmp_path / "choices.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({**ok, "seed": 0, "ok": True}),
                "{not json",
                json.dumps(failed),
                json.dumps({**ok, "seed": 2, "ok": True}),
                "",
            ]
        )
        + "\n"
    )

    games = load_games(path)

    assert [game["seed"] for game in games] == [0, 2]


def test_load_games_omits_null_placements(tmp_path: Path) -> None:
    row = _choices_row()
    choices = row["choices"]
    assert isinstance(choices, list)
    choices[0][1] = None
    choices[3] = [None, None]
    path = tmp_path / "choices.jsonl"
    path.write_text(json.dumps(row) + "\n")

    games = load_games(path)

    steps = games[0]["steps"]
    assert [step["seat"] for step in steps] == [0, 1, 2, 2, 1]
    assert [step["placement"] for step in steps] == [1, 1, 1, 2, 2]
    assert steps[0]["vertex"] == choices[0][0]["vertex"]


def test_page_marks_unfinished_rows_and_counts_them() -> None:
    assert "✗ Row" in PAGE
    assert "not scored because the draft did not finish" in PAGE
    row = _choices_row()
    choices = row["choices"]
    assert isinstance(choices, list)
    choices[0][1] = None
    game = attach_evaluations(
        [{**row, "steps": []}],
        [{"players": ["random", "", "", ""], "metrics": None}],
    )[0]
    page = render_page([game])
    assert "✗ Row" in page
    assert '"metrics": null' in page


def test_attach_evaluations_rejects_length_mismatch(tmp_path: Path) -> None:
    choices_path = tmp_path / "choices.jsonl"
    choices_path.write_text(
        "".join(json.dumps(_choices_row()) + "\n" for _ in range(2))
    )
    games = load_games(choices_path)
    with pytest.raises(ValueError, match="evaluation has 1 rows but choices has 2"):
        attach_evaluations(
            games,
            [
                {
                    "players": ["random", "random", "random", "random"],
                    "metrics": {"diversity": [True, True, True, True]},
                }
            ],
        )


def _scored(
    players: tuple[str, str, str, str],
    metrics: dict[str, list[bool]],
) -> dict[str, object]:
    return {
        **_choices_row(players),
        "evaluation": {"players": list(players), "metrics": metrics},
    }


def test_load_directory_pairs_sources_and_skips_unpaired(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    players = ("jev-latest", "random", "random", "random")
    (tmp_path / "choices.jsonl").write_text(json.dumps(_choices_row()) + "\n")
    (tmp_path / "orphan.evaluate.jsonl").write_text("{}\n")
    (tmp_path / "jev.jsonl").write_text(json.dumps(_choices_row(players)) + "\n")
    (tmp_path / "jev.evaluate.jsonl").write_text(
        json.dumps(
            {
                "players": list(players),
                "metrics": {"diversity": [True, False, False, False]},
            }
        )
        + "\n"
    )
    (tmp_path / "luna.jsonl").write_text(json.dumps(_choices_row()) + "\n")
    (tmp_path / "luna.evaluate.jsonl").write_text(
        json.dumps(
            {
                "players": ["random", "random", "random", "random"],
                "metrics": {"diversity": [False, False, False, True]},
            }
        )
        + "\n"
    )

    games = load_directory(tmp_path)

    assert [game["source"] for game in games] == ["jev", "luna"]
    assert games[0]["evaluation"]["players"][0] == "jev-latest"
    assert "steps" in games[1]
    assert (
        "skipping choices.jsonl: no choices.evaluate.jsonl" in capsys.readouterr().err
    )


def test_load_directory_rejects_length_mismatch(tmp_path: Path) -> None:
    (tmp_path / "jev.jsonl").write_text(
        "".join(json.dumps(_choices_row()) + "\n" for _ in range(2))
    )
    (tmp_path / "jev.evaluate.jsonl").write_text(
        json.dumps(
            {
                "players": ["random", "random", "random", "random"],
                "metrics": {"diversity": [True, True, True, True]},
            }
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="evaluation has 1 rows but choices has 2"):
        load_directory(tmp_path)


def test_load_directory_requires_a_pair(tmp_path: Path) -> None:
    (tmp_path / "choices.jsonl").write_text(json.dumps(_choices_row()) + "\n")
    with pytest.raises(ValueError, match="no choices/evaluation pairs"):
        load_directory(tmp_path)


def test_performance_by_metric_mean_and_sample_count() -> None:
    players = ("alpha", "beta", "gamma", "delta")
    games = [
        _scored(players, {"diversity": [True, False, True, False]}),
        _scored(players, {"diversity": [False, True, False, True]}),
        {
            "choices": _choices_row(players)["choices"],
            "evaluation": {"players": ["alpha", "", "", ""], "metrics": None},
        },
        _scored(players, {"production": [True, False, False, False]}),
    ]

    report = performance_by_metric(games)

    by_metric = {row["metric"]: row for row in report}
    assert list(by_metric) == ["diversity", "production"]
    assert by_metric["diversity"]["label"] == "Diversity"
    assert "grid" not in by_metric["diversity"]
    assert [item["player"] for item in by_metric["diversity"]["players"]] == [
        "alpha",
        "beta",
        "delta",
        "gamma",
    ]
    alpha = by_metric["diversity"]["players"][0]
    assert alpha["n"] == 2
    assert alpha["mean"] == pytest.approx(0.5)
    assert set(alpha) == {"player", "n", "mean"}
    produced = by_metric["production"]["players"][0]
    assert produced["player"] == "alpha"
    assert produced["n"] == 1
    assert produced["mean"] == pytest.approx(1.0)
    assert by_metric["production"]["players"][1]["n"] == 1
    assert by_metric["production"]["players"][1]["mean"] == pytest.approx(0.0)


def test_mean_follows_the_pass_rate() -> None:
    players = ("alpha", "beta", "gamma", "delta")
    games = [
        _scored(players, {"diversity": [passed, True, True, True]})
        for passed in (False, False, False, True)
    ]

    row = performance_by_metric(games)[0]
    alpha = row["players"][0]

    assert alpha["n"] == 4
    assert alpha["mean"] == pytest.approx(0.25)


def test_performance_by_seat_splits_means_by_turn_position() -> None:
    games = [
        _scored(
            ("alpha", "beta", "gamma", "delta"),
            {"diversity": [True, False, False, False]},
        ),
        _scored(
            ("beta", "gamma", "delta", "alpha"),
            {"diversity": [False, False, False, False]},
        ),
        {
            "choices": _choices_row(("alpha", "beta", "gamma", "delta"))["choices"],
            "evaluation": {"players": ["alpha", "", "", ""], "metrics": None},
        },
    ]

    report = performance_by_seat(games)

    assert [row["label"] for row in report] == ["First", "Second", "Third", "Fourth"]
    assert [row["seat"] for row in report] == [0, 1, 2, 3]
    by_seat = {row["seat"]: row for row in report}
    assert by_seat[0]["metrics"][0]["label"] == "Diversity"
    first = {item["player"]: item for item in by_seat[0]["metrics"][0]["players"]}
    fourth = {item["player"]: item for item in by_seat[3]["metrics"][0]["players"]}
    third = {item["player"]: item for item in by_seat[2]["metrics"][0]["players"]}
    assert [item["player"] for item in by_seat[0]["metrics"][0]["players"]] == [
        "alpha",
        "beta",
        "delta",
        "gamma",
    ]
    assert first["alpha"]["n"] == 1
    assert first["alpha"]["mean"] == pytest.approx(1.0)
    assert fourth["alpha"]["n"] == 1
    assert fourth["alpha"]["mean"] == pytest.approx(0.0)
    assert third["beta"]["n"] == 0
    assert third["beta"]["mean"] is None


def test_page_has_games_summary_and_source_tabs() -> None:
    players = ("alpha", "beta", "gamma", "delta")
    games = [
        {
            **_scored(players, {"diversity": [True, False, True, False]}),
            "source": "jev",
            "steps": [],
        },
        {**_choices_row(), "source": "luna", "steps": []},
    ]
    page = render_page(games)
    assert 'id="tab-games"' in page
    assert 'id="tab-summary"' in page
    assert 'id="sources"' in page
    assert 'id="performance-chart"' not in page
    assert 'id="radar-chart"' in page
    assert 'id="radar-seat-0"' in page
    assert 'id="radar-seat-1"' in page
    assert 'id="radar-seat-2"' in page
    assert 'id="radar-seat-3"' in page
    assert "The radar shows the mean pass rate across all seats." in page
    assert "All seats" in page
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in page
    assert '"source": "jev"' in page
    assert '"source": "luna"' in page
    assert '"label": "Diversity"' in page
    assert 'id="latency-section"' in page
    assert '"edges": []' in page


def test_latency_histograms_share_bins_and_skip_missing() -> None:
    games = [
        {
            "choices": [
                [
                    {**_placement(0, 0, "slow"), "metadata": {"latency_ms": 100}},
                    {**_placement(0, 1, "slow"), "metadata": {"latency_ms": True}},
                ],
                [_placement(1, 0, "random"), None],
                [
                    {**_placement(2, 0, "fast"), "metadata": {"latency_ms": 0}},
                    {**_placement(2, 1, "fast"), "metadata": {"latency_ms": 10}},
                ],
                [None, None],
            ]
        }
    ]

    report = latency_histograms(games)

    assert report["edges"] == [[index * 10, (index + 1) * 10] for index in range(10)]
    by_player = {row["player"]: row for row in report["players"]}
    assert list(by_player) == ["fast", "slow"]
    assert by_player["fast"]["n"] == 2
    assert by_player["fast"]["counts"] == [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    assert by_player["slow"]["n"] == 1
    assert by_player["slow"]["counts"] == [0, 0, 0, 0, 0, 0, 0, 0, 0, 1]


def test_latency_histograms_collapse_a_single_value() -> None:
    games = [
        {
            "choices": [
                [
                    {**_placement(0, 0, "model"), "metadata": {"latency_ms": 842}},
                    {**_placement(0, 1, "model"), "metadata": {"latency_ms": 842}},
                ]
            ]
        }
    ]

    assert latency_histograms(games) == {
        "edges": [[842, 842]],
        "players": [{"player": "model", "counts": [2], "n": 2}],
    }


def test_page_embeds_latency_histograms() -> None:
    game = {
        "choices": [
            [
                {**_placement(0, 0, "model"), "metadata": {"latency_ms": 842}},
                {**_placement(0, 1, "model"), "metadata": {"latency_ms": 842}},
            ]
        ],
        "source": "luna",
        "steps": [],
    }

    page = render_page([game])

    assert 'id="latency-section"' in page
    assert "Each bar counts model calls that recorded latency." in page
    assert "renderLatency" in page
    assert '"edges": [[842, 842]]' in page
    assert '"player": "model"' in page
    assert '"counts": [2]' in page
    assert '"n": 2' in page
