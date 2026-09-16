"""바로 쓸 수 있는 기본 도구 모음.

* :func:`calculator`  - 안전한 사칙연산/수학 함수 평가
* :func:`current_time` - 시간대별 현재 시각
* :class:`Workspace`  - 지정한 디렉터리 안에서만 동작하는 파일 읽기/쓰기/목록
"""

from __future__ import annotations

import ast
import math
import operator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .tools import Tool, tool

__all__ = ["calculator", "current_time", "Workspace"]

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    name: getattr(math, name)
    for name in ("sqrt", "sin", "cos", "tan", "log", "log10", "log2", "exp", "floor", "ceil", "fabs")
}
_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("지수가 너무 큽니다")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise ValueError("키워드 인자는 지원하지 않습니다")
        return _FUNCS[node.func.id](*(_eval(a) for a in node.args))
    raise ValueError(f"허용되지 않는 표현식: {ast.dump(node)[:60]}")


@tool
def calculator(expression: str) -> str:
    """수학 표현식을 계산한다.

    산술, 비교가 필요한 계산, 단위 환산처럼 정확한 숫자가 필요할 때 암산 대신 호출한다.
    사칙연산, 거듭제곱(**), 괄호, sqrt/sin/cos/log/exp/abs/round/min/max, pi, e 를 지원한다.

    Args:
        expression: 파이썬 문법의 수식. 예: "(3 + 4) * 2 ** 3", "sqrt(2) * pi"
    """
    tree = ast.parse(expression.strip(), mode="eval")
    result = _eval(tree)
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)


@tool
def current_time(timezone: str = "UTC") -> str:
    """지정한 시간대의 현재 날짜와 시각을 돌려준다.

    "지금 몇 시야", "오늘 날짜", 날짜 계산의 기준이 필요할 때 호출한다.

    Args:
        timezone: IANA 시간대 이름. 예: "Asia/Seoul", "UTC", "America/New_York"
    """
    now = datetime.now(ZoneInfo(timezone))
    return now.strftime("%Y-%m-%d %H:%M:%S %Z (%A)")


class Workspace:
    """``root`` 디렉터리 밖으로 나갈 수 없는 파일 도구 세트."""

    def __init__(self, root: str | Path, *, max_read_chars: int = 50_000) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_read_chars = max_read_chars

    def _resolve(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if target != self.root and self.root not in target.parents:
            raise PermissionError(f"작업 공간 밖의 경로는 허용되지 않습니다: {path}")
        return target

    def list_files(self, path: str = ".") -> str:
        """작업 공간 안의 파일과 디렉터리 목록을 돌려준다.

        어떤 파일이 있는지 모를 때, 파일을 읽거나 쓰기 전에 먼저 호출한다.

        Args:
            path: 작업 공간 루트 기준 상대 경로. 기본값은 루트.
        """
        target = self._resolve(path)
        if not target.exists():
            return f"없는 경로: {path}"
        if target.is_file():
            return path
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        if not entries:
            return "(비어 있음)"
        return "\n".join(f"{p.name}/" if p.is_dir() else p.name for p in entries)

    def read_file(self, path: str) -> str:
        """작업 공간 안의 텍스트 파일 내용을 돌려준다.

        Args:
            path: 작업 공간 루트 기준 상대 경로
        """
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"파일이 없습니다: {path}")
        text = target.read_text(encoding="utf-8")
        if len(text) > self.max_read_chars:
            return text[: self.max_read_chars] + f"\n...(총 {len(text)}자 중 앞부분만 표시)"
        return text

    def write_file(self, path: str, content: str) -> str:
        """작업 공간 안에 텍스트 파일을 만들거나 덮어쓴다.

        결과물을 파일로 남겨야 할 때 호출한다. 기존 파일은 덮어써진다.

        Args:
            path: 작업 공간 루트 기준 상대 경로. 중간 디렉터리는 자동 생성된다.
            content: 파일 전체 내용
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"{path} 에 {len(content)}자 저장됨"

    def tools(self, *, approve_writes: bool = True) -> list[Tool]:
        return [
            Tool(self.list_files, name="list_files"),
            Tool(self.read_file, name="read_file"),
            Tool(self.write_file, name="write_file", requires_approval=approve_writes),
        ]
