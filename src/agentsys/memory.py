"""세션을 넘어 남는 간단한 파일 기반 메모리.

에이전트에게 ``remember`` / ``recall`` / ``forget`` 세 도구를 제공합니다.
저장소는 JSON 파일 하나이며, 프로세스를 다시 시작해도 내용이 남습니다.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from .tools import Tool

__all__ = ["FileMemory"]


class FileMemory:
    def __init__(self, path: str | Path = ".agent_memory.json") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    # -- 저장소 --------------------------------------------------------------
    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self, data: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- 도구 함수 -----------------------------------------------------------
    def remember(self, key: str, content: str) -> str:
        """나중에 다시 필요할 사실이나 사용자 선호를 저장한다.

        사용자가 이름, 선호, 프로젝트 맥락 등 "기억해 달라"고 하거나
        이후 대화에서 유용할 정보를 알게 됐을 때 호출한다.

        Args:
            key: 짧은 식별자. 예: "user_name", "preferred_language"
            content: 저장할 내용
        """
        with self._lock:
            data = self._load()
            data[key] = {"content": content, "updated_at": datetime.now(timezone.utc).isoformat()}
            self._save(data)
        return f"저장됨: {key}"

    def recall(self, query: str = "") -> str:
        """저장된 메모리를 검색한다.

        사용자에 대해 이전에 알게 된 정보가 필요할 때, 또는 대화를 시작할 때 호출한다.
        query 가 비어 있으면 전체를 돌려준다.

        Args:
            query: 키 또는 내용에 포함될 검색어 (대소문자 무시)
        """
        with self._lock:
            data = self._load()
        needle = query.strip().lower()
        hits = {
            k: v["content"]
            for k, v in data.items()
            if not needle or needle in k.lower() or needle in v["content"].lower()
        }
        if not hits:
            return "일치하는 메모리가 없습니다."
        return "\n".join(f"- {k}: {v}" for k, v in hits.items())

    def forget(self, key: str) -> str:
        """저장된 메모리 하나를 삭제한다.

        Args:
            key: 삭제할 메모리의 키
        """
        with self._lock:
            data = self._load()
            if key not in data:
                return f"없는 키: {key}"
            del data[key]
            self._save(data)
        return f"삭제됨: {key}"

    def tools(self) -> list[Tool]:
        return [
            Tool(self.remember, name="remember"),
            Tool(self.recall, name="recall"),
            Tool(self.forget, name="forget"),
        ]
