import random as random_module
from collections.abc import Callable

from solver.players.generative import GenerativePlayer
from solver.players.jev import JevPlayer
from solver.players.openai_decision import OpenAIDecisionPlayer
from solver.players.random import RandomPlayer
from solver.players.system_one import SystemOnePlayer
from solver.settings import Settings

PLAYERS: dict[
    str,
    Callable[
        [Settings, random_module.Random | None],
        RandomPlayer
        | GenerativePlayer
        | JevPlayer
        | OpenAIDecisionPlayer
        | SystemOnePlayer,
    ],
] = {
    "random": RandomPlayer,
    "generative": GenerativePlayer,
    "jev": JevPlayer,
    "openai-decision": OpenAIDecisionPlayer,
    "system-one": SystemOnePlayer,
}
