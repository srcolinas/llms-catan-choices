from __future__ import annotations

import argparse
import io
import json
import logging
import random
from pathlib import Path
from typing import Any

import pytest
from openai.types.decision import (
    AnswerAnswerResourceChoice,
    AnswerAnswerResourceRefusal,
    Decision,
)
from pydantic_ai.models.decision import (
    ChoiceAnswer,
    ChoiceQuestion,
    DecisionModel,
    DecisionModelSettings,
    DecisionRequest,
    DecisionResponse,
)
from pydantic_ai.models.test import TestModel
from solver.__main__ import _configure_logging, _players_argument, _positive_int, play
from solver.dataset import recorded_name, write_lines
from solver.players import PLAYERS
from solver.players.calls import CallLog, timed
from solver.players.generative import GenerativePlayer, instructions, user_message
from solver.players.jev import JevPlayer, placement_criteria, placement_state
from solver.players.openai_decision import OpenAIDecisionPlayer
from solver.players.system_one import SystemOnePlayer
from solver.settings import Settings, settings

from simulation import Board, Edge, Vertex


def test_settings_reads_llm_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOLVER_LLM_MODEL", "openai:gpt-4o")
    settings.cache_clear()
    loaded = settings()
    assert loaded.llm_model == "openai:gpt-4o"
    assert loaded.heuristics == Path("docs/heuristics.md")
    settings.cache_clear()


def test_instructions_include_heuristics_and_board(tmp_path: Path) -> None:
    heuristics = tmp_path / "heuristics.md"
    heuristics.write_text("Prefer ore and wheat.\n")
    board = Board.from_seed(0)
    text = instructions(board, heuristics.read_text())
    tile = board.tiles[0]
    assert "Prefer ore and wheat." in text
    assert tile.terrain in text
    assert str(tile.number) in text


def test_user_message_lists_the_offered_vertex_and_edge() -> None:
    vertex = Vertex(1, -1, 2)
    edge = Edge(1, -1, 3)
    prior_vertex = Vertex(0, 0, 0)
    prior_edge = Edge(0, 0, 1)
    text = user_message(
        [(vertex, edge)],
        [(2, prior_vertex, prior_edge)],
        ["not on the board"],
    )
    assert json.dumps({"q": vertex.q, "r": vertex.r, "index": vertex.index}) in text
    assert json.dumps({"q": edge.q, "r": edge.r, "index": edge.index}) in text
    assert '"seat": 2' in text
    assert (
        json.dumps(
            {"q": prior_vertex.q, "r": prior_vertex.r, "index": prior_vertex.index}
        )
        in text
    )
    assert "not on the board" in text


def test_jev_state_includes_prior_placements() -> None:
    vertex = Vertex(0, 0, 0)
    edge = Edge(0, 0, 1)

    state = placement_state(
        Board.from_seed(0),
        "Prefer ports.",
        [(1, vertex, edge)],
        [],
    )

    assert state["prior_placements"] == [
        {
            "seat": 1,
            "vertex": {"q": vertex.q, "r": vertex.r, "index": vertex.index},
            "edge": {"q": edge.q, "r": edge.r, "index": edge.index},
        }
    ]


def test_call_log_records_one_call() -> None:
    log = CallLog()
    log.start_turn([])
    log.add(0.842)
    log.end_turn()
    assert log.finish(1) == [{"latency_ms": 842}]


def test_call_log_sums_calls_in_one_turn() -> None:
    log = CallLog()
    log.start_turn([])
    log.add(0.4)
    log.add(0.442)
    log.end_turn()
    assert log.finish(1) == [{"latency_ms": 842}]


def test_call_log_drops_a_rejected_attempt() -> None:
    log = CallLog()
    log.start_turn([])
    log.add(1.5)
    log.end_turn()
    log.start_turn(["vertex is not available"])
    log.add(0.2)
    log.end_turn()
    assert log.finish(1) == [{"latency_ms": 200}]


