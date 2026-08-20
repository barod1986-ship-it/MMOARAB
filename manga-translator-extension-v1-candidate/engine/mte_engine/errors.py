from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EngineApiError(Exception):
    code: str
    message: str
    status_code: int = 400
    retryable: bool = False
    details: dict[str, str | int | bool | None] | None = None

    def envelope(self) -> dict[str, object]:
        error: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            error["details"] = self.details
        return {"error": error}
