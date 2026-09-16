"""주가 데이터 조회 (국내 + 미국).

yfinance 를 사용합니다. 국내 종목은 6자리 코드 뒤에 ``.KS``(코스피) 또는 ``.KQ``(코스닥)
가 붙은 심볼을 씁니다. 자주 찾는 종목은 한글 이름으로 바로 찾을 수 있게 별칭 표를 둡니다.

테스트에서는 :class:`MarketData` 를 상속해 ``_history`` / ``_meta`` / ``_search`` 만 바꿔 끼웁니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = ["MarketData", "Quote", "KR_ALIASES", "US_ALIASES", "normalize_symbol"]

# 자주 묻는 국내 종목 (이름 -> 야후 심볼)
KR_ALIASES: dict[str, str] = {
    "삼성전자": "005930.KS", "삼성전자우": "005935.KS", "SK하이닉스": "000660.KS",
    "현대차": "005380.KS", "현대자동차": "005380.KS", "기아": "000270.KS",
    "네이버": "035420.KS", "NAVER": "035420.KS", "카카오": "035720.KS",
    "LG에너지솔루션": "373220.KS", "삼성바이오로직스": "207940.KS", "셀트리온": "068270.KS",
    "POSCO홀딩스": "005490.KS", "포스코홀딩스": "005490.KS", "KB금융": "105560.KS",
    "신한지주": "055550.KS", "하나금융지주": "086790.KS", "삼성SDI": "006400.KS",
    "LG화학": "051910.KS", "현대모비스": "012330.KS", "삼성물산": "028260.KS",
    "SK이노베이션": "096770.KS", "한국전력": "015760.KS", "LG전자": "066570.KS",
    "삼성생명": "032830.KS", "KT&G": "033780.KS", "SK텔레콤": "017670.KS", "KT": "030200.KS",
    "한화에어로스페이스": "012450.KS", "HD현대중공업": "329180.KS", "두산에너빌리티": "034020.KS",
    "에코프로": "086520.KQ", "에코프로비엠": "247540.KQ", "알테오젠": "196170.KQ", "HLB": "028300.KQ",
}

# 자주 묻는 미국 종목 (한글 이름 -> 심볼)
US_ALIASES: dict[str, str] = {
    "애플": "AAPL", "테슬라": "TSLA", "엔비디아": "NVDA", "마이크로소프트": "MSFT",
    "구글": "GOOGL", "알파벳": "GOOGL", "아마존": "AMZN", "메타": "META", "페이스북": "META",
    "넷플릭스": "NFLX", "코카콜라": "KO", "버크셔": "BRK-B", "버크셔해서웨이": "BRK-B",
    "브로드컴": "AVGO", "인텔": "INTC", "팔란티어": "PLTR", "코스트코": "COST",
    "월마트": "WMT", "존슨앤존슨": "JNJ", "비자": "V", "마스터카드": "MA", "디즈니": "DIS",
    "S&P500": "SPY", "나스닥100": "QQQ", "코스피": "^KS11", "코스닥": "^KQ11", "나스닥": "^IXIC",
}

_KR_CODE = re.compile(r"^\d{6}$")


def normalize_symbol(text: str) -> str:
    """사용자 입력을 야후 심볼로 정리한다. 별칭 표, 6자리 코드, 대문자화를 처리한다."""
    raw = text.strip()
    key = raw.replace(" ", "")
    for table in (KR_ALIASES, US_ALIASES):
        for name, symbol in table.items():
            if key.lower() == name.lower():
                return symbol
    if _KR_CODE.match(key):
        return f"{key}.KS"
    return key.upper()


@dataclass
class Quote:
    symbol: str
    name: str
    currency: str
    price: float
    as_of: str
    change_1d_pct: float | None
    change_1w_pct: float | None
    change_1m_pct: float | None
    change_3m_pct: float | None
    change_1y_pct: float | None
    high_52w: float | None
    low_52w: float | None

    def as_dict(self) -> dict[str, Any]:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


class MarketData:
    """주가 조회 진입점. 네트워크 부분은 ``_history`` / ``_meta`` / ``_search`` 에만 있다."""

    # -- 네트워크 (테스트에서 덮어쓴다) ----------------------------------------
    def _history(self, symbol: str, period: str) -> list[tuple[str, float]]:
        """(날짜 'YYYY-MM-DD', 종가) 리스트를 오래된 순으로 돌려준다."""
        import yfinance as yf  # 지연 임포트: 테스트는 이 함수를 쓰지 않는다

        hist = yf.Ticker(symbol).history(period=period, auto_adjust=True)
        if hist is None or hist.empty:
            return []
        return [(idx.strftime("%Y-%m-%d"), float(close)) for idx, close in hist["Close"].items()]

    def _meta(self, symbol: str) -> dict[str, Any]:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        meta: dict[str, Any] = {}
        try:
            fast = ticker.fast_info
            meta["currency"] = fast.currency
            meta["high_52w"] = fast.year_high
            meta["low_52w"] = fast.year_low
        except Exception:
            pass
        try:
            info = ticker.info or {}
            meta["name"] = info.get("shortName") or info.get("longName")
        except Exception:
            pass
        return meta

    def _search(self, query: str) -> list[dict[str, Any]]:
        import yfinance as yf

        try:
            result = yf.Search(query, max_results=8)
            return [
                {"symbol": q.get("symbol"), "name": q.get("shortname") or q.get("longname"), "exchange": q.get("exchange")}
                for q in result.quotes
                if q.get("symbol")
            ]
        except Exception:
            return []

    # -- 공개 API ------------------------------------------------------------
    def find(self, query: str) -> list[dict[str, Any]]:
        """이름이나 코드로 종목 후보를 찾는다. 별칭 표에 있으면 그것만 돌려준다."""
        normalized = normalize_symbol(query)
        for table in (KR_ALIASES, US_ALIASES):
            for name, symbol in table.items():
                if symbol == normalized and query.replace(" ", "").lower() == name.lower():
                    return [{"symbol": symbol, "name": name, "exchange": "KRX" if symbol.endswith((".KS", ".KQ")) else "US"}]
        return self._search(query)

    def quote(self, symbol_or_name: str) -> Quote:
        symbol = normalize_symbol(symbol_or_name)
        closes = self._history(symbol, "1y")
        if not closes and symbol.endswith(".KS"):
            # 코스닥 종목일 수 있다
            symbol = symbol[:-3] + ".KQ"
            closes = self._history(symbol, "1y")
        if not closes:
            raise LookupError(f"'{symbol_or_name}' 의 시세를 찾지 못했습니다. find_stock 으로 정확한 심볼을 먼저 찾으세요.")

        meta = self._meta(symbol)
        prices = [c for _, c in closes]
        last_date, last = closes[-1]

        def change(n: int) -> float | None:
            if len(prices) > n and prices[-1 - n]:
                return (last / prices[-1 - n] - 1) * 100
            return None

        year = (last / prices[0] - 1) * 100 if len(prices) > 1 and prices[0] else None
        return Quote(
            symbol=symbol,
            name=meta.get("name") or _alias_name(symbol) or symbol,
            currency=meta.get("currency") or ("KRW" if symbol.endswith((".KS", ".KQ")) else "USD"),
            price=last,
            as_of=last_date,
            change_1d_pct=change(1),
            change_1w_pct=change(5),
            change_1m_pct=change(21),
            change_3m_pct=change(63),
            change_1y_pct=year,
            high_52w=meta.get("high_52w") or max(prices),
            low_52w=meta.get("low_52w") or min(prices),
        )

    def weekly_closes(self, symbol_or_name: str, weeks: int = 12) -> list[dict[str, Any]]:
        """최근 N주 동안 매주 마지막 거래일 종가. 흐름을 짧게 설명할 때 쓴다."""
        symbol = normalize_symbol(symbol_or_name)
        closes = self._history(symbol, "1y")
        if not closes:
            raise LookupError(f"'{symbol_or_name}' 의 시세를 찾지 못했습니다.")
        # 5 거래일 간격으로 뒤에서부터 표본을 뽑는다
        sampled = closes[::-1][::5][:weeks][::-1]
        return [{"date": d, "close": round(c, 2)} for d, c in sampled]


def _alias_name(symbol: str) -> str | None:
    for table in (KR_ALIASES, US_ALIASES):
        for name, sym in table.items():
            if sym == symbol:
                return name
    return None
