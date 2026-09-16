"""단일 에이전트: 모델 호출 <-> 도구 실행 루프를 직접 소유한다.

SDK 의 tool runner 대신 루프를 직접 쓰는 이유:

* 승인 게이트, 이벤트 스트림, 토큰 집계, 최대 반복 횟수 같은 제어를 한곳에서 관리
* ``client`` 를 주입할 수 있어 API 키 없이도 테스트 가능
* 오케스트레이터가 같은 루프를 재사용해 하위 에이전트를 도구처럼 호출
"""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Literal, Sequence

import anthropic

from .events import AgentEvent, EventHandler
from .tools import Tool, ToolCall, ToolInputError, ToolRegistry

__all__ = [
    "Agent",
    "AgentConfig",
    "AgentError",
    "ContextWindowExceeded",
    "RunResult",
    "Usage",
    "DEFAULT_MODEL",
]

DEFAULT_MODEL = "claude-opus-5"
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"

CONTINUE_PROMPT = (
    "이전 응답이 출력 토큰 한도에 걸려 잘렸습니다. "
    "앞부분을 반복하지 말고 끊긴 지점부터 이어서 완성하세요."
)


class AgentError(RuntimeError):
    """에이전트 루프가 정상 종료하지 못했을 때."""


class ContextWindowExceeded(AgentError):
    """대화가 모델 컨텍스트 창을 넘었을 때. reset() 하거나 히스토리를 줄여야 한다."""


@dataclass
class AgentConfig:
    model: str = DEFAULT_MODEL
    # 스트리밍이므로 넉넉히 준다. 한도에 걸리면 한 번 이어쓰기를 시도한다.
    max_tokens: int = 64000
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    thinking_display: Literal["summarized", "omitted"] = "summarized"
    max_iterations: int = 30
    # 정책상 거부 시 서버가 대체 모델로 같은 요청을 다시 실행하도록 한다.
    refusal_fallbacks: bool = True
    parallel_tools: bool = True
    cache_system_prompt: bool = True


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    requests: int = 0

    def add(self, usage: Any) -> None:
        self.requests += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_creation_input_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    def merge(self, other: "Usage") -> None:
        self.requests += other.requests
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class RunResult:
    text: str
    stop_reason: str
    iterations: int
    usage: Usage
    refused: bool = False
    refusal_category: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


ApprovalHandler = Callable[[ToolCall], bool]


