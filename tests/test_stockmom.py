import json
from datetime import datetime, timedelta

import pytest

from conftest import make_message, text_block, tool_use_block
from stockmom import MarketData, Portfolio, build_agent, generate_report, normalize_symbol, save_report
from stockmom.notify import email_configured, send_email
from stockmom.tools import build_tools


class FakeMarket(MarketData):
    """네트워크 없이 정해진 가격을 돌려주는 시장 데이터."""

    def __init__(self, prices: dict[str, list[float]] | None = None) -> None:
        self.prices = prices or {}

    def _history(self, symbol, period):
        series = self.prices.get(symbol)
        if not series:
            return []
        start = datetime(2026, 1, 1)
        return [((start + timedelta(days=i)).strftime("%Y-%m-%d"), p) for i, p in enumerate(series)]

    def _meta(self, symbol):
        return {"currency": "KRW" if symbol.endswith((".KS", ".KQ")) else "USD"}

    def _search(self, query):
        return [{"symbol": "ZZZ", "name": f"검색:{query}", "exchange": "NMS"}]


def linear(start: float, end: float, n: int = 260) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


@pytest.mark.parametrize(
    "text,expected",
    [("삼성전자", "005930.KS"), ("삼성 전자", "005930.KS"), ("005930", "005930.KS"), ("aapl", "AAPL"),
     ("애플", "AAPL"), ("에코프로", "086520.KQ"), ("NVDA", "NVDA")],
)
def test_normalize_symbol(text, expected):
    assert normalize_symbol(text) == expected


def test_quote_computes_changes():
    market = FakeMarket({"005930.KS": linear(50000, 70000)})
    q = market.quote("삼성전자")
    assert q.symbol == "005930.KS" and q.name == "삼성전자" and q.currency == "KRW"
    assert q.price == 70000
    assert q.change_1y_pct == pytest.approx(40.0)
    assert q.change_1d_pct is not None and 0 < q.change_1d_pct < 1
    assert q.high_52w == 70000 and q.low_52w == 50000


def test_quote_falls_back_to_kosdaq_then_errors():
    market = FakeMarket({"123456.KQ": linear(10, 20)})
    assert market.quote("123456").symbol == "123456.KQ"
    with pytest.raises(LookupError):
        market.quote("없는종목")


def test_find_uses_alias_before_search():
    market = FakeMarket()
    assert market.find("애플") == [{"symbol": "AAPL", "name": "애플", "exchange": "US"}]
    assert market.find("이상한회사")[0]["symbol"] == "ZZZ"


def test_weekly_closes_samples_every_five_days():
    market = FakeMarket({"AAPL": linear(100, 200, 60)})
    rows = market.weekly_closes("AAPL", weeks=4)
    assert len(rows) == 4
    assert rows[-1]["close"] == 200
    assert rows[0]["date"] < rows[-1]["date"]


def test_portfolio_roundtrip_and_status(tmp_path):
    p = Portfolio(tmp_path / "pf.json")
    p.add_holding("삼성전자", "삼성전자", 10, 60000)
    p.add_holding("애플", "AAPL", 2, 150)
    p.add_watch("테슬라", "테슬라")
    assert [h["symbol"] for h in p.holdings()] == ["005930.KS", "AAPL"]
    assert p.watchlist() == [{"name": "테슬라", "symbol": "TSLA"}]

    market = FakeMarket({"005930.KS": linear(50000, 70000), "AAPL": linear(100, 120)})
    status = p.status(market)
    samsung, apple = status["holdings"]
    assert samsung["profit"] == 100000 and samsung["profit_pct"] == pytest.approx(16.67, abs=0.01)
    assert apple["currency"] == "USD" and apple["profit"] == -60
    assert status["totals_by_currency"]["KRW"]["profit"] == 100000
    assert status["totals_by_currency"]["USD"]["profit_pct"] == -20

    assert p.remove_holding("AAPL") is True
    assert p.remove_holding("AAPL") is False
    assert p.remove_watch("TSLA") is True
    with pytest.raises(ValueError):
        p.add_holding("x", "AAPL", 0, 1)

    # 조회 실패는 예외 대신 error 필드
    p.add_holding("유령", "GHOST", 1, 1)
    row = p.status(market)["holdings"][-1]
    assert "error" in row


