import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from solver.__main__ import _players_argument, play
from solver.players.human import HUMAN_PAGE, active_table, deactivate
from solver.settings import Settings
from solver.view import PAGE


def test_viewer_and_human_page_share_the_board() -> None:
    assert "function drawBoard(game, shown)" in PAGE
    assert "function hexToPixel" in PAGE
    assert "function drawBoard(game, shown)" in HUMAN_PAGE
    assert "function hexToPixel" in HUMAN_PAGE
    assert "function renderMarkdown" in HUMAN_PAGE
    assert "<div id=\"rules\">" in HUMAN_PAGE
    assert 'id="rules-split"' in HUMAN_PAGE
    assert "width: 360px" in HUMAN_PAGE
    assert "pending_human" in HUMAN_PAGE
    assert "waiting_random" in HUMAN_PAGE
    assert "✓" not in HUMAN_PAGE
    assert "heuristics .pass" not in HUMAN_PAGE


def test_players_argument_accepts_human() -> None:
    assert _players_argument("human,random,random,random") == [
        "human",
        "random",
        "random",
        "random",
    ]


def test_human_choice_follows_random_and_rejects_an_illegal_pair(
    tmp_path: Path,
) -> None:
    heuristics = tmp_path / "heuristics.md"
    heuristics.write_text("Prefer ore and wheat.\n")
    loaded = Settings(llm_model="test:model", heuristics=heuristics)
    found: dict[str, Any] = {}

    def run() -> None:
        try:
            found["lines"] = list(
                play(
                    [4],
                    ["human", "random", "random", "random"],
                    loaded,
                    workers=1,
                    human_browser=False,
                    human_beat=0,
                )
            )
        except Exception as exc:  # noqa: BLE001
            found["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        table = _wait_for_table()
        posted = _answer(table, 4)
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert "error" not in found
        history = table.statuses(4)
        waiting = [i for i, status in enumerate(history) if status == "waiting_random"]
        pending = [i for i, status in enumerate(history) if status == "pending_human"]
        assert any(wait < later for wait in waiting for later in pending)
        lines = found["lines"]
        assert isinstance(lines, list)
        row = json.loads(lines[0])
        assert row["ok"] is True
        human = next(
            seat
            for seat in row["choices"]
            if seat[0] is not None and seat[0]["kind"] == "human"
        )
        assert [choice["vertex"] for choice in human] == [
            pair["vertex"] for pair in posted
        ]
        assert [choice["edge"] for choice in human] == [pair["edge"] for pair in posted]
        assert human[0]["player"] == "human"
    finally:
        current = active_table()
        if current is not None:
            for item in current.snapshot()["rows"]:
                if item["status"] == "pending_human":
                    current.finish(item["seed"], ok=False)
            current.close()
            deactivate(current)
        thread.join(timeout=5)


def _wait_for_table():
    deadline = time.time() + 5
    while time.time() < deadline:
        table = active_table()
        if table is not None and table.url:
            return table
        time.sleep(0.01)
    raise AssertionError("human table did not open")


def _answer(table: Any, seed: int) -> list[dict[str, Any]]:
    page = _request("GET", table.url)
    assert page[0] == 200
    assert "function drawBoard(game, shown)" in page[1]
    posted: list[dict[str, Any]] = []
    rejected = False
    deadline = time.time() + 10
    while time.time() < deadline:
        row = _row(table, seed)
        if row["status"] == "done":
            assert len(posted) == 2
            return posted
        if row["status"] == "failed":
            raise AssertionError(row)
        if row["status"] != "pending_human":
            time.sleep(0.01)
            continue
        if not rejected:
            illegal = _illegal_pair(row["available"])
            status, body = _request(
                "POST",
                table.url + "choose",
                {"seed": seed, "vertex": illegal["vertex"], "edge": illegal["edge"]},
            )
            assert status == 400
            assert body == "not a legal placement"
            state_status, state_body = _request("GET", table.url + "state")
            assert state_status == 200
            assert "Prefer ore and wheat." in state_body
            rejected = True
        before = len(row["placements"])
        previous = row["available"]
        choice = previous[0]
        status, _body = _request(
            "POST",
            table.url + "choose",
            {"seed": seed, "vertex": choice["vertex"], "edge": choice["edge"]},
        )
        assert status == 200
        posted.append(choice)
        while time.time() < deadline:
            current = _row(table, seed)
            if current["status"] != "pending_human":
                break
            if len(current["placements"]) > before and current["available"] != previous:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("turn did not advance")
    raise AssertionError("draft did not finish")


def _row(table: Any, seed: int) -> dict[str, Any]:
    rows = table.snapshot()["rows"]
    return next(row for row in rows if row["seed"] == seed)


def _illegal_pair(available: list[dict[str, Any]]) -> dict[str, Any]:
    taken = {
        (
            item["vertex"]["q"],
            item["vertex"]["r"],
            item["vertex"]["index"],
            item["edge"]["q"],
            item["edge"]["r"],
            item["edge"]["index"],
        )
        for item in available
    }
    vertex = available[0]["vertex"]
    for index in range(6):
        edge = {"q": vertex["q"], "r": vertex["r"], "index": index}
        key = (vertex["q"], vertex["r"], vertex["index"], edge["q"], edge["r"], index)
        if key not in taken:
            return {"vertex": vertex, "edge": edge}
    raise AssertionError("every edge index on the vertex was legal")


def _request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload).encode()
    headers = {} if data is None else {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()
