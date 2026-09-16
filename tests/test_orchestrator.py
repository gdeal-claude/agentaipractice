import pytest

from agentsys import Agent, EventCollector, Orchestrator
from conftest import FakeClient, make_message, text_block, tool_use_block


class RoutingClient:
    """model 별이 아니라 system 프롬프트로 응답을 골라 주는 가짜 클라이언트."""

    def __init__(self, scripts: dict[str, list]) -> None:
        self.clients = {key: FakeClient(msgs) for key, msgs in scripts.items()}
        self.beta = self

    @property
    def messages(self):
        return self

    def stream(self, **params):
        system_text = params["system"][0]["text"]
        for key, client in self.clients.items():
            if key in system_text:
                return client.messages.stream(**params)
        raise AssertionError(f"라우팅 실패: {system_text[:40]}")


def test_delegate_tool_schema_lists_workers(fake_client):
    coder = Agent(name="coder", description="코드 작성", system="CODER", client=fake_client())
    writer = Agent(name="writer", description="글 작성", system="WRITER", client=fake_client())
    orch = Orchestrator([coder, writer], client=fake_client())

    param = orch.tools.get("delegate").to_param()
    assert param["input_schema"]["properties"]["worker"]["enum"] == ["coder", "writer"]
    assert "coder: 코드 작성" in param["description"]
    assert "writer: 글 작성" in param["description"]


def test_orchestrator_delegates_and_collects_results():
    client = RoutingClient(
        {
            "ORCH": [
                make_message(
                    [
                        tool_use_block("delegate", {"worker": "coder", "task": "함수 짜"}, id="d1"),
                        tool_use_block("delegate", {"worker": "writer", "task": "문서 써"}, id="d2"),
                    ],
                    stop_reason="tool_use",
                ),
                make_message([text_block("둘 다 끝났습니다")]),
            ],
            "CODER": [make_message([text_block("def f(): pass")], output_tokens=50)],
            "WRITER": [make_message([text_block("# 문서")], output_tokens=20)],
        }
    )
    events = EventCollector()
    coder = Agent(name="coder", description="코드", system="CODER", client=client)
    writer = Agent(name="writer", description="문서", system="WRITER", client=client)
    orch = Orchestrator([coder, writer], system="ORCH", client=client, on_event=events)

    result = orch.run("함수랑 문서 만들어")

    assert result.text == "둘 다 끝났습니다"
    orch_calls = client.clients["ORCH"].calls
    tool_results = orch_calls[1]["messages"][2]["content"]
    assert [r["content"] for r in tool_results] == ["def f(): pass", "# 문서"]

    # 워커는 spawn 된 복제본에서 돌았으므로 템플릿 히스토리는 비어 있다
    assert coder.messages == [] and writer.messages == []
    # 워커 사용량이 따로 집계된다
    assert orch.worker_usage.output_tokens == 70
    assert result.usage.output_tokens == 10  # 오케스트레이터 자신의 것만
    # 워커 이벤트도 같은 콜백으로 흘러온다
    assert {e.agent for e in events.events} == {"orchestrator", "coder", "writer"}


def test_unknown_worker_is_rejected_by_schema():
    client = RoutingClient(
        {
            "ORCH": [
                make_message(
                    [tool_use_block("delegate", {"worker": "ghost", "task": "x"}, id="d1")],
                    stop_reason="tool_use",
                ),
                make_message([text_block("없는 워커였네요")]),
            ],
        }
    )
    coder = Agent(name="coder", description="코드", system="CODER", client=client)
    orch = Orchestrator([coder], system="ORCH", client=client)
    orch.run("go")

    tool_result = client.clients["ORCH"].calls[1]["messages"][2]["content"][0]
    assert tool_result["is_error"] is True
    assert "입력 검증 실패" in tool_result["content"]


def test_worker_refusal_is_relayed_as_text():
    client = RoutingClient(
        {
            "ORCH": [
                make_message(
                    [tool_use_block("delegate", {"worker": "coder", "task": "x"}, id="d1")],
                    stop_reason="tool_use",
                ),
                make_message([text_block("워커가 거부했어요")]),
            ],
            "CODER": [
                make_message(
                    [text_block("")],
                    stop_reason="refusal",
                    stop_details={"type": "refusal", "category": "cyber"},
                )
            ],
        }
    )
    coder = Agent(name="coder", description="코드", system="CODER", client=client)
    orch = Orchestrator([coder], system="ORCH", client=client)
    orch.run("go")
    tool_result = client.clients["ORCH"].calls[1]["messages"][2]["content"][0]
    assert "거부" in tool_result["content"]
    assert "is_error" not in tool_result


def test_orchestrator_requires_workers(fake_client):
    with pytest.raises(ValueError):
        Orchestrator([], client=fake_client())
