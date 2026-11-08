"""Owner-controlled presentation helpers for the native desktop companion."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from b12.desktop.actions import ACTION_STYLE

AUTOSTART_NAME = "b12-neon-companion.desktop"
AUTOSTART_MARKER = "X-B12-Managed=true"


def autostart_target() -> Path:
    """Resolve the XDG user autostart entry without changing the system."""
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "autostart" / AUTOSTART_NAME


def autostart_entry() -> tuple[Path | None, str | None]:
    """Return a safe desktop entry or a reason it cannot be generated."""
    executable = shutil.which("b12")
    if executable is None:
        return None, "Не знайдено команду b12 у PATH; автозапуск недоступний."
    target = autostart_target()
    # Desktop Exec syntax uses quoted argv tokens, not shell evaluation.
    escaped_executable = executable.replace("\\", "\\\\").replace('"', '\\"')
    command = f'"{escaped_executable}" desktop'
    text = "\n".join(
        (
            "[Desktop Entry]",
            "Type=Application",
            "Name=Capri Neon Companion",
            "Comment=Local desktop companion client",
            f"Exec={command}",
            "Terminal=false",
            "X-GNOME-Autostart-enabled=true",
            AUTOSTART_MARKER,
            "",
        )
    )
    return target, text


def autostart_enabled() -> bool:
    target = autostart_target()
    try:
        return AUTOSTART_MARKER in target.read_text(encoding="utf-8")
    except OSError:
        return False


def set_autostart(enabled: bool) -> tuple[bool, str]:
    """Write/remove only the companion-owned entry, preserving other files."""
    target = autostart_target()
    if enabled:
        entry_target, content = autostart_entry()
        if entry_target is None or content is None:
            return False, "Не вдалося сформувати запис автозапуску."
        if target.exists():
            try:
                current = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return False, f"Файл існує, але його не вдалося прочитати: {target}"
            if AUTOSTART_MARKER not in current:
                return False, f"Файл уже зайнятий іншим записом; його не змінено: {target}"
            if current == content:
                return True, f"Автозапуск уже налаштований: {target}"
            return False, f"Запис Capri змінено вручну; його не перезаписано: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, target)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
        return True, f"Автозапуск увімкнено для поточного користувача: {target}"

    if not target.exists():
        return True, "Запис автозапуску вже відсутній."
    try:
        current = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False, f"Файл не прочитано й не видалено: {target}"
    if AUTOSTART_MARKER not in current:
        return False, f"Це не запис Capri; файл не видалено: {target}"
    _expected_path, expected = autostart_entry()
    if expected is None or current != expected:
        return False, f"Запис змінено вручну; його залишено без змін: {target}"
    target.unlink()
    return True, f"Автозапуск вимкнено; видалено лише запис Capri: {target}"


class GuideDialog(QDialog):
    """Short, transparent guide to chat, permissions, integrations and privacy."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ДОВІДНИК CAPRI")
        self.setMinimumSize(580, 440)
        self.setStyleSheet(ACTION_STYLE)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        pages = (
            (
                "РОЗМОВА",
                "Компактне поле біля персонажа і повний чат працюють з тією самою сесією Capri. "
                "Натисни Enter, щоб надіслати повідомлення; кнопку зупинки — щоб попросити "
                "runtime перервати поточний хід. Швидкі фрази лише заповнюють поле.",
            ),
            (
                "ДІЇ ТА ДОЗВОЛИ",
                "Запуск локальної програми або системну дію підтверджуй за точним показаним "
                "target. Shell-команди проходять через звичайні інструменти Capri і його "
                "control/grant/approval правила. Hook події зовнішніх агентів не є дозволом "
                "для Capri і не підтверджують її запити.",
            ),
            (
                "ПРИВАТНІСТЬ",
                "Локальний профіль, нагадування й ярлики лишаються в налаштуваннях цього "
                "користувача. Hook-журнал зберігає лише типи подій та лічильники; без prompt, "
                "аргументів, шляхів, виводу та секретів. Пошук файлів обмежений вибраною текою. "
                "Знімок екрана не передається моделі, доки Capri не має окремого image input.",
            ),
        )
        for title, text in pages:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet("font-size:14px; padding:16px; line-height:1.5;")
            page_layout.addWidget(label, 1)
            tabs.addTab(page, title)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class AutostartDialog(QDialog):
    """Show exact XDG entry before enabling per-user startup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("АВТОЗАПУСК COMPANION")
        self.setMinimumSize(560, 390)
        self.setStyleSheet(ACTION_STYLE)
        layout = QVBoxLayout(self)
        self.state = QLabel()
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumBlockCount(30)
        layout.addWidget(self.preview, 1)
        self._target, self._entry = autostart_entry()
        if self._target is not None and self._entry is not None:
            self.preview.setPlainText(f"Файл: {self._target}\n\n{self._entry}")
        else:
            self.preview.setPlainText(self._entry or "")
        buttons = QDialogButtonBox()
        self.enable = buttons.addButton("УВІМКНУТИ", QDialogButtonBox.ButtonRole.ActionRole)
        self.disable = buttons.addButton("ВИМКНУТИ", QDialogButtonBox.ButtonRole.ActionRole)
        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.enable.clicked.connect(lambda: self._set(True))
        self.disable.clicked.connect(lambda: self._set(False))
        close.clicked.connect(self.accept)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        target = autostart_target()
        self.state.setText(
            f"Стан: {'УВІМКНЕНО' if autostart_enabled() else 'ВИМКНЕНО'}\n"
            f"Шлях: {target}\n"
            "Застосовується лише до поточного користувача; за замовчуванням вимкнено."
        )
        available = self._target is not None and self._entry is not None
        self.enable.setEnabled(available)

    def _set(self, enabled: bool) -> None:
        try:
            ok, message = set_autostart(enabled)
        except OSError as exc:
            message = f"Операція не вдалася: {exc}"
        self.state.setText(message)
        self.refresh()
