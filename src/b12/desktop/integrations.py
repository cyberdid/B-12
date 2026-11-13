"""Opt-in, observational hooks for local coding-assistant integrations.

This module edits provider JSON configuration only after an explicit UI action.
It never starts a listener or installs hooks during import or status inspection.
"""

from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from b12.desktop.activity import ACCEPTED_EVENTS, HOOK_OWNER_MARKER, ActivityJournal

OWNER_MARKER = HOOK_OWNER_MARKER
MAX_CONFIG_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class ProviderInfo:
    provider_id: str
    label: str
    config_kind: str


PROVIDERS: tuple[ProviderInfo, ...] = (
    ProviderInfo("claude", "Claude Code", "claude"),
    ProviderInfo("codex", "Codex", "codex"),
    ProviderInfo("antigravity", "Antigravity", "antigravity"),
)
_PROVIDERS_BY_ID = {provider.provider_id: provider for provider in PROVIDERS}


class HookManagerError(RuntimeError):
    """Stable, non-sensitive hook management failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _provider_id(value: str) -> str:
    if value not in _PROVIDERS_BY_ID:
        raise HookManagerError("provider_unknown")
    return value


def _default_paths(home: Path) -> dict[str, Path]:
    claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")).expanduser()
    codex_dir = Path(os.environ.get("CODEX_HOME", home / ".codex")).expanduser()
    agy_dir = Path(os.environ.get("AGY_CONFIG_DIR", home / ".gemini" / "config")).expanduser()
    return {
        "claude": claude_dir / "settings.json",
        "codex": codex_dir / "hooks.json",
        "antigravity": agy_dir / "hooks.json",
    }


def _hook_command(
    provider: str,
    event: str,
    *,
    python_executable: str,
    journal_path: Path,
) -> str:
    argv = [
        python_executable,
        "-m",
        "b12.desktop.hooks",
        "--provider",
        provider,
        "--event",
        event,
        "--owner-marker",
        OWNER_MARKER,
        "--journal-file",
        str(journal_path),
    ]
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def _is_owned_hook(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("type") != "command":
        return False
    command = value.get("command")
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return False
    expected = f"--owner-marker={OWNER_MARKER}"
    return expected in tokens or any(
        token == "--owner-marker" and index + 1 < len(tokens) and tokens[index + 1] == OWNER_MARKER
        for index, token in enumerate(tokens)
    )


def _remove_marked_groups(event_map: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove only this app's command entries from Claude/Codex hook groups."""
    changed = False
    for event, groups in list(event_map.items()):
        if not isinstance(groups, list):
            raise HookManagerError("configuration_invalid")
        next_groups = []
        for group in groups:
            if not isinstance(group, dict):
                raise HookManagerError("configuration_invalid")
            hooks = group.get("hooks")
            if hooks is None:
                next_groups.append(group)
                continue
            if not isinstance(hooks, list):
                raise HookManagerError("configuration_invalid")
            kept = [hook for hook in hooks if not _is_owned_hook(hook)]
            if len(kept) == len(hooks):
                next_groups.append(group)
                continue
            changed = True
            if kept:
                group = {**group, "hooks": kept}
                next_groups.append(group)
            elif set(group) - {"hooks"}:
                # Preserve matchers and any provider/user metadata even when the
                # B-12 command was the only hook in that group.
                next_groups.append({**group, "hooks": []})
            # An otherwise empty group was created solely to contain our hook.
        if next_groups:
            event_map[event] = next_groups
        else:
            del event_map[event]
    return event_map, changed


