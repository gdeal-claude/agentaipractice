import pytest

from agentsys import FileMemory, Workspace, calculator


def test_calculator_basic_and_functions():
    assert calculator.run({"expression": "(3 + 4) * 2 ** 3"}) == "56"
    assert calculator.run({"expression": "sqrt(16) + abs(-2)"}) == "6"
    assert calculator.run({"expression": "10 / 4"}) == "2.5"


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "2 ** 99999", "a + 1"])
def test_calculator_rejects_unsafe(expr):
    with pytest.raises(Exception):
        calculator.run({"expression": expr})


def test_workspace_is_sandboxed(tmp_path):
    ws = Workspace(tmp_path / "ws")
    tools = {t.name: t for t in ws.tools()}

    assert tools["write_file"].requires_approval is True
    assert tools["write_file"].run({"path": "a/b.txt", "content": "hi"}).endswith("저장됨")
    assert tools["read_file"].run({"path": "a/b.txt"}) == "hi"
    assert tools["list_files"].run({"path": "."}) == "a/"
    assert tools["list_files"].run({"path": "a"}) == "b.txt"

    with pytest.raises(PermissionError):
        tools["read_file"].run({"path": "../../etc/passwd"})
    with pytest.raises(PermissionError):
        tools["write_file"].run({"path": "/tmp/x", "content": ""})


def test_file_memory_roundtrip(tmp_path):
    mem = FileMemory(tmp_path / "mem.json")
    tools = {t.name: t for t in mem.tools()}

    assert tools["recall"].run({"query": ""}) == "일치하는 메모리가 없습니다."
    tools["remember"].run({"key": "user_name", "content": "지수"})
    tools["remember"].run({"key": "lang", "content": "Python 선호"})
    assert "user_name: 지수" in tools["recall"].run({"query": "지수"})
    assert "lang" in tools["recall"].run({"query": "python"})
    assert tools["forget"].run({"key": "lang"}) == "삭제됨: lang"
    assert tools["forget"].run({"key": "lang"}) == "없는 키: lang"

    # 새 인스턴스에서도 남아 있어야 한다
    again = FileMemory(tmp_path / "mem.json")
    assert "user_name" in again.recall("")
