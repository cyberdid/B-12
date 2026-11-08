"""Desktop companion application shell, tray, and owner-token loading."""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QPoint,
    QRect,
    QSettings,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QActionGroup, QCursor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon, QToolTip

from b12.desktop.actions import (
    CommandDraftDialog,
    LauncherDialog,
    PromptShortcutDialog,
    ReminderDialog,
    SiteShortcutDialog,
    due_reminders,
    read_items,
)
from b12.desktop.activity import ActivityJournal
from b12.desktop.cat import ACTION_LABELS, CatAtlas, CompanionOverlay, QtPackAtlas
from b12.desktop.chat import ChatWindow
from b12.desktop.client import DesktopApiClient, DesktopApiError
from b12.desktop.presentation import AutostartDialog, GuideDialog
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
        from b12.desktop.profile import load_companion_profile

        self.overlay.set_owner_name(str(load_companion_profile(self.settings)["name"]))
        self.overlay.motion = not self.settings_value_bool("presentation/reduced_motion", False)
        self._auto_sleep_enabled = self.settings_value_bool("presentation/auto_sleep", True)
        self._last_companion_activity = time.monotonic()
        self._follow_cursor_screen = self.settings_value_bool(
            "presentation/follow_cursor_screen", False
        )
        self._follow_candidate_screen = None
        self._follow_candidate_since = 0.0
        self._wander_active = False
        self._pre_peek_position: QPoint | None = None
        self._wander_timer = QTimer(self)
        self._wander_timer.setInterval(7000)
        self._wander_timer.timeout.connect(self._wander_step)
        self._sound_enabled = self.settings_value_bool("presentation/sounds", False)
        self.activity_journal = ActivityJournal.default()
        self._external_observed_provider = str(
            self.settings.value("integrations/observed_provider", "all")
        )
        self._external_activity_key = self._latest_external_activity_key(
            self._external_observed_provider
        )
        self._external_activity_until = 0.0
        self._external_activity_active = False
        self._external_activity_started = 0.0
        self._external_activity_label = ""
        self._external_phase: str | None = None
        self.chat = ChatWindow(client, persist_default=persist_default)
        self.chat.set_companion_profile_provider(lambda: load_companion_profile(self.settings))
        self.chat.set_compact_character(self.overlay.appearance_name)
        self.chat.phase_changed.connect(self.overlay.set_phase)
        self.chat.phase_changed.connect(self._remember_phase)
        self.chat.phase_changed.connect(self._on_chat_phase)
        self.chat.compact_close_requested.connect(self.hide_compact_chat)
        self.chat.expand_requested.connect(self.show_chat)
        self.chat.compact_actions_requested.connect(self.show_compact_actions)
        self.chat.interaction_recorded.connect(self._record_interaction)
        self.chat.reminder_candidate.connect(self._handle_reminder_candidate)
        self.overlay.open_chat.connect(self._pet_clicked)
        self.overlay.open_chat.connect(lambda: self._record_interaction("pet"))
        self.overlay.activity.connect(self._mark_companion_activity)
        self.overlay.position_changed.connect(self._save_position)
        self.overlay.menu_requested.connect(self.show_pet_menu)
        self._last_approval_ids: set[str] | None = None
        self._notified_reminder_ids: set[str] = set()
        self._notification_job: ApiJob | None = None
        self._menu = self._build_menu()
        self._menu.aboutToShow.connect(self._refresh_pet_menu)
        self._tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(self._icon(), self)
            self._tray.setToolTip(f"Capri · {self.overlay.appearance_name}")
            self._tray.setContextMenu(self._menu)
            self._tray.activated.connect(self._tray_activated)
            self._tray.show()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5000)
        self._poll_timer.timeout.connect(self._poll_notifications)
        self._poll_timer.start()
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(5000)
        self._reminder_timer.timeout.connect(self._poll_reminders)
        self._reminder_timer.start()
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(1000)
        self._activity_timer.timeout.connect(self._poll_external_activity)
        self._activity_timer.start()
        self._presence_timer = QTimer(self)
        self._presence_timer.setInterval(1000)
        self._presence_timer.timeout.connect(self._presence_tick)
        self._presence_timer.start()
        self._place_overlay()
        self.overlay.show()
        if self.overlay.appearance_id == "capri":
            self.overlay.play_action("intro")
        self._poll_notifications()
        self._poll_reminders()

    def settings_value_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

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
        self.chat.set_compact_character(appearance_name)
        self.settings.setValue("appearance", appearance_id)
        if hasattr(self, "animation_menu"):
            self.animation_menu.setEnabled(appearance_id == "capri" and self.overlay.motion)
        for skin_id, action in self.appearance_actions.items():
            action.setChecked(skin_id == appearance_id)
        if self._tray is not None:
            self._tray.setToolTip(f"Capri · {appearance_name}")
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
        self._place_chat_panel()

    def _remember_phase(self, phase: str, detail: str) -> None:
        self.settings.setValue("overlay/last_phase", phase)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background:#0b1020; color:#dbe4f5; border:1px solid #304666; padding:6px; }"
            "QMenu::item:selected { background:#15324a; color:#69f4df; }"
        )
        self.open_chat_action = menu.addAction("КОМПАКТНА РОЗМОВА З CAPRI")
        self.open_chat_action.triggered.connect(self.show_compact_chat)
        self.new_chat_action = menu.addAction("＋ НОВА РОЗМОВА")
        self.new_chat_action.triggered.connect(self._new_chat)
        menu.addSeparator()
        self.reminders_action = menu.addAction("НАГАДУВАННЯ")
        self.reminders_action.triggered.connect(self.show_reminders)
        self.launchers_action = menu.addAction("ЗАПУСТИТИ ПРОГРАМУ…")
        self.launchers_action.triggered.connect(self.show_launchers)
        self.sites_action = menu.addAction("ЯРЛИКИ САЙТІВ…")
        self.sites_action.triggered.connect(self.show_sites)
        self.command_action = menu.addAction("СИСТЕМНА КОМАНДА…")
        self.command_action.triggered.connect(self.show_command_draft)
        self.prompts_action = menu.addAction("ШВИДКІ ФРАЗИ…")
        self.prompts_action.triggered.connect(self.show_prompt_shortcuts)
        self.catchphrases_action = menu.addAction("МОЇ ФРАЗИ…")
        self.catchphrases_action.triggered.connect(self.show_companion_catchphrases)
        self.profile_note_action = menu.addAction("ВСТАВИТИ ПОБАЖАННЯ ДО СТИЛЮ")
        self.profile_note_action.triggered.connect(self.insert_profile_style_note)
        self.profile_action = menu.addAction("ПРОФІЛЬ CAPRI…")
        self.profile_action.triggered.connect(self.show_profile)
        self.integrations_action = menu.addAction("АГЕНТИ / МІСІЇ…")
        self.integrations_action.triggered.connect(self.show_integrations)
        self.local_features_action = menu.addAction("ФАЙЛИ / СИСТЕМА / МЕДІА…")
        self.local_features_action.triggered.connect(self.show_local_features)
        self.runtime_action = menu.addAction("МОДЕЛЬ / СТАН CAPRI")
        self.runtime_action.triggered.connect(self.show_runtime_status)
        menu.addSeparator()
        appearance_menu = menu.addMenu("ВИГЛЯД CAPRI")
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
            unavailable = appearance_menu.addAction("Арт Capri: локальний пак не встановлено")
            unavailable.setEnabled(False)
        menu.addSeparator()
        self.pet_action = menu.addAction("ЗАСНУТИ / ПРОКИНУТИСЯ")
        self.pet_action.triggered.connect(self.toggle_pet)
        self.motion_action = menu.addAction("ЗМЕНШИТИ РУХ")
        self.motion_action.setCheckable(True)
        self.motion_action.setChecked(not self.overlay.motion)
        self.motion_action.triggered.connect(self.set_reduced_motion)
        self.auto_sleep_action = menu.addAction("ЗАСИНАТИ ПІСЛЯ 10 ХВ БЕЗДІЯЛЬНОСТІ")
        self.auto_sleep_action.setCheckable(True)
        self.auto_sleep_action.setChecked(self._auto_sleep_enabled)
        self.auto_sleep_action.triggered.connect(self.set_auto_sleep)
        self.follow_screen_action = menu.addAction("СЛІДУВАТИ ЗА КУРСОРОМ МІЖ ЕКРАНАМИ")
        self.follow_screen_action.setCheckable(True)
        self.follow_screen_action.setChecked(self._follow_cursor_screen)
        self.follow_screen_action.setEnabled(self.overlay.motion)
        self.follow_screen_action.triggered.connect(self.set_follow_cursor_screen)
        self.wander_action = menu.addAction("БЛУКАННЯ")
        self.wander_action.setCheckable(True)
        self.wander_action.triggered.connect(self.set_wander)
        self.peek_action = menu.addAction("ВИГЛЯНУТИ ЗА КРАЙ")
        self.peek_action.triggered.connect(self.peek)
        self.demo_action = menu.addAction("ДЕМОНСТРАЦІЯ")
        self.demo_action.triggered.connect(self.demo)
        self.animation_menu = menu.addMenu("АНІМАЦІЇ CAPRI")
        self.animation_menu.setEnabled(
            self.overlay.appearance_id == "capri" and self.overlay.motion
        )
        self.animation_actions = {}
        animation_groups = {
            "РЕАКЦІЇ": ("intro", "curious", "talk", "sit", "lounge", "peek", "sleep"),
            "РУХ": ("leap", "fall", "throw", "held", "tumble", "ko"),
            "ЕФЕКТИ": (
                "teleport",
                "satellite",
                "beam",
                "lightning",
                "shards",
                "shockwave",
                "speed",
                "celebrate",
                "glitch",
                "cutin",
            ),
        }
        for group, action_ids in animation_groups.items():
            submenu = self.animation_menu.addMenu(group)
            for action_id in action_ids:
                action = submenu.addAction(ACTION_LABELS[action_id])
                action.triggered.connect(
                    lambda checked=False, name=action_id: self.play_animation(name)
                )
                self.animation_actions[action_id] = action
        self.move_to_cursor_action = menu.addAction("ПЕРЕНЕСТИ НА ЕКРАН КУРСОРА")
        self.move_to_cursor_action.triggered.connect(self.move_to_pointer_screen)
        self.sound_action = menu.addAction("ЗВУКОВІ СИГНАЛИ")
        self.sound_action.setCheckable(True)
        self.sound_action.setChecked(self._sound_enabled)
        self.sound_action.triggered.connect(self.set_sound_enabled)
        self.hide_action = menu.addAction("ПРИХОВАТИ ДО TRAY")
        self.hide_action.triggered.connect(self.hide_to_tray)
        self.hide_action.setEnabled(QSystemTrayIcon.isSystemTrayAvailable())
        self.show_pet_action = menu.addAction("ПОКАЗАТИ CAPRI")
        self.show_pet_action.triggered.connect(self.show_pet)
        self.show_pet_action.setVisible(False)
        menu.addSeparator()
        self.guide_action = menu.addAction("ЯК КОРИСТУВАТИСЯ…")
        self.guide_action.triggered.connect(lambda: GuideDialog().exec())
        self.autostart_action = menu.addAction("АВТОЗАПУСК…")
        self.autostart_action.triggered.connect(lambda: AutostartDialog().exec())
        menu.addSeparator()
        self.mute_action = menu.addAction("ЗАБЛОКУВАТИ МІКРОФОН")
        self.mute_action.triggered.connect(lambda: self.chat.set_voice_muted(True))
        self.unmute_action = menu.addAction("ЗНЯТИ БЛОКУВАННЯ МІКРОФОНА")
        self.unmute_action.triggered.connect(lambda: self.chat.set_voice_muted(False))
        menu.addSeparator()
        self.web_action = menu.addAction("ВІДКРИТИ CAPRI WEB UI")
        self.web_action.triggered.connect(self.open_web_ui)
        self.quit_action = menu.addAction("ВИЙТИ")
        self.quit_action.triggered.connect(self.app.quit)
        return menu

    def show_pet_menu(self, point: QPoint) -> None:
        self._refresh_pet_menu()
        self._menu.popup(point)

    def _tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if not self.overlay.isVisible():
                self.show_pet()
            else:
                self.show_compact_chat()

    def _refresh_pet_menu(self) -> None:
        visible = self.overlay.isVisible()
        self.show_pet_action.setVisible(not visible)
        self.hide_action.setVisible(visible)

    def show_pet(self) -> None:
        self._mark_companion_activity()
        self.overlay.show()
        self.overlay.raise_()

    def show_compact_chat(self) -> None:
        self._mark_companion_activity()
        self.chat.set_compact_mode(True)
        self.chat.show()
        self._place_chat_panel()
        self.chat.raise_()
        self.chat.activateWindow()
        self.chat.composer.setFocus()

    def hide_compact_chat(self) -> None:
        if self.chat.is_compact_mode():
            self.chat.hide()

    def show_chat(self) -> None:
        self._mark_companion_activity()
        self.chat.set_compact_mode(False)
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()

    def _pet_clicked(self) -> None:
        self._mark_companion_activity()
        if self.overlay.phase == "sleeping":
            self.overlay.set_phase("idle")
            if self.overlay.appearance_id == "capri":
                self.overlay.play_action("intro")
        if self._sound_enabled:
            QApplication.beep()
        if self.chat.is_compact_mode() and self.chat.isVisible():
            self.hide_compact_chat()
        else:
            self.show_compact_chat()

    def _new_chat(self) -> None:
        self.show_compact_chat()
        self.chat.create_session()

    def _place_chat_panel(self) -> None:
        if not self.chat.is_compact_mode() or not self.chat.isVisible():
            return
        pet_rect = QRect(self.overlay.pos(), self.overlay.size())
        screen = self.app.screenAt(pet_rect.center()) or self.app.primaryScreen()
        available = screen.availableGeometry()
        width = min(420, max(330, available.width() - 24))
        height = min(400, max(320, available.height() - 24))
        self.chat.resize(width, height)
        margin = 12
        x_center = pet_rect.center().x() - width // 2
        candidates = [
            QRect(x_center, pet_rect.bottom() + margin + 1, width, height),
            QRect(x_center, pet_rect.top() - height - margin, width, height),
            QRect(
                pet_rect.right() + margin + 1,
                pet_rect.center().y() - height // 2,
                width,
                height,
            ),
            QRect(
                pet_rect.left() - width - margin,
                pet_rect.center().y() - height // 2,
                width,
                height,
            ),
        ]
        target = next((rect for rect in candidates if available.contains(rect)), candidates[0])
        max_x = available.right() - width + 1
        max_y = available.bottom() - height + 1
        self.chat.move(
            min(max(target.x(), available.left()), max_x),
            min(max(target.y(), available.top()), max_y),
        )

    def show_compact_actions(self) -> None:
        menu = QMenu(self.chat)
        menu.setStyleSheet(
            "QMenu { background:#0b1020; color:#dbe4f5; border:1px solid #304666; padding:6px; }"
            "QMenu::item:selected { background:#15324a; color:#69f4df; }"
        )
        menu.addAction(self.reminders_action.text(), self.show_reminders)
        menu.addAction("Застосунки…", self.show_launchers)
        menu.addAction("Сайти…", self.show_sites)
        menu.addAction("Системна команда…", self.show_command_draft)
        menu.addAction("Швидкі фрази…", self.show_prompt_shortcuts)
        menu.addAction("Мої фрази…", self.show_companion_catchphrases)
        menu.addAction("Вставити побажання до стилю", self.insert_profile_style_note)
        menu.addAction("Профіль…", self.show_profile)
        menu.addAction("Агенти / місії…", self.show_integrations)
        menu.addAction("Файли / система / медіа…", self.show_local_features)
        menu.addAction("Модель / стан Capri…", self.show_runtime_status)
        point = self.chat.compact_actions_button.mapToGlobal(
            QPoint(0, self.chat.compact_actions_button.height())
        )
        menu.popup(point)

    def show_reminders(self) -> None:
        before = {item.get("id") for item in read_items(self.settings, "reminders")}
        dialog = ReminderDialog(self.settings)
        dialog.finished.connect(lambda _result: self._poll_reminders())
        dialog.exec()
        after = {item.get("id") for item in read_items(self.settings, "reminders")}
        if after - before:
            self._record_interaction("reminder")

    def show_launchers(self) -> None:
        LauncherDialog(self.settings).exec()

    def show_sites(self) -> None:
        SiteShortcutDialog(self.settings).exec()

    def show_prompt_shortcuts(self) -> None:
        dialog = PromptShortcutDialog(self.settings)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_prompt:
            self.show_compact_chat()
            self.chat.composer.setPlainText(dialog.selected_prompt)
            self.chat.composer.setFocus()

    def show_command_draft(self) -> None:
        dialog = CommandDraftDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if values is None:
            return
        command, cwd = values
        self.show_compact_chat()
        self.chat.composer.setPlainText(
            "Виконай цю системну shell-команду через наявні інструменти Capri. "
            "Не змінюй команду або робочу теку; покажи точні параметри для підтвердження.\n"
            f"Робоча тека: {cwd}\nКоманда:\n```sh\n{command}\n```"
        )
        self.chat.composer.setFocus()

    def show_profile(self) -> None:
        from b12.desktop.profile import CompanionProfileDialog

        dialog = CompanionProfileDialog(self.settings)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved_profile:
            self.overlay.set_owner_name(str(dialog.saved_profile["name"]))

    def show_companion_catchphrases(self) -> None:
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        from b12.desktop.profile import load_companion_catchphrases

        phrases = load_companion_catchphrases(self.settings)
        if not phrases:
            QMessageBox.information(
                self.chat,
                "ВЛАСНІ ФРАЗИ",
                "Спочатку додай фрази у профілі companion.",
            )
            self.show_profile()
            return
        phrase, accepted = QInputDialog.getItem(
            self.chat, "МОЇ ФРАЗИ", "Вибери фразу для composer:", phrases, 0, False
        )
        if accepted and phrase:
            self.show_compact_chat()
            self.chat.composer.setPlainText(phrase)
            self.chat.composer.setFocus()

    def insert_profile_style_note(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from b12.desktop.profile import load_companion_profile

        note = str(load_companion_profile(self.settings)["style_note"]).strip()
        if not note:
            QMessageBox.information(
                self.chat,
                "ПОБАЖАННЯ ДО СТИЛЮ",
                "Додай побажання у профілі companion, а потім встав його в composer вручну.",
            )
            self.show_profile()
            return
        self.show_compact_chat()
        self.chat.composer.setPlainText(f"Моє побажання до стилю відповіді: {note}\n\n")
        self.chat.composer.setFocus()

    def _record_interaction(self, kind: str) -> None:
        from b12.desktop.profile import record_companion_interaction

        self._mark_companion_activity()
        record_companion_interaction(self.settings, kind)

    def _mark_companion_activity(self) -> None:
        self._last_companion_activity = time.monotonic()
        if self.overlay.phase == "sleeping":
            self.overlay.set_phase("idle")

    def _on_chat_phase(self, _phase: str, _detail: str) -> None:
        self._mark_companion_activity()

    def set_auto_sleep(self, enabled: bool) -> None:
        self._auto_sleep_enabled = enabled
        self.settings.setValue("presentation/auto_sleep", enabled)
        self.settings.sync()
        self._last_companion_activity = time.monotonic()

    def set_follow_cursor_screen(self, enabled: bool) -> None:
        if enabled and not self.overlay.motion:
            self.follow_screen_action.setChecked(False)
            return
        self._follow_cursor_screen = enabled
        self._follow_candidate_screen = None
        self._follow_candidate_since = 0.0
        self.settings.setValue("presentation/follow_cursor_screen", enabled)
        self.settings.sync()

    def _presence_tick(self) -> None:
        now = time.monotonic()
        if (
            self._auto_sleep_enabled
            and self.overlay.isVisible()
            and self.overlay.phase == "idle"
            and not self.chat.is_user_busy()
            and not self._last_approval_ids
            and now - self._last_companion_activity >= 600
        ):
            self.overlay.set_phase("sleeping")

        if not self._follow_cursor_screen or not self.overlay.isVisible():
            self._follow_candidate_screen = None
            return
        if self.overlay.is_dragging:
            self._follow_candidate_screen = None
            return
        pointer_screen = self.app.screenAt(QCursor.pos())
        pet_screen = self.app.screenAt(self.overlay.geometry().center())
        if pointer_screen is None or pet_screen is None or pointer_screen == pet_screen:
            self._follow_candidate_screen = None
            return
        if pointer_screen != self._follow_candidate_screen:
            self._follow_candidate_screen = pointer_screen
            self._follow_candidate_since = now
            return
        if now - self._follow_candidate_since < 3:
            return
        self.overlay.move(
            default_overlay_position(pointer_screen.availableGeometry(), self.overlay.size())
        )
        self.overlay.position_changed.emit(self.overlay.pos())
        self._follow_candidate_screen = None

    def _latest_external_activity_key(
        self, provider: str = "all"
    ) -> tuple[str, str, str, str | None] | None:
        rows = self.activity_journal.snapshot(limit=1000)
        if provider != "all":
            rows = [row for row in rows if row["provider"] == provider]
        if not rows:
            return None
        row = rows[-1]
        return (row["at"], row["provider"], row["event"], row["session"])

    def _poll_external_activity(self) -> None:
        observed = str(self.settings.value("integrations/observed_provider", "all"))
        if observed != self._external_observed_provider:
            self._external_observed_provider = observed
            self._external_activity_key = self._latest_external_activity_key(observed)
            self._external_activity_active = False
            return
        rows = self.activity_journal.snapshot(limit=100)
        if observed != "all":
            rows = [row for row in rows if row["provider"] == observed]
        if rows:
            row = rows[-1]
            key = (row["at"], row["provider"], row["event"], row["session"])
            if key != self._external_activity_key:
                self._external_activity_key = key
                chat_active = bool(self.chat.pending_turn_id or self.chat._active_turn_id)
                if not chat_active and self.overlay.isVisible():
                    provider = row["provider"].upper()
                    event = row["event"]
                    if event in {"PermissionRequest", "Notification"}:
                        phase, detail = "approval", f"{provider} · ПЕРЕВІР У ТОМУ АГЕНТІ"
                        duration = 300.0
                    elif event in {"PostToolUseFailure", "StopFailure"}:
                        phase, detail = "error", f"{provider} · ПОМИЛКА АГЕНТА"
                        duration = 10.0
                    elif event in {"Stop", "SessionEnd"}:
                        phase, detail = "success", f"{provider} · ХІД ЗАВЕРШЕНО"
                        duration = 3.0
                    elif event in {"PreToolUse", "PostToolUse"}:
                        phase, detail = "working", f"{provider} · ВИКЛИК ІНСТРУМЕНТА"
                        duration = 1800.0
                    elif event in {"SessionStart", "UserPromptSubmit", "PreInvocation"}:
                        phase, detail = "thinking", f"{provider} · ПРАЦЮЄ"
                        duration = 1800.0 if event != "SessionStart" else 30.0
                    else:
                        phase, detail = "working", f"{provider} · {event}"
                        duration = 30.0
                    self.overlay.set_phase(phase, detail)
                    self._external_phase = phase
                    self._external_activity_active = True
                    now_monotonic = time.monotonic()
                    self._external_activity_until = now_monotonic + duration
                    self._external_activity_label = detail
                    if event in {"SessionStart", "UserPromptSubmit", "PreInvocation"}:
                        self._external_activity_started = now_monotonic
                    if event == "SessionStart":
                        self._record_interaction("work_session")
        if self._external_activity_active and self.overlay.isVisible():
            if (
                self.overlay.phase == self._external_phase
                and self.overlay.phase in {"thinking", "working"}
                and self._external_activity_started
                and not self.chat.pending_turn_id
                and not self.chat._active_turn_id
            ):
                elapsed = int(time.monotonic() - self._external_activity_started)
                minutes, seconds = divmod(elapsed, 60)
                self.overlay.detail = (
                    f"{self._external_activity_label} · {minutes:02d}:{seconds:02d}"
                )
                self.overlay.update()
        if (
            self._external_activity_active
            and time.monotonic() >= self._external_activity_until
            and not self.chat.pending_turn_id
            and not self.chat._active_turn_id
        ):
            self._external_activity_active = False
            if self.overlay.phase == self._external_phase and (
                self.overlay.phase != "approval" or not self._last_approval_ids
            ):
                self.overlay.set_phase("idle")

    def _handle_reminder_candidate(self, text: str) -> None:
        from b12.desktop.profile import parse_reminder_request

        parsed = parse_reminder_request(text)
        if parsed.status == "not_reminder":
            return
        QTimer.singleShot(0, lambda result=parsed: self._resolve_reminder_candidate(result))

    def _resolve_reminder_candidate(self, parsed) -> None:
        from PySide6.QtWidgets import QMessageBox

        if parsed.status == "ready":
            due_text = time.strftime("%d.%m.%Y %H:%M", time.localtime(parsed.due_at))
            answer = QMessageBox.question(
                self.chat,
                "ЗБЕРЕГТИ НАГАДУВАННЯ?",
                f"З повідомлення розпізнано локальне нагадування.\n\n"
                f"Текст: {parsed.task}\nЧас: {due_text}\n\nДодати його до нагадувань?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                ReminderDialog._persist_reminder(self.settings, parsed.task, parsed.due_at)
                self._record_interaction("reminder")
                self._poll_reminders()
            return

        clarification = parsed.clarification or "Уточни текст і точний час нагадування."
        answer = QMessageBox.question(
            self.chat,
            "УТОЧНИТИ НАГАДУВАННЯ",
            f"{clarification}\n\nВідкрити форму, щоб указати точні дані?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            before = {item.get("id") for item in read_items(self.settings, "reminders")}
            ReminderDialog(
                self.settings,
                self.chat,
                initial_task=parsed.task,
                initial_due_at=parsed.due_at,
            ).exec()
            after = {item.get("id") for item in read_items(self.settings, "reminders")}
            if after - before:
                self._record_interaction("reminder")
            self._poll_reminders()

    def show_integrations(self) -> None:
        from b12.desktop.integrations import IntegrationDialog

        IntegrationDialog(self.settings).exec()

    def show_local_features(self) -> None:
        from b12.desktop.local_features import LocalFeaturesDialog

        LocalFeaturesDialog(self.settings).exec()

    def show_runtime_status(self) -> None:
        self.show_chat()
        self.chat.tabs.setCurrentIndex(2)
        self.chat.refresh_dashboard()
        self.chat.request_voice_status()

    def set_reduced_motion(self, reduced: bool) -> None:
        self.overlay.set_motion(not reduced)
        self.animation_menu.setEnabled(self.overlay.appearance_id == "capri" and not reduced)
        self.settings.setValue("presentation/reduced_motion", bool(reduced))
        self.settings.sync()
        if reduced:
            self._wander_active = False
            self._wander_timer.stop()
            self.wander_action.setChecked(False)
            self._follow_cursor_screen = False
            self._follow_candidate_screen = None
            self.follow_screen_action.setChecked(False)
            self.follow_screen_action.setEnabled(False)
            self.settings.setValue("presentation/follow_cursor_screen", False)
            self.settings.sync()
        else:
            self.follow_screen_action.setEnabled(True)
        self.overlay.update()

    def set_wander(self, enabled: bool) -> None:
        if enabled and not self.overlay.motion:
            self.wander_action.setChecked(False)
            return
        self._wander_active = enabled
        if enabled:
            self._wander_timer.start()
            self._wander_step()
        else:
            self._wander_timer.stop()

    def play_animation(self, action: str) -> None:
        if self.overlay.appearance_id != "capri":
            return
        self._mark_companion_activity()
        self.overlay.set_phase("idle")
        self.overlay.play_action(action)

    def _wander_step(self) -> None:
        if not self._wander_active or not self.overlay.isVisible():
            return
        current = self.app.screenAt(self.overlay.geometry().center()) or self.app.primaryScreen()
        geometry = current.availableGeometry()
        margin = 18
        max_x = max(0, geometry.width() - self.overlay.width() - 2 * margin)
        max_y = max(0, geometry.height() - self.overlay.height() - 2 * margin)
        point = QPoint(
            geometry.left() + margin + random.randint(0, max_x),
            geometry.top() + margin + random.randint(0, max_y),
        )
        self.overlay.move(point)
        self.overlay.position_changed.emit(point)
        if self.overlay.appearance_id == "capri":
            self.overlay.play_action("teleport")

    def peek(self) -> None:
        if not self.overlay.isVisible():
            self.overlay.show()
        self._pre_peek_position = self.overlay.pos()
        screen = self.app.screenAt(self.overlay.geometry().center()) or self.app.primaryScreen()
        area = screen.availableGeometry()
        current = self.overlay.geometry()
        edge_x = (
            area.left() + 8
            if current.center().x() >= area.center().x()
            else area.right() - self.overlay.width() - 8
        )
        edge_y = min(
            max(current.top(), area.top() + 8),
            max(area.top() + 8, area.bottom() - self.overlay.height() - 8),
        )
        self.overlay.move(edge_x, edge_y)
        self.overlay.set_phase("thinking", "ВИГЛЯДАЮ…")
        self.overlay.play_action("peek")
        self.overlay.raise_()
        QTimer.singleShot(1600, self._finish_peek)

    def _finish_peek(self) -> None:
        if self._pre_peek_position is not None:
            self.overlay.move(self._pre_peek_position)
            self._pre_peek_position = None
        self.overlay.set_phase("idle")

    def demo(self) -> None:
        if not self.overlay.isVisible():
            self.overlay.show()
        self.overlay.set_phase("typing", "ДЕМОНСТРАЦІЯ")
        QTimer.singleShot(700, lambda: self.overlay.set_phase("thinking", "ОБМІРКОВУЮ"))
        QTimer.singleShot(1500, lambda: self.overlay.set_phase("speaking", "ДІЛЮСЯ ЗНАХІДКОЮ"))
        QTimer.singleShot(2600, lambda: self.overlay.set_phase("success", "ГОТОВО"))
        QTimer.singleShot(4000, lambda: self.overlay.set_phase("idle"))

    def move_to_pointer_screen(self) -> None:
        screen = self.app.screenAt(QCursor.pos()) or self.app.primaryScreen()
        self.overlay.move(default_overlay_position(screen.availableGeometry(), self.overlay.size()))
        self.overlay.position_changed.emit(self.overlay.pos())
        if self.chat.isVisible() and self.chat.is_compact_mode():
            self._place_chat_panel()

    def set_sound_enabled(self, enabled: bool) -> None:
        self._sound_enabled = enabled
        self.settings.setValue("presentation/sounds", enabled)
        self.settings.sync()

    def hide_to_tray(self) -> None:
        if self._tray is not None:
            self.overlay.hide()

    def _poll_reminders(self) -> None:
        due = due_reminders(self.settings)
        due_ids = {item["id"] for item in due}
        count = len(due)
        self.reminders_action.setText(
            f"НАГАДУВАННЯ · {count} ЧАС НАСТАВ" if count else "НАГАДУВАННЯ"
        )
        chat_busy = self.chat.is_user_busy()
        defer_notice = self._last_approval_ids is None or bool(self._last_approval_ids) or chat_busy
        for item in due:
            reminder_id = item["id"]
            if reminder_id in self._notified_reminder_ids or defer_notice:
                continue
            self._notified_reminder_ids.add(reminder_id)
            message = item["title"][:180]
            if self._tray is not None:
                self._tray.showMessage(
                    "Нагадування Capri",
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    10000,
                )
            else:
                QToolTip.showText(QCursor.pos(), f"Нагадування Capri\n{message}", self.overlay)
        self._notified_reminder_ids.intersection_update(due_ids)

    def toggle_pet(self) -> None:
        if self.overlay.isVisible():
            self.overlay.set_phase("sleeping")
            if self._tray is not None:
                self.overlay.hide()
        else:
            self.overlay.set_phase("idle")
            self.overlay.show()
            if self.overlay.appearance_id == "capri":
                self.overlay.play_action("intro")

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
        QThreadPool.globalInstance().start(job)

    def _notifications_ready(self, tag: str, result: dict) -> None:
        if not result.get("connected"):
            if self._last_approval_ids is None:
                self._last_approval_ids = set()
            if self.overlay.phase not in {"error", "approval"}:
                self.overlay.set_phase("error", "API Capri офлайн")
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
                        "Capri потребує твого рішення",
                        f"Підтверди або відхили дію {first.get('name', 'дії')} у чаті.",
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
                    "Capri потребує твого рішення",
                    f"Підтверди або відхили дію {first.get('name', 'дії')} у чаті.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    8000,
                )
        elif not ids and self.overlay.phase == "approval":
            self.overlay.set_phase("idle")

    def _notifications_failed(self, tag: str, code: str) -> None:
        if self._last_approval_ids is None:
            self._last_approval_ids = set()
        if self.overlay.phase != "approval":
            self.overlay.set_phase("error", code)

    def _notification_finished(self, job) -> None:
        if job is self._notification_job:
            self._notification_job = None

    def shutdown(self) -> None:
        self._poll_timer.stop()
        self._reminder_timer.stop()
        self._activity_timer.stop()
        self._presence_timer.stop()
        if self._tray is not None:
            self._tray.hide()
        self.overlay.close()
        self.chat.close()
        # Closing the stream client lets the API observe disconnect and cancel active work.
        # Approval waits remain server-owned and expire under the existing control policy.
        self.client.close()
        # Let QRunnable jobs finish emitting before their Qt signal objects are torn down.
        workers_stopped = QThreadPool.globalInstance().waitForDone(5000)
        if not workers_stopped:
            sys.stderr.write(
                "Capri desktop: background API workers did not stop within 5 seconds.\n"
            )


def run_desktop(settings, url: str, *, persist_default: bool = False) -> int:
    """Launch the native client only; server/model/audio processes are never started here."""
    token = load_owner_token(settings.state_dir)
    client = DesktopApiClient(url, token)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Capri Neon Companion")
    app.setOrganizationName("B-12")
    app.setQuitOnLastWindowClosed(False)
    shell = DesktopShell(app, client, persist_default)
    app.aboutToQuit.connect(shell.shutdown)
    return int(app.exec())
