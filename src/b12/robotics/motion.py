"""Single-writer, bounded motion control independent of the LLM.

Exactly one writer may command actuators at a time (lease token). Every target is
validated against hard angle limits and a maximum angular speed: out-of-range commands
are rejected, never silently clamped. stop() interrupts immediately and holds the
current pose; sleep() moves to the safe pose; after a disconnect the controller
re-enters the safe state and never resumes an interrupted motion on reconnect.
"""

import asyncio
import math
import time
from dataclasses import dataclass, field
from uuid import uuid4

JOINTS = ("head_yaw", "head_pitch", "head_roll", "body_yaw", "antenna_left", "antenna_right")
DEFAULT_LIMITS = {
    "head_yaw": (-60.0, 60.0),
    "head_pitch": (-30.0, 30.0),
    "head_roll": (-20.0, 20.0),
    "body_yaw": (-90.0, 90.0),
    "antenna_left": (-80.0, 80.0),
    "antenna_right": (-80.0, 80.0),
}
SAFE_POSE = dict.fromkeys(JOINTS, 0.0)


class MotionRejected(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MotionCommand:
    targets: dict
    duration_s: float


@dataclass
class Limits:
    angles: dict = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    max_speed_deg_s: float = 90.0
    min_duration_s: float = 0.2
    max_duration_s: float = 10.0


class MotionController:
    def __init__(self, transport, limits: Limits | None = None):
        self.transport, self.limits = transport, limits or Limits()
        self._lease: str | None = None
        self._task: asyncio.Task | None = None
        self.state = "disconnected"  # disconnected | safe | moving | holding | sleeping
        self.log: list[dict] = []

    # --- single writer ---------------------------------------------------------
    def acquire(self) -> str:
        if self._lease is not None:
            raise MotionRejected("writer_busy")
        self._lease = str(uuid4())
        return self._lease

    def release(self, lease: str):
        if lease == self._lease:
            self._lease = None

    def _check_lease(self, lease):
        if lease is None or lease != self._lease:
            raise MotionRejected("not_writer")

    # --- lifecycle -------------------------------------------------------------
    async def connect(self):
        await self.transport.connect()
        await self._safe("connect")

    async def _safe(self, reason):
        await self.transport.send(MotionCommand(dict(SAFE_POSE), 1.0))
        self.state = "safe"
        self.log.append({"event": "safe", "reason": reason, "at": time.monotonic()})

    async def on_disconnect(self):
        """Transport lost: drop any motion; on reconnect go to safe pose, never resume."""
        await self._interrupt()
        self.state = "disconnected"
        self.log.append({"event": "disconnected", "at": time.monotonic()})

    async def reconnect(self):
        await self.transport.connect()
        await self._safe("reconnect")

    # --- validation --------------------------------------------------------------
    def validate(self, command: MotionCommand):
        if set(command.targets) - set(JOINTS):
            raise MotionRejected("unknown_joint")
        if not (self.limits.min_duration_s <= command.duration_s <= self.limits.max_duration_s):
            raise MotionRejected("duration_out_of_range")
        current = self.transport.pose()
        for joint, target in command.targets.items():
            if type(target) not in (int, float) or not math.isfinite(target):
                raise MotionRejected("invalid_target")
            low, high = self.limits.angles[joint]
            if not low <= target <= high:
                raise MotionRejected("angle_out_of_range")
            speed = abs(target - current[joint]) / command.duration_s
            if speed > self.limits.max_speed_deg_s:
                raise MotionRejected("speed_out_of_range")

    # --- motion ----------------------------------------------------------------
    async def move(self, lease: str, command: MotionCommand):
        self._check_lease(lease)
        if self.state in ("disconnected", "sleeping"):
            raise MotionRejected(f"robot_{self.state}")
        self.validate(command)
        await self._interrupt()
        self.state = "moving"
        self.log.append({"event": "move", "targets": command.targets, "at": time.monotonic()})
        task = self._task = asyncio.create_task(self.transport.execute(command))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():  # stop()/disconnect cancelled the motion, not our caller
                return "interrupted"
            raise
        self.state = "holding"
        return "done"

    async def _interrupt(self):
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await self.transport.hold()

    async def stop(self):
        """Interrupt immediately from any path (owner, audio barge-in); hold pose."""
        await self._interrupt()
        if self.state == "moving":
            self.state = "holding"
        self.log.append({"event": "stop", "at": time.monotonic()})

    async def sleep(self, lease: str):
        self._check_lease(lease)
        await self._interrupt()
        await self._safe("sleep")
        self.state = "sleeping"

    async def wake(self, lease: str):
        self._check_lease(lease)
        if self.state == "sleeping":
            self.state = "safe"
