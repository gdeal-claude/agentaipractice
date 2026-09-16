"""도구(Tool) 정의와 레지스트리.

파이썬 함수 하나를 ``@tool`` 로 감싸면 다음이 자동으로 만들어집니다.

* 함수 시그니처 + 타입 힌트 -> Claude 에게 보낼 ``input_schema`` (JSON Schema)
* docstring 의 요약 -> 도구 ``description``
* docstring ``Args:`` 섹션 -> 각 파라미터의 ``description``
* pydantic 모델 -> 모델이 보낸 입력의 검증 (스트리밍 시 잘린 JSON 방어)
"""

from __future__ import annotations

import inspect
import json
import re
from typing import Any, Callable, Iterable, get_type_hints

from pydantic import BaseModel, Field, ValidationError, create_model

__all__ = ["Tool", "ToolCall", "ToolInputError", "ToolRegistry", "tool"]

_PARAM_LINE = re.compile(r"^\s*(\w+)\s*(?:\([^)]*\))?\s*:\s*(.+?)\s*$")
_ARGS_HEADERS = {"args:", "arguments:", "parameters:", "params:"}
_STOP_HEADERS = ("returns:", "return:", "raises:", "yields:", "example", "note")


class ToolInputError(ValueError):
    """모델이 보낸 도구 입력이 스키마와 맞지 않을 때."""


class ToolCall(BaseModel):
    """모델이 요청한 도구 호출 한 건."""

    id: str
    name: str
    input: dict[str, Any]


def _parse_docstring(doc: str | None) -> tuple[str, dict[str, str]]:
    """Google 스타일 docstring 에서 (설명, {파라미터: 설명}) 을 뽑아낸다."""
    if not doc:
        return "", {}
    lines = inspect.cleandoc(doc).splitlines()
    description: list[str] = []
    params: dict[str, str] = {}
    in_args = False
    current: str | None = None
    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered in _ARGS_HEADERS:
            in_args = True
            current = None
            continue
        if in_args:
            if stripped and not line[:1].isspace():
                # 들여쓰기 없는 새 섹션(Returns: 등) -> Args 종료
                in_args = False
                current = None
                continue
            match = _PARAM_LINE.match(line)
            if match:
                current = match.group(1)
                params[current] = match.group(2)
            elif current and stripped:
                params[current] += " " + stripped
            continue
        if lowered.startswith(_STOP_HEADERS):
            break
        description.append(stripped)
    text = "\n".join(description).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, params


class Tool:
    """Claude 가 호출할 수 있는 파이썬 함수 래퍼."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
        requires_approval: bool = False,
    ) -> None:
        self.fn = fn
        self.name = name or fn.__name__
        summary, param_docs = _parse_docstring(fn.__doc__)
        self.description = description or summary or self.name
        self.requires_approval = requires_approval
        self._model = self._build_model(fn, param_docs)
        self.input_schema = self._build_schema()

    # -- 스키마 생성 ---------------------------------------------------------
    def _build_model(self, fn: Callable[..., Any], docs: dict[str, str]) -> type[BaseModel]:
        hints = get_type_hints(fn)
        fields: dict[str, Any] = {}
        for param in inspect.signature(fn).parameters.values():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                raise TypeError(f"도구 '{self.name}' 는 *args/**kwargs 를 사용할 수 없습니다")
            annotation = hints.get(param.name, Any)
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[param.name] = (annotation, Field(default, description=docs.get(param.name)))
        return create_model(f"{self.name}_input", **fields)

    def _build_schema(self) -> dict[str, Any]:
        schema = self._model.model_json_schema()
        schema.pop("title", None)
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        for prop in schema["properties"].values():
            prop.pop("title", None)
        return schema

    # -- 실행 ----------------------------------------------------------------
    def validate(self, raw_input: Any) -> dict[str, Any]:
        """모델이 준 입력을 검증해 파이썬 인자 dict 로 돌려준다."""
        if not isinstance(raw_input, dict):
            raise ToolInputError(f"입력은 JSON object 여야 합니다 (받은 타입: {type(raw_input).__name__})")
        try:
            validated = self._model.model_validate(raw_input)
        except ValidationError as exc:
            raise ToolInputError(str(exc)) from exc
        return {name: getattr(validated, name) for name in self._model.model_fields}

    def run(self, raw_input: Any) -> str:
        """입력을 검증하고 함수를 실행한 뒤 결과를 문자열로 돌려준다."""
        result = self.fn(**self.validate(raw_input))
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)

    # -- API 파라미터 --------------------------------------------------------
    def to_param(self, *, streaming: bool = True) -> dict[str, Any]:
        param: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if streaming:
            # 큰 입력(파일 내용 등)이 버퍼링 없이 바로 스트리밍되도록 한다.
            # 대신 JSON 이 잘릴 수 있으므로 run() 에서 항상 검증한다.
            param["eager_input_streaming"] = True
        return param

    def __repr__(self) -> str:
        return f"Tool(name={self.name!r})"


def tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    requires_approval: bool = False,
) -> Any:
    """함수를 :class:`Tool` 로 바꾸는 데코레이터.

    ``@tool`` 또는 ``@tool(name=..., requires_approval=True)`` 둘 다 됩니다.
    """

    def wrap(func: Callable[..., Any]) -> Tool:
        return Tool(func, name=name, description=description, requires_approval=requires_approval)

    return wrap(fn) if fn is not None else wrap


class ToolRegistry:
    """이름으로 도구를 찾는 컬렉션."""

    def __init__(self, tools: Iterable[Tool | Callable[..., Any]] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for item in tools or ():
            self.register(item)

    def register(self, item: Tool | Callable[..., Any]) -> Tool:
        t = item if isinstance(item, Tool) else Tool(item)
        if t.name in self._tools:
            raise ValueError(f"도구 이름이 중복됩니다: {t.name}")
        self._tools[t.name] = t
        return t

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def params(self, *, streaming: bool = True) -> list[dict[str, Any]]:
        # 항상 같은 순서로 내보내야 프롬프트 캐시가 유지된다.
        return [t.to_param(streaming=streaming) for t in self._tools.values()]
