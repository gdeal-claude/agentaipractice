"""API 키 없이 에이전트 루프를 검증하기 위한 가짜 Anthropic 클라이언트."""

from __future__ import annotations

import itertools
from typing import Any

import pytest
from anthropic.types.beta import BetaMessage

_ids = itertools.count(1)


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def tool_use_block(name: str, input: dict[str, Any], id: str | None = None) -> dict[str, Any]:
    return {"type": "tool_use", "id": id or f"toolu_{next(_ids)}", "name": name, "input": input}


def make_message(
    content: list[dict[str, Any]],
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
    stop_details: dict[str, Any] | None = None,
) -> BetaMessage:
    payload: dict[str, Any] = {
        "id": f"msg_{next(_ids)}",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    if stop_details is not None:
        payload["stop_details"] = stop_details
    return BetaMessage.model_validate(payload)


class FakeStream:
    def __init__(self, message: BetaMessage) -> None:
        self.message = message

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def __iter__(self):
        # 실제 스트림처럼 텍스트 델타 이벤트를 흉내낸다
        for block in self.message.content:
            if block.type == "text":
                yield type("TextEvent", (), {"type": "text", "text": block.text})()

    def get_final_message(self) -> BetaMessage:
        return self.message


class FakeMessages:
    def __init__(self, scripted: list[BetaMessage]) -> None:
        self.scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []

    def stream(self, **params: Any) -> FakeStream:
        # 요청 시점의 messages 스냅샷을 남긴다 (리스트가 이후에 변형되므로)
        snapshot = dict(params)
        snapshot["messages"] = [dict(m) for m in params["messages"]]
        self.calls.append(snapshot)
        if not self.scripted:
            raise AssertionError("스크립트된 응답이 더 없는데 모델이 호출되었습니다")
        return FakeStream(self.scripted.pop(0))


class FakeClient:
    """``client.beta.messages.stream(...)`` 만 흉내내는 최소 클라이언트."""

    def __init__(self, scripted: list[BetaMessage]) -> None:
        self.messages = FakeMessages(scripted)
        self.beta = type("Beta", (), {"messages": self.messages})()

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.messages.calls


@pytest.fixture
def fake_client():
    def factory(*messages: BetaMessage) -> FakeClient:
        return FakeClient(list(messages))

    return factory
