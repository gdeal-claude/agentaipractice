"""어머니의 보유 종목과 관심 종목을 JSON 파일 하나에 저장한다."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .market import MarketData, normalize_symbol

__all__ = ["Portfolio", "DEFAULT_PORTFOLIO_PATH"]

DEFAULT_PORTFOLIO_PATH = Path("data/portfolio.json")


class Portfolio:
    def __init__(self, path: str | Path = DEFAULT_PORTFOLIO_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    # -- 저장소 --------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"holdings": [], "watchlist": []}
        data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        data.setdefault("holdings", [])
        data.setdefault("watchlist", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # -- 보유 종목 -----------------------------------------------------------
    def holdings(self) -> list[dict[str, Any]]:
        return self._load()["holdings"]

    def watchlist(self) -> list[dict[str, Any]]:
        return self._load()["watchlist"]

    def add_holding(self, name: str, symbol: str, quantity: float, avg_price: float) -> dict[str, Any]:
        symbol = normalize_symbol(symbol)
        if quantity <= 0 or avg_price <= 0:
            raise ValueError("수량과 평균 매수가는 0보다 커야 합니다")
        with self._lock:
            data = self._load()
            entry = {"name": name, "symbol": symbol, "quantity": quantity, "avg_price": avg_price}
            data["holdings"] = [h for h in data["holdings"] if h["symbol"] != symbol] + [entry]
            self._save(data)
        return entry

    def remove_holding(self, symbol: str) -> bool:
        symbol = normalize_symbol(symbol)
        with self._lock:
            data = self._load()
            before = len(data["holdings"])
            data["holdings"] = [h for h in data["holdings"] if h["symbol"] != symbol]
            self._save(data)
        return len(data["holdings"]) < before

    def add_watch(self, name: str, symbol: str) -> dict[str, Any]:
        symbol = normalize_symbol(symbol)
        with self._lock:
            data = self._load()
            entry = {"name": name, "symbol": symbol}
            data["watchlist"] = [w for w in data["watchlist"] if w["symbol"] != symbol] + [entry]
            self._save(data)
        return entry

    def remove_watch(self, symbol: str) -> bool:
        symbol = normalize_symbol(symbol)
        with self._lock:
            data = self._load()
            before = len(data["watchlist"])
            data["watchlist"] = [w for w in data["watchlist"] if w["symbol"] != symbol]
            self._save(data)
        return len(data["watchlist"]) < before

    # -- 평가 ----------------------------------------------------------------
    def status(self, market: MarketData) -> dict[str, Any]:
        """보유 종목마다 현재가와 손익을 붙여 돌려준다. 조회 실패는 error 필드로 남긴다."""
        rows: list[dict[str, Any]] = []
        totals: dict[str, dict[str, float]] = {}
        for h in self.holdings():
            row = dict(h)
            try:
                q = market.quote(h["symbol"])
                value = q.price * h["quantity"]
                cost = h["avg_price"] * h["quantity"]
                row.update(
                    price=round(q.price, 2),
                    currency=q.currency,
                    as_of=q.as_of,
                    value=round(value, 2),
                    profit=round(value - cost, 2),
                    profit_pct=round((value / cost - 1) * 100, 2) if cost else None,
                    change_1d_pct=None if q.change_1d_pct is None else round(q.change_1d_pct, 2),
                    change_1m_pct=None if q.change_1m_pct is None else round(q.change_1m_pct, 2),
                )
                t = totals.setdefault(q.currency, {"value": 0.0, "cost": 0.0})
                t["value"] += value
                t["cost"] += cost
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
        summary = {
            cur: {
                "value": round(t["value"], 2),
                "cost": round(t["cost"], 2),
                "profit": round(t["value"] - t["cost"], 2),
                "profit_pct": round((t["value"] / t["cost"] - 1) * 100, 2) if t["cost"] else None,
            }
            for cur, t in totals.items()
        }
        return {"holdings": rows, "totals_by_currency": summary, "watchlist": self.watchlist()}
