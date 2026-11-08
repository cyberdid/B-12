"""Owner-authored companion reminders, prompt shortcuts, launchers, and command drafts."""

from __future__ import annotations

import json
import os
import shlex
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QDateTime, QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

ACTION_STYLE = """
QDialog { background:#080d19; color:#dbe4f5; }
QLabel { color:#dbe4f5; }
QLineEdit, QPlainTextEdit, QDateTimeEdit, QListWidget {
  background:#0b1324; color:#e2e9f7; border:1px solid #2a3c58;
  border-radius:5px; padding:7px; selection-background-color:#255b70;
}
QPushButton { background:#132338; color:#b6c5de; border:1px solid #38516f;
  border-radius:5px; padding:7px 12px; font-weight:700; }
QPushButton:hover { background:#1a334d; border-color:#69f4df; color:#69f4df; }
"""


def read_items(settings: QSettings, key: str) -> list[dict]:
    """Read bounded local JSON settings; malformed values are ignored."""
    raw = settings.value(key, "[]")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data[:100] if isinstance(item, dict)]


def write_items(settings: QSettings, key: str, items: list[dict]) -> None:
    settings.setValue(key, json.dumps(items[:100], ensure_ascii=False, separators=(",", ":")))
    settings.sync()


def due_reminders(settings: QSettings, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    result = []
    for item in read_items(settings, "reminders"):
        try:
            due_at = float(item["due_at"])
            title = str(item["title"]).strip()
            reminder_id = str(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if reminder_id and title and due_at <= now:
            result.append({**item, "id": reminder_id, "title": title, "due_at": due_at})
    return result


class ReminderDialog(QDialog):
    """Manage local reminders without writing them into B-12 model memory."""

    def __init__(
        self,
        settings: QSettings,
        parent=None,
        *,
        initial_task: str = "",
        initial_due_at: float | None = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.initial_task = initial_task[:200]
        self.initial_due_at = initial_due_at
        self.setWindowTitle("НАГАДУВАННЯ CAPRI")
        self.setMinimumSize(410, 380)
        self.setStyleSheet(ACTION_STYLE)
        layout = QVBoxLayout(self)
        self.note = QLabel("Нагадування зберігаються локально на цьому комп’ютері.")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        quick_row = QHBoxLayout()
        self.quick_reminder = QLineEdit()
        self.quick_reminder.setMaxLength(500)
        self.quick_reminder.setPlaceholderText(
            "Наприклад: нагадай мені завтра о 18:30 зателефонувати"
        )
        parse = QPushButton("РОЗПІЗНАТИ ФРАЗУ")
        parse.clicked.connect(self.add_from_natural_language)
        quick_row.addWidget(self.quick_reminder, 1)
        quick_row.addWidget(parse)
        layout.addLayout(quick_row)
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ ДОДАТИ")
        snooze = QPushButton("ВІДКЛАСТИ 10 ХВ")
        dismiss = QPushButton("ЗАКРИТИ")
        row.addWidget(add)
        row.addWidget(snooze)
        row.addWidget(dismiss)
        layout.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)
        add.clicked.connect(lambda: self.add_reminder())
        snooze.clicked.connect(self.snooze_selected)
        dismiss.clicked.connect(self.dismiss_selected)
        self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        now = time.time()
        entries = read_items(self.settings, "reminders")

        def reminder_sort_key(item: dict) -> float:
            try:
                return float(item.get("due_at", 0))
            except (TypeError, ValueError):
                return float("inf")

        entries.sort(key=reminder_sort_key)
        for entry in entries:
            try:
                reminder_id = str(entry["id"])
                due_at = float(entry["due_at"])
                title = str(entry["title"])
            except (KeyError, TypeError, ValueError):
                continue
            state = "ЧАС НАСТАВ" if due_at <= now else "ЗАПЛАНОВАНО"
            due_text = time.strftime("%d.%m.%Y %H:%M", time.localtime(due_at))
            item = QListWidgetItem(f"{state}  ·  {due_text}\n{title}")
            item.setData(Qt.ItemDataRole.UserRole, reminder_id)
            self.items.addItem(item)

    def _selected_id(self) -> str | None:
        item = self.items.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    @staticmethod
    def _persist_reminder(settings: QSettings, title_text: str, due_at: float) -> None:
        entries = read_items(settings, "reminders")
        entries.append(
            {"id": uuid.uuid4().hex, "title": title_text.strip()[:200], "due_at": due_at}
        )
        write_items(settings, "reminders", entries)

    def add_from_natural_language(self) -> None:
        from b12.desktop.profile import parse_reminder_request

        phrase = self.quick_reminder.text().strip()
        parsed = parse_reminder_request(phrase)
        if parsed.status == "not_reminder":
            QMessageBox.information(
                self,
                "ЦЕ НЕ СХОЖЕ НА НАГАДУВАННЯ",
                "Скажи, що саме нагадати й коли. Можна також додати нагадування вручну.",
            )
            return
        if parsed.status == "ready":
            due_text = time.strftime("%d.%m.%Y %H:%M", time.localtime(parsed.due_at))
            answer = QMessageBox.question(
                self,
                "ПІДТВЕРДИ НАГАДУВАННЯ",
                f"Текст: {parsed.task}\nЧас: {due_text}\n\nДодати локальне нагадування?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._persist_reminder(self.settings, parsed.task, float(parsed.due_at))
                self.quick_reminder.clear()
                self.refresh()
            return

        QMessageBox.information(
            self,
            "УТОЧНИМО НАГАДУВАННЯ",
            parsed.clarification or "Укажи точний час і текст нагадування.",
        )
        self.add_reminder(initial_title=parsed.task, initial_due_at=parsed.due_at)

    def add_reminder(
        self, *, initial_title: str | None = None, initial_due_at: float | None = None
    ) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("НОВЕ НАГАДУВАННЯ")
        dialog.setStyleSheet(ACTION_STYLE)
        layout = QFormLayout(dialog)
        title = QLineEdit()
        title.setMaxLength(200)
        title.setPlaceholderText("Що нагадати?")
        title.setText(self.initial_task if initial_title is None else initial_title)
        due_at = self.initial_due_at if initial_due_at is None else initial_due_at
        initial_time = (
            QDateTime.fromSecsSinceEpoch(int(due_at))
            if due_at is not None
            else QDateTime.currentDateTime().addSecs(600)
        )
        when = QDateTimeEdit(initial_time)
        when.setCalendarPopup(True)
        when.setDisplayFormat("dd.MM.yyyy HH:mm")
        layout.addRow("Нагадати:", title)
        layout.addRow("Коли:", when)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not title.text().strip():
            return
        self._persist_reminder(self.settings, title.text(), when.dateTime().toSecsSinceEpoch())
        self.refresh()

    def snooze_selected(self) -> None:
        reminder_id = self._selected_id()
        if not reminder_id:
            return
        entries = read_items(self.settings, "reminders")
        for entry in entries:
            if entry.get("id") == reminder_id:
                entry["due_at"] = time.time() + 600
                break
        write_items(self.settings, "reminders", entries)
        self.refresh()

    def dismiss_selected(self) -> None:
        reminder_id = self._selected_id()
        if not reminder_id:
            return
        write_items(
            self.settings,
            "reminders",
            [
                entry
                for entry in read_items(self.settings, "reminders")
                if entry.get("id") != reminder_id
            ],
        )
        self.refresh()


class LauncherDialog(QDialog):
    """Manage explicit owner-click application launchers (never shell commands)."""

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("ЗАПУСК ПРОГРАМ")
        self.setMinimumSize(500, 390)
        self.setStyleSheet(ACTION_STYLE)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Програми запускаються лише після твого кліку. Shell-синтаксис не виконується."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ ДОДАТИ")
        launch = QPushButton("ЗАПУСТИТИ")
        remove = QPushButton("ВИДАЛИТИ")
        row.addWidget(add)
        row.addWidget(launch)
        row.addWidget(remove)
        layout.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)
        add.clicked.connect(self.add_launcher)
        launch.clicked.connect(self.launch_selected)
        remove.clicked.connect(self.remove_selected)
        self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        for entry in read_items(self.settings, "app_launchers"):
            try:
                name = str(entry["name"])
                executable = str(entry["executable"])
                raw_argv = entry.get("argv", [])
                if not isinstance(raw_argv, list) or any(
                    not isinstance(arg, str) or "\x00" in arg for arg in raw_argv
                ):
                    continue
                argv = raw_argv
            except (KeyError, TypeError):
                continue
            item = QListWidgetItem(
                f"{name}\n{executable} {json.dumps(argv, ensure_ascii=False)}".strip()
            )
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.items.addItem(item)

    def add_launcher(self) -> None:
        executable, _ = QFileDialog.getOpenFileName(self, "Вибрати виконуваний файл")
        if not executable:
            return
        path = Path(executable)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            QMessageBox.warning(self, "Не можна додати", "Потрібен наявний виконуваний файл.")
            return
        from PySide6.QtWidgets import QInputDialog

        name, accepted = QInputDialog.getText(self, "Назва", "Коротка назва програми:")
        if not accepted or not name.strip():
            return
        arguments_text, accepted = QInputDialog.getText(
            self,
            "Аргументи",
            "Аргументи (необов’язково; лапки групують слова):",
        )
        if not accepted:
            return
        try:
            argv = shlex.split(arguments_text)
        except ValueError:
            QMessageBox.warning(self, "Некоректні аргументи", "Перевір парні лапки.")
            return
        if len(argv) > 64 or any("\x00" in arg or len(arg) > 2048 for arg in argv):
            QMessageBox.warning(self, "Забагато аргументів", "Обмеження: 64 аргументи.")
            return
        entries = read_items(self.settings, "app_launchers")
        entries.append(
            {
                "id": uuid.uuid4().hex,
                "name": name.strip()[:60],
                "executable": str(path),
                "argv": argv,
            }
        )
        write_items(self.settings, "app_launchers", entries)
        self.refresh()

    def launch_selected(self) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        path = Path(str(entry.get("executable", "")))
        argv = entry.get("argv", [])
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            QMessageBox.warning(self, "Не можна запустити", "Програма відсутня або не виконувана.")
            return
        summary = f"Executable: {path}\nargv: {json.dumps(argv, ensure_ascii=False)}"
        answer = QMessageBox.question(
            self,
            "Підтвердити запуск",
            f"Запустити {entry.get('name', 'програму')} з такими аргументами?\n\n{summary}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        from PySide6.QtCore import QProcess

        started, _pid = QProcess.startDetached(
            str(path), [str(arg) for arg in argv], str(path.parent)
        )
        if not started:
            QMessageBox.warning(self, "Помилка запуску", "Qt не зміг запустити цю програму.")

    def remove_selected(self) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        write_items(
            self.settings,
            "app_launchers",
            [
                saved
                for saved in read_items(self.settings, "app_launchers")
                if saved.get("id") != entry.get("id")
            ],
        )
        self.refresh()


class SiteShortcutDialog(QDialog):
    """Manage owner-authored HTTP(S) links opened only by an explicit click."""

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("ЯРЛИКИ САЙТІВ")
        self.setMinimumSize(490, 370)
        self.setStyleSheet(ACTION_STYLE)
        layout = QVBoxLayout(self)
        note = QLabel("Відкриття сайту переходить у зовнішній браузер тільки після натискання.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ ДОДАТИ")
        open_site = QPushButton("ВІДКРИТИ")
        remove = QPushButton("ВИДАЛИТИ")
        row.addWidget(add)
        row.addWidget(open_site)
        row.addWidget(remove)
        layout.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)
        add.clicked.connect(self.add_site)
        open_site.clicked.connect(self.open_selected)
        remove.clicked.connect(self.remove_selected)
        self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        for entry in read_items(self.settings, "site_shortcuts"):
            try:
                name, address = str(entry["name"]), str(entry["url"])
            except KeyError:
                continue
            item = QListWidgetItem(f"{name}\n{address}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.items.addItem(item)

    @staticmethod
    def _valid_url(address: str) -> QUrl | None:
        url = QUrl(address.strip(), QUrl.ParsingMode.StrictMode)
        if (
            not url.isValid()
            or url.scheme().lower() not in {"http", "https"}
            or not url.host()
            or url.userName()
            or url.password()
        ):
            return None
        return url

    def add_site(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, accepted = QInputDialog.getText(self, "Новий сайт", "Назва:")
        if not accepted or not name.strip():
            return
        address, accepted = QInputDialog.getText(self, "Новий сайт", "URL (https://…):")
        if not accepted:
            return
        url = self._valid_url(address)
        if url is None:
            QMessageBox.warning(
                self,
                "Некоректний URL",
                "Потрібне посилання http:// або https:// без логіна/пароля.",
            )
            return
        entries = read_items(self.settings, "site_shortcuts")
        entries.append(
            {"id": uuid.uuid4().hex, "name": name.strip()[:60], "url": url.toString()[:2048]}
        )
        write_items(self.settings, "site_shortcuts", entries)
        self.refresh()

    def open_selected(self) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        url = self._valid_url(str(entry.get("url", "")))
        if url is None or not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Не вдалося відкрити", "Перевір URL і налаштування браузера.")

    def remove_selected(self) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        write_items(
            self.settings,
            "site_shortcuts",
            [
                saved
                for saved in read_items(self.settings, "site_shortcuts")
                if saved.get("id") != entry.get("id")
            ],
        )
        self.refresh()


class PromptShortcutDialog(QDialog):
    """Manage local prompt shortcuts; choosing one only fills the composer."""

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.selected_prompt: str | None = None
        self.setWindowTitle("ШВИДКІ ФРАЗИ")
        self.setMinimumSize(460, 350)
        self.setStyleSheet(ACTION_STYLE)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Фраза вставляється в поле вводу й не надсилається автоматично."))
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        row = QHBoxLayout()
        add = QPushButton("＋ ДОДАТИ")
        use = QPushButton("ВСТАВИТИ")
        remove = QPushButton("ВИДАЛИТИ")
        row.addWidget(add)
        row.addWidget(use)
        row.addWidget(remove)
        layout.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)
        add.clicked.connect(self.add_prompt)
        use.clicked.connect(self.use_selected)
        remove.clicked.connect(self.remove_selected)
        self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        for entry in read_items(self.settings, "prompt_shortcuts"):
            try:
                name, text = str(entry["name"]), str(entry["text"])
            except KeyError:
                continue
            item = QListWidgetItem(f"{name}\n{text[:120]}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.items.addItem(item)

    def add_prompt(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, accepted = QInputDialog.getText(self, "Нова фраза", "Назва:")
        if not accepted or not name.strip():
            return
        text, accepted = QInputDialog.getMultiLineText(self, "Нова фраза", "Текст запиту:")
        if not accepted or not text.strip():
            return
        entries = read_items(self.settings, "prompt_shortcuts")
        entries.append(
            {"id": uuid.uuid4().hex, "name": name.strip()[:60], "text": text.strip()[:2000]}
        )
        write_items(self.settings, "prompt_shortcuts", entries)
        self.refresh()

    def use_selected(self) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        text = str(entry.get("text", "")).strip()
        if text:
            self.selected_prompt = text
            self.accept()

    def remove_selected(self) -> None:
        item = self.items.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        write_items(
            self.settings,
            "prompt_shortcuts",
            [
                saved
                for saved in read_items(self.settings, "prompt_shortcuts")
                if saved.get("id") != entry.get("id")
            ],
        )
        self.refresh()


class CommandDraftDialog(QDialog):
    """Collect command text to submit via B-12 chat; never start a shell here."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("СИСТЕМНА КОМАНДА ДЛЯ CAPRI")
        self.setMinimumSize(560, 380)
        self.setStyleSheet(ACTION_STYLE)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Команду виконає Capri через наявний tool/grant/approval контроль. "
                "Компаньйон не запускає shell самостійно."
            )
        )
        form = QFormLayout()
        self.command = QPlainTextEdit()
        self.command.setPlaceholderText("Наприклад: uname -a")
        self.command.setMaximumHeight(120)
        self.cwd = QLineEdit(str(Path.home()))
        form.addRow("Команда:", self.command)
        cwd_row = QHBoxLayout()
        cwd_row.addWidget(self.cwd, 1)
        browse = QPushButton("ТЕКА…")
        browse.clicked.connect(self.choose_cwd)
        cwd_row.addWidget(browse)
        form.addRow("Робоча тека:", cwd_row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("ПЕРЕДАТИ В ЧАТ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_cwd(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Робоча тека", self.cwd.text())
        if path:
            self.cwd.setText(path)

    def values(self) -> tuple[str, str] | None:
        command = self.command.toPlainText().strip()
        cwd = Path(self.cwd.text()).expanduser()
        if not command or len(command) > 4096 or "\x00" in command:
            QMessageBox.warning(
                self, "Некоректна команда", "Введи команду довжиною до 4096 символів."
            )
            return None
        if not cwd.is_absolute() or not cwd.is_dir():
            QMessageBox.warning(
                self, "Некоректна тека", "Робоча тека має існувати й бути абсолютною."
            )
            return None
        return command, str(cwd.resolve())

    def accept(self) -> None:
        if self.values() is not None:
            super().accept()
