"""Robot adapter protocol on the simulator. Not physical acceptance."""

import asyncio
import math

import pytest

from b12.robotics.motion import (
    SAFE_POSE,
    Limits,
    MotionCommand,
    MotionController,
    MotionRejected,
)
from b12.robotics.transport import SimulatedRobot


@pytest.fixture
async def robot():
    sim = SimulatedRobot()
    controller = MotionController(sim, Limits(max_speed_deg_s=120.0))
    await controller.connect()
    return sim, controller


async def test_single_writer_lease(robot):
    _, controller = robot
    lease = controller.acquire()
    with pytest.raises(MotionRejected, match="writer_busy"):
        controller.acquire()
    with pytest.raises(MotionRejected, match="not_writer"):
        await controller.move("forged", MotionCommand({"head_yaw": 10.0}, 1.0))
    controller.release(lease)
    assert controller.acquire()


@pytest.mark.parametrize(
    "targets,duration,code",
    [
        ({"head_yaw": 75.0}, 2.0, "angle_out_of_range"),
        ({"head_yaw": 50.0}, 0.2, "speed_out_of_range"),
        ({"tail": 1.0}, 1.0, "unknown_joint"),
        ({"head_yaw": math.nan}, 1.0, "invalid_target"),
        ({"head_yaw": 5.0}, 30.0, "duration_out_of_range"),
    ],
)
async def test_out_of_bounds_commands_are_rejected_not_clamped(robot, targets, duration, code):
    sim, controller = robot
    lease = controller.acquire()
    before = sim.pose()
    with pytest.raises(MotionRejected, match=code):
        await controller.move(lease, MotionCommand(targets, duration))
    assert sim.pose() == before


async def test_motion_respects_speed_bound_and_reaches_target(robot):
    sim, controller = robot
    lease = controller.acquire()
    assert await controller.move(lease, MotionCommand({"head_yaw": 40.0}, 0.5)) == "done"
    assert sim.pose()["head_yaw"] == pytest.approx(40.0)
    assert sim.max_observed_speed <= 120.0 * 1.6  # tick discretisation margin
    assert controller.state == "holding"


async def test_stop_interrupts_immediately_and_holds(robot):
    sim, controller = robot
    lease = controller.acquire()
    move = asyncio.create_task(controller.move(lease, MotionCommand({"body_yaw": 80.0}, 2.0)))
    await asyncio.sleep(0.3)
    started = asyncio.get_running_loop().time()
    await controller.stop()
    assert asyncio.get_running_loop().time() - started < 0.1
    assert await move == "interrupted"
    frozen = sim.pose()["body_yaw"]
    await asyncio.sleep(0.2)
    assert sim.pose()["body_yaw"] == frozen and 0 < frozen < 80
    assert sim.commands[-1] == "hold"


async def test_disconnect_goes_safe_and_never_resumes(robot):
    sim, controller = robot
    lease = controller.acquire()
    move = asyncio.create_task(controller.move(lease, MotionCommand({"head_pitch": 25.0}, 2.0)))
    await asyncio.sleep(0.2)
    sim.drop()
    await controller.on_disconnect()
    await asyncio.gather(move, return_exceptions=True)
    with pytest.raises(MotionRejected, match="robot_disconnected"):
        await controller.move(lease, MotionCommand({"head_pitch": 5.0}, 1.0))
    await controller.reconnect()
    assert sim.pose() == SAFE_POSE and controller.state == "safe"
    await asyncio.sleep(0.3)
    assert sim.pose() == SAFE_POSE  # interrupted motion was not resumed


async def test_sleep_blocks_motion_until_wake(robot):
    sim, controller = robot
    lease = controller.acquire()
    await controller.sleep(lease)
    assert sim.pose() == SAFE_POSE
    with pytest.raises(MotionRejected, match="robot_sleeping"):
        await controller.move(lease, MotionCommand({"head_yaw": 10.0}, 1.0))
    await controller.wake(lease)
    assert await controller.move(lease, MotionCommand({"head_yaw": 10.0}, 1.0)) == "done"