def test_call_log_drops_a_raised_attempt() -> None:
    log = CallLog()
    log.start_turn([])
    log.add(1.5)
    assert log.finish(0) == []


def test_call_log_omits_metadata_when_no_model_was_called() -> None:
    log = CallLog()
    log.start_turn([])
    log.end_turn()
    assert log.finish(1) == [None]


def test_timed_records_elapsed_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 0.0

    def clock() -> float:
        nonlocal now
        now += 0.421
        return now

    monkeypatch.setattr("solver.players.calls.time.perf_counter", clock)
    log = CallLog()
    log.start_turn([])
    with timed(log):
        pass
    log.end_turn()
    assert log.finish(1) == [{"latency_ms": 421}]


def test_choose_returns_structured_vertex_and_edge(tmp_path: Path) -> None:
    loaded = _settings(tmp_path)
    payload = {
        "vertex": {"q": 1, "r": 2, "index": 3},
        "edge": {"q": 4, "r": -1, "index": 0},
    }
    player = GenerativePlayer(loaded)
    player._model = TestModel(custom_output_args=payload)
    vertex, edge = player.choose(
        Board.from_seed(0),
        [(Vertex(0, 0, 0), Edge(0, 0, 1))],
        [],
        [],
    )
    assert vertex == Vertex(1, 2, 3)
    assert edge == Edge(4, -1, 0)


def test_choose_records_model_latency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 0.0

    def clock() -> float:
        nonlocal now
        now += 0.421
        return now

    monkeypatch.setattr("solver.players.calls.time.perf_counter", clock)
    loaded = _settings(tmp_path)
    payload = {
        "vertex": {"q": 1, "r": 2, "index": 3},
        "edge": {"q": 4, "r": -1, "index": 0},
    }
    player = GenerativePlayer(loaded)
    player._model = TestModel(custom_output_args=payload)
    player.choose(
        Board.from_seed(0),
        [(Vertex(0, 0, 0), Edge(0, 0, 1))],
        [],
        [],
    )
    assert player.accepted_calls(1) == [{"latency_ms": 421}]


def test_choose_rejects_more_than_255_options(tmp_path: Path) -> None:
    player = JevPlayer(_settings(tmp_path))
    available = [(Vertex(0, 0, 0), Edge(0, 0, 1))] * 256
    with pytest.raises(ValueError, match="255"):
        player.choose(Board.from_seed(0), available, [], [])


def test_players_argument_accepts_jev() -> None:
    assert _players_argument("random,generative,jev,random") == [
        "random",
        "generative",
        "jev",
        "random",
    ]


def test_players_argument_accepts_system_one() -> None:
    assert _players_argument("random,system-one,jev,random") == [
        "random",
        "system-one",
        "jev",
        "random",
    ]


def test_players_argument_accepts_openai_decision() -> None:
    assert _players_argument("random,openai-decision,jev,random") == [
        "random",
        "openai-decision",
        "jev",
        "random",
    ]


def test_system_one_choose_returns_the_picked_placement(tmp_path: Path) -> None:
    board = Board.from_seed(0)
    first = (Vertex(0, 0, 1), Edge(0, 0, 0))
    second = (Vertex(1, -1, 2), Edge(1, -1, 3))
    prior = (3, Vertex(2, -2, 1), Edge(2, -2, 0))
    player = SystemOnePlayer(_settings(tmp_path))
    capture = _Capture(choice="o1")
    player._model = capture

    vertex, edge = player.choose(board, [first, second], [prior], ["not on the board"])

    assert (vertex, edge) == second
    assert len(capture.requests) == 1
    state = json.loads(str(capture.requests[0].state))
    assert "heuristics" not in state
    assert state["rejected_choices"] == ["not on the board"]
    assert state["prior_placements"] == [
        {
            "seat": 3,
            "vertex": {"q": 2, "r": -2, "index": 1},
            "edge": {"q": 2, "r": -2, "index": 0},
        }
    ]
    question = capture.requests[0].questions["placement"]
    assert isinstance(question, ChoiceQuestion)
    criteria, _options = placement_criteria(board, [first, second])
    assert json.loads(str(question.criteria["o1"])) == criteria["o1"]


