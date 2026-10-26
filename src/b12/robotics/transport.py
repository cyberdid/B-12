"""Transport protocol plus a time-integrating simulator used for protocol tests.

A real Reachy Mini transport (vendor SDK, wired or wireless) must implement the same
methods; physical acceptance requires the device and is not claimed by these tests.
"""

import asyncio
import time

from b12.robotics.motion import JOINTS, SAFE_POSE


class SimulatedRobot:
    """Linear interpolation per joint; records every command; injectable disconnect."""

    def __init__(self, *, tick_s: float = 0.01):
        self.tick_s = tick_s
        self.connected = False
        self._pose = dict(SAFE_POSE)
        self.commands = []
        self.max_observed_speed = 0.0

    async def connect(self):
        self.connected = True

    def pose(self) -> dict:
        return dict(self._pose)

    async def send(self, command):
        if not self.connected:
            raise ConnectionError("robot disconnected")
        self.commands.append(command)
        self._pose.update(command.targets)

    async def execute(self, command):
        if not self.connected:
            raise ConnectionError("robot disconnected")
        self.commands.append(command)
        start, began = self.pose(), time.monotonic()
        while True:
            await asyncio.sleep(self.tick_s)
            if not self.connected:
                raise ConnectionError("robot disconnected")
            fraction = min(1.0, (time.monotonic() - began) / command.duration_s)
            previous = self.pose()
            for joint in JOINTS:
                if joint in command.targets:
                    target = command.targets[joint]
                    self._pose[joint] = start[joint] + (target - start[joint]) * fraction
            moved = max(abs(self._pose[j] - previous[j]) for j in JOINTS)
            self.max_observed_speed = max(self.max_observed_speed, moved / self.tick_s)
            if fraction >= 1.0:
                return

    async def hold(self):
        self.commands.append("hold")

    def drop(self):
        self.connected = False
