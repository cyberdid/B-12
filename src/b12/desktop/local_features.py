"""Bounded, owner-driven Linux/X11 file, host-status, and media utilities."""

from __future__ import annotations

import os
import re
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from b12.desktop.actions import ACTION_STYLE

MAX_SEARCH_ENTRIES = 5000
MAX_SEARCH_RESULTS = 100
MAX_SEARCH_DEPTH = 10
MAX_CONTENT_FILES = 400
MAX_CONTENT_FILE_BYTES = 256 * 1024
MAX_CONTENT_TOTAL_BYTES = 16 * 1024 * 1024
SKIP_DIRS = {
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}
SAFE_OPEN_SUFFIXES = {
    ".csv",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".log",
    ".md",
    ".pdf",
    ".png",
    ".rst",
    ".text",
    ".toml",
    ".txt",
    ".webp",
    ".yaml",
    ".yml",
}
SEARCHABLE_TEXT_SUFFIXES = {
    ".cfg",
    ".c",
    ".cpp",
    ".csv",
    ".css",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".ipynb",
    ".java",
    ".js",
    ".json",
    ".log",
    ".md",
    ".py",
    ".rb",
    ".rst",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class FileSearchResult:
    paths: tuple[Path, ...]
    visited: int
    truncated: bool


def is_linux_x11() -> bool:
    """Return whether the current process is running in an X11 Linux session."""
    if not sys.platform.startswith("linux"):
        return False
    session = os.environ.get("XDG_SESSION_TYPE", "").casefold()
    return bool(os.environ.get("DISPLAY")) and session != "wayland"


def search_filenames(
    root: str | Path,
    query: str,
    *,
    max_entries: int = MAX_SEARCH_ENTRIES,
    max_results: int = MAX_SEARCH_RESULTS,
    max_depth: int = MAX_SEARCH_DEPTH,
) -> FileSearchResult:
    """Search names only under one explicit folder, without following symlinks."""
    needle = query.strip().casefold()
    base = Path(root).expanduser().resolve(strict=True)
    if not base.is_dir():
        raise ValueError("Вибрана тека недоступна")
    if not needle:
        return FileSearchResult((), 0, False)
    if min(max_entries, max_results, max_depth) < 1:
        raise ValueError("Ліміти пошуку мають бути додатними")

    matches: list[Path] = []
    visited = 0
    truncated = False
    pending: list[tuple[Path, int]] = [(base, 0)]
    while pending and visited < max_entries and len(matches) < max_results:
        directory, depth = pending.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        try:
            with entries:
                for entry in entries:
                    if visited >= max_entries or len(matches) >= max_results:
                        truncated = True
                        break
                    visited += 1
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        is_file = entry.is_file(follow_symlinks=False)
                    except OSError:
                        continue
                    if entry.name.casefold().startswith("."):
                        continue
                    if needle in entry.name.casefold() and (is_file or is_dir):
                        matches.append(Path(entry.path))
                    if is_dir and depth < max_depth and entry.name.casefold() not in SKIP_DIRS:
                        pending.append((Path(entry.path), depth + 1))
        except OSError:
            continue
    if pending and (visited >= max_entries or len(matches) >= max_results):
        truncated = True
    return FileSearchResult(tuple(matches), visited, truncated)


def search_file_contents(
    root: str | Path,
    query: str,
    *,
    max_entries: int = MAX_SEARCH_ENTRIES,
    max_results: int = MAX_SEARCH_RESULTS,
    max_depth: int = MAX_SEARCH_DEPTH,
    max_files: int = MAX_CONTENT_FILES,
    max_file_bytes: int = MAX_CONTENT_FILE_BYTES,
    max_total_bytes: int = MAX_CONTENT_TOTAL_BYTES,
) -> FileSearchResult:
    """Search common UTF-8 text files locally with strict per-file and total caps."""
    needle = query.strip().casefold()
    base = Path(root).expanduser().resolve(strict=True)
    if not base.is_dir():
        raise ValueError("Вибрана тека недоступна")
    if not needle:
        return FileSearchResult((), 0, False)
    if min(max_entries, max_results, max_depth, max_files, max_file_bytes, max_total_bytes) < 1:
        raise ValueError("Ліміти пошуку мають бути додатними")

    matches: list[Path] = []
    visited = 0
    scanned_files = 0
    scanned_bytes = 0
    truncated = False
    pending: list[tuple[Path, int]] = [(base, 0)]
    while pending and visited < max_entries and len(matches) < max_results:
        directory, depth = pending.pop()
        try:
            entries = os.scandir(directory)
        except OSError:
            continue
        try:
            with entries:
                for entry in entries:
                    if visited >= max_entries or len(matches) >= max_results:
                        truncated = True
                        break
                    visited += 1
                    if entry.name.startswith("."):
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        is_file = entry.is_file(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        if depth < max_depth and entry.name.casefold() not in SKIP_DIRS:
                            pending.append((Path(entry.path), depth + 1))
                        continue
                    if (
                        not is_file
                        or Path(entry.name).suffix.casefold() not in SEARCHABLE_TEXT_SUFFIXES
                    ):
                        continue
                    if scanned_files >= max_files or scanned_bytes >= max_total_bytes:
                        truncated = True
                        break
                    try:
                        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                        descriptor = os.open(entry.path, flags)
                        with os.fdopen(descriptor, "rb") as source:
                            stat_result = os.fstat(source.fileno())
                            if not stat.S_ISREG(stat_result.st_mode):
                                continue
                            if stat_result.st_size > max_file_bytes:
                                continue
                            remaining = max_total_bytes - scanned_bytes
                            if stat_result.st_size > remaining:
                                truncated = True
                                break
                            raw = source.read(min(max_file_bytes, remaining))
                    except OSError:
                        continue
                    scanned_files += 1
                    scanned_bytes += len(raw)
                    try:
                        content = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    if needle in content.casefold():
                        matches.append(Path(entry.path))
        except OSError:
            continue
    if pending and (visited >= max_entries or len(matches) >= max_results):
        truncated = True
    return FileSearchResult(tuple(matches), visited, truncated)


def _read_cpu_totals() -> tuple[int, int] | None:
    try:
        fields = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()[1:]
        values = [int(value) for value in fields]
    except (OSError, ValueError, IndexError):
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def system_snapshot() -> list[tuple[str, str]]:
    """Return read-only local CPU, RAM, home-volume, battery, and network state."""
    rows: list[tuple[str, str]] = []
    now_cpu = _read_cpu_totals()
    previous = getattr(system_snapshot, "_cpu_previous", None)
    system_snapshot._cpu_previous = now_cpu  # type: ignore[attr-defined]
    if now_cpu is None:
        rows.append(("CPU", "недоступно: /proc/stat"))
    elif previous:
        total_delta = now_cpu[0] - previous[0]
        idle_delta = now_cpu[1] - previous[1]
        percent = 100 * (1 - idle_delta / total_delta) if total_delta > 0 else 0.0
        rows.append(("CPU", f"{percent:.0f}%"))
    else:
        rows.append(("CPU", "збираю перший інтервал вимірювання…"))

    try:
        memory = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, value = line.split(":", 1)
            memory[key] = int(value.strip().split()[0])
        total = memory["MemTotal"]
        available = memory["MemAvailable"]
        rows.append(("RAM", f"{(total - available) / 1024:.0f} / {total / 1024:.0f} MiB"))
    except (OSError, ValueError, KeyError, IndexError):
        rows.append(("RAM", "недоступно: /proc/meminfo"))

    try:
        usage = shutil.disk_usage(Path.home())
        rows.append(("Диск · тека користувача", f"{usage.free / 2**30:.1f} GiB вільно"))
    except OSError:
        rows.append(("Диск · тека користувача", "недоступно: shutil.disk_usage"))

    power_supply = Path("/sys/class/power_supply")
    batteries = sorted(power_supply.glob("*")) if power_supply.exists() else []
    battery_rows = []
    for battery in batteries:
        try:
            if (battery / "type").read_text(encoding="ascii").strip() != "Battery":
                continue
            capacity = (battery / "capacity").read_text(encoding="ascii").strip()
            state = (battery / "status").read_text(encoding="ascii").strip()
            battery_rows.append(f"{battery.name}: {capacity}% · {state}")
        except OSError:
            continue
    rows.append(
        (
            "Батарея",
            "; ".join(battery_rows) if battery_rows else "не виявлено: /sys/class/power_supply",
        )
    )

    interfaces = []
    try:
        for interface in sorted(Path("/sys/class/net").iterdir()):
            if interface.name == "lo":
                continue
            try:
                state = (interface / "operstate").read_text(encoding="ascii").strip()
            except OSError:
                state = "стан недоступний"
            interfaces.append(f"{interface.name}: {state}")
    except OSError:
        rows.append(("Мережа", "недоступно: /sys/class/net"))
    else:
        rows.append(("Мережа · інтерфейси", "; ".join(interfaces) if interfaces else "не виявлено"))
    rows.append(("Локальна адреса", _local_address()))
    return rows


def _local_address() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            return sock.getsockname()[0]
    except OSError:
        return "недоступно"


def available_media_tools() -> dict[str, str | None]:
    """Detect fixed Linux media command paths without executing user-provided text."""
    return {
        "playerctl": shutil.which("playerctl"),
        "wpctl": shutil.which("wpctl"),
        "pactl": shutil.which("pactl"),
    }


def _fixed_command(argv: list[str]) -> tuple[bool, str]:
    """Run a fixed-argument host query/control with timeout; never invoke a shell."""
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output or f"код завершення {completed.returncode}"


class LocalFeaturesDialog(QDialog):
    """Compact local feature center; every external action is initiated by an owner click."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ЛОКАЛЬНІ МОЖЛИВОСТІ CAPRI")
        self.setMinimumSize(520, 450)
        self.resize(620, 520)
        self.setStyleSheet(ACTION_STYLE)
        self._root: Path | None = None
        self._tools = available_media_tools()
        self._host_tools = {
            name: shutil.which(name)
            for name in ("loginctl", "systemctl", "shutdown", "gsettings", "xrandr")
        }

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        tabs.addTab(self._build_files_tab(), "ФАЙЛИ")
        tabs.addTab(self._build_system_tab(), "СИСТЕМА")
        tabs.addTab(self._build_media_tab(), "МЕДІА")
        tabs.addTab(self._build_desktop_tab(), "РОБОЧИЙ СТІЛ")
        close = QPushButton("ЗАКРИТИ")
        close.clicked.connect(self.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    def _build_files_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel(
            "Пошук працює лише у вибраній теці. Пошук за вмістом вимкнений за замовчуванням; "
            "коли його ввімкнено, текст читається локально в межах лімітів і не зберігається."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.root_label = QLabel("Теку не вибрано")
        self.root_label.setWordWrap(True)
        layout.addWidget(self.root_label)
        choose = QPushButton("ОБРАТИ ТЕКУ…")
        choose.clicked.connect(self._choose_root)
        layout.addWidget(choose)
        row = QHBoxLayout()
        self.file_query = QLineEdit()
        self.file_query.setPlaceholderText("Фрагмент назви файла або теки")
        self.file_query.setMaxLength(160)
        search = QPushButton("ШУКАТИ")
        search.clicked.connect(self._search)
        self.file_query.returnPressed.connect(self._search)
        row.addWidget(self.file_query, 1)
        row.addWidget(search)
        layout.addLayout(row)
        self.search_contents = QCheckBox("Шукати також у вмісті текстових файлів")
        self.search_contents.setToolTip(
            "Локально, тільки у вибраній теці: до 400 UTF-8 файлів, 256 KiB на файл "
            "і 16 MiB загалом."
        )
        layout.addWidget(self.search_contents)
        self.file_results = QListWidget()
        self.file_results.setToolTip(
            "Показує точні шляхи; вміст не зберігається й не надсилається."
        )
        layout.addWidget(self.file_results, 1)
        buttons = QHBoxLayout()
        open_file = QPushButton("ВІДКРИТИ БЕЗПЕЧНИЙ ФАЙЛ…")
        reveal = QPushButton("ПОКАЗАТИ ТЕКУ…")
        open_file.clicked.connect(self._open_selected_file)
        reveal.clicked.connect(self._reveal_selected)
        buttons.addWidget(open_file)
        buttons.addWidget(reveal)
        layout.addLayout(buttons)
        return page

    def _build_system_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel("Лише локальне читання системних лічильників; дані не надсилаються мережею.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.system_values = QListWidget()
        layout.addWidget(self.system_values, 1)
        refresh = QPushButton("ОНОВИТИ ЗРІЗ")
        refresh.clicked.connect(self._refresh_system)
        layout.addWidget(refresh)
        self._system_timer = QTimer(self)
        self._system_timer.setInterval(2000)
        self._system_timer.timeout.connect(self._refresh_system)
        self._system_timer.start()
        self._refresh_system()
        return page

    def _build_media_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        if not is_linux_x11():
            label = QLabel(
                "Керування медіа доступне лише в Linux/X11; поточне середовище не підтримується."
            )
            label.setWordWrap(True)
            layout.addWidget(label)
            return page

        self.media_status = QLabel()
        self.media_status.setWordWrap(True)
        layout.addWidget(self.media_status)
        self.player_box = QComboBox()
        layout.addWidget(self.player_box)
        self._refresh_players()
        player_row = QHBoxLayout()
        for label, verb in (("⏯", "play-pause"), ("◀◀", "previous"), ("▶▶", "next")):
            button = QPushButton(label)
            button.setToolTip(f"Медіакоманда: {verb}; ціль указана вище")
            button.clicked.connect(lambda _checked=False, action=verb: self._control_player(action))
            player_row.addWidget(button)
        refresh = QPushButton("ОНОВИТИ")
        refresh.clicked.connect(self._refresh_players)
        player_row.addWidget(refresh)
        layout.addLayout(player_row)

        volume_label = QLabel(self._volume_target())
        volume_label.setWordWrap(True)
        layout.addWidget(volume_label)
        volume_row = QHBoxLayout()
        for label, action in (("−5%", "down"), ("+5%", "up"), ("MUTE", "mute")):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, selected=action: self._control_volume(selected)
            )
            volume_row.addWidget(button)
        layout.addLayout(volume_row)
        return page

    def _build_desktop_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        if not is_linux_x11():
            unavailable = QLabel(
                "Керування сеансом, темою та дисплеями доступне лише в Linux/X11; "
                "поточне середовище не підтримується."
            )
            unavailable.setWordWrap(True)
            layout.addWidget(unavailable)
            return page

        power_note = QLabel(
            "Дії стосуються лише поточного локального сеансу. Сон, перезапуск і вимкнення "
            "вимагають введення точної назви дії."
        )
        power_note.setWordWrap(True)
        layout.addWidget(power_note)
        power_row = QHBoxLayout()
        self.power_buttons: dict[str, QPushButton] = {}
        actions = (
            ("lock", "ЗАБЛОКУВАТИ", "loginctl"),
            ("suspend", "СОН", "systemctl"),
            ("reboot", "ПЕРЕЗАПУСК", "systemctl"),
            ("poweroff", "ВИМКНУТИ", "systemctl"),
            ("cancel", "СКАСУВАТИ SHUTDOWN", "shutdown"),
        )
        for action, label, tool in actions:
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, selected=action: self._run_host_action(selected)
            )
            executable = self._host_tools[tool]
            button.setEnabled(bool(executable))
            if not executable:
                button.setToolTip(f"Недоступно: не знайдено {tool} у PATH")
            self.power_buttons[action] = button
            power_row.addWidget(button)
        layout.addLayout(power_row)

        theme_row = QHBoxLayout()
        self.theme_status = QLabel("Тема GNOME: перевір інструмент gsettings")
        self.theme_status.setWordWrap(True)
        theme_row.addWidget(self.theme_status, 1)
        self.theme_button = QPushButton("ЗМІНИТИ ТЕМУ…")
        self.theme_button.setEnabled(bool(self._host_tools["gsettings"]))
        self.theme_button.clicked.connect(self._toggle_gnome_theme)
        if not self._host_tools["gsettings"]:
            self.theme_button.setToolTip("Недоступно: не знайдено gsettings у PATH")
        theme_row.addWidget(self.theme_button)
        layout.addLayout(theme_row)
        self._refresh_gnome_theme()

        display_note = QLabel(
            "Дисплейні режими читаються з xrandr. Можна змінити режим одного підключеного виходу."
        )
        display_note.setWordWrap(True)
        layout.addWidget(display_note)
        display_row = QHBoxLayout()
        self.display_box = QComboBox()
        display_row.addWidget(self.display_box, 1)
        self.display_refresh = QPushButton("ОНОВИТИ")
        self.display_refresh.clicked.connect(self._refresh_display_modes)
        display_row.addWidget(self.display_refresh)
        layout.addLayout(display_row)
        self.display_apply = QPushButton("ЗАСТОСУВАТИ ВИБРАНИЙ РЕЖИМ…")
        self.display_apply.clicked.connect(self._apply_display_mode)
        layout.addWidget(self.display_apply)
        self._refresh_display_modes()
        layout.addStretch(1)
        return page

    def _run_host_action(self, action: str) -> None:
        # The action map contains fixed executables and argv; no composer or model text is accepted.
        command_map = {
            "lock": ("loginctl", ["lock-session"], "заблокувати поточний сеанс", None),
            "suspend": (
                "systemctl",
                ["--no-ask-password", "suspend"],
                "перевести комп’ютер у сон",
                "СОН",
            ),
            "reboot": (
                "systemctl",
                ["--no-ask-password", "reboot"],
                "перезапустити комп’ютер",
                "ПЕРЕЗАПУСК",
            ),
            "poweroff": (
                "systemctl",
                ["--no-ask-password", "poweroff"],
                "вимкнути комп’ютер",
                "ВИМКНУТИ",
            ),
            "cancel": ("shutdown", ["-c"], "скасувати заплановане вимкнення", "СКАСУВАТИ SHUTDOWN"),
        }
        configured = command_map.get(action)
        if not configured:
            return
        tool_name, arguments, title, required_phrase = configured
        executable = self._host_tools.get(tool_name)
        if not executable:
            return
        argv = [executable, *arguments]
        exact = f"Дія: {title}\nЦіль: поточний локальний комп’ютер / сеанс\nКоманда: {argv!r}"
        if required_phrase:
            typed, accepted = QInputDialog.getText(
                self,
                "ТОЧНЕ ПІДТВЕРДЖЕННЯ",
                f"Щоб підтвердити дію, введи {required_phrase}:\n\n{exact}",
            )
            if not accepted or typed.strip().upper() != required_phrase:
                return
        elif (
            QMessageBox.question(self, "ПІДТВЕРДИ ДІЮ", f"Виконати дію?\n\n{exact}")
            != QMessageBox.StandardButton.Yes
        ):
            return
        ok, output = _fixed_command(argv)
        if not ok:
            QMessageBox.warning(self, "ДІЯ НЕ ВДАЛАСЯ", f"{exact}\n\n{output}")

    def _refresh_gnome_theme(self) -> None:
        gsettings = self._host_tools["gsettings"]
        if not gsettings:
            self.theme_status.setText("GNOME theme недоступна: не знайдено gsettings у PATH")
            self.theme_button.setEnabled(False)
            return
        ok, value = _fixed_command(
            [gsettings, "get", "org.gnome.desktop.interface", "color-scheme"]
        )
        if not ok or value not in {"'default'", "'prefer-dark'", "'prefer-light'"}:
            self.theme_status.setText(
                "GNOME theme недоступна: не знайдено schema/key "
                "org.gnome.desktop.interface color-scheme"
            )
            self.theme_button.setEnabled(False)
            self.theme_button.setToolTip(value)
            return
        label = {"'default'": "системна", "'prefer-dark'": "темна", "'prefer-light'": "світла"}[
            value
        ]
        self.theme_status.setText(
            f"GNOME color-scheme: {label} · точний key: org.gnome.desktop.interface color-scheme"
        )
        self.theme_button.setEnabled(True)

    def _toggle_gnome_theme(self) -> None:
        gsettings = self._host_tools["gsettings"]
        if not gsettings:
            return
        ok, current = _fixed_command(
            [gsettings, "get", "org.gnome.desktop.interface", "color-scheme"]
        )
        if not ok or current not in {"'prefer-dark'", "'prefer-light'", "'default'"}:
            self._refresh_gnome_theme()
            return
        new_value = "prefer-light" if current == "'prefer-dark'" else "prefer-dark"
        target = f"GNOME key org.gnome.desktop.interface color-scheme → {new_value}"
        if (
            QMessageBox.question(self, "ЗМІНИТИ GNOME THEME", f"Застосувати зміну?\n\n{target}")
            != QMessageBox.StandardButton.Yes
        ):
            return
        ok, output = _fixed_command(
            [gsettings, "set", "org.gnome.desktop.interface", "color-scheme", new_value]
        )
        if not ok:
            QMessageBox.warning(self, "НЕ ВДАЛОСЯ ЗМІНИТИ ТЕМУ", f"{target}\n\n{output}")
        self._refresh_gnome_theme()

    @staticmethod
    def _parse_xrandr(output: str) -> list[tuple[str, str, bool]]:
        modes: list[tuple[str, str, bool]] = []
        active_output: str | None = None
        for line in output.splitlines():
            if line and not line[0].isspace():
                fields = line.split()
                active_output = fields[0] if len(fields) > 1 and fields[1] == "connected" else None
                continue
            if not active_output:
                continue
            match = re.match(r"\s+(\d{3,5}x\d{3,5})(?:\s+.*)?$", line)
            if match:
                modes.append((active_output, match.group(1), "*" in line))
        return modes

    def _refresh_display_modes(self) -> None:
        self.display_box.clear()
        xrandr = self._host_tools["xrandr"]
        self.display_box.setEnabled(False)
        self.display_apply.setEnabled(False)
        if not xrandr:
            self.display_box.addItem("Недоступно: не знайдено xrandr у PATH")
            self.display_refresh.setToolTip("Недоступно: не знайдено xrandr у PATH")
            return
        ok, output = _fixed_command([xrandr, "--query"])
        if not ok:
            self.display_box.addItem(f"Недоступно: xrandr --query · {output}")
            return
        modes = self._parse_xrandr(output)
        seen: set[tuple[str, str]] = set()
        for name, mode, selected in modes:
            if (name, mode) in seen:
                continue
            seen.add((name, mode))
            label = f"{name} · {mode}" + (" · ПОТОЧНИЙ" if selected else "")
            self.display_box.addItem(label, (name, mode))
        has_modes = self.display_box.count() > 0
        if not has_modes:
            self.display_box.addItem("Немає доступних режимів у xrandr")
        self.display_box.setEnabled(has_modes)
        self.display_apply.setEnabled(has_modes)

    def _apply_display_mode(self) -> None:
        selected = self.display_box.currentData()
        xrandr = self._host_tools["xrandr"]
        if not xrandr or not isinstance(selected, tuple) or len(selected) != 2:
            return
        output_name, mode = selected
        exact = (
            f"Вихід дисплея: {output_name}\nРежим: {mode}\n"
            f"Команда: {[xrandr, '--output', output_name, '--mode', mode]!r}"
        )
        if (
            QMessageBox.question(self, "ПІДТВЕРДИ РЕЖИМ ДИСПЛЕЯ", f"Застосувати режим?\n\n{exact}")
            != QMessageBox.StandardButton.Yes
        ):
            return
        ok, output = _fixed_command([xrandr, "--output", output_name, "--mode", mode])
        if not ok:
            QMessageBox.warning(self, "НЕ ВДАЛОСЯ ЗМІНИТИ РЕЖИМ", f"{exact}\n\n{output}")
        self._refresh_display_modes()

    def _choose_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "ОБЕРИ ТЕКУ ДЛЯ ПОШУКУ", str(Path.home()))
        if selected:
            self._root = Path(selected).resolve()
            self.root_label.setText(f"Корінь пошуку: {self._root}")

    def _search(self) -> None:
        if not self._root:
            QMessageBox.information(self, "ОБЕРИ ТЕКУ", "Спочатку вибери теку пошуку.")
            return
        try:
            query = self.file_query.text()
            name_result = search_filenames(self._root, query)
            if self.search_contents.isChecked():
                content_result = search_file_contents(self._root, query)
                result = FileSearchResult(
                    tuple(dict.fromkeys((*name_result.paths, *content_result.paths)))[
                        :MAX_SEARCH_RESULTS
                    ],
                    name_result.visited + content_result.visited,
                    name_result.truncated or content_result.truncated,
                )
            else:
                result = name_result
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "ПОМИЛКА ПОШУКУ", str(exc))
            return
        self.file_results.clear()
        for path in result.paths:
            item = QListWidgetItem(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.file_results.addItem(item)
        suffix = " · ліміт досягнуто" if result.truncated else ""
        self.file_results.setToolTip(f"Переглянуто {result.visited} записів{suffix}")
        if result.truncated:
            QMessageBox.information(
                self,
                "ПОШУК ОБМЕЖЕНО",
                f"Показано {len(result.paths)} збігів; переглянуто до "
                f"{result.visited} записів. Уточни запит або вибери меншу теку.",
            )

    def _selected_path(self) -> Path | None:
        item = self.file_results.currentItem()
        raw = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not raw or not self._root:
            return None
        try:
            target = Path(str(raw)).resolve(strict=True)
            target.relative_to(self._root)
        except (OSError, ValueError):
            return None
        return target

    def _open_selected_file(self) -> None:
        target = self._selected_path()
        if not target or not target.is_file():
            QMessageBox.information(
                self, "ФАЙЛ НЕ ВИБРАНО", "Вибери звичайний файл у результатах пошуку."
            )
            return
        if target.suffix.casefold() not in SAFE_OPEN_SUFFIXES or target.name.endswith(".desktop"):
            QMessageBox.warning(
                self,
                "ТИП ФАЙЛУ ОБМЕЖЕНО",
                f"Відкриття цього типу не дозволене з цього інтерфейсу.\n\nТочний файл: {target}",
            )
            return
        if (
            QMessageBox.question(
                self,
                "ПІДТВЕРДИ ВІДКРИТТЯ",
                f"Відкрити цей файл у системному застосунку?\n\n{target}",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            QMessageBox.warning(self, "НЕ ВДАЛОСЯ ВІДКРИТИ", f"Система не відкрила файл:\n{target}")

    def _reveal_selected(self) -> None:
        target = self._selected_path()
        if not target:
            QMessageBox.information(self, "ОБ’ЄКТ НЕ ВИБРАНО", "Вибери результат пошуку.")
            return
        folder = target.parent if target.is_file() else target
        if (
            QMessageBox.question(
                self, "ПОКАЗАТИ ТОЧНУ ТЕКУ", f"Відкрити теку у файловому менеджері?\n\n{folder}"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            QMessageBox.warning(
                self, "НЕ ВДАЛОСЯ ВІДКРИТИ ТЕКУ", f"Система не відкрила теку:\n{folder}"
            )

    def _refresh_system(self) -> None:
        self.system_values.clear()
        for name, value in system_snapshot():
            item = QListWidgetItem(f"{name}   ·   {value}")
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.system_values.addItem(item)

    def _refresh_players(self) -> None:
        self.player_box.clear()
        playerctl = self._tools["playerctl"]
        players = []
        if playerctl:
            ok, output = _fixed_command([playerctl, "-l"])
            players = [line.strip() for line in output.splitlines() if line.strip()] if ok else []
        self.player_box.addItems(players)
        if players:
            self.media_status.setText("Виявлені MPRIS цілі: " + ", ".join(players))
        else:
            missing = (
                "playerctl" if not playerctl else "MPRIS програвач не відповів через playerctl"
            )
            self.media_status.setText(f"Керування плеєром недоступне: {missing}.")
        self.player_box.setEnabled(bool(players))

    def _control_player(self, action: str) -> None:
        playerctl = self._tools["playerctl"]
        player = self.player_box.currentText()
        if not playerctl or not player or action not in {"play-pause", "previous", "next"}:
            return
        target = f"MPRIS програвач {player} · команда {action}"
        if (
            QMessageBox.question(self, "ПІДТВЕРДИ МЕДІАКОМАНДУ", f"Виконати дію?\n\n{target}")
            != QMessageBox.StandardButton.Yes
        ):
            return
        ok, output = _fixed_command([playerctl, f"--player={player}", action])
        if not ok:
            QMessageBox.warning(self, "МЕДІАКОМАНДА НЕ ВДАЛАСЯ", f"{target}\n\n{output}")

    def _volume_target(self) -> str:
        if self._tools["wpctl"]:
            return "Ціль гучності: PipeWire default sink (@DEFAULT_AUDIO_SINK@) через wpctl"
        if self._tools["pactl"]:
            return "Ціль гучності: PulseAudio default sink (@DEFAULT_SINK@) через pactl"
        return "Керування гучністю недоступне: не знайдено wpctl або pactl"

    def _control_volume(self, action: str) -> None:
        if action not in {"up", "down", "mute"}:
            return
        if self._tools["wpctl"]:
            tool = self._tools["wpctl"]
            target = "PipeWire @DEFAULT_AUDIO_SINK@"
            args = [tool, "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"]
        elif self._tools["pactl"]:
            tool = self._tools["pactl"]
            target = "PulseAudio @DEFAULT_SINK@"
            args = [tool, "set-sink-mute", "@DEFAULT_SINK@", "toggle"]
        else:
            QMessageBox.information(self, "НЕМАЄ КОНТРОЛЕРА", self._volume_target())
            return
        action_label = {
            "up": "збільшити на 5%",
            "down": "зменшити на 5%",
            "mute": "перемкнути mute",
        }[action]
        if action != "mute":
            query = (
                [tool, "get-volume", "@DEFAULT_AUDIO_SINK@"]
                if self._tools["wpctl"]
                else [tool, "get-sink-volume", "@DEFAULT_SINK@"]
            )
            ok, current_text = _fixed_command(query)
            pattern = (
                r"(?:Volume:\s*)?(\d+(?:\.\d+)?)" if self._tools["wpctl"] else r"/\s*(\d{1,3})%"
            )
            match = re.search(pattern, current_text)
            if not ok or not match:
                QMessageBox.warning(
                    self,
                    "СТАН ГУЧНОСТІ НЕДОСТУПНИЙ",
                    f"Не змінював гучність для {target}: не вдалося прочитати "
                    f"поточне значення.\n\n{current_text}",
                )
                return
            if self._tools["wpctl"]:
                current = float(match.group(1))
                new_value = min(1.0, max(0.0, current + (0.05 if action == "up" else -0.05)))
                args = [tool, "set-volume", "@DEFAULT_AUDIO_SINK@", f"{new_value:.2f}"]
                action_label += f" · {current:.0%} → {new_value:.0%}"
            else:
                current = int(match.group(1))
                new_value = min(100, max(0, current + (5 if action == "up" else -5)))
                args = [tool, "set-sink-volume", "@DEFAULT_SINK@", f"{new_value}%"]
                action_label += f" · {current}% → {new_value}%"
        exact = f"{target} · {action_label} · argv: {args!r}"
        if (
            QMessageBox.question(self, "ПІДТВЕРДИ ЗМІНУ ГУЧНОСТІ", f"Виконати дію?\n\n{exact}")
            != QMessageBox.StandardButton.Yes
        ):
            return
        ok, output = _fixed_command(args)
        if not ok:
            QMessageBox.warning(self, "НЕ ВДАЛОСЯ ЗМІНИТИ ГУЧНІСТЬ", f"{exact}\n\n{output}")

    def closeEvent(self, event) -> None:
        timer = getattr(self, "_system_timer", None)
        if timer:
            timer.stop()
        super().closeEvent(event)