def test_system_one_returns_the_only_placement_without_asking(tmp_path: Path) -> None:
    only = (Vertex(0, 0, 1), Edge(0, 0, 0))
    player = SystemOnePlayer(_settings(tmp_path))
    capture = _Capture()
    player._model = capture

    assert player.choose(Board.from_seed(0), [only], [], []) == only
    assert capture.requests == []


def test_openai_decision_choose_returns_the_picked_placement(tmp_path: Path) -> None:
    board = Board.from_seed(0)
    first = (Vertex(0, 0, 1), Edge(0, 0, 0))
    second = (Vertex(1, -1, 2), Edge(1, -1, 3))
    prior = (3, Vertex(2, -2, 1), Edge(2, -2, 0))
    capture = _OpenAICapture(choice="o1")
    player = OpenAIDecisionPlayer(_settings(tmp_path), client=capture)

    vertex, edge = player.choose(board, [first, second], [prior], ["not on the board"])

    assert (vertex, edge) == second
    assert player.name == "gpt-6-luna"
    assert len(capture.requests) == 1
    request = capture.requests[0]
    assert request["model"] == "gpt-6-luna"
    state = json.loads(str(request["input"]))
    assert "heuristics" not in state
    assert state["rejected_choices"] == ["not on the board"]
    assert state["prior_placements"] == [
        {
            "seat": 3,
            "vertex": {"q": 2, "r": -2, "index": 1},
            "edge": {"q": 2, "r": -2, "index": 0},
        }
    ]
    question = request["questions"][0]
    assert question["type"] == "choice"
    assert question["name"] == "placement"
    assert "Prefer ports." in str(question["instructions"])
    criteria, _options = placement_criteria(board, [first, second])
    choices = question["choices"]
    assert isinstance(choices, list)
    described = {
        str(item["value"]): json.loads(str(item["description"])) for item in choices
    }
    assert described["o1"] == criteria["o1"]


def test_openai_decision_returns_the_only_placement_without_asking(
    tmp_path: Path,
) -> None:
    only = (Vertex(0, 0, 1), Edge(0, 0, 0))
    capture = _OpenAICapture()
    player = OpenAIDecisionPlayer(_settings(tmp_path), client=capture)

    assert player.choose(Board.from_seed(0), [only], [], []) == only
    assert capture.requests == []


def test_openai_decision_rejects_more_than_255_options(tmp_path: Path) -> None:
    capture = _OpenAICapture()
    player = OpenAIDecisionPlayer(_settings(tmp_path), client=capture)
    available = [(Vertex(0, 0, 0), Edge(0, 0, 1))] * 256

    with pytest.raises(ValueError, match="255"):
        player.choose(Board.from_seed(0), available, [], [])
    assert capture.requests == []


def test_openai_decision_refusal_raises(tmp_path: Path) -> None:
    capture = _OpenAICapture(refusal=True)
    player = OpenAIDecisionPlayer(_settings(tmp_path), client=capture)
    available = [
        (Vertex(0, 0, 1), Edge(0, 0, 0)),
        (Vertex(1, -1, 2), Edge(1, -1, 3)),
    ]

    with pytest.raises(ValueError, match="refused"):
        player.choose(Board.from_seed(0), available, [], [])


def test_system_one_narrows_to_the_option_cap(tmp_path: Path) -> None:
    heuristics = tmp_path / "heuristics.md"
    heuristics.write_text("Prefer ports.\n")
    loaded = Settings(
        llm_model="test:model",
        heuristics=heuristics,
        system_one_max_options=2,
    )
    pairs = [(Vertex(offset, 0, 1), Edge(offset, 0, 0)) for offset in range(4)]
    player = SystemOnePlayer(loaded)
    capture = _Capture()
    player._model = capture

    assert player.choose(Board.from_seed(0), pairs, [], []) == pairs[0]
    assert [
        list(request.questions["placement"].criteria)
        for request in capture.requests
        if isinstance(request.questions["placement"], ChoiceQuestion)
    ] == [
        ["o0", "o1"],
        ["o2", "o3"],
        ["o0", "o2"],
    ]


