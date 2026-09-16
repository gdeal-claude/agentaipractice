"""stockmom 에이전트 조립."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentsys import Agent, AgentConfig, FileMemory
from agentsys.events import EventHandler

from .market import MarketData
from .portfolio import DEFAULT_PORTFOLIO_PATH, Portfolio
from .prompts import MOM_SYSTEM
from .tools import WEB_SEARCH_TOOL, build_tools

__all__ = ["build_agent"]


def build_agent(
    *,
    market: MarketData | None = None,
    portfolio: Portfolio | None = None,
    memory_path: str | Path = "data/memory.json",
    client: Any | None = None,
    config: AgentConfig | None = None,
    on_event: EventHandler | None = None,
    web_search: bool = True,
) -> Agent:
    market = market or MarketData()
    portfolio = portfolio or Portfolio(DEFAULT_PORTFOLIO_PATH)
    memory = FileMemory(memory_path)
    return Agent(
        name="주식도우미",
        system=MOM_SYSTEM,
        tools=[*build_tools(market, portfolio), *memory.tools()],
        server_tools=[WEB_SEARCH_TOOL] if web_search else None,
        client=client,
        config=config or AgentConfig(effort="high"),
        on_event=on_event,
    )
