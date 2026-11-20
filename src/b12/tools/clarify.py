"""Structured clarification tool: ask the speaker a question with 2-4 choices."""

from typing import Annotated

from pydantic import Field, field_validator

from b12.tools._common import Args
from b12.tools.outcomes import HandlerOutcome
from b12.tools.policy import EffectGuard


class ClarifyArgs(Args):
    question: str = Field(
        min_length=1,
        max_length=500,
        description="Short clear question to ask the speaker",
    )
    choices: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        min_length=2,
        max_length=4,
        description="Two to four concise answer choices for the speaker",
    )
    allow_other: bool = Field(
        default=True,
        description="Whether the speaker may give a free-form answer instead of a listed choice",
    )

    @field_validator("question")
    @classmethod
    def _nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value

    @field_validator("choices")
    @classmethod
    def _nonblank_choices(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("choices must not contain blank items")
        return values


async def clarify(args: ClarifyArgs, guard: EffectGuard) -> HandlerOutcome:
    """Consume the speaker's clarification answer (or skip/timeout) from ControlStore."""
    guard.check()
    return HandlerOutcome(content=guard.store.consume_clarify(guard.operation_id))


def register(registry) -> None:
    registry.register(
        "clarify",
        "Ask the speaker a short clarifying question with 2-4 choices and wait for their reply. "
        "Use only when genuine ambiguity blocks proceeding.",
        ClarifyArgs,
        clarify,
        "time.read",
        clarify=True,
    )
