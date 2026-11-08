"""Transparent desktop companion with the built-in cat and optional local skins."""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from b12.skins import SkinManifest

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

ACTION_LABELS = {
    "intro": "З’ЯВЛЯЮСЯ",
    "curious": "ЦІКАВО…",
    "talk": "РОЗПОВІДАЮ",
    "sit": "ПЕРЕПОЧИНУ",
    "lounge": "РЕЛАКСУЮ",
    "peek": "ВИГЛЯДАЮ",
    "leap": "СТРИБОК!",
    "fall": "ОЙ…",
    "throw": "ПОЛІТ",
    "held": "ТРИМАЮСЯ",
    "tumble": "ПЕРЕКИД",
    "ko": "ПЕРЕЗАВАНТАЖЕННЯ",
    "teleport": "ЗСУВ КООРДИНАТ",
    "satellite": "ОРБІТА",
    "beam": "ПРОМІНЬ",
    "lightning": "ІМПУЛЬС",
    "shards": "ЦИФРОВІ УРИВКИ",
    "shockwave": "ХВИЛЯ",
    "speed": "РИВОК",
    "celebrate": "Є!",
    "glitch": "ПЕРЕЗ’ЄДНУЮСЯ",
    "cutin": "УВАГА!",
    "sleep": "СОН",
}
ACTION_DURATIONS_MS = {
    "intro": 1700,
    "curious": 1300,
    "talk": 1600,
    "sit": 2200,
    "lounge": 2400,
    "peek": 1500,
    "leap": 1050,
    "fall": 1300,
    "throw": 1400,
    "held": 900,
    "tumble": 1500,
    "ko": 1900,
    "teleport": 1150,
    "satellite": 2200,
    "beam": 1700,
    "lightning": 900,
    "shards": 1250,
    "shockwave": 1100,
    "speed": 850,
    "celebrate": 1500,
    "glitch": 950,
    "cutin": 1150,
    "sleep": 1700,
}
PHASE_ACTIONS = {
    "typing": "curious",
    "thinking": "satellite",
    "speaking": "talk",
    "working": "speed",
    "approval": "held",
    "success": "celebrate",
    "error": "glitch",
    "cancelled": "shockwave",
    "sleeping": "sleep",
}


def _action_pose(action: str, progress: float) -> tuple[float, float, float, float, float, float]:
    """Return original Qt presentation transforms: x/y, angle, x/y scale, opacity."""
    t = min(1.0, max(0.0, progress))
    wave = math.sin(math.pi * t)
    pulse = math.sin(math.tau * t)
    poses = {
        "intro": (0, 18 * (1 - t), -6 * wave, 0.62 + 0.38 * t, 0.62 + 0.38 * t, t),
        "curious": (5 * pulse, -4 * wave, 7 * wave, 1.0 + 0.035 * wave, 1.0 - 0.025 * wave, 1),
        "talk": (2 * pulse, -2 * abs(pulse), 2.5 * pulse, 1.0, 1.0 + 0.025 * abs(pulse), 1),
        "sit": (0, 9 * wave, 0, 1.0, 0.92, 1),
        "lounge": (9 * wave, 4 * wave, 7 * wave, 0.98, 0.9, 1),
        "peek": (12 * (1 - t), 0, 0, 0.94 + 0.06 * t, 1, 1),
        "leap": (0, -48 * wave, -4 * pulse, 1.0 - 0.07 * wave, 1.0 + 0.09 * wave, 1),
        "fall": (12 * t, 34 * wave, 68 * wave, 0.88, 0.88, 1 - 0.12 * wave),
        "throw": (42 * wave, -58 * wave, 540 * t, 0.76, 0.76, 1),
        "held": (3 * pulse, -3 * wave, 5 * pulse, 0.94, 0.94, 1),
        "tumble": (0, -13 * wave, 540 * t, 0.7 + 0.12 * wave, 0.7 + 0.12 * wave, 1),
        "ko": (0, 15 * t, -10 * math.sin(math.pi * t * 2) * (1 - t), 0.78, 0.78, 1 - 0.23 * t),
        "teleport": (0, 0, 0, 0.76 + 0.24 * abs(pulse), 0.76 + 0.24 * abs(pulse), abs(pulse)),
        "satellite": (2 * pulse, -2 * wave, 1.5 * pulse, 1.0, 1.0, 1),
        "beam": (0, -2 * wave, 0, 1.0 + 0.018 * wave, 1.0, 1),
        "lightning": (2 * pulse, 0, 3 * pulse, 0.97, 1.02, 1),
        "shards": (0, -5 * wave, -2 * pulse, 1.0, 1.0, 1),
        "shockwave": (0, -5 * wave, 0, 1.0 + 0.02 * wave, 1.0 + 0.02 * wave, 1),
        "speed": (16 * pulse, -2 * wave, 3 * pulse, 0.97, 1.02, 1),
        "celebrate": (0, -17 * abs(pulse), 5 * pulse, 0.94 + 0.08 * wave, 0.94 + 0.08 * wave, 1),
        "glitch": (5 * pulse, 0, 0, 0.98, 1, 0.88 + 0.12 * abs(pulse)),
        "cutin": (4 * pulse, 0, -5 * pulse, 0.96 + 0.04 * wave, 0.96 + 0.04 * wave, 1),
        "sleep": (0, 8 * wave, 4 * wave, 0.9, 0.88, 0.85),
    }
    return poses.get(action, (0, 0, 0, 1, 1, 1))


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


