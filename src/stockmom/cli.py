"""stockmom 명령.

    stockmom chat                         어머니와 대화 (도구 사용 실시간)
    stockmom morning [--email]            아침 리포트 생성 (+이메일)
    stockmom add 삼성전자 005930 10 70000   보유 종목 등록
    stockmom watch 애플 AAPL              관심 종목 등록
    stockmom list                         등록된 종목 보기
"""

from __future__ import annotations

import argparse
import os
import sys

from agentsys import AgentConfig, AgentError, ConsolePrinter

from .agent import build_agent
from .market import MarketData
from .morning import generate_report, save_report
from .notify import email_configured, send_email
from .portfolio import DEFAULT_PORTFOLIO_PATH, Portfolio


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--portfolio", default=str(DEFAULT_PORTFOLIO_PATH), help="보유 종목 파일")
    parser.add_argument("--model", default=AgentConfig.model)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--no-web", action="store_true", help="웹 검색 끄기")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stockmom", description="어머니를 위한 주식 비서")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="대화 모드")
    _common(chat)
    chat.add_argument("--show-thinking", action="store_true")

    morning = sub.add_parser("morning", help="아침 리포트 생성")
    _common(morning)
    morning.add_argument("--email", action="store_true", help="이메일로도 보내기 (SMTP 환경변수 필요)")
    morning.add_argument("--out", default="reports", help="리포트 저장 폴더")

    add = sub.add_parser("add", help="보유 종목 등록")
    add.add_argument("name")
    add.add_argument("symbol")
    add.add_argument("quantity", type=float)
    add.add_argument("avg_price", type=float)
    add.add_argument("--portfolio", default=str(DEFAULT_PORTFOLIO_PATH))

    watch = sub.add_parser("watch", help="관심 종목 등록")
    watch.add_argument("name")
    watch.add_argument("symbol")
    watch.add_argument("--portfolio", default=str(DEFAULT_PORTFOLIO_PATH))

    lst = sub.add_parser("list", help="등록된 종목 보기")
    lst.add_argument("--portfolio", default=str(DEFAULT_PORTFOLIO_PATH))

    return parser.parse_args(argv)


def _warn_if_no_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("경고: ANTHROPIC_API_KEY 가 없습니다. 모델 호출이 실패할 수 있어요.", file=sys.stderr)


def cmd_chat(args: argparse.Namespace) -> int:
    _warn_if_no_key()
    agent = build_agent(
        portfolio=Portfolio(args.portfolio),
        config=AgentConfig(model=args.model, effort=args.effort),
        on_event=ConsolePrinter(show_thinking=args.show_thinking),
        web_search=not args.no_web,
    )
    print("주식 도우미예요. 궁금한 걸 편하게 물어보세요. (그만하려면 /quit)")
    while True:
        try:
            text = input("\n어머니> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text in ("/quit", "/exit", "그만"):
            return 0
        try:
            agent.run(text)
        except AgentError as exc:
            print(f"\n문제가 생겼어요: {exc}")
    return 0


def cmd_morning(args: argparse.Namespace) -> int:
    _warn_if_no_key()
    agent = build_agent(
        portfolio=Portfolio(args.portfolio),
        config=AgentConfig(model=args.model, effort=args.effort),
        on_event=ConsolePrinter(),
        web_search=not args.no_web,
    )
    report = generate_report(agent)
    path = save_report(report, directory=args.out)
    print(f"\n리포트 저장: {path}")
    if args.email:
        if not email_configured():
            print("이메일 환경변수(SMTP_HOST, SMTP_USER, SMTP_PASSWORD, MAIL_TO)가 없어 발송을 건너뜁니다.")
        else:
            subject = report.splitlines()[0].lstrip("# ").strip() if report else "아침 주식 브리핑"
            send_email(subject, report)
            print(f"이메일 발송 완료: {os.environ.get('MAIL_TO')}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    entry = Portfolio(args.portfolio).add_holding(args.name, args.symbol, args.quantity, args.avg_price)
    print(f"등록: {entry}")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    entry = Portfolio(args.portfolio).add_watch(args.name, args.symbol)
    print(f"관심 종목: {entry}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    p = Portfolio(args.portfolio)
    print("보유 종목:")
    for h in p.holdings() or []:
        print(f"  - {h['name']} ({h['symbol']}): {h['quantity']}주 @ {h['avg_price']}")
    if not p.holdings():
        print("  (없음)")
    print("관심 종목:")
    for w in p.watchlist() or []:
        print(f"  - {w['name']} ({w['symbol']})")
    if not p.watchlist():
        print("  (없음)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return {"chat": cmd_chat, "morning": cmd_morning, "add": cmd_add, "watch": cmd_watch, "list": cmd_list}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
