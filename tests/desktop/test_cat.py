import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from b12.desktop.cat import CatAtlas, CyberCatOverlay, gaze_for_pointer, pose_for


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("phase", "expected_pose"),
    [
        ("idle", 0),
        ("typing", 0),
        ("thinking", 9),
        ("working", 9),
        ("approval", 3),
        ("speaking", 8),
        ("success", 7),
        ("error", 5),
        ("cancelled", 5),
    ],
)
def test_pet_pose_tracks_b12_turn_phase(phase, expected_pose):
    assert pose_for(phase, frame=0)[0] == expected_pose


def test_atlas_is_original_b12_rgba_sheet():
    atlas = CatAtlas()
    assert atlas.sheet.size() == QSize(1448, 1086)
    assert atlas.cell_size == 362
    assert atlas.sheet.pixelColor(0, 0).alpha() == 0


def test_pointer_gaze_has_dead_zone_and_tracks_each_side():
    widget = (100, 200, 200, 200)
    assert gaze_for_pointer(widget, QPoint(200, 300)) == (0, 0)
    assert gaze_for_pointer(widget, QPoint(110, 300)) == (-1, 0)
    assert gaze_for_pointer(widget, QPoint(290, 390)) == (1, 1)


def test_click_opens_chat_and_right_click_requests_menu(qapp):
    overlay = CyberCatOverlay()
    opened = []
    menu_requests = []
    overlay.open_chat.connect(lambda: opened.append(True))
    overlay.menu_requested.connect(menu_requests.append)
    overlay.show()
    QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=QPoint(125, 125))
    QTest.mouseClick(overlay, Qt.MouseButton.RightButton, pos=QPoint(125, 125))
    qapp.processEvents()
    overlay.close()
    assert opened == [True]
    assert len(menu_requests) == 1


def test_drag_emits_new_overlay_position(qapp):
    overlay = CyberCatOverlay()
    positions = []
    overlay.position_changed.connect(positions.append)
    overlay.show()
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QTest.mouseMove(overlay, QPoint(75, 70), delay=10)
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(75, 70))
    qapp.processEvents()
    overlay.close()
    assert positions
    assert positions[-1] != QPoint(0, 0)
