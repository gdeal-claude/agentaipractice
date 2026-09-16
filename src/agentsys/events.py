"""에이전트가 실행 중에 내보내는 이벤트.

UI, 로깅, 테스트에서 에이전트 내부를 관찰할 때 사용합니다.
``Agent(on_event=콜백)`` 으로 등록하면 아래 ``kind`` 를 가진 이벤트가 순서대로 옵니다.

* ``request``      모델 호출 직전 (iteration, message_count)
* ``text_delta``   스트리밍 텍스트 조각 (text)
* ``thinking``     요약된 thinking 블록 (text)
* ``text``         완성된 텍스트 블록 (text)
* ``tool_call``    모델이 요청한 도구 호출 (id, name, input)
* ``tool_result``  도구 실행 결과 (id, name, content, is_error)
* ``tool_denied``  승인 게이트에서 거부됨 (id, name)
* ``turn_end``     모델 응답 하나가 끝남 (stop_reason, usage)
* ``refusal``      정책상 거부 (category, explanation)
* ``done``         run() 종료 (iterations, usage)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable, TextIO

__all__ = ["AgentEvent", "EventHandler", "ConsolePrinter", "EventCollector"]


@dataclass
class AgentEvent:
    kind: str
    agent: str
    data: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[AgentEvent], None]


class EventCollector:
    """테스트용: 이벤트를 리스트에 모은다."""

    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def __call__(self, event: AgentEvent) -> None:
        self.events.append(event)

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]


class ConsolePrinter:
    """CLI 용: 스트리밍 텍스트와 도구 호출을 터미널에 출력한다."""

    def __init__(self, stream: TextIO | None = None, *, show_thinking: bool = False) -> None:
        self.stream = stream or sys.stdout
        self.show_thinking = show_thinking
        self._line_open = False

    def _write(self, text: str) -> None:
        self.stream.write(text)
        self.stream.flush()

    def _newline(self) -> None:
        if self._line_open:
            self._write("\n")
            self._line_open = False

    def __call__(self, event: AgentEvent) -> None:
        d = event.data
        prefix = f"[{event.agent}]"
        if event.kind == "text_delta":
            self._write(d["text"])
            self._line_open = True
        elif event.kind == "thinking" and self.show_thinking and d.get("text"):
            self._newline()
            self._write(f"{prefix} (thinking) {d['text'].strip()}\n")
        elif event.kind == "tool_call":
            self._newline()
            self._write(f"{prefix} -> {d['name']}({_short(d['input'])})\n")
        elif event.kind == "tool_result":
            self._newline()
            tag = "error" if d["is_error"] else "ok"
            self._write(f"{prefix} <- {d['name']} [{tag}] {_short(d['content'])}\n")
        elif event.kind == "tool_denied":
            self._newline()
            self._write(f"{prefix} x {d['name']} 사용자가 거부함\n")
        elif event.kind == "refusal":
            self._newline()
            self._write(f"{prefix} 모델이 요청을 거부했습니다 (category={d.get('category')})\n")
        elif event.kind == "done":
            self._newline()


def _short(value: Any, limit: int = 120) -> str:
    text = value if isinstance(value, str) else repr(value)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."