class Agent:
    """도구를 쓰는 대화형 에이전트.

    Args:
        name: 이벤트/로그와 오케스트레이터에서 이 에이전트를 부르는 이름.
        system: 시스템 프롬프트. 실행 중 바꾸지 않아야 프롬프트 캐시가 유지된다.
        tools: ``Tool`` 또는 일반 함수 목록.
        description: 오케스트레이터가 어떤 일을 맡길지 판단할 때 쓰는 설명.
        client: ``anthropic.Anthropic`` 호환 객체. 테스트에서는 가짜 클라이언트를 넣는다.
        config: 모델/토큰/반복 설정.
        on_event: 이벤트 콜백 (:mod:`agentsys.events` 참고).
        approve: ``requires_approval=True`` 인 도구 호출 전에 불리는 승인 함수.
            없으면 그런 도구는 자동 거부된다.
        server_tools: 서버 측 도구 정의 dict 목록 (예: web_search).
    """

    def __init__(
        self,
        *,
        name: str = "agent",
        system: str,
        tools: Iterable[Tool | Callable[..., Any]] | None = None,
        description: str = "",
        client: Any | None = None,
        config: AgentConfig | None = None,
        on_event: EventHandler | None = None,
        approve: ApprovalHandler | None = None,
        server_tools: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self.system = system
        self.description = description
        self.tools = ToolRegistry(tools)
        self.client = client or anthropic.Anthropic()
        self.config = config or AgentConfig()
        self.on_event = on_event
        self.approve = approve
        self.server_tools = list(server_tools or [])
        self.messages: list[dict[str, Any]] = []
        self.total_usage = Usage()

    # ------------------------------------------------------------------ 상태
    def reset(self) -> None:
        """대화 히스토리를 비운다."""
        self.messages = []

    def spawn(self, *, name: str | None = None) -> "Agent":
        """같은 설정과 도구를 가진, 히스토리가 빈 새 에이전트를 만든다.

        오케스트레이터가 작업마다 독립된 워커를 띄울 때 쓴다.
        """
        clone = copy.copy(self)
        clone.name = name or self.name
        clone.messages = []
        clone.total_usage = Usage()
        clone.config = replace(self.config)
        return clone

    # ------------------------------------------------------------------ 실행
    def run(self, user_input: str | list[dict[str, Any]], *, reset: bool = False) -> RunResult:
        """사용자 입력 하나를 처리해 최종 답을 돌려준다.

        히스토리는 인스턴스에 누적되므로 여러 번 부르면 멀티턴 대화가 된다.
        """
        if reset:
            self.reset()
        self.messages.append({"role": "user", "content": user_input})

        usage = Usage()
        tool_calls: list[ToolCall] = []
        carried_text = ""
        continued_after_cutoff = False

        for iteration in range(1, self.config.max_iterations + 1):
            self._emit("request", iteration=iteration, message_count=len(self.messages))
            message = self._call_model()
            usage.add(message.usage)
            self.total_usage.add(message.usage)

            # thinking/tool_use 블록을 그대로 되돌려 보내야 하므로 content 전체를 보존한다.
            self.messages.append({"role": "assistant", "content": message.content})
            self._emit_blocks(message)
            stop_reason = message.stop_reason or "end_turn"
            self._emit("turn_end", stop_reason=stop_reason, usage=usage.as_dict())

            if stop_reason == "tool_use":
                calls = self._pending_tool_calls(message)
                if not calls:
                    # 서버 측 도구만 있었던 경우 등: 이어서 진행
                    continue
                tool_calls.extend(calls)
                results = self._execute_tool_calls(calls)
                # 병렬 호출 결과는 반드시 하나의 user 메시지에 모두 담는다.
                self.messages.append({"role": "user", "content": results})
                carried_text = ""
                continue

            if stop_reason in ("pause_turn", "compaction"):
                # 서버 측 도구 루프 일시정지 / 압축 블록 수신: 그대로 다시 요청하면 이어진다.
                continue

            if stop_reason == "max_tokens":
                if continued_after_cutoff:
                    raise AgentError("출력이 두 번 연속 max_tokens 에 걸렸습니다. max_tokens 를 늘리세요.")
                continued_after_cutoff = True
                carried_text += self._text_of(message)
                self.messages.append({"role": "user", "content": CONTINUE_PROMPT})
                continue

            if stop_reason == "refusal":
                details = getattr(message, "stop_details", None)
                category = getattr(details, "category", None)
                self._emit("refusal", category=category, explanation=getattr(details, "explanation", None))
                self._emit("done", iterations=iteration, usage=usage.as_dict())
                return RunResult(
                    text=carried_text + self._text_of(message),
                    stop_reason=stop_reason,
                    iterations=iteration,
                    usage=usage,
                    refused=True,
                    refusal_category=category,
                    tool_calls=tool_calls,
                )

            if stop_reason == "model_context_window_exceeded":
                raise ContextWindowExceeded(
                    "대화가 컨텍스트 창을 넘었습니다. reset() 하거나 히스토리를 줄이세요."
                )

            # end_turn, stop_sequence
            self._emit("done", iterations=iteration, usage=usage.as_dict())
            return RunResult(
                text=carried_text + self._text_of(message),
                stop_reason=stop_reason,
                iterations=iteration,
                usage=usage,
                tool_calls=tool_calls,
            )

        raise AgentError(f"max_iterations({self.config.max_iterations}) 에 도달했습니다.")

    # ------------------------------------------------------------------ 모델 호출
    def _request_params(self) -> dict[str, Any]:
        cfg = self.config
        system: Any = self.system
        if cfg.cache_system_prompt:
            system = [{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}]
        params: dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "system": system,
            "messages": self.messages,
            "thinking": {"type": "adaptive", "display": cfg.thinking_display},
            "output_config": {"effort": cfg.effort},
            # 대화 꼬리까지 자동으로 캐시 브레이크포인트를 잡는다.
            "cache_control": {"type": "ephemeral"},
        }
        tools = self.tools.params(streaming=True) + self.server_tools
        if tools:
            params["tools"] = tools
        if cfg.refusal_fallbacks:
            params["betas"] = [REFUSAL_FALLBACK_BETA]
            params["fallbacks"] = "default"
        return params

    def _call_model(self) -> Any:
        params = self._request_params()
        with self.client.beta.messages.stream(**params) as stream:
            for event in stream:
                if getattr(event, "type", None) == "text":
                    self._emit("text_delta", text=event.text)
            return stream.get_final_message()

    # ------------------------------------------------------------------ 도구 실행
    @staticmethod
    def _pending_tool_calls(message: Any) -> list[ToolCall]:
        return [
            ToolCall(id=block.id, name=block.name, input=dict(block.input or {}))
            for block in message.content
            if getattr(block, "type", None) == "tool_use"
        ]

    def _execute_tool_calls(self, calls: list[ToolCall]) -> list[dict[str, Any]]:
        if self.config.parallel_tools and len(calls) > 1:
            with ThreadPoolExecutor(max_workers=len(calls)) as pool:
                return list(pool.map(self._execute_one, calls))
        return [self._execute_one(call) for call in calls]

    def _execute_one(self, call: ToolCall) -> dict[str, Any]:
        self._emit("tool_call", id=call.id, name=call.name, input=call.input)
        tool = self.tools.get(call.name)
        if tool is None:
            return self._tool_result(call, f"알 수 없는 도구: {call.name}", is_error=True)

        if tool.requires_approval:
            allowed = bool(self.approve and self.approve(call))
            if not allowed:
                self._emit("tool_denied", id=call.id, name=call.name)
                return self._tool_result(call, "사용자가 이 도구 호출을 거부했습니다.", is_error=True)

        try:
            content = tool.run(call.input)
            return self._tool_result(call, content)
        except ToolInputError as exc:
            return self._tool_result(call, f"입력 검증 실패: {exc}", is_error=True)
        except Exception as exc:  # 도구 자체의 예외는 모델에게 알려 재시도하게 한다
            return self._tool_result(call, f"{type(exc).__name__}: {exc}", is_error=True)

    def _tool_result(self, call: ToolCall, content: str, *, is_error: bool = False) -> dict[str, Any]:
        self._emit("tool_result", id=call.id, name=call.name, content=content, is_error=is_error)
        result: dict[str, Any] = {"type": "tool_result", "tool_use_id": call.id, "content": content}
        if is_error:
            result["is_error"] = True
        return result

    # ------------------------------------------------------------------ 유틸
    @staticmethod
    def _text_of(message: Any) -> str:
        return "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )

    def _emit_blocks(self, message: Any) -> None:
        for block in message.content:
            kind = getattr(block, "type", None)
            if kind == "thinking" and getattr(block, "thinking", ""):
                self._emit("thinking", text=block.thinking)
            elif kind == "text":
                self._emit("text", text=block.text)

    def _emit(self, kind: str, **data: Any) -> None:
        if self.on_event is not None:
            self.on_event(AgentEvent(kind=kind, agent=self.name, data=data))
