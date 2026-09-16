"""터미널 REPL.

    agentsys            단일 에이전트 (계산기, 시각, 메모리, 작업 공간 파일 도구)
    agentsys --team     오케스트레이터 + 리서처/코더/리뷰어 워커
    agentsys --web      web_search 서버 도구 추가
"""

from __future__ import annotations

import argparse
import os
import sys

from .agent import Agent, AgentConfig, AgentError
from .builtin_tools import Workspace, calculator, current_time
from .events import ConsolePrinter
from .memory import FileMemory
from .orchestrator import Orchestrator
from .tools import ToolCall

SINGLE_SYSTEM = """당신은 도구를 활용하는 유능한 어시스턴트입니다.
정확한 숫자는 calculator 로, 현재 시각은 current_time 으로 확인하세요.
사용자에 대해 기억해 둘 만한 정보는 remember 로 저장하고, 필요하면 recall 로 찾아보세요.
파일 작업은 작업 공간 도구(list_files/read_file/write_file)만 사용하세요.
한국어로 간결하게 답하세요."""

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}


def build_single_agent(args: argparse.Namespace, printer: ConsolePrinter) -> Agent:
    workspace = Workspace(args.workspace)
    memory = FileMemory(args.memory)
    return Agent(
        name="assistant",
        system=SINGLE_SYSTEM,
        tools=[calculator, current_time, *memory.tools(), *workspace.tools()],
        config=AgentConfig(model=args.model, effort=args.effort),
        on_event=printer,
        approve=ask_approval,
        server_tools=[WEB_SEARCH_TOOL] if args.web else None,
    )


def build_team(args: argparse.Namespace, printer: ConsolePrinter) -> Orchestrator:
    workspace = Workspace(args.workspace)
    worker_config = AgentConfig(model=args.model, effort="medium")
    server_tools = [WEB_SEARCH_TOOL] if args.web else None

    researcher = Agent(
        name="researcher",
        description="주제를 조사하고 사실을 정리한다. 자료 조사, 비교, 요약에 적합.",
        system="당신은 리서처입니다. 주어진 주제를 조사하고 핵심 사실을 근거와 함께 구조적으로 정리하세요. "
        "모르는 것은 모른다고 하세요.",
        tools=[calculator, current_time, *workspace.tools(approve_writes=False)],
        config=worker_config,
        server_tools=server_tools,
    )
    coder = Agent(
        name="coder",
        description="코드를 작성하거나 수정하고 작업 공간에 파일로 저장한다.",
        system="당신은 시니어 개발자입니다. 요구사항에 맞는 코드를 작성하고, 결과물은 반드시 "
        "write_file 로 작업 공간에 저장한 뒤 파일 경로와 요약을 답하세요.",
        tools=[calculator, *workspace.tools(approve_writes=False)],
        config=worker_config,
    )
    reviewer = Agent(
        name="reviewer",
        description="작업 공간의 코드나 문서를 읽고 문제점과 개선안을 지적한다.",
        system="당신은 꼼꼼한 리뷰어입니다. 작업 공간의 파일을 읽고 버그, 누락, 개선점을 "
        "심각도 순으로 정리하세요. 칭찬보다 구체적인 지적을 우선하세요.",
        tools=[*workspace.tools(approve_writes=False)],
        config=worker_config,
    )
    return Orchestrator(
        [researcher, coder, reviewer],
        config=AgentConfig(model=args.model, effort=args.effort),
        on_event=printer,
    )


def ask_approval(call: ToolCall) -> bool:
    print(f"\n승인 요청: {call.name}({call.input})")
    answer = input("실행할까요? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agentsys", description="Claude 에이전트 REPL")
    parser.add_argument("--team", action="store_true", help="멀티 에이전트 팀 모드")
    parser.add_argument("--web", action="store_true", help="web_search 서버 도구 활성화")
    parser.add_argument("--model", default=AgentConfig.model, help="모델 ID")
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--workspace", default="workspace", help="파일 도구가 접근할 디렉터리")
    parser.add_argument("--memory", default=".agent_memory.json", help="메모리 파일 경로")
    parser.add_argument("--show-thinking", action="store_true", help="요약된 thinking 출력")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("경고: ANTHROPIC_API_KEY 가 설정되어 있지 않습니다. `ant auth login` 프로필이 없으면 실패합니다.")

    printer = ConsolePrinter(show_thinking=args.show_thinking)
    agent = build_team(args, printer) if args.team else build_single_agent(args, printer)
    mode = "팀" if args.team else "단일"
    print(f"agentsys {mode} 모드 (model={args.model}, effort={args.effort}). 종료: /quit, 초기화: /reset")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input in ("/quit", "/exit"):
            break
        if user_input == "/reset":
            agent.reset()
            print("히스토리를 비웠습니다.")
            continue
        try:
            result = agent.run(user_input)
        except AgentError as exc:
            print(f"\n오류: {exc}")
            continue
        u = result.usage
        print(f"\n[usage] requests={u.requests} in={u.input_tokens} out={u.output_tokens} "
              f"cache_read={u.cache_read_input_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
