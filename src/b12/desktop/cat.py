"""Transparent desktop cybercat using the approved B-12 sprite atlas."""

from __future__ import annotations

import time
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

PHASES = {
    "idle": ("ПОРУЧ ІЗ ТОБОЮ", "Я тут. Я слухаю.", "#69f4df"),
    "typing": ("УВАЖНО СЛУХАЮ", "Що ти задумав?", "#69f4df"),
    "thinking": ("ОБМІРКОВУЮ", "Ловлю нитку думки…", "#b6a0ff"),
    "speaking": ("ВІДПОВІДАЮ", "Ділюся тим, що знайшов.", "#69f4df"),
    "working": ("ПРАЦЮЮ", "Перевіряю, а не вгадую.", "#ffd58a"),
    "approval": ("ЧЕКАЮ НА ТЕБЕ", "Цю дію вирішуєш ти.", "#ffd58a"),
    "success": ("ГОТОВО", "Ще одну пригоду?", "#69f4df"),
    "error": ("ЗВ’ЯЗОК ПЕРЕРВАНО", "Я тут. Спробуємо ще раз.", "#ff8193"),
    "cancelled": ("ЗУПИНИВСЯ", "Можемо змінити напрям.", "#b6a0ff"),
    "sleeping": ("ТИХИЙ РЕЖИМ", "Поклич мене, коли знадоблюсь.", "#8b9ab6"),
}
TAIL_BOX = (0, 168, 112, 324)
ASSET_PATH = Path(__file__).resolve().parents[1] / "tui" / "assets" / "cybercat-atlas.png"