def test_players_argument_counts_one_generative_seat() -> None:
    roster = _players_argument("random,random,generative,random")
    assert roster.count("random") == 3
    assert roster.count("generative") == 1
    with pytest.raises(argparse.ArgumentTypeError):
        _players_argument("random,random")


@pytest.mark.parametrize("value", ["0", "-1"])
def test_workers_must_be_positive(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        _positive_int(value)
    assert _positive_int("4") == 4


def test_library_logs_are_dropped() -> None:
    root = logging.getLogger()
    solver_logger = logging.getLogger("solver")
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_solver_level = solver_logger.level
    buffer = io.StringIO()
    try:
        _configure_logging("INFO")
        for handler in root.handlers:
            assert isinstance(handler, logging.StreamHandler)
            handler.setStream(buffer)
        logging.getLogger("httpx2").error("library failure")
        logging.getLogger("solver.players").info("solver placement")
        logging.getLogger("solver.players").debug("solver detail")
        text = buffer.getvalue()
    finally:
        for handler in list(root.handlers):
            if handler not in saved_handlers:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(saved_level)
        solver_logger.setLevel(saved_solver_level)
    assert "library failure" not in text
    assert "solver placement" in text
    assert "solver detail" not in text


def test_one_langfuse_session_per_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections import defaultdict

    import pydantic_ai
    from langfuse import Langfuse
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    observer = Langfuse(
        public_key="pk-test-sessions",
        secret_key="sk-test-sessions",
        base_url="http://127.0.0.1:9",
        span_exporter=exporter,
        flush_at=1000,
        flush_interval=60,
    )
    pydantic_ai.Agent.instrument_all()
    monkeypatch.setattr(GenerativePlayer, "choose", _traced_first_legal)
    try:
        rows = list(
            play(
                range(2),
                ["generative", "random", "random", "random"],
                _settings(tmp_path),
                workers=2,
                observer=observer,
            )
        )
        observer.flush()
    finally:
        pydantic_ai.Agent.instrument_all(False)
        observer.shutdown()

    assert len(rows) == 2
    conversations: dict[str, set[str]] = defaultdict(set)
    for span in exporter.get_finished_spans():
        attributes = span.attributes or {}
        conversation_id = attributes.get("gen_ai.conversation.id")
        if not conversation_id:
            continue
        session_id = attributes.get("session.id")
        assert isinstance(session_id, str)
        conversations[session_id].add(str(conversation_id))

    assert set(conversations) == {"0", "1"}
    assert all(len(ids) == 2 for ids in conversations.values())


def test_parallel_play_matches_serial_play(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = _settings(tmp_path)
    roster = ["random", "random", "generative", "random"]
    serial_output = tmp_path / "serial.jsonl"
    parallel_output = tmp_path / "parallel.jsonl"
    monkeypatch.setattr(GenerativePlayer, "choose", _first_legal)

    write_lines(play(range(4), roster, loaded, workers=1), serial_output)
    write_lines(play(range(4), roster, loaded, workers=4), parallel_output)

    serial = serial_output.read_text()
    assert parallel_output.read_text() == serial

    orders = [_shuffled_labels(roster, seed, loaded) for seed in range(4)]
    assert len({tuple(order) for order in orders}) > 1
    rows = [json.loads(line) for line in serial.splitlines()]
    assert len(rows) == 4
    for seed, row in enumerate(rows):
        labels = [_seat_label(seat) for seat in row["choices"]]
        assert labels == orders[seed]


class _OpenAICapture:
    def __init__(self, choice: str | None = None, *, refusal: bool = False) -> None:
        self.choice = choice
        self.refusal = refusal
        self.requests: list[dict[str, Any]] = []
        self.decisions = self

    def create(
        self,
        *,
        input: str,
        model: str,
        questions: object,
    ) -> Decision:
        self.requests.append({"input": input, "model": model, "questions": questions})
        if self.refusal:
            answer: AnswerAnswerResourceRefusal | AnswerAnswerResourceChoice = (
                AnswerAnswerResourceRefusal.model_construct(
                    type="refusal",
                    name="placement",
                )
            )
        else:
            offered = _choice_values(questions)
            key = self.choice if self.choice in offered else offered[0]
            answer = AnswerAnswerResourceChoice.model_construct(
                type="choice",
                name="placement",
                choice=key,
                confidence=1.0,
                probabilities=[],
            )
        return Decision.model_construct(answers=[answer], model=model)


def _choice_values(questions: object) -> list[str]:
    if not isinstance(questions, list) or not questions:
        raise TypeError("expected a choice question")
    question = questions[0]
    if not isinstance(question, dict):
        raise TypeError("expected a choice question")
    choices = question.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TypeError("expected choice options")
    values: list[str] = []
    for item in choices:
        if not isinstance(item, dict) or not isinstance(item.get("value"), str):
            raise TypeError("expected string choice values")
        values.append(item["value"])
    return values


class _Capture(DecisionModel):
    def __init__(self, choice: str | None = None) -> None:
        super().__init__()
        self.choice = choice
        self.requests: list[DecisionRequest] = []

    @property
    def model_name(self) -> str:
        return "capture"

    @property
    def system(self) -> str:
        return "test"

    @property
    def base_url(self) -> str:
        return "http://test"

    async def decide(
        self,
        request: DecisionRequest,
        model_settings: DecisionModelSettings,
    ) -> DecisionResponse:
        del model_settings
        self.requests.append(request)
        question = request.questions["placement"]
        if not isinstance(question, ChoiceQuestion):
            raise TypeError("expected a choice question")
        key = (
            self.choice
            if self.choice in question.criteria
            else next(iter(question.criteria))
        )
        return DecisionResponse(
            answers={
                "placement": ChoiceAnswer(
                    choice=key,
                    confidence=1.0,
                    probabilities={
                        name: float(name == key) for name in question.criteria
                    },
                )
            },
            model_name=self.model_name,
        )


def _settings(tmp_path: Path) -> Settings:
    heuristics = tmp_path / "heuristics.md"
    heuristics.write_text("Prefer ports.\n")
    return Settings(llm_model="test:model", heuristics=heuristics)


def _traced_first_legal(
    player: GenerativePlayer,
    board: Board,
    available: list[tuple[Vertex, Edge]],
    prior: list[tuple[int, Vertex, Edge]],
    errors: list[str],
) -> tuple[Vertex, Edge]:
    del prior
    player._calls.start_turn(errors)
    vertex, edge = available[0]
    if player._agent is None:
        player._model = TestModel(
            custom_output_args={
                "vertex": {"q": vertex.q, "r": vertex.r, "index": vertex.index},
                "edge": {"q": edge.q, "r": edge.r, "index": edge.index},
            }
        )
    player._agent_for(board).run_sync("choose")
    player._calls.end_turn()
    return available[0]


def _first_legal(
    player: GenerativePlayer,
    board: Board,
    available: list[tuple[Vertex, Edge]],
    prior: list[tuple[int, Vertex, Edge]],
    errors: list[str],
) -> tuple[Vertex, Edge]:
    del board, prior
    player._calls.start_turn(errors)
    player._calls.end_turn()
    return available[0]


def _shuffled_labels(kinds: list[str], seed: int, loaded: Settings) -> list[str]:
    rng = random.Random(seed)
    labels = [recorded_name(kind, PLAYERS[kind](loaded, rng).name) for kind in kinds]
    rng.shuffle(labels)
    return labels


def _seat_label(seat: list[dict[str, object]]) -> object:
    labels = {choice["player"] for choice in seat}
    assert len(labels) == 1
    return labels.pop()
