"""Trusted catalog risk and cooperative effect guard, not an OS sandbox.

Arbitrary executable/interpreter code may perform any effect allowed by the OS.
argv is a transport format, not isolation. No command blacklist is a guarantee.
Generic full execution does not add external messaging/publication capabilities.
"""

import time
from dataclasses import dataclass
from enum import StrEnum

from b12.control import ControlError, ControlStore, ExecutionContext


class Risk(StrEnum):
    TYPED = "typed"
    ARBITRARY = "arbitrary"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True, slots=True)
class EffectGuard:
    """Task6 handlers must check immediately before EACH effect/persistence.

    Async handlers must be cooperative/nonblocking and propagate cancellation.
    A check cannot revoke an already-running OS operation or rollback its effect.
    """

    store: ControlStore
    context: ExecutionContext
    capability: str
    operation_id: str
    execution_deadline: float

    @property
    def cancel(self):
        return self.context.cancel

    @property
    def deadline(self):
        return self.execution_deadline

    def check(self):
        if time.monotonic() >= self.execution_deadline:
            raise ControlError("deadline_exceeded")
        self.store.check(self.context, self.capability)
        row = self.store.db.execute(
            "SELECT state FROM operations WHERE id=?", (self.operation_id,)
        ).fetchone()
        if not row or row[0] != "started":
            raise ControlError("operation_not_active")