def pose_for(
    phase: str,
    *,
    frame: int,
    look_x: int = 0,
    look_y: int = 0,
    purring: bool = False,
    motion: bool = True,
) -> tuple[int, int, int]:
    """Select pose, registered tail frame, and native-pixel breathing offset."""
    if phase not in PHASES:
        raise ValueError("unknown_companion_phase")
    if purring or phase == "success":
        pose = 7
    elif motion and frame % 56 in (51, 52, 53, 54):
        pose = 5 if frame % 56 in (51, 54) else 6
    elif phase == "speaking":
        pose = 8 if not motion or frame % 4 < 2 else 0
    elif phase in ("thinking", "working"):
        pose = 9
    elif phase == "approval":
        pose = 3
    elif phase in ("error", "cancelled"):
        pose = 5
    elif phase == "sleeping":
        pose = 6
    elif look_x:
        pose = 1 if look_x < 0 else 2
    elif look_y:
        pose = 3 if look_y < 0 else 4
    else:
        pose = 0
    tail = (0, 10, 0, 11)[frame % 40 // 10] if motion else 0
    bob = 2 if motion and frame % 28 >= 14 else 0
    return pose, tail, bob


def gaze_for_pointer(
    widget_rect: tuple[int, int, int, int], global_point: QPoint
) -> tuple[int, int]:
    """Map the global pointer to the same three-step gaze used by the TUI cat."""
    x0, y0, width, height = widget_rect
    x = (global_point.x() - x0) / max(1, width) - 0.5
    y = (global_point.y() - y0) / max(1, height) - 0.5
    return (
        (-1 if x < 0 else 1) if abs(x) > 0.18 else 0,
        (-1 if y < 0 else 1) if abs(y) > 0.18 else 0,
    )


class CatAtlas:
    """Read and composite the existing transparent 4×3 B-12 sprite sheet."""

    def __init__(self, path: Path = ASSET_PATH):
        self.sheet = QImage(str(path)).convertToFormat(QImage.Format.Format_RGBA8888)
        if self.sheet.isNull() or self.sheet.width() % 4 or self.sheet.height() % 3:
            raise ValueError("cybercat_atlas_must_be_a_4_by_3_image")
        self.cell_size = self.sheet.width() // 4
        if self.sheet.height() // 3 != self.cell_size:
            raise ValueError("cybercat_atlas_cells_must_be_square")
        self._cache: OrderedDict[tuple[int, int, int], QImage] = OrderedDict()

    def frame(self, *, phase: str, frame: int, look_x=0, look_y=0, purring=False, motion=True):
        key = pose_for(
            phase,
            frame=frame,
            look_x=look_x,
            look_y=look_y,
            purring=purring,
            motion=motion,
        )
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        pose, tail, bob = key
        side = self.cell_size
        image = self.sheet.copy(QRect((pose % 4) * side, (pose // 4) * side, side, side))
        tail_cell = QRect((tail % 4) * side, (tail // 4) * side, side, side)
        left, top, right, bottom = TAIL_BOX
        tail_image = self.sheet.copy(
            QRect(tail_cell.x() + left, tail_cell.y() + top, right - left, bottom - top)
        )
        painter = QPainter(image)
        painter.drawImage(left, top, tail_image)
        painter.end()
        if bob:
            shifted = QImage(side, side, QImage.Format.Format_RGBA8888)
            shifted.fill(Qt.GlobalColor.transparent)
            painter = QPainter(shifted)
            painter.drawImage(0, bob, image)
            painter.end()
            image = shifted
        if len(self._cache) >= 48:
            self._cache.popitem(last=False)
        self._cache[key] = image
        return image


class CyberCatOverlay(QWidget):
    """Small non-activating, topmost pet overlay; all reactions stay presentation-only."""

    open_chat = Signal()
    menu_requested = Signal(QPoint)
    position_changed = Signal(QPoint)
    phase_changed = Signal(str)

    def __init__(self, *, atlas: CatAtlas | None = None, parent=None):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(parent, flags)
        self.setObjectName("b12CyberCatOverlay")
        self.setWindowTitle("B-12 · Кіберкіт")
        self.setAccessibleName("B-12, кіберкіт")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setFixedSize(244, 272)
        self.atlas = atlas or CatAtlas()
        self.phase = "idle"
        self.detail = ""
        self.motion = True
        self.frame = 0
        self.look_x = 0
        self.look_y = 0
        self._reaction_until = 0.0
        self._phase_until = 0.0
        self._drag_origin: QPoint | None = None
        self._widget_origin: QPoint | None = None
        self._dragged = False
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_phase(self, phase: str, detail: str = "") -> None:
        if phase not in PHASES:
            raise ValueError("unknown_companion_phase")
        self.phase = phase
        self.detail = detail[:80]
        self._phase_until = (
            time.monotonic() + 3 if phase in ("success", "error", "cancelled") else 0
        )
        self.phase_changed.emit(phase)
        self.update()

    def toggle_motion(self) -> None:
        self.motion = not self.motion
        self.update()

    def _tick(self) -> None:
        now = time.monotonic()
        if self._phase_until and now >= self._phase_until:
            self.set_phase("idle")
        if now < self._reaction_until:
            self.update()
        if self.motion:
            self.frame += 1
        from PySide6.QtGui import QCursor

        self.look_x, self.look_y = gaze_for_pointer(
            (self.x(), self.y(), self.width(), self.height()), QCursor.pos()
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        title, caption, accent = PHASES[self.phase]
        if time.monotonic() < self._reaction_until:
            caption, accent = "Мурр… це було приємно ♥", "#ff79c8"
        elif self.detail:
            caption = self.detail
        image = self.atlas.frame(
            phase=self.phase,
            frame=self.frame,
            look_x=self.look_x,
            look_y=self.look_y,
            purring=time.monotonic() < self._reaction_until,
            motion=self.motion,
        )
        painter.drawImage(QRectF(12, 0, 220, 220), image)
        card = QRectF(17, 220, 210, 45)
        painter.setPen(QPen(QColor(accent), 1.2))
        painter.setBrush(QColor(8, 13, 27, 218))
        painter.drawRoundedRect(card, 9, 9)
        painter.setPen(QColor(accent))
        painter.drawText(QRectF(25, 224, 194, 17), Qt.AlignmentFlag.AlignCenter, title)
        painter.setPen(QColor("#c4cce0"))
        painter.drawText(QRectF(25, 241, 194, 18), Qt.AlignmentFlag.AlignCenter, caption[:30])
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        if event.button() == Qt.MouseButton.RightButton:
            self.menu_requested.emit(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._widget_origin = self.pos()
            self._dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        if self._drag_origin is not None and self._widget_origin is not None:
            delta = event.globalPosition().toPoint() - self._drag_origin
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
                self.move(self._widget_origin + delta)
                self.position_changed.emit(self.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        if event.button() == Qt.MouseButton.LeftButton and self._drag_origin is not None:
            if not self._dragged:
                self._reaction_until = time.monotonic() + 1.8
                self.open_chat.emit()
                self.update()
            else:
                self.position_changed.emit(self.pos())
            self._drag_origin = None
            self._widget_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