def test_tools_schema_and_execution(tmp_path):
    market = FakeMarket({"005930.KS": linear(50000, 70000)})
    portfolio = Portfolio(tmp_path / "pf.json")
    tools = {t.name: t for t in build_tools(market, portfolio)}
    assert set(tools) == {
        "find_stock", "get_stock_quote", "get_stock_history", "get_portfolio_status",
        "add_holding", "remove_holding", "add_watchlist", "remove_watchlist",
    }
    quote = json.loads(tools["get_stock_quote"].run({"symbol": "삼성전자"}))
    assert quote["price"] == 70000
    assert "등록됨" in tools["add_holding"].run({"name": "삼성전자", "symbol": "005930", "quantity": 3, "avg_price": 65000})
    status = json.loads(tools["get_portfolio_status"].run({}))
    assert status["holdings"][0]["profit"] == 15000
    assert "찾지 못했습니다" not in tools["find_stock"].run({"query": "삼성전자"})
    assert tools["get_stock_history"].run({"symbol": "삼성전자", "weeks": 999}).count("date") == 52


def test_build_agent_wires_tools_and_web_search(fake_client, tmp_path):
    client = fake_client(make_message([text_block("안녕하세요 어머니")]))
    agent = build_agent(
        market=FakeMarket(), portfolio=Portfolio(tmp_path / "pf.json"),
        memory_path=tmp_path / "mem.json", client=client,
    )
    result = agent.run("안녕")
    assert result.text == "안녕하세요 어머니"
    params = client.calls[0]
    names = [t.get("name") for t in params["tools"]]
    assert "get_portfolio_status" in names and "remember" in names
    assert params["tools"][-1]["type"] == "web_search_20260209"
    assert "50대 어머니" in params["system"][0]["text"]


def test_morning_report_flow(fake_client, tmp_path):
    portfolio = Portfolio(tmp_path / "pf.json")
    portfolio.add_holding("삼성전자", "005930", 10, 60000)
    market = FakeMarket({"005930.KS": linear(50000, 70000)})
    client = fake_client(
        make_message([tool_use_block("get_portfolio_status", {}, id="s1")], stop_reason="tool_use"),
        make_message([text_block("# 📈 아침 브리핑\n\n삼성전자가 올랐어요.")]),
    )
    agent = build_agent(market=market, portfolio=portfolio, memory_path=tmp_path / "m.json", client=client)

    report = generate_report(agent, today=datetime(2026, 9, 16))
    assert report.startswith("# 📈 아침 브리핑")
    # 프롬프트에 날짜가 들어가고, 도구 결과가 모델에게 전달됐다
    assert "2026년 09월 16일" in client.calls[0]["messages"][0]["content"]
    tool_result = client.calls[1]["messages"][2]["content"][0]["content"]
    assert '"profit": 100000' in tool_result

    path = save_report(report, directory=tmp_path / "reports", today=datetime(2026, 9, 16))
    assert path.name == "2026-09-16.md" and path.read_text(encoding="utf-8") == report


def test_morning_report_refusal_message(fake_client, tmp_path):
    client = fake_client(make_message([text_block("")], stop_reason="refusal",
                                      stop_details={"type": "refusal", "category": "general_harms"}))
    agent = build_agent(market=FakeMarket(), portfolio=Portfolio(tmp_path / "pf.json"),
                        memory_path=tmp_path / "m.json", client=client)
    assert "만들지 못했어요" in generate_report(agent)


def test_send_email_uses_env_and_smtp():
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port):
            sent["host"], sent["port"] = host, port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self): sent["tls"] = True
        def login(self, u, p): sent["login"] = (u, p)
        def send_message(self, msg): sent["msg"] = msg

    env = {"SMTP_HOST": "smtp.test", "SMTP_PORT": "2525", "SMTP_USER": "me@test", "SMTP_PASSWORD": "pw", "MAIL_TO": "mom@test"}
    assert email_configured(env) is True
    assert email_configured({}) is False
    send_email("제목", "본문", env=env, smtp_factory=FakeSMTP)
    assert sent["host"] == "smtp.test" and sent["port"] == 2525 and sent["tls"] is True
    assert sent["msg"]["To"] == "mom@test" and sent["msg"]["Subject"] == "제목"
    with pytest.raises(RuntimeError):
        send_email("x", "y", env={})
