# llms-catan-building-placement-choices

This project benchmarks the ability of LLMs to place buildings on a map of Catan. The `catan-simulation` crate runs the setup snake draft on a board. The caller passes that board and 3 or 4 players in seat order. Each player chooses a settlement and a connected road when asked. 

## Evaluation

It is realy hard to characterize the setup placement as good or bad, specially because how you and your friends play afterwards has a great impact on how we assess the initial possition. However, there are a few heuristics that experienced players generally follow: [heuristics](./docs/heuristics.md).

In some cases, it is literally impossible to get all those heuristics right and we need to take this into account when evaluating the choices made by LLMs to place their settlments. 

In the benchmarks we measure how often a placement selection follows the heuristics. 


## Simulator

`Simulator::new` takes a board and 3 or 4 players in first-round seat order. `simulate` calls each player's `choose` method with the board, the legal town-and-road pairs, and that player's error messages so far, then calls them again in reverse. A choice is a town vertex and a road edge. Invalid choices are recorded and the player is asked again until that player reaches `max_errors`, which stops the draft. The report lists each player's error messages and the town vertices they placed.

## Running

If you have already setup the project (by running `task setup`), run:

1. Generate LLM answers with `task solve` (writes `data/choices.jsonl`).
2. Evaluate performance with `task evaluate` (writes `data/evaluation.jsonl`, one line per choices row).
3. Optionally visualize with `task view` (reads `data/`, pairing `name.jsonl` with `name.evaluate.jsonl`). One file is `task view -- data/luna.jsonl --eval data/luna.evaluate.jsonl`. Games are browsed per file; Summary shows the mean pass rate per heuristic as a radar chart, plus four radars for players sitting first, second, third, and fourth.

`task format`, `task lint`, and `task test` cover Python and Rust. `task clean` removes caches and the virtualenv. 

