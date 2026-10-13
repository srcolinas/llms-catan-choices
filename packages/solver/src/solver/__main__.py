from __future__ import annotations

import argparse
import logging
import random
from collections.abc import Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager, nullcontext
from pathlib import Path

from tqdm import tqdm

from simulation import Board, Simulator
from solver.dataset import append_lines, failure_line, game_line, pending_seeds
from solver.players import PLAYERS
from solver.settings import Settings, settings

_DEFAULT_WORKERS = 16


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Catan setup drafts as JSONL")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--workers", type=_positive_int, default=_DEFAULT_WORKERS)
    parser.add_argument("--output", type=Path, default=Path("data/choices.jsonl"))
    parser.add_argument(
        "--players",
        type=_players_argument,
        default=["random", "random", "random", "random"],
    )
    parser.add_argument("--langfuse", action="store_true")
    args = parser.parse_args()
    loaded = settings()

    loglevel = logging.getLevelNamesMapping()[loaded.loglevel]
    print(f"Setting log level to: {loaded.loglevel} ({loglevel})")
    _configure_logging(loaded.loglevel)

    pending = pending_seeds(args.output, args.count)
    if not pending:
        print(f"{args.count} games already finished in {args.output}")
        return
    print(f"{args.count - len(pending)} finished, playing {len(pending)}")

    observer = _langfuse(loaded) if args.langfuse else None
    try:
        append_lines(
            play(
                pending,
                args.players,
                loaded,
                workers=args.workers,
                observer=observer,
            ),
            args.output,
        )
    finally:
        if observer is not None:
            observer.flush()


def play(
    seeds: Sequence[int],
    kinds: Sequence[str],
    loaded: Settings,
    *,
    workers: int = _DEFAULT_WORKERS,
    observer: object | None = None,
) -> Iterator[str]:
    """Play ``seeds``, yielding one JSONL row per game in that order.

    Games run ``workers`` at a time. A row is yielded as soon as that seed and
    every earlier seed in ``seeds`` have finished, so the caller can write it
    immediately.
    """
    ordered = list(seeds)
    if not ordered:
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: dict[Future[str], int] = {
            pool.submit(
                _play_one, seed, kinds=kinds, loaded=loaded, observer=observer
            ): seed
            for seed in ordered
        }
        finished: dict[int, str] = {}
        next_index = 0
        for future in tqdm(
            as_completed(futures), total=len(ordered), desc="Playing games"
        ):
            finished[futures[future]] = future.result()
            while next_index < len(ordered) and ordered[next_index] in finished:
                yield finished.pop(ordered[next_index])
                next_index += 1


def _play_one(
    seed: int,
    *,
    kinds: Sequence[str],
    loaded: Settings,
    observer: object | None,
) -> str:
    try:
        with _game_span(observer, seed) if observer is not None else nullcontext():
            rng = random.Random(seed)
            board = Board.from_seed(seed)
            players = [PLAYERS[kind](loaded, rng) for kind in kinds]
            rng.shuffle(players)
            report = Simulator(board, players).simulate(1)
            return game_line(
                seed,
                board,
                [(player.kind, player.name) for player in players],
                report,
                [
                    _accepted_calls(player, seat)
                    for player, seat in zip(players, report.placements, strict=True)
                ],
            )
    # Record the seed instead of aborting the batch. KeyboardInterrupt is a
    # BaseException, so stopping the process still leaves flushed rows in place.
    except Exception as exc:  # noqa: BLE001
        return failure_line(seed, len(kinds), str(exc))


def _accepted_calls(
    player: object,
    seat: tuple[object, object],
) -> list[dict[str, int] | None]:
    placed = sum(slot is not None for slot in seat)
    record = getattr(player, "accepted_calls", None)
    if not callable(record):
        return [None] * placed
    calls: list[dict[str, int] | None] = record(placed)
    return calls


def _langfuse(loaded: Settings):
    import langfuse
    import pydantic_ai

    public_key = loaded.langfuse_public_key
    secret_key = loaded.langfuse_secret_key
    base_url = loaded.langfuse_base_url
    if public_key is None or secret_key is None or base_url is None:
        raise SystemExit(
            "Set SOLVER_LANGFUSE_PUBLIC_KEY, SOLVER_LANGFUSE_SECRET_KEY, "
            "and SOLVER_LANGFUSE_BASE_URL to trace with --langfuse."
        )
    observer = langfuse.Langfuse(
        public_key=public_key.get_secret_value(),
        secret_key=secret_key.get_secret_value(),
        base_url=base_url,
    )
    pydantic_ai.Agent.instrument_all()
    return observer


@contextmanager
def _game_span(observer: object, seed: int) -> Iterator[None]:
    from langfuse import Langfuse, propagate_attributes

    if not isinstance(observer, Langfuse):
        raise TypeError("expected a Langfuse client")
    # Each placement starts a new Pydantic AI conversation, and Langfuse uses
    # that id as the session. One row places twice, so pin the session to the row.
    with (
        propagate_attributes(session_id=str(seed)),
        observer.start_as_current_observation(
            name="catan-setup",
            as_type="span",
            metadata={"seed": seed},
        ),
    ):
        yield


class _SolverLogFilter(logging.Filter):
    """Keep this package's logs and drop every other library."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "solver" or record.name.startswith("solver.")


def _configure_logging(level_name: str) -> None:
    level = logging.getLevelNamesMapping()[level_name]
    handler = logging.StreamHandler()
    handler.addFilter(_SolverLogFilter())
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("solver").setLevel(level)


def _players_argument(value: str) -> list[str]:
    kinds = [part.strip() for part in value.split(",")]
    if len(kinds) not in (3, 4) or any(kind not in PLAYERS for kind in kinds):
        raise argparse.ArgumentTypeError(
            "expected 3 or 4 players, each `random`, `generative`, `jev`, "
            "`system-one`, or `openai-decision`"
        )
    return kinds


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


if __name__ == "__main__":
    main()
