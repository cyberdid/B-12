import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QApplication

from b12.desktop.app import (
    DesktopShell,
    default_overlay_position,
    load_owner_token,
    restore_overlay_position,
)
from b12.desktop.client import DesktopApiError


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_default_pet_position_is_inside_target_display():
    screen = QRect(1920, 0, 1920, 1080)
    size = QSize(244, 272)
    position = default_overlay_position(screen, size)
    assert screen.contains(position + QPoint(size.width(), size.height()))
    assert position.x() < screen.right() - size.width()


def test_restore_position_clamps_pet_to_a_connected_screen():
    screens = [QRect(0, 0, 1920, 1080), QRect(1920, 0, 1280, 1024)]
    assert restore_overlay_position(QPoint(5000, 4000), screens, QSize(244, 272)) == QPoint(
        2938, 734
    )


def test_missing_or_empty_owner_token_is_not_created(tmp_path):
    state = tmp_path / "state"
    with pytest.raises(DesktopApiError, match="owner_token_missing"):
        load_owner_token(state)
    assert not state.exists()

    token_file = state / "api" / "owner.token"
    token_file.parent.mkdir(parents=True)
    token_file.write_text("  secret\n")
    assert load_owner_token(state) == "secret"
    token_file.write_text(" \n")
    with pytest.raises(DesktopApiError, match="owner_token_missing"):
        load_owner_token(state)


def test_shell_starts_pet_without_opening_chat_or_starting_voice(qapp):
    class OfflineClient:
        base_url = "http://127.0.0.1:8712"

        def __init__(self):
            self.health_calls = 0
            self.health_checked = threading.Event()
            self.voice_calls = 0
            self.closed = False

        def health(self):
            self.health_calls += 1
            self.health_checked.set()
            return False

        def close(self):
            self.closed = True

    client = OfflineClient()
    shell = DesktopShell(qapp, client, persist_default=False)
    assert shell.overlay.isVisible()
    assert not shell.chat.isVisible()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not client.health_checked.is_set():
        qapp.processEvents()
        time.sleep(0.01)
    assert client.health_calls == 1
    assert client.voice_calls == 0
    shell.shutdown()
    assert client.closed


def test_pending_approval_pose_survives_offline_reconnect(qapp):
    class OfflineClient:
        base_url = "http://127.0.0.1:8712"

        def health(self):
            return False

        def close(self):
            pass

    shell = DesktopShell(qapp, OfflineClient(), persist_default=False)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and shell._notification_job is not None:
        qapp.processEvents()
        time.sleep(0.01)
    shell._last_approval_ids = {"op-pending"}
    shell.overlay.set_phase("approval", "file_write")

    shell._notifications_ready("notifications", {"connected": False, "approvals": []})
    assert shell.overlay.phase == "approval"

    shell._notifications_ready(
        "notifications",
        {
            "connected": True,
            "approvals": [{"operation_id": "op-pending", "name": "file_write"}],
        },
    )
    assert shell.overlay.phase == "approval"
    shell.shutdown()


def test_sleep_and_wake_remain_available_without_a_system_tray(qapp):
    class OfflineClient:
        base_url = "http://127.0.0.1:8712"

        def health(self):
            return False

        def close(self):
            pass

    shell = DesktopShell(qapp, OfflineClient(), persist_default=False)
    if shell._tray is not None:
        shell._tray.hide()
    shell._tray = None
    shell.toggle_pet()
    assert shell.overlay.isVisible()
    assert shell.overlay.phase == "sleeping"

    shell._pet_clicked()
    assert shell.overlay.phase == "idle"
    assert shell.chat.isVisible()
    shell.shutdown()
