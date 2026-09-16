"""멀티 에이전트 예제: 오케스트레이터가 코더와 리뷰어에게 위임.

실행: ANTHROPIC_API_KEY=... python examples/02_multi_agent.py
결과물은 ./workspace 에 저장된다.
"""

from agentsys import Agent, AgentConfig, ConsolePrinter, Orchestrator, Workspace

ws = Workspace("workspace")
printer = ConsolePrinter()
worker_config = AgentConfig(effort="medium")

coder = Agent(
    name="coder",
    description="요구사항대로 파이썬 코드를 작성해 작업 공간에 파일로 저장한다.",
    system="당신은 시니어 파이썬 개발자입니다. 코드는 write_file 로 저장하고 파일 경로와 요약을 답하세요.",
    tools=ws.tools(approve_writes=False),
    config=worker_config,
)
reviewer = Agent(
    name="reviewer",
    description="작업 공간의 코드를 읽고 버그와 개선점을 심각도 순으로 지적한다.",
    system="당신은 꼼꼼한 코드 리뷰어입니다. 파일을 read_file 로 읽고 구체적으로 지적하세요.",
    tools=ws.tools(approve_writes=False),
    config=worker_config,
)

team = Orchestrator([coder, reviewer], on_event=printer)
result = team.run(
    "문자열 유틸 모듈 text_utils.py 를 만들어 줘. slugify, truncate, word_count 함수가 필요해. "
    "리뷰어에게 리뷰받고 지적 사항을 반영한 최종본을 저장해 줘."
)
print("\n---")
print(result.text)
print("오케스트레이터 토큰:", result.usage.as_dict())
print("워커 토큰:", team.worker_usage.as_dict())
