"""멀티 에이전트: 오케스트레이터가 워커 에이전트에게 작업을 위임한다.

오케스트레이터는 그냥 :class:`Agent` 이고, ``delegate`` 도구 하나가 추가됩니다.
모델이 ``delegate(worker=..., task=...)`` 를 부르면 해당 워커의 새 인스턴스가
독립된 히스토리로 작업을 수행하고 최종 텍스트만 돌려줍니다.
병렬 도구 호출이 켜져 있으면 여러 워커가 동시에 돌아갑니다.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Iterable, Literal, Sequence

from .agent import Agent, AgentConfig, Usage
from .events import EventHandler
from .tools import Tool

__all__ = ["Orchestrator"]

DEFAULT_ORCHESTRATOR_SYSTEM = """당신은 팀을 이끄는 오케스트레이터입니다.

사용자의 요청을 분석해 필요한 하위 작업으로 나누고, 각 작업을 가장 알맞은 워커에게
`delegate` 도구로 맡기세요. 서로 독립적인 작업은 한 번에 여러 개 위임해 병렬로 처리하세요.
워커는 이전 대화를 모르므로 task 에 필요한 맥락을 모두 담아 자족적으로 쓰세요.
워커 결과를 검토하고 부족하면 다시 위임하거나 직접 보완한 뒤, 최종 답을 사용자에게 정리해 주세요.
직접 답할 수 있는 간단한 요청은 위임 없이 바로 답하세요."""


class Orchestrator(Agent):
    """워커 에이전트들을 도구처럼 부르는 상위 에이전트."""

    def __init__(
        self,
        workers: Sequence[Agent],
        *,
        name: str = "orchestrator",
        system: str | None = None,
        tools: Iterable[Tool | Callable[..., Any]] | None = None,
        client: Any | None = None,
        config: AgentConfig | None = None,
        on_event: EventHandler | None = None,
        **kwargs: Any,
    ) -> None:
        if not workers:
            raise ValueError("워커가 최소 하나 필요합니다")
        self.workers: dict[str, Agent] = {}
        for worker in workers:
            if worker.name in self.workers:
                raise ValueError(f"워커 이름이 중복됩니다: {worker.name}")
            self.workers[worker.name] = worker
        self.worker_usage = Usage()
        self._usage_lock = threading.Lock()

        delegate_tool = self._build_delegate_tool()
        super().__init__(
            name=name,
            system=system or DEFAULT_ORCHESTRATOR_SYSTEM,
            tools=[delegate_tool, *(tools or ())],
            client=client,
            config=config,
            on_event=on_event,
            **kwargs,
        )

    def _build_delegate_tool(self) -> Tool:
        names = tuple(self.workers)
        roster = "\n".join(
            f"- {w.name}: {w.description or '(설명 없음)'}" for w in self.workers.values()
        )

        def delegate(worker: str, task: str) -> str:
            return self._delegate(worker, task)

        # 워커 이름을 enum 으로 노출해 모델이 없는 워커를 부르지 못하게 한다.
        delegate.__annotations__ = {"worker": Literal[names], "task": str, "return": str}
        delegate.__doc__ = f"""하위 작업을 전문 워커 에이전트에게 맡기고 결과 텍스트를 받는다.

여러 단계가 필요하거나 전문성이 필요한 작업일 때 호출한다.
독립적인 작업들은 한 응답에서 여러 번 호출해 병렬로 처리한다.

사용 가능한 워커:
{roster}

Args:
    worker: 작업을 맡길 워커 이름
    task: 워커에게 줄 자족적인 지시문. 워커는 이전 대화를 볼 수 없으므로 필요한 맥락과 기대 결과물을 모두 적는다.
"""
        return Tool(delegate, name="delegate")

    def _delegate(self, worker: str, task: str) -> str:
        template = self.workers.get(worker)
        if template is None:
            raise ValueError(f"없는 워커: {worker}. 사용 가능: {', '.join(self.workers)}")
        instance = template.spawn()
        if instance.on_event is None:
            instance.on_event = self.on_event
        result = instance.run(task)
        with self._usage_lock:
            self.worker_usage.merge(result.usage)
        if result.refused:
            return f"[워커 {worker} 가 정책상 요청을 거부했습니다: category={result.refusal_category}]"
        return result.text or "(워커가 빈 응답을 돌려줬습니다)"
