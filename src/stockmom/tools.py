"""stockmom 이 에이전트에게 주는 도구들."""

from __future__ import annotations

import json
from typing import Any

from agentsys import Tool

from .market import MarketData
from .portfolio import Portfolio

__all__ = ["build_tools", "WEB_SEARCH_TOOL"]

# Anthropic 서버에서 실행되는 웹 검색. 뉴스와 시세 조회 실패 시 대안으로 쓴다.
WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search_20260209", "name": "web_search", "max_uses": 8}


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def build_tools(market: MarketData, portfolio: Portfolio) -> list[Tool]:
    def find_stock(query: str) -> str:
        """종목 이름이나 코드로 정확한 심볼을 찾는다.

        사용자가 말한 종목이 어떤 심볼인지 확실하지 않을 때, 시세 조회 전에 먼저 호출한다.
        한글 이름(삼성전자, 애플)도 된다.

        Args:
            query: 종목 이름, 6자리 코드, 또는 심볼. 예: "삼성전자", "005930", "AAPL"
        """
        results = market.find(query)
        if not results:
            return f"'{query}' 로 종목을 찾지 못했습니다. 다른 이름이나 코드로 다시 시도하세요."
        return _dump(results)

    def get_stock_quote(symbol: str) -> str:
        """종목의 현재가와 최근 변동률(하루/1주/1달/3달/1년), 52주 최고·최저가를 돌려준다.

        종목 상태를 설명하거나 "어때?", "얼마야?" 질문에 답할 때 호출한다.
        국내 종목은 약 20분 지연 시세일 수 있다.

        Args:
            symbol: 심볼 또는 한글 이름. 예: "005930.KS", "삼성전자", "AAPL"
        """
        return _dump(market.quote(symbol).as_dict())

    def get_stock_history(symbol: str, weeks: int = 12) -> str:
        """최근 몇 주간 매주 종가를 돌려준다. 흐름이 오르는지 내리는지 설명할 때 호출한다.

        Args:
            symbol: 심볼 또는 한글 이름
            weeks: 몇 주치를 볼지 (기본 12주, 최대 52주)
        """
        weeks = max(1, min(int(weeks), 52))
        return _dump(market.weekly_closes(symbol, weeks))

    def get_portfolio_status() -> str:
        """어머니의 보유 종목(현재가, 손익 포함)과 관심 종목 전체를 돌려준다.

        "내 주식 어때?", 아침 리포트, 전체 점검 요청에 가장 먼저 호출한다.
        """
        return _dump(portfolio.status(market))

    def add_holding(name: str, symbol: str, quantity: float, avg_price: float) -> str:
        """보유 종목을 등록하거나 수정한다.

        사용자가 어떤 종목을 몇 주, 얼마에 샀는지 말하면 호출한다. 같은 심볼이 있으면 덮어쓴다.

        Args:
            name: 종목 이름 (표시용). 예: "삼성전자"
            symbol: 심볼. 예: "005930.KS", "AAPL"
            quantity: 보유 수량 (주)
            avg_price: 평균 매수 단가 (원 또는 달러, 종목 통화 기준)
        """
        entry = portfolio.add_holding(name, symbol, quantity, avg_price)
        return f"등록됨: {_dump(entry)}"

    def remove_holding(symbol: str) -> str:
        """보유 종목을 목록에서 뺀다. 다 팔았다고 하면 호출한다.

        Args:
            symbol: 심볼 또는 한글 이름
        """
        return "삭제됨" if portfolio.remove_holding(symbol) else "그 종목은 목록에 없었습니다"

    def add_watchlist(name: str, symbol: str) -> str:
        """관심 종목을 등록한다. 사지는 않았지만 지켜보고 싶다고 하면 호출한다.

        Args:
            name: 종목 이름
            symbol: 심볼
        """
        return f"관심 종목 등록됨: {_dump(portfolio.add_watch(name, symbol))}"

    def remove_watchlist(symbol: str) -> str:
        """관심 종목에서 뺀다.

        Args:
            symbol: 심볼 또는 한글 이름
        """
        return "삭제됨" if portfolio.remove_watch(symbol) else "그 종목은 관심 목록에 없었습니다"

    return [
        Tool(find_stock, name="find_stock"),
        Tool(get_stock_quote, name="get_stock_quote"),
        Tool(get_stock_history, name="get_stock_history"),
        Tool(get_portfolio_status, name="get_portfolio_status"),
        Tool(add_holding, name="add_holding"),
        Tool(remove_holding, name="remove_holding"),
        Tool(add_watchlist, name="add_watchlist"),
        Tool(remove_watchlist, name="remove_watchlist"),
    ]
