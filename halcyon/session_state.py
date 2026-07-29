from dataclasses import dataclass, field
from typing import Protocol


class SessionState(Protocol):
    def get_history(self, session_id: str, surface: str) -> list[dict]: ...
    def append_turn(
        self, session_id: str, surface: str, user_msg: str, assistant_msg: str
    ) -> None: ...
    def clear_history(self, session_id: str, surface: str) -> None: ...
    def get_level(self, session_id: str, module: str) -> str | None: ...
    def set_level(self, session_id: str, module: str, level: str) -> None: ...


@dataclass
class InMemorySessionState:
    _history: dict[tuple[str, str], list[dict]] = field(default_factory=dict)
    _levels: dict[tuple[str, str], str] = field(default_factory=dict)

    def get_history(self, session_id: str, surface: str) -> list[dict]:
        return [dict(m) for m in self._history.get((session_id, surface), [])]

    def append_turn(
        self, session_id: str, surface: str, user_msg: str, assistant_msg: str
    ) -> None:
        h = self._history.setdefault((session_id, surface), [])
        h.append({"role": "user", "content": user_msg})
        h.append({"role": "assistant", "content": assistant_msg})

    def clear_history(self, session_id: str, surface: str) -> None:
        self._history.pop((session_id, surface), None)

    def get_level(self, session_id: str, module: str) -> str | None:
        return self._levels.get((session_id, module))

    def set_level(self, session_id: str, module: str, level: str) -> None:
        self._levels[(session_id, module)] = level
