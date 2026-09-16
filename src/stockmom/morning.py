"""아침 리포트 생성: 에이전트를 한 번 돌려 마크다운 파일로 저장하고, 설정돼 있으면 이메일로 보낸다."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agentsys import Agent

from .prompts import MORNING_REPORT_PROMPT

__all__ = ["generate_report", "save_report"]

KST = ZoneInfo("Asia/Seoul")


def generate_report(agent: Agent, *, today: datetime | None = None) -> str:
    today = today or datetime.now(KST)
    prompt = MORNING_REPORT_PROMPT.replace("{date}", today.strftime("%Y년 %m월 %d일 (%a)"))
    result = agent.run(prompt, reset=True)
    if result.refused:
        return f"# 오늘 리포트를 만들지 못했어요\n\n모델이 요청을 거부했습니다 (category={result.refusal_category})."
    return result.text.strip() + "\n"


def save_report(markdown: str, *, directory: str | Path = "reports", today: datetime | None = None) -> Path:
    today = today or datetime.now(KST)
    path = Path(directory) / f"{today.strftime('%Y-%m-%d')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path
