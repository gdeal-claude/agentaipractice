import pytest

from agentsys import Tool, ToolInputError, ToolRegistry, tool


@tool
def add(a: int, b: int = 1) -> int:
    """두 수를 더한다.

    합계가 필요할 때 호출한다.

    Args:
        a: 첫 번째 수
        b: 두 번째 수 (기본 1)
    """
    return a + b


def test_schema_from_signature_and_docstring():
    param = add.to_param(streaming=False)
    assert param["name"] == "add"
    assert param["description"].startswith("두 수를 더한다.")
    assert "합계가 필요할 때" in param["description"]
    props = param["input_schema"]["properties"]
    assert props["a"] == {"type": "integer", "description": "첫 번째 수"}
    assert props["b"]["default"] == 1
    assert param["input_schema"]["required"] == ["a"]
    assert "eager_input_streaming" not in param


def test_streaming_param_enables_eager_input():
    assert add.to_param(streaming=True)["eager_input_streaming"] is True


def test_run_validates_and_serializes():
    assert add.run({"a": 2, "b": 3}) == "5"
    assert add.run({"a": "7"}) == "8"  # pydantic 이 문자열을 정수로 변환


def test_invalid_input_raises_tool_input_error():
    with pytest.raises(ToolInputError):
        add.run({"b": 3})
    with pytest.raises(ToolInputError):
        add.run({"a": "not-a-number"})
    with pytest.raises(ToolInputError):
        add.run("garbage")


def test_decorator_with_options():
    @tool(name="danger", requires_approval=True, description="위험한 작업")
    def _impl(path: str) -> str:
        return path

    assert _impl.name == "danger"
    assert _impl.requires_approval is True
    assert _impl.description == "위험한 작업"


def test_non_string_results_become_json():
    @tool
    def info() -> dict:
        """정보."""
        return {"ok": True, "items": [1, 2]}

    assert info.run({}) == '{"ok": true, "items": [1, 2]}'


def test_registry_rejects_duplicates_and_keeps_order():
    reg = ToolRegistry([add, Tool(lambda x: x, name="ident")])
    assert reg.names == ["add", "ident"]
    with pytest.raises(ValueError):
        reg.register(add)
    assert [p["name"] for p in reg.params()] == ["add", "ident"]
