import pytest

from agentsys import Agent, AgentConfig, AgentError, ContextWindowExceeded, EventCollector, tool
from conftest import make_message, text_block, tool_use_block


@tool
def add(a: int, b: int) -> int:
    """두 수를 더한다.

    Args:
        a: 첫 번째
        b: 두 번째
    """
    return a + b


@tool
def boom() -> str:
    """항상 실패한다."""
    raise RuntimeError("터짐")


@tool(requires_approval=True)
def delete_everything(target: str) -> str:
    """위험한 삭제.

    Args:
        target: 대상
    """
    return f"deleted {target}"


def test_simple_answer_without_tools(fake_client):
    client = fake_client(make_message([text_block("안녕하세요!")]))
    agent = Agent(system="테스트", client=client)
    result = agent.run("안녕")

    assert result.text == "안녕하세요!"
    assert result.stop_reason == "end_turn"
    assert result.iterations == 1
    assert result.usage.requests == 1
    assert result.usage.input_tokens == 10
    # 히스토리: user + assistant
    assert [m["role"] for m in agent.messages] == ["user", "assistant"]


def test_request_params_follow_design(fake_client):
    client = fake_client(make_message([text_block("ok")]))
    agent = Agent(system="시스템", tools=[add], client=client, config=AgentConfig(effort="medium"))
    agent.run("hi")

    params = client.calls[0]
    assert params["model"] == "claude-opus-5"
    assert params["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert params["output_config"] == {"effort": "medium"}
    assert params["cache_control"] == {"type": "ephemeral"}
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["betas"] == ["server-side-fallback-2026-07-01"]
    assert params["fallbacks"] == "default"
    assert [t["name"] for t in params["tools"]] == ["add"]
    assert params["tools"][0]["eager_input_streaming"] is True


def test_refusal_fallbacks_can_be_disabled(fake_client):
    client = fake_client(make_message([text_block("ok")]))
    Agent(system="s", client=client, config=AgentConfig(refusal_fallbacks=False)).run("hi")
    assert "fallbacks" not in client.calls[0]
    assert "betas" not in client.calls[0]


def test_tool_loop_executes_and_feeds_back(fake_client):
    client = fake_client(
        make_message(
            [text_block("계산할게요"), tool_use_block("add", {"a": 2, "b": 3}, id="t1")],
            stop_reason="tool_use",
        ),
        make_message([text_block("답은 5입니다")]),
    )
    events = EventCollector()
    agent = Agent(system="s", tools=[add], client=client, on_event=events)
    result = agent.run("2+3?")

    assert result.text == "답은 5입니다"
    assert result.iterations == 2
    assert [c.name for c in result.tool_calls] == ["add"]

    # 두 번째 요청에는 assistant(tool_use) + user(tool_result) 가 들어가야 한다
    second = client.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    tool_results = second[2]["content"]
    assert tool_results == [{"type": "tool_result", "tool_use_id": "t1", "content": "5"}]

    kinds = events.kinds()
    assert kinds.count("request") == 2
    assert "tool_call" in kinds and "tool_result" in kinds and kinds[-1] == "done"


def test_parallel_tool_calls_return_single_user_message(fake_client):
    client = fake_client(
        make_message(
            [
                tool_use_block("add", {"a": 1, "b": 1}, id="p1"),
                tool_use_block("add", {"a": 2, "b": 2}, id="p2"),
                tool_use_block("add", {"a": 3, "b": 3}, id="p3"),
            ],
            stop_reason="tool_use",
        ),
        make_message([text_block("done")]),
    )
    agent = Agent(system="s", tools=[add], client=client)
    agent.run("go")

    results = client.calls[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["p1", "p2", "p3"]  # 순서 유지
    assert [r["content"] for r in results] == ["2", "4", "6"]


def test_tool_errors_are_reported_not_raised(fake_client):
    client = fake_client(
        make_message(
            [
                tool_use_block("boom", {}, id="e1"),
                tool_use_block("add", {"a": "x", "b": 1}, id="e2"),
                tool_use_block("nope", {}, id="e3"),
            ],
            stop_reason="tool_use",
        ),
        make_message([text_block("복구했습니다")]),
    )
    agent = Agent(system="s", tools=[add, boom], client=client)
    result = agent.run("go")

    results = client.calls[1]["messages"][2]["content"]
    assert all(r["is_error"] is True for r in results)
    assert "RuntimeError: 터짐" in results[0]["content"]
    assert "입력 검증 실패" in results[1]["content"]
    assert "알 수 없는 도구" in results[2]["content"]
    assert result.text == "복구했습니다"


def test_approval_gate_denies_without_handler(fake_client):
    client = fake_client(
        make_message([tool_use_block("delete_everything", {"target": "/"}, id="d1")], stop_reason="tool_use"),
        make_message([text_block("취소했습니다")]),
    )
    events = EventCollector()
    agent = Agent(system="s", tools=[delete_everything], client=client, on_event=events)
    agent.run("다 지워")

    result = client.calls[1]["messages"][2]["content"][0]
    assert result["is_error"] is True and "거부" in result["content"]
    assert "tool_denied" in events.kinds()


def test_approval_gate_allows_with_handler(fake_client):
    client = fake_client(
        make_message([tool_use_block("delete_everything", {"target": "tmp"}, id="d1")], stop_reason="tool_use"),
        make_message([text_block("지웠습니다")]),
    )
    seen = []
    agent = Agent(
        system="s",
        tools=[delete_everything],
        client=client,
        approve=lambda call: seen.append(call.name) or True,
    )
    agent.run("지워")
    assert seen == ["delete_everything"]
    assert client.calls[1]["messages"][2]["content"][0]["content"] == "deleted tmp"


def test_max_tokens_continues_once(fake_client):
    client = fake_client(
        make_message([text_block("앞부분...")], stop_reason="max_tokens"),
        make_message([text_block("뒷부분")]),
    )
    agent = Agent(system="s", client=client)
    result = agent.run("길게 써줘")

    assert result.text == "앞부분...뒷부분"
    assert client.calls[1]["messages"][-1]["role"] == "user"
    assert "잘렸습니다" in client.calls[1]["messages"][-1]["content"]


def test_max_tokens_twice_raises(fake_client):
    client = fake_client(
        make_message([text_block("a")], stop_reason="max_tokens"),
        make_message([text_block("b")], stop_reason="max_tokens"),
    )
    with pytest.raises(AgentError):
        Agent(system="s", client=client).run("x")


def test_pause_turn_resends_without_user_message(fake_client):
    client = fake_client(
        make_message([text_block("검색 중")], stop_reason="pause_turn"),
        make_message([text_block("결과입니다")]),
    )
    agent = Agent(system="s", client=client)
    result = agent.run("찾아줘")
    assert result.text == "결과입니다"
    assert [m["role"] for m in client.calls[1]["messages"]] == ["user", "assistant"]


def test_refusal_is_returned_not_raised(fake_client):
    client = fake_client(
        make_message(
            [text_block("")],
            stop_reason="refusal",
            stop_details={"type": "refusal", "category": "cyber", "explanation": "정책"},
        )
    )
    events = EventCollector()
    result = Agent(system="s", client=client, on_event=events).run("...")
    assert result.refused is True
    assert result.refusal_category == "cyber"
    assert "refusal" in events.kinds()


def test_context_window_exceeded_raises(fake_client):
    client = fake_client(make_message([text_block("")], stop_reason="model_context_window_exceeded"))
    with pytest.raises(ContextWindowExceeded):
        Agent(system="s", client=client).run("x")


def test_max_iterations_guard(fake_client):
    loop = [
        make_message([tool_use_block("add", {"a": 1, "b": 1})], stop_reason="tool_use") for _ in range(5)
    ]
    client = fake_client(*loop)
    agent = Agent(system="s", tools=[add], client=client, config=AgentConfig(max_iterations=3))
    with pytest.raises(AgentError, match="max_iterations"):
        agent.run("loop")
    assert len(client.calls) == 3


def test_multi_turn_history_and_reset(fake_client):
    client = fake_client(make_message([text_block("1")]), make_message([text_block("2")]), make_message([text_block("3")]))
    agent = Agent(system="s", client=client)
    agent.run("a")
    agent.run("b")
    assert len(client.calls[1]["messages"]) == 3  # user, assistant, user
    agent.run("c", reset=True)
    assert len(client.calls[2]["messages"]) == 1
    assert agent.total_usage.requests == 3


def test_spawn_gives_fresh_history(fake_client):
    client = fake_client(make_message([text_block("x")]))
    agent = Agent(name="w", system="s", tools=[add], client=client)
    agent.run("hi")
    clone = agent.spawn(name="w-2")
    assert clone.messages == []
    assert clone.name == "w-2"
    assert clone.tools is agent.tools
    assert agent.messages  # 원본은 그대로
