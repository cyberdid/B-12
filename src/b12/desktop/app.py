"""Desktop companion application shell, tray, and owner-token loading."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QActionGroup, QCursor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from b12.desktop.cat import CatAtlas, CompanionOverlay, QtPackAtlas
from b12.desktop.chat import ChatWindow
from b12.desktop.client import DesktopApiClient, DesktopApiError
from b12.desktop.workers import ApiJob
from b12.skins import SkinManifest, SkinOption, available_skins


def skin_directory() -> Path:
    """Resolve the optional desktop pack without triggering a download."""
    configured = os.environ.get("B12_CAPRI_DIR") or os.environ.get("B12_TUI_CAPRI_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "b12" / "skins" / "capri"


def load_owner_token(state_dir: Path) -> str:
    """Read the existing token in place; never create or copy credentials."""
    token_path = Path(state_dir) / "api" / "owner.token"
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DesktopApiError("owner_token_missing") from exc
    if not token:
        raise DesktopApiError("owner_token_missing")
    return token


def default_overlay_position(screen: QRect, size: QSize, margin: int = 18) -> QPoint:
    """Place the overlay inside the chosen display with a small edge margin."""
    x = screen.right() - size.width() - margin + 1
    y = screen.bottom() - size.height() - margin + 1
    return QPoint(max(screen.left(), x), max(screen.top(), y))


def restore_overlay_position(
    saved: QPoint | None,
    screens: list[QRect],
    size: QSize,
    margin: int = 18,
) -> QPoint:
    """Keep saved positions on a connected display and clamp the whole pet into view."""
    if not screens:
        return saved or QPoint(0, 0)
    anchor = saved or default_overlay_position(screens[0], size, margin)
    center = anchor + QPoint(size.width() // 2, size.height() // 2)
    screen = min(screens, key=lambda candidate: (candidate.center() - center).manhattanLength())
    max_x = max(screen.left(), screen.right() - size.width() - margin + 1)
    max_y = max(screen.top(), screen.bottom() - size.height() - margin + 1)
    return QPoint(
        min(max(anchor.x(), screen.left() + margin), max_x),
        min(max(anchor.y(), screen.top() + margin), max_y),
    )


class DesktopShell(QObject):
    """Own the pet, chat, tray and lightweight approval notifications."""

    def __init__(self, app: QApplication, client: DesktopApiClient, persist_default: bool):
        super().__init__(app)
        self.app = app
        self.client = client
        self.settings = QSettings("B-12", "NeonCompanion")
        self.skin_options = available_skins(skin_directory())
        self.skin_by_id = {option.id: option for option in self.skin_options}
        saved_appearance = str(self.settings.value("appearance", ""))
        initial_appearance = saved_appearance if saved_appearance in self.skin_by_id else ""
        if not initial_appearance:
            initial_appearance = "capri" if "capri" in self.skin_by_id else "cybercat"
        try:
            atlas, appearance_name = self._load_appearance(initial_appearance)
        except Exception:
            initial_appearance = "cybercat"
            atlas, appearance_name = CatAtlas(), "КІБЕРКІТ"
        self.overlay = CompanionOverlay(
            atlas=atlas,
            appearance_id=initial_appearance,
            appearance_name=appearance_name,
        )
        self.chat = ChatWindow(client, persist_default=persist_default)
        self.chat.phase_changed.connect(self.overlay.set_phase)
        self.chat.phase_changed.connect(self._remember_phase)
        self.overlay.open_chat.connect(self._pet_clicked)
        self.overlay.position_changed.connect(self._save_position)
        self.overlay.menu_requested.connect(self.show_pet_menu)
        self._last_approval_ids: set[str] | None = None
        self._notification_job: ApiJob | None = None
        self._menu = self._build_menu()
        self._tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(self._icon(), self)
            self._tray.setToolTip(f"B-12 · {self.overlay.appearance_name}")
            self._tray.setContextMenu(self._menu)
            self._tray.activated.connect(self._tray_activated)
            self._tray.show()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5000)
        self._poll_timer.timeout.connect(self._poll_notifications)
        self._poll_timer.start()
        self._place_overlay()
        self.overlay.show()
        self._poll_notifications()

    def _icon(self) -> QIcon:
        frame = self.overlay.atlas.frame(phase="idle", frame=0, motion=False)
        pixmap = QPixmap.fromImage(frame).scaled(
            QSize(48, 48),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return QIcon(pixmap)

    def _load_appearance(self, appearance_id: str):
        if appearance_id == "cybercat":
            return CatAtlas(), "КІБЕРКІТ"
        option: SkinOption | None = self.skin_by_id.get(appearance_id)
        if option is None or option.manifest_path is None:
            raise ValueError("skin_unavailable")
        manifest = SkinManifest.load(option.manifest_path)
        if manifest.id != appearance_id:
            raise ValueError("skin_manifest_changed")
        return QtPackAtlas(manifest), manifest.display_name

    def set_appearance(self, appearance_id: str) -> None:
        try:
            atlas, appearance_name = self._load_appearance(appearance_id)
        except Exception:
            # Optional pack changes must never prevent the built-in appearance from working.
            appearance_id = "cybercat"
            atlas, appearance_name = CatAtlas(), "КІБЕРКІТ"
        self.overlay.set_appearance(appearance_id, appearance_name, atlas)
        self.settings.setValue("appearance", appearance_id)
        for skin_id, action in self.appearance_actions.items():
            action.setChecked(skin_id == appearance_id)
        if self._tray is not None:
            self._tray.setToolTip(f"B-12 · {appearance_name}")
            self._tray.setIcon(self._icon())

    def _place_overlay(self) -> None:
        size = self.overlay.size()
        saved = self.settings.value("overlay/position")
        if isinstance(saved, tuple) and len(saved) == 2:
            saved = QPoint(int(saved[0]), int(saved[1]))
        if not isinstance(saved, QPoint):
            saved = None
        screens = [screen.availableGeometry() for screen in self.app.screens()]
        if saved is None:
            screen = self.app.screenAt(QCursor.pos()) or self.app.primaryScreen()
            position = default_overlay_position(screen.availableGeometry(), size)
        else:
            position = restore_overlay_position(saved, screens, size)
        self.overlay.move(position)

    def _save_position(self, point: QPoint) -> None:
        self.settings.setValue("overlay/position", point)

    def _remember_phase(self, phase: str, detail: str) -> None:
        self.settings.setValue("overlay/last_phase", phase)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background:#0b1020; color:#dbe4f5; border:1px solid #304666; padding:6px; }"
            "QMenu::item:selected { background:#15324a; color:#69f4df; }"
        )
        self.open_chat_action = menu.addAction("ЗВ’ЯЗАТИСЯ З B-12")
        self.open_chat_action.triggered.connect(self.show_chat)
        self.new_chat_action = menu.addAction("＋ НОВА РОЗМОВА")
        self.new_chat_action.triggered.connect(self._new_chat)
        menu.addSeparator()
        appearance_menu = menu.addMenu("ВИГЛЯД COMPANION")
        self.appearance_actions = {}
        self.appearance_group = QActionGroup(self)
        self.appearance_group.setExclusive(True)
        for option in self.skin_options:
            action = appearance_menu.addAction(option.display_name)
            action.setCheckable(True)
            action.setChecked(option.id == self.overlay.appearance_id)
            self.appearance_group.addAction(action)
            action.triggered.connect(
                lambda checked=False, skin_id=option.id: (
                    self.set_appearance(skin_id) if checked else None
                )
            )
            self.appearance_actions[option.id] = action
        if "capri" not in self.skin_by_id:
            unavailable = appearance_menu.addAction("Capri: локальний пак не встановлено")
            unavailable.setEnabled(False)
        menu.addSeparator()
        self.pet_action = menu.addAction("ЗАСНУТИ / ПРОКИНУТИСЯ")
        self.pet_action.triggered.connect(self.toggle_pet)
        self.motion_action = menu.addAction("ПАУЗА АНІМАЦІЇ")
        self.motion_action.setCheckable(True)
        self.motion_action.triggered.connect(self.overlay.toggle_motion)
        menu.addSeparator()
        self.mute_action = menu.addAction("ЗАБЛОКУВАТИ МІКРОФОН")
        self.mute_action.triggered.connect(lambda: self.chat.set_voice_muted(True))
        self.unmute_action = menu.addAction("ЗНЯТИ БЛОКУВАННЯ МІКРОФОНА")
        self.unmute_action.triggered.connect(lambda: self.chat.set_voice_muted(False))
        menu.addSeparator()
        self.web_action = menu.addAction("ВІДКРИТИ B-12 WEB UI")
        self.web_action.triggered.connect(self.open_web_ui)
        self.quit_action = menu.addAction("ВИЙТИ")
        self.quit_action.triggered.connect(self.app.quit)
        return menu

    def show_pet_menu(self, point: QPoint) -> None:
        self._menu.popup(point)

    def _tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_chat()

    def show_chat(self) -> None:
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()

    def _pet_clicked(self) -> None:
        if self.overlay.phase == "sleeping":
            self.overlay.set_phase("idle")
        self.show_chat()

    def _new_chat(self) -> None:
        self.show_chat()
        self.chat.create_session()

    def toggle_pet(self) -> None:
        if self.overlay.isVisible():
            self.overlay.set_phase("sleeping")
            if self._tray is not None:
                self.overlay.hide()
        else:
            self.overlay.set_phase("idle")
            self.overlay.show()

    def open_web_ui(self) -> None:
        QDesktopServices.openUrl(QUrl(self.client.base_url))

    def _poll_notifications(self) -> None:
        if self._notification_job is not None:
            return

        def poll():
            if not self.client.health():
                return {"connected": False, "approvals": []}
            return {"connected": True, "approvals": self.client.approvals()}

        job = ApiJob("notifications", poll)
        self._notification_job = job
        job.signals.result.connect(self._notifications_ready)
        job.signals.error.connect(self._notifications_failed)
        job.signals.finished.connect(self._notification_finished)
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(job)

    def _notifications_ready(self, tag: str, result: dict) -> None:
        if not result.get("connected"):
            if self.overlay.phase not in {"error", "approval"}:
                self.overlay.set_phase("error", "API B-12 офлайн")
            return
        if self.overlay.phase == "error":
            self.overlay.set_phase("idle")
        approvals = result.get("approvals", [])
        ids = {str(item.get("operation_id")) for item in approvals}
        if self._last_approval_ids is None:
            self._last_approval_ids = ids
            if ids:
                first = approvals[0]
                self.overlay.set_phase("approval", str(first.get("name", "дія")))
                if self._tray is not None:
                    self._tray.showMessage(
                        "B-12 потребує твого рішення",
                        f"Підтверди або відхили дію {first.get('name', 'B-12')} у чаті.",
                        QSystemTrayIcon.MessageIcon.Warning,
                        8000,
                    )
            return
        new_ids = ids - self._last_approval_ids
        self._last_approval_ids = ids
        if new_ids:
            first = next(item for item in approvals if str(item.get("operation_id")) in new_ids)
            self.overlay.set_phase("approval", str(first.get("name", "дія")))
            if self._tray is not None:
                self._tray.showMessage(
                    "B-12 потребує твого рішення",
                    f"Підтверди або відхили дію {first.get('name', 'B-12')} у чаті.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    8000,
                )
        elif not ids and self.overlay.phase == "approval":
            self.overlay.set_phase("idle")

    def _notifications_failed(self, tag: str, code: str) -> None:
        if self.overlay.phase != "approval":
            self.overlay.set_phase("error", code)

    def _notification_finished(self, job) -> None:
        if job is self._notification_job:
            self._notification_job = None

    def shutdown(self) -> None:
        self._poll_timer.stop()
        if self._tray is not None:
            self._tray.hide()
        self.overlay.close()
        self.chat.close()
        # Closing the stream client lets the API observe disconnect and cancel active work.
        # Approval waits remain server-owned and expire under the existing control policy.
        self.client.close()


def run_desktop(settings, url: str, *, persist_default: bool = False) -> int:
    """Launch the native client only; server/model/audio processes are never started here."""
    token = load_owner_token(settings.state_dir)
    client = DesktopApiClient(url, token)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("B-12 Neon Companion")
    app.setOrganizationName("B-12")
    app.setQuitOnLastWindowClosed(False)
    shell = DesktopShell(app, client, persist_default)
    app.aboutToQuit.connect(shell.shutdown)
    return int(app.exec())