def _remove_marked_direct_hooks(event_map: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove only marked direct or grouped Antigravity hooks."""
    changed = False
    for event, entries in list(event_map.items()):
        if not isinstance(entries, list):
            raise HookManagerError("configuration_invalid")
        kept = []
        for entry in entries:
            if _is_owned_hook(entry):
                changed = True
                continue
            if isinstance(entry, dict) and isinstance(entry.get("hooks"), list):
                child_hooks = [hook for hook in entry["hooks"] if not _is_owned_hook(hook)]
                if len(child_hooks) != len(entry["hooks"]):
                    changed = True
                    if child_hooks:
                        kept.append({**entry, "hooks": child_hooks})
                    elif set(entry) - {"hooks"}:
                        kept.append({**entry, "hooks": []})
                    continue
            kept.append(entry)
        if kept:
            event_map[event] = kept
        else:
            del event_map[event]
    return event_map, changed


class IntegrationManager:
    """Read or explicitly edit provider hook config; no listener is managed here."""

    def __init__(
        self,
        *,
        journal: ActivityJournal | None = None,
        home: str | Path | None = None,
        config_paths: dict[str, str | Path] | None = None,
        python_executable: str | None = None,
    ):
        self.home = Path(home).expanduser() if home is not None else Path.home()
        self.paths = _default_paths(self.home)
        for provider, path in (config_paths or {}).items():
            self.paths[_provider_id(provider)] = Path(path).expanduser()
        self.journal = journal or ActivityJournal.default()
        self.python_executable = python_executable or sys.executable

    def config_path(self, provider: str) -> Path:
        return self.paths[_provider_id(provider)]

    def statuses(self) -> list[dict[str, Any]]:
        return [self.status(provider.provider_id) for provider in PROVIDERS]

    def status(self, provider: str) -> dict[str, Any]:
        provider = _provider_id(provider)
        path = self.config_path(provider)
        result = {
            "provider": provider,
            "label": _PROVIDERS_BY_ID[provider].label,
            "config_path": str(path),
            "installed": False,
            "complete": False,
            "events": [],
            "expected_events": list(ACCEPTED_EVENTS[provider]),
            "error": None,
        }
        try:
            data, exists = self._read_config(path)
            if not exists:
                return result
            events = self._installed_events(provider, data)
            result["events"] = sorted(events)
            result["installed"] = bool(events)
            result["complete"] = set(events) == set(ACCEPTED_EVENTS[provider])
        except HookManagerError as exc:
            result["error"] = exc.code
        return result

    def install(self, provider: str, *, confirmed: bool = False) -> dict[str, Any]:
        """Install observational hooks only after the UI has obtained explicit consent."""
        provider = _provider_id(provider)
        if confirmed is not True:
            raise HookManagerError("confirmation_required")
        path = self.config_path(provider)
        data, _exists = self._read_config(path)
        if provider in {"claude", "codex"}:
            self._install_group_hooks(provider, data)
        else:
            self._install_antigravity_hooks(data)
        backup = self._write_config(path, data)
        result = self.status(provider)
        result["backup_path"] = str(backup) if backup else None
        return result

    def uninstall(self, provider: str, *, confirmed: bool = False) -> dict[str, Any]:
        """Remove only hook commands carrying this app's exact ownership marker."""
        provider = _provider_id(provider)
        if confirmed is not True:
            raise HookManagerError("confirmation_required")
        path = self.config_path(provider)
        data, exists = self._read_config(path)
        if not exists:
            return self.status(provider)
        if provider in {"claude", "codex"}:
            hook_map = data.get("hooks", {})
            if not isinstance(hook_map, dict):
                raise HookManagerError("configuration_invalid")
            _, changed = _remove_marked_groups(hook_map)
            if not hook_map:
                data.pop("hooks", None)
        else:
            entry = data.get("b12-desktop", {})
            if not isinstance(entry, dict):
                raise HookManagerError("configuration_invalid")
            event_map = {key: value for key, value in entry.items() if isinstance(value, list)}
            event_map, changed = _remove_marked_direct_hooks(event_map)
            for key, value in list(entry.items()):
                if isinstance(value, list) and key not in event_map:
                    del entry[key]
            entry.update(event_map)
        backup = self._write_config(path, data) if changed else None
        result = self.status(provider)
        result["backup_path"] = str(backup) if backup else None
        result["removed"] = changed
        return result

    def _install_group_hooks(self, provider: str, data: dict[str, Any]) -> None:
        hook_map = data.setdefault("hooks", {})
        if not isinstance(hook_map, dict):
            raise HookManagerError("configuration_invalid")
        hook_map, _removed = _remove_marked_groups(hook_map)
        for event in ACCEPTED_EVENTS[provider]:
            hook = {
                "type": "command",
                "command": self._command(provider, event),
                "async": True,
                "timeout": 3,
            }
            groups = hook_map.setdefault(event, [])
            if not isinstance(groups, list):
                raise HookManagerError("configuration_invalid")
            groups.append({"hooks": [hook]})
        data["hooks"] = hook_map

    def _install_antigravity_hooks(self, data: dict[str, Any]) -> None:
        # Antigravity's hook protocol expects JSON on stdout. The B-12 hook
        # handler returns only the neutral empty object and installs no event
        # that can approve, deny, or stop an agent action.
        entry = data.setdefault("b12-desktop", {"enabled": True})
        if not isinstance(entry, dict):
            raise HookManagerError("configuration_invalid")
        events = {key: value for key, value in entry.items() if isinstance(value, list)}
        old_event_keys = set(events)
        events, _removed = _remove_marked_direct_hooks(events)
        for key in old_event_keys - set(events):
            entry.pop(key, None)
        entry.update(events)
        entry["enabled"] = True
        for event in ACCEPTED_EVENTS["antigravity"]:
            hook = {
                "type": "command",
                "command": self._command("antigravity", event),
                "timeout": 3,
            }
            entries = entry.setdefault(event, [])
            if not isinstance(entries, list):
                raise HookManagerError("configuration_invalid")
            if event in {"PreToolUse", "PostToolUse"}:
                entries.append({"matcher": "*", "hooks": [hook]})
            else:
                entries.append(hook)
        data["b12-desktop"] = entry

    def _command(self, provider: str, event: str) -> str:
        return _hook_command(
            provider,
            event,
            python_executable=self.python_executable,
            journal_path=self.journal.path,
        )

    def _read_config(self, path: Path) -> tuple[dict[str, Any], bool]:
        if path.is_symlink():
            raise HookManagerError("config_symlink_refused")
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return {}, False
        except OSError as exc:
            raise HookManagerError("configuration_unreadable") from exc
        if len(raw) > MAX_CONFIG_BYTES:
            raise HookManagerError("configuration_too_large")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise HookManagerError("configuration_invalid_json") from exc
        if not isinstance(value, dict):
            raise HookManagerError("configuration_invalid")
        return value, True

    def _write_config(self, path: Path, data: dict[str, Any]) -> Path | None:
        payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(payload) > MAX_CONFIG_BYTES:
            raise HookManagerError("configuration_too_large")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise HookManagerError("config_symlink_refused")
        existed = path.exists()
        backup = self._backup(path) if existed else None
        mode = stat.S_IMODE(path.stat().st_mode) if existed else 0o600
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.b12-", dir=path.parent)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            self._fsync_directory(path.parent)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(temporary).unlink(missing_ok=True)
            raise
        return backup

    @staticmethod
    def _backup(path: Path) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        base = path.with_name(f"{path.name}.b12-backup-{stamp}")
        backup = base
        suffix = 1
        while backup.exists():
            backup = Path(f"{base}.{suffix}")
            suffix += 1
        try:
            source = path.read_bytes()
            mode = 0o600
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            with os.fdopen(fd, "wb") as output:
                output.write(source)
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            raise HookManagerError("configuration_backup_failed") from exc
        return backup

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _installed_events(provider: str, data: dict[str, Any]) -> set[str]:
        if provider in {"claude", "codex"}:
            hook_map = data.get("hooks", {})
            if not isinstance(hook_map, dict):
                raise HookManagerError("configuration_invalid")
            installed: set[str] = set()
            for event, groups in hook_map.items():
                if not isinstance(groups, list):
                    continue
                for group in groups:
                    if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                        continue
                    if any(_is_owned_hook(hook) for hook in group["hooks"]):
                        installed.add(event)
            return installed
        entry = data.get("b12-desktop", {})
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            return set()
        installed: set[str] = set()
        for event, hooks in entry.items():
            if not isinstance(hooks, list):
                continue
            if event in {"PreToolUse", "PostToolUse"}:
                if any(
                    isinstance(group, dict)
                    and isinstance(group.get("hooks"), list)
                    and any(_is_owned_hook(hook) for hook in group["hooks"])
                    for group in hooks
                ):
                    installed.add(event)
            elif any(_is_owned_hook(hook) for hook in hooks):
                installed.add(event)
        return installed


class IntegrationDialog(QDialog):
    """Qt dialog for provider status and explicit hook install/removal actions."""

    def __init__(self, settings=None, manager: IntegrationManager | None = None, parent=None):
        super().__init__(parent)
        self.manager = manager or IntegrationManager()
        self.settings = settings or QSettings("B-12", "NeonCompanion")
        self.setWindowTitle("ІНТЕГРАЦІЇ З AI-КОДИНГ АГЕНТАМИ")
        self.setMinimumSize(620, 390)
        self.setStyleSheet(
            "QDialog { background:#0b1020; color:#dbe4f5; }"
            "QLabel { color:#aebbd2; }"
            "QTableWidget, QComboBox { background:#111a2c; color:#dbe4f5; "
            "border:1px solid #304666; padding:5px; }"
            "QHeaderView::section { background:#142139; color:#67f2dc; padding:5px; }"
            "QPushButton { background:#17233a; color:#dbe4f5; "
            "border:1px solid #405a7c; padding:7px; }"
            "QPushButton:hover { color:#67f2dc; border-color:#67f2dc; }"
        )
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Hooks лише записують тип події та знеособлений session ID локально. "
                "Prompts, шляхи, аргументи, відповіді й секрети не зберігаються."
            )
        )
        layout.addWidget(QLabel("За яким агентом показувати активність:"))
        self.observe_provider = QComboBox()
        self.observe_provider.addItem("Усі підключені агенти", "all")
        for provider in PROVIDERS:
            self.observe_provider.addItem(provider.label, provider.provider_id)
        saved_provider = str(self.settings.value("integrations/observed_provider", "all"))
        index = self.observe_provider.findData(saved_provider)
        self.observe_provider.setCurrentIndex(index if index >= 0 else 0)
        self.observe_provider.currentIndexChanged.connect(self._save_observed_provider)
        layout.addWidget(self.observe_provider)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Провайдер", "Статус", "Події"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)

        self.mission_summary = QLabel()
        self.mission_summary.setWordWrap(True)
        layout.addWidget(self.mission_summary)
        self.copy_report_button = QPushButton("СКОПІЮВАТИ ЗВІТ ЯК ЗОБРАЖЕННЯ")
        self.copy_report_button.clicked.connect(self.copy_report_image)
        layout.addWidget(self.copy_report_button)
        self.recent_activity = QListWidget()
        self.recent_activity.setMaximumHeight(130)
        layout.addWidget(self.recent_activity)

        actions = QHBoxLayout()
        self.install_button = QPushButton("ПІДКЛЮЧИТИ…")
        self.uninstall_button = QPushButton("ВІДКЛЮЧИТИ…")
        self.refresh_button = QPushButton("ОНОВИТИ СТАТУС")
        self.clear_journal_button = QPushButton("ОЧИСТИТИ ЖУРНАЛ…")
        for button in (
            self.install_button,
            self.uninstall_button,
            self.refresh_button,
            self.clear_journal_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.install_button.clicked.connect(self._install_selected)
        self.uninstall_button.clicked.connect(self._uninstall_selected)
        self.refresh_button.clicked.connect(self.refresh)
        self.clear_journal_button.clicked.connect(self._clear_journal)
        self.refresh()

    def refresh(self) -> None:
        selected = self._selected_provider()
        self.table.setRowCount(0)
        for status in self.manager.statuses():
            row = self.table.rowCount()
            self.table.insertRow(row)
            error = status.get("error")
            label = (
                "ПОМИЛКА КОНФІГУРАЦІЇ"
                if error
                else ("ПІДКЛЮЧЕНО" if status["installed"] else "НЕ ПІДКЛЮЧЕНО")
            )
            events = ", ".join(status["events"]) or "—"
            values = (status["label"], label, events)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, status["provider"])
                self.table.setItem(row, column, item)
            if status["provider"] == selected:
                self.table.selectRow(row)
        if self.table.currentRow() < 0 and self.table.rowCount():
            self.table.selectRow(0)
        self._selection_changed()
        self._refresh_activity()

    def _selected_provider(self) -> str | None:
        row = self.table.currentRow() if hasattr(self, "table") else -1
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _selection_changed(self) -> None:
        provider = self._selected_provider()
        self.install_button.setEnabled(provider is not None)
        self.uninstall_button.setEnabled(provider is not None)

    def _save_observed_provider(self, _index: int) -> None:
        self.settings.setValue(
            "integrations/observed_provider", self.observe_provider.currentData()
        )
        self.settings.sync()
        self._refresh_activity()

    def _refresh_activity(self) -> None:
        observed = str(self.observe_provider.currentData() or "all")
        report = self.manager.journal.mission_report(provider=observed)
        self._mission_report = report
        self.mission_summary.setText(
            f"ЗВІТ ЗА {report['day']} · СЕСІЙ {report['sessions']} · "
            f"ЗАПИТІВ {report['prompts']} · ДІЙ {report['actions']} · "
            f"ОЧІКУВАННЯ ДОЗВОЛУ {report['approvals']} · "
            f"ПОМИЛОК {report['errors']} · ЗАВЕРШЕНЬ {report['completed']}"
        )
        rows = self.manager.journal.snapshot(limit=40)
        if observed != "all":
            rows = [row for row in rows if row["provider"] == observed]
        self.recent_activity.clear()
        for row in reversed(rows[-15:]):
            try:
                stamp = datetime.fromisoformat(row["at"].replace("Z", "+00:00"))
                local_stamp = stamp.astimezone().strftime("%H:%M:%S")
            except (TypeError, ValueError):
                local_stamp = "--:--:--"
            provider = next(
                (item.label for item in PROVIDERS if item.provider_id == row["provider"]),
                row["provider"],
            )
            self.recent_activity.addItem(
                QListWidgetItem(f"{local_stamp} · {provider} · {row['event']}")
            )
        if not rows:
            self.recent_activity.addItem("За цей фільтр подій ще немає.")

    def copy_report_image(self) -> None:
        """Render today's metadata-only report to the local clipboard, without saving it."""
        report = getattr(self, "_mission_report", None)
        if not isinstance(report, dict):
            return
        pixmap = QPixmap(1200, 680)
        pixmap.fill(QColor("#080d19"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#29425d"))
        painter.setBrush(QColor("#0d1627"))
        painter.drawRoundedRect(QRectF(24, 24, 1152, 632), 20, 20)

        painter.setPen(QColor("#ff315f"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(24, 24, 1152, 632), 20, 20)
        painter.setPen(QColor("#00efc3"))
        painter.setFont(QFont("Noto Sans", 16, QFont.Weight.Bold))
        painter.drawText(64, 82, "CAPRI   //   LOCAL MISSION REPORT")
        painter.setPen(QColor("#dbe4f5"))
        painter.setFont(QFont("Noto Sans", 32, QFont.Weight.Bold))
        painter.drawText(64, 142, str(report.get("day", "")))

        labels = (
            ("ЗАПИТИ", "prompts", "#69f4df"),
            ("ДІЇ", "actions", "#ff527d"),
            ("СЕСІЇ", "sessions", "#ad91ff"),
            ("ДОЗВОЛИ", "approvals", "#ffbb58"),
            ("ПОМИЛКИ", "errors", "#ff6578"),
            ("ЗАВЕРШЕННЯ", "completed", "#5bf0a5"),
        )
        card_width = 340
        card_height = 154
        gap_x = 28
        gap_y = 24
        origin_x = 64
        origin_y = 182
        for index, (label, key, accent) in enumerate(labels):
            column = index % 3
            row = index // 3
            x = origin_x + column * (card_width + gap_x)
            y = origin_y + row * (card_height + gap_y)
            painter.setPen(QColor("#263a54"))
            painter.setBrush(QColor("#101d31"))
            painter.drawRoundedRect(QRectF(x, y, card_width, card_height), 12, 12)
            painter.setPen(QColor(accent))
            painter.setFont(QFont("Noto Sans", 15, QFont.Weight.Bold))
            painter.drawText(
                QRectF(x + 20, y + 18, card_width - 40, 28),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            painter.setPen(QColor("#f1f5ff"))
            painter.setFont(QFont("Noto Sans", 38, QFont.Weight.Bold))
            painter.drawText(
                QRectF(x + 20, y + 50, card_width - 40, 78),
                Qt.AlignmentFlag.AlignVCenter,
                str(report.get(key, 0)),
            )

        painter.setPen(QColor("#8194b0"))
        painter.setFont(QFont("Noto Sans", 11))
        painter.drawText(
            QRectF(64, 584, 1070, 36),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Лише локальні лічильники подій · без prompt, команд, шляхів і відповідей",
        )
        painter.end()
        QApplication.clipboard().setPixmap(pixmap)
        self.copy_report_button.setToolTip("Зображення звіту скопійовано в clipboard")

    def _clear_journal(self) -> None:
        answer = QMessageBox.question(
            self,
            "ОЧИСТИТИ ЖУРНАЛ",
            "Видалити всі локальні event metadata та сіль псевдонімів? "
            "Це не змінює конфігурації зовнішніх агентів.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.manager.journal.clear()
            self._refresh_activity()

    def _install_selected(self) -> None:
        provider = self._selected_provider()
        if provider is None:
            return
        status = self.manager.status(provider)
        answer = QMessageBox.question(
            self,
            "Підключити спостереження",
            f"Додати пасивні hooks для {status['label']} у файл:\n{status['config_path']}?\n\n"
            "Capri зберігатиме лише тип події, час, лічильник і знеособлений session ID. "
            "Зміни конфігурації матимуть резервну копію.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.install(provider, confirmed=True)
        except HookManagerError as exc:
            QMessageBox.warning(self, "Не вдалося підключити", exc.code)
        self.refresh()

    def _uninstall_selected(self) -> None:
        provider = self._selected_provider()
        if provider is None:
            return
        status = self.manager.status(provider)
        answer = QMessageBox.question(
            self,
            "Відключити спостереження",
            f"Видалити лише hooks Capri для {status['label']}?\n{status['config_path']}\n\n"
            "Інші hooks та налаштування залишаться на місці.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.manager.uninstall(provider, confirmed=True)
        except HookManagerError as exc:
            QMessageBox.warning(self, "Не вдалося відключити", exc.code)
        self.refresh()