class QtPackAtlas:
    """Render a validated shared manifest atlas without TUI's opaque background."""

    def __init__(self, manifest: SkinManifest):
        self.manifest = manifest
        source = QImage(str(manifest.atlas_path))
        if source.isNull():
            raise ValueError("skin_atlas_unreadable")
        self.sheet = source.convertToFormat(QImage.Format.Format_RGBA8888)
        expected = (
            manifest.frame_width * manifest.columns,
            manifest.frame_height * manifest.rows,
        )
        if (self.sheet.width(), self.sheet.height()) != expected:
            raise ValueError("skin_atlas_dimensions_changed")
        self._cache: OrderedDict[int, QImage] = OrderedDict()

    def frame(
        self,
        *,
        phase: str,
        frame: int,
        look_x=0,
        look_y=0,
        purring=False,
        motion=True,
    ) -> QImage:
        phases = self.manifest.phases
        reaction = ""
        if purring and "purr" in phases:
            reaction = "purr"
        elif phase in ("idle", "typing"):
            if look_x:
                reaction = "look_left" if look_x < 0 else "look_right"
            elif look_y:
                reaction = "look_up" if look_y < 0 else "look_down"
        sequence = phases.get(reaction) or phases.get(phase) or phases["idle"]
        offset = frame * 120 // self.manifest.frame_duration_ms if motion else 0
        index = sequence[offset % len(sequence)]
        cached = self._cache.get(index)
        if cached is not None:
            self._cache.move_to_end(index)
            return cached
        manifest = self.manifest
        cell = QRect(
            index % manifest.columns * manifest.frame_width,
            index // manifest.columns * manifest.frame_height,
            manifest.frame_width,
            manifest.frame_height,
        )
        image = self.sheet.copy(cell)
        if len(self._cache) >= 48:
            self._cache.popitem(last=False)
        self._cache[index] = image
        return image


