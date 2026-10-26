"""Small shared bounded-output helpers; no authorization lives here."""

import base64
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from b12.tools.outcomes import HandlerOutcome

AbsolutePath = Annotated[str, Field(min_length=1, max_length=1024, pattern=r"^/[^\x00-\x1f\x7f]*$")]


class Args(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class EmptyArgs(Args):
    pass


def clip(text: str, limit: int) -> tuple[str, bool]:
    raw = text.encode("utf-8")
    return raw[:limit].decode("utf-8", errors="ignore"), len(raw) > limit


def body(data: bytes) -> dict:
    try:
        text = data.decode("utf-8")
        if "\x00" in text:
            raise ValueError
        return {"encoding": "utf-8", "text": text}
    except (UnicodeDecodeError, ValueError):
        return {"encoding": "base64", "data": base64.b64encode(data).decode("ascii")}


def failure(error: OSError | str) -> HandlerOutcome:
    code = (
        error
        if isinstance(error, str)
        else (
            "not_found"
            if isinstance(error, FileNotFoundError)
            else "permission_denied"
            if isinstance(error, PermissionError)
            else "unsupported"
        )
    )
    return HandlerOutcome(status="failed", error_code=code)
