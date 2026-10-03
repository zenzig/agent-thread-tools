from __future__ import annotations

import pytest

from tests.fixtures.build_fixtures import build


@pytest.fixture(scope="session", autouse=True)
def rebuild_generated_fixtures() -> None:
    build()


@pytest.fixture(autouse=True)
def no_real_jev_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    # A developer's saved OpenRouter key must never make tests call Jev for real.
    monkeypatch.setenv("AGENT_THREAD_JEV", "off")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