class CompanionOverlay(QWidget):
    """Small non-activating, topmost pet overlay; reactions stay presentation-only."""

    open_chat = Signal()
    menu_requested = Signal(QPoint)
    position_changed = Signal(QPoint)
    phase_changed = Signal(str)
    activity = Signal()

    def __init__(
        self,
        *,
        atlas: CatAtlas | QtPackAtlas | None = None,
        appearance_id: str = "cybercat",
        appearance_name: str = "КІБЕРКІТ",
        parent=None,
    ):
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(parent, flags)
        self.setObjectName("b12CompanionOverlay")
        self.appearance_id = appearance_id
        self.appearance_name = appearance_name
        self.setWindowTitle(f"Capri · {appearance_name}")
        self.setAccessibleName(f"Capri, {appearance_name}")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setFixedSize(300, 410)
        self.atlas = atlas or CatAtlas()
        self.phase = "idle"
        self.detail = ""
        self.owner_name = ""
        self.motion = True
        self.frame = 0
        self.look_x = 0
        self.look_y = 0
        self._reaction_until = 0.0
        self._phase_until = 0.0
        self._action = ""
        self._action_started = 0.0
        self._action_duration = 0.0
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
        self._action = ""
        action = PHASE_ACTIONS.get(phase)
        if action and self.appearance_id == "capri":
            self.play_action(action)
        self.phase_changed.emit(phase)
        self.update()

    def play_action(self, action: str, *, duration_ms: int | None = None) -> None:
        """Play a bounded, presentation-only gesture composed from the local sprite."""
        if action not in ACTION_DURATIONS_MS:
            raise ValueError("unknown_companion_action")
        if not self.motion:
            self._action = ""
            self.update()
            return
        duration = duration_ms or ACTION_DURATIONS_MS[action]
        self._action = action
        self._action_started = time.monotonic()
        self._action_duration = max(120, min(8000, int(duration))) / 1000
        self.update()

    def set_motion(self, enabled: bool) -> None:
        self.motion = bool(enabled)
        if not self.motion:
            self._action = ""
        self.update()

    def _current_action(self) -> tuple[str, float]:
        if not self._action or not self.motion:
            return "", 0.0
        progress = (time.monotonic() - self._action_started) / self._action_duration
        if progress >= 1:
            if PHASE_ACTIONS.get(self.phase) == self._action:
                self._action_started = time.monotonic()
                return self._action, 0.0
            self._action = ""
            return "", 0.0
        return self._action, max(0.0, progress)

    def toggle_motion(self) -> None:
        self.motion = not self.motion
        self.update()

    def set_appearance(
        self,
        appearance_id: str,
        appearance_name: str,
        atlas: CatAtlas | QtPackAtlas,
    ) -> None:
        self.appearance_id = appearance_id
        self.appearance_name = appearance_name
        self.atlas = atlas
        self.setWindowTitle(f"Capri · {appearance_name}")
        self.setAccessibleName(f"Capri, {appearance_name}")
        self.update()

    def set_owner_name(self, name: str) -> None:
        """Use the owner-authored display name in the idle caption only."""
        self.owner_name = " ".join(str(name).split())[:24]
        self.update()

    @property
    def is_dragging(self) -> bool:
        return self._drag_origin is not None

    def _tick(self) -> None:
        now = time.monotonic()
        if self._phase_until and now >= self._phase_until:
            self.set_phase("idle")
        if now < self._reaction_until:
            self.update()
        if self.motion:
            self.frame += 1
            if self._action:
                self.update()
        from PySide6.QtGui import QCursor

        self.look_x, self.look_y = gaze_for_pointer(
            (self.x(), self.y(), self.width(), self.height()), QCursor.pos()
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        title, caption, accent = PHASES[self.phase]
        action, progress = self._current_action()
        if self.phase == "idle" and self.owner_name:
            caption = f"Я тут, {self.owner_name}"[:36]
        if time.monotonic() < self._reaction_until:
            caption, accent = "Мурр… це було приємно ♥", "#ff79c8"
        elif self.detail:
            caption = self.detail
        elif action:
            caption = ACTION_LABELS[action]
        image = self.atlas.frame(
            phase=self.phase,
            frame=self.frame,
            look_x=self.look_x,
            look_y=self.look_y,
            purring=time.monotonic() < self._reaction_until,
            motion=self.motion,
        )
        image_area = QRectF(14, 2, 272, 334)
        scale = min(image_area.width() / image.width(), image_area.height() / image.height())
        draw_width = image.width() * scale
        draw_height = image.height() * scale
        image_rect = QRectF(
            image_area.center().x() - draw_width / 2,
            image_area.center().y() - draw_height / 2,
            draw_width,
            draw_height,
        )
        if isinstance(self.atlas, QtPackAtlas) and not any(
            direction in self.atlas.manifest.phases
            for direction in ("look_left", "look_right", "look_up", "look_down")
        ):
            # Keep cursor feedback for packs without registered eye/gaze frames.
            image_rect.translate(self.look_x * 3, self.look_y * 2)
        image_opacity = 0.58 if self.phase == "sleeping" else 1.0
        self._draw_action_fx(painter, action, progress)
        dx, dy, angle, scale_x, scale_y, opacity = _action_pose(action, progress)
        painter.save()
        painter.translate(image_rect.center())
        painter.rotate(angle)
        painter.scale(scale_x, scale_y)
        painter.setOpacity(image_opacity * opacity)
        painter.drawImage(
            QRectF(
                -image_rect.width() / 2 + dx,
                -image_rect.height() / 2 + dy,
                image_rect.width(),
                image_rect.height(),
            ),
            image,
        )
        painter.restore()
        painter.setOpacity(1.0)
        card = QRectF(20, 344, 260, 52)
        if self.appearance_id == "capri":
            path = QPainterPath()
            path.moveTo(card.left() + 13, card.top())
            path.lineTo(card.right(), card.top())
            path.lineTo(card.right(), card.bottom() - 12)
            path.lineTo(card.right() - 12, card.bottom())
            path.lineTo(card.left(), card.bottom())
            path.lineTo(card.left(), card.top() + 13)
            path.closeSubpath()
            painter.setPen(QPen(QColor("#ff0054"), 1.6))
            painter.setBrush(QColor(8, 5, 16, 230))
            painter.drawPath(path)
            title_color = QColor("#00ef83")
            caption_color = QColor("#f1e8f2")
            painter.setPen(QPen(QColor("#00ef83"), 2))
            painter.drawLine(232, 352, 249, 352)
            painter.drawLine(254, 352, 261, 352)
        else:
            painter.setPen(QPen(QColor(accent), 1.2))
            painter.setBrush(QColor(8, 13, 27, 218))
            painter.drawRoundedRect(card, 9, 9)
            title_color = QColor(accent)
            caption_color = QColor("#c4cce0")
        painter.setPen(title_color)
        painter.drawText(QRectF(30, 347, 220, 18), Qt.AlignmentFlag.AlignLeft, title)
        painter.setPen(caption_color)
        painter.drawText(QRectF(30, 366, 232, 22), Qt.AlignmentFlag.AlignLeft, caption[:36])
        painter.end()

    def _draw_action_fx(self, painter: QPainter, action: str, progress: float) -> None:
        """Draw clean-room neon motion accents; no upstream sprites or FX assets."""
        if not action:
            return
        t = progress
        cx, cy = 150.0, 168.0
        pulse = math.sin(math.pi * t)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if action in {"teleport", "shockwave", "intro"}:
            color = QColor("#ff0054" if action == "teleport" else "#00ef83")
            color.setAlphaF(max(0.08, 1 - t))
            painter.setPen(QPen(color, 2.2 if action != "intro" else 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            radius = 24 + t * (150 if action == "shockwave" else 104)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
            if action in {"teleport", "intro"}:
                inner = max(2, radius * 0.58)
                color.setAlphaF(max(0.06, 0.75 - t))
                painter.setPen(QPen(color, 1.4))
                painter.drawEllipse(QRectF(cx - inner, cy - inner, inner * 2, inner * 2))
        elif action == "satellite":
            angle = math.tau * t * 1.6
            rx, ry = 128.0, 42.0
            painter.setPen(QPen(QColor(255, 0, 84, 100), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2, ry * 2))
            sx, sy = cx + math.cos(angle) * rx, cy + math.sin(angle) * ry
            painter.setPen(QPen(QColor("#00ef83"), 1.3))
            painter.setBrush(QColor(0, 239, 131, 220))
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(sx, sy - 7),
                        QPointF(sx + 7, sy),
                        QPointF(sx, sy + 7),
                        QPointF(sx - 7, sy),
                    ]
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(QPointF(cx, cy), QPointF(sx, sy))
        elif action == "beam":
            alpha = int(70 + 120 * pulse)
            path = QPainterPath()
            path.moveTo(64, 94)
            path.lineTo(116, 119)
            path.lineTo(214, 302)
            path.lineTo(182, 315)
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 239, 131, alpha))
            painter.drawPath(path)
            painter.setPen(QPen(QColor(255, 0, 84, alpha), 2))
            painter.drawLine(QPointF(86, 102), QPointF(202, 306))
        elif action == "lightning":
            path = QPainterPath()
            path.moveTo(206, 56)
            for index, (x, y) in enumerate(
                ((174, 96), (194, 112), (146, 163), (166, 181), (125, 226))
            ):
                path.lineTo(x + math.sin(index * 8.7 + t * 20) * 5, y)
            painter.setPen(
                QPen(
                    QColor("#00ef83"),
                    3.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(path)
            painter.setPen(QPen(QColor("#ff0054"), 1.2))
            painter.drawPath(path)
        elif action == "shards":
            painter.setPen(QPen(QColor(255, 0, 84, 185), 1.1))
            painter.setBrush(QColor(0, 239, 131, 90))
            for index in range(7):
                angle = math.tau * index / 7 + t * 0.9
                distance = 48 + 66 * t
                x, y = cx + math.cos(angle) * distance, cy + math.sin(angle) * distance
                painter.drawPolygon(
                    QPolygonF(
                        [
                            QPointF(x, y),
                            QPointF(
                                x + math.cos(angle + 0.35) * 15, y + math.sin(angle + 0.35) * 15
                            ),
                            QPointF(x + math.cos(angle - 0.4) * 24, y + math.sin(angle - 0.4) * 24),
                        ]
                    )
                )
        elif action == "speed":
            painter.setPen(QPen(QColor(0, 239, 131, 115), 1.4))
            for index in range(8):
                y = 76 + index * 26
                offset = (t * 90 + index * 29) % 54
                painter.drawLine(QPointF(16 + offset, y), QPointF(56 + offset, y))
                painter.drawLine(QPointF(225 - offset, y + 8), QPointF(278 - offset, y + 8))
        elif action == "glitch":
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(6):
                y = 48 + ((index * 47 + int(t * 160)) % 270)
                width = 34 + ((index * 31) % 92)
                color = QColor("#ff0054" if index % 2 else "#00ef83")
                color.setAlpha(75 + (index * 19) % 100)
                painter.setBrush(color)
                x = (index * 59 + int(t * (170 if index % 2 else -110))) % 250
                painter.drawRect(QRectF(x, y, width, 2 + index % 3))
        elif action == "cutin":
            alpha = int(90 + 125 * pulse)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 0, 84, alpha))
            painter.drawPolygon(
                QPolygonF([QPointF(0, 44), QPointF(300, 20), QPointF(300, 38), QPointF(0, 62)])
            )
            painter.setBrush(QColor(0, 239, 131, alpha))
            painter.drawPolygon(
                QPolygonF([QPointF(0, 296), QPointF(300, 322), QPointF(300, 340), QPointF(0, 314)])
            )
            painter.setPen(QPen(QColor("#090b12"), 1))
            painter.drawText(
                QRectF(26, 29, 248, 25), Qt.AlignmentFlag.AlignLeft, "// CAPRI  ·  З’ЯВЛЯЄТЬСЯ"
            )
        elif action == "sleep":
            painter.setPen(QPen(QColor("#00ef83"), 1.7))
            painter.drawText(QRectF(206, 72 - 18 * t, 38, 24), Qt.AlignmentFlag.AlignCenter, "Z")
            painter.drawText(QRectF(228, 48 - 12 * t, 28, 20), Qt.AlignmentFlag.AlignCenter, "z")
        elif action in {"fall", "throw", "tumble", "leap", "ko"}:
            painter.setPen(QPen(QColor(0, 239, 131, 110), 1.2))
            for index in range(5):
                x = 38 + index * 48
                shift = 18 * t
                painter.drawLine(QPointF(x, 78 + shift), QPointF(x - 8, 112 + shift))
        elif action == "celebrate":
            painter.setPen(QPen(QColor("#00ef83"), 2))
            for index in range(5):
                angle = math.tau * index / 5 + t * 3
                x = cx + math.cos(angle) * (88 + 20 * pulse)
                y = cy + math.sin(angle) * (96 + 18 * pulse)
                painter.drawLine(QPointF(x - 4, y), QPointF(x + 4, y))
                painter.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
        painter.restore()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        self.activity.emit()
        if event.button() == Qt.MouseButton.RightButton:
            self.menu_requested.emit(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self.appearance_id == "capri":
                self.play_action("held")
            self._drag_origin = event.globalPosition().toPoint()
            self._widget_origin = self.pos()
            self._dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        self.activity.emit()
        if self._drag_origin is not None and self._widget_origin is not None:
            delta = event.globalPosition().toPoint() - self._drag_origin
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
                self.move(self._widget_origin + delta)
                self.position_changed.emit(self.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        self.activity.emit()
        if event.button() == Qt.MouseButton.LeftButton and self._drag_origin is not None:
            if not self._dragged:
                self._reaction_until = time.monotonic() + 1.8
                if self.appearance_id == "capri":
                    self.play_action("curious")
                self.open_chat.emit()
                self.update()
            else:
                self.position_changed.emit(self.pos())
                if self.appearance_id == "capri":
                    self.play_action("throw")
            self._drag_origin = None
            self._widget_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


# Compatibility for callers which used the original class name.
CyberCatOverlay = CompanionOverlay
