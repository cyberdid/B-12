"""Cyberpunk chat, approvals, memory, and runtime status panels."""

from __future__ import annotations

import html
import json
from functools import partial

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from b12.desktop.client import DesktopApiClient
from b12.desktop.workers import ApiJob

STYLE = """
QWidget#desktopChat { background: #080d19; color: #dbe4f5; font-family: 'Noto Sans', sans-serif; }
QLabel#brand { color: #69f4df; font-size: 18px; font-weight: 800; letter-spacing: 1px; }
QLabel#status { color: #9cb0ce; padding: 5px 8px; }
QLabel#status[online="true"] { color: #69f4df; }
QLabel#status[error="true"] { color: #ff8193; }
QTabWidget::pane { border: 1px solid #263751; background: #0a1020; }
QTabBar::tab { background: #10182a; color: #a8b7d3; padding: 10px 18px; border: 1px solid #263751; }
QTabBar::tab:selected { color: #69f4df; background: #111e31; border-bottom: 2px solid #69f4df; }
QLineEdit, QPlainTextEdit, QComboBox, QListWidget, QTextBrowser {
  background: #0b1324; color: #e2e9f7; border: 1px solid #2a3c58; border-radius: 5px; padding: 8px;
  selection-background-color: #255b70;
}
QTextBrowser { border: none; background: transparent; padding: 6px 10px; }
QPushButton { background: #132338; color: #b6c5de; border: 1px solid #38516f;
  border-radius: 5px; padding: 8px 13px; font-weight: 700; }
QPushButton:hover { background: #1a334d; border-color: #69f4df; color: #69f4df; }
QPushButton:disabled { color: #687790; border-color: #263247; }
QPushButton#send { background: #69f4df; color: #07111c; border-color: #69f4df; padding: 10px 18px; }
QPushButton#approve { color: #07111c; background: #69f4df; border-color: #69f4df; }
QPushButton#deny { color: #ff9aab; border-color: #714053; }
QCheckBox { color: #aebbd0; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #60758f;
  border-radius: 3px; background: #0b1324; }
QCheckBox::indicator:checked { background: #69f4df; border-color: #69f4df; }
QFrame#approvalCard, QFrame#memoryCard { background: #101829; border: 1px solid #4d4750;
  border-radius: 6px; }
QLabel#sectionTitle { color: #69f4df; font-weight: 700; padding: 4px 0; }
QLabel#mutedNote { color: #8698b4; }
"""

PHASE_FOR_RESULT = {
    "completed": "success",
    "awaiting_approval": "approval",
    "cancelled": "cancelled",
    "failed": "error",
}


class ChatWindow(QWidget):
    """Native owner client. Every API operation runs in a QRunnable worker."""

    phase_changed = Signal(str, str)
    approval_requested = Signal(str, bool)

    def __init__(
        self,
        client: DesktopApiClient,
        *,
        persist_default: bool = False,
        auto_load: bool = True,
        auto_poll: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.client = client
        self.setObjectName("desktopChat")
        self.setWindowTitle("B-12 · Neon Companion")
        self.setMinimumSize(620, 620)
        self.resize(760, 820)
        self.setStyleSheet(STYLE)
        self._jobs: set[ApiJob] = set()
        self._entries: list[tuple[str, str]] = []
        self._tool_entries: dict[str, int] = {}
        self._assistant_index: int | None = None
        self._active_turn_id: str | None = None
        self.pending_turn_id: str | None = None
        self._approval_turns: dict[str, str | None] = {}
        self._approval_sessions: dict[str, str | None] = {}
        self._decision_inflight: set[str] = set()
        self._approval_cards: dict[str, QFrame] = {}
        self._current_session: str | None = None
        self._loaded = False
        self._bootstrap_inflight = False
        self._history_loading_session: str | None = None
        self._history_loaded_session: str | None = None
        self._poll_inflight = False
        self._voice_muted: bool | None = None
        self._auto_load = auto_load
        self._auto_poll = auto_poll
        self._persist_default = persist_default
        self._build_ui()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(5000)
        self._poll_timer.timeout.connect(self.refresh_dashboard)
        self._memory_debounce = QTimer(self)
        self._memory_debounce.setSingleShot(True)
        self._memory_debounce.setInterval(300)
        self._memory_debounce.timeout.connect(self.refresh_memory)
        self.session_box.currentIndexChanged.connect(self._session_selected)
        self.memory_search.textChanged.connect(lambda _: self._memory_debounce.start())
        self.new_session_button.clicked.connect(self.create_session)
        self.send_button.clicked.connect(self.send_prompt)
        self.composer.textChanged.connect(self._composer_changed)
        self._send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._send_shortcut.activated.connect(self.send_prompt)
        self.cancel_button.clicked.connect(self.cancel_turn)
        self.consent_toggle.toggled.connect(self.set_consent)
        self.memory_add_button.clicked.connect(self.add_memory)
        self.voice_status_button.clicked.connect(self.request_voice_status)
        self.voice_mute_button.clicked.connect(self.toggle_voice_mute)
        self.phase_changed.connect(self._set_cat_phase)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        header = QHBoxLayout()
        brand = QLabel("B-12  /  NEON COMPANION")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch(1)
        self.status_label = QLabel("◌  ПІДКЛЮЧЕННЯ…")
        self.status_label.setObjectName("status")
        self.status_label.setProperty("online", "false")
        header.addWidget(self.status_label)
        root.addLayout(header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_chat_tab()
        self._build_memory_tab()
        self._build_status_tab()

    def _build_chat_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        sessions = QHBoxLayout()
        self.session_box = QComboBox()
        self.session_box.setMinimumWidth(240)
        sessions.addWidget(self.session_box, 1)
        self.new_session_button = QPushButton("＋ НОВА")
        sessions.addWidget(self.new_session_button)
        layout.addLayout(sessions)

        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setPlaceholderText("Тут з’явиться розмова з B-12.")
        self.transcript.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.transcript, 1)

        self.approvals_title = QLabel("ПІДТВЕРДЖЕННЯ  ·  0")
        self.approvals_title.setObjectName("sectionTitle")
        layout.addWidget(self.approvals_title)
        approval_scroll = QScrollArea()
        approval_scroll.setWidgetResizable(True)
        approval_scroll.setMaximumHeight(112)
        approval_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.approval_host = QWidget()
        self.approval_layout = QVBoxLayout(self.approval_host)
        self.approval_layout.setContentsMargins(0, 0, 0, 0)
        self.approval_layout.setSpacing(6)
        approval_scroll.setWidget(self.approval_host)
        layout.addWidget(approval_scroll)

        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText("Напиши B-12…  ·  Ctrl+Enter надсилає")
        self.composer.setMaximumHeight(96)
        layout.addWidget(self.composer)
        controls = QHBoxLayout()
        self.consent_toggle = QCheckBox("ПАМ’ЯТЬ")
        self.persist_toggle = QCheckBox("ПРОДОВЖУВАТИ ДОВГИЙ ХІД")
        self.persist_toggle.setChecked(self._persist_default)
        controls.addWidget(self.consent_toggle)
        controls.addWidget(self.persist_toggle)
        controls.addStretch(1)
        self.cancel_button = QPushButton("ЗУПИНИТИ")
        self.cancel_button.setEnabled(False)
        controls.addWidget(self.cancel_button)
        self.send_button = QPushButton("НАДІСЛАТИ  ↗")
        self.send_button.setObjectName("send")
        controls.addWidget(self.send_button)
        layout.addLayout(controls)
        self.tabs.addTab(page, "РОЗМОВА")

    def _build_memory_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("ПАМ’ЯТЬ B-12")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.memory_search = QLineEdit()
        self.memory_search.setPlaceholderText("Пошук за змістом…")
        layout.addWidget(self.memory_search)
        add_row = QHBoxLayout()
        self.memory_text = QLineEdit()
        self.memory_text.setPlaceholderText("Запам’ятати новий факт…")
        self.memory_add_button = QPushButton("ЗАПАМ’ЯТАТИ")
        add_row.addWidget(self.memory_text, 1)
        add_row.addWidget(self.memory_add_button)
        layout.addLayout(add_row)
        self.memory_list = QListWidget()
        layout.addWidget(self.memory_list, 1)
        note = QLabel("Джерело та керування пам’яттю лишаються на стороні B-12.")
        note.setObjectName("mutedNote")
        layout.addWidget(note)
        self.tabs.addTab(page, "ПАМ’ЯТЬ")

    def _build_status_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("СТАН СИСТЕМИ")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.runtime_summary = QLabel("Очікую на локальний API B-12…")
        self.runtime_summary.setWordWrap(True)
        self.runtime_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.runtime_summary)
        voice_title = QLabel("ГОЛОС")
        voice_title.setObjectName("sectionTitle")
        layout.addWidget(voice_title)
        self.voice_summary = QLabel("Компаньйон не записує й не відтворює аудіо.")
        self.voice_summary.setWordWrap(True)
        layout.addWidget(self.voice_summary)
        voice_controls = QHBoxLayout()
        self.voice_status_button = QPushButton("ПЕРЕВІРИТИ СТАН МІКРОФОНА")
        self.voice_mute_button = QPushButton("БЛОКУВАННЯ МІКРОФОНА")
        self.voice_mute_button.setEnabled(False)
        voice_controls.addWidget(self.voice_status_button)
        voice_controls.addWidget(self.voice_mute_button)
        layout.addLayout(voice_controls)
        layout.addStretch(1)
        self.tabs.addTab(page, "СТАН")

    def showEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        super().showEvent(event)
        if self._auto_load and not self._loaded and not self._bootstrap_inflight:
            self.bootstrap()
        if self._auto_poll and not self._poll_timer.isActive():
            self._poll_timer.start()
            self.refresh_dashboard()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt virtual
        self._poll_timer.stop()
        super().closeEvent(event)

    def _start_job(self, tag: str, operation, *, streaming: bool = False) -> None:
        job = ApiJob(tag, operation, streaming=streaming)
        self._jobs.add(job)
        job.signals.event.connect(self._on_job_event)
        job.signals.result.connect(self._on_job_result)
        job.signals.error.connect(self._on_job_error)
        job.signals.finished.connect(self._on_job_finished)
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().start(job)

    @Slot(object)
    def _on_job_finished(self, job) -> None:
        self._jobs.discard(job)

    @Slot(str, object)
    def _on_job_event(self, tag: str, event: dict) -> None:
        if tag in {"chat", "resume"} and event.get("type") != "result":
            self.handle_turn_event(event)

    @Slot(str, object)
    def _on_job_result(self, tag: str, result) -> None:
        if tag == "bootstrap":
            self._bootstrap_inflight = False
            self._set_sessions(result["sessions"])
            self.consent_toggle.blockSignals(True)
            self.consent_toggle.setChecked(bool(result["me"].get("consent")))
            self.consent_toggle.blockSignals(False)
            self._loaded = True
            if self._current_session:
                self._load_history(self._current_session)
            self.refresh_dashboard()
        elif tag == "sessions":
            self._set_sessions(result)
        elif tag == "new_session":
            self._current_session = result
            self.bootstrap()
        elif tag.startswith("history:"):
            session_id = tag.partition(":")[2]
            if session_id == self._current_session:
                self._history_loading_session = None
                self._history_loaded_session = session_id
                self._set_history(result)
                self._sync_send_state()
                self._sync_approval_actions()
        elif tag in {"chat", "resume"}:
            self.handle_turn_event(result)
        elif tag.startswith("decision:"):
            operation_id = tag.partition(":")[2]
            approval_session = self._approval_sessions.get(operation_id)
            turn_id = self._approval_turns.get(operation_id) or self.pending_turn_id
            self._decision_inflight.discard(operation_id)
            self._remove_approval_card(operation_id)
            self.refresh_approvals()
            if self._active_turn_id == "starting":
                self._active_turn_id = None
            if turn_id and approval_session == self._current_session:
                self._active_turn_id = turn_id
                self.pending_turn_id = turn_id
                self.send_button.setEnabled(False)
                self.cancel_button.setEnabled(True)
                self._sync_session_selector()
                self._start_job(
                    "resume",
                    lambda emit: self.client.resume(turn_id, emit),
                    streaming=True,
                )
            else:
                self._sync_send_state()
                self._sync_session_selector()
                self._sync_approval_actions()
        elif tag == "approvals":
            self._render_approvals(result)
        elif tag == "poll":
            self._poll_inflight = False
            if not result.get("connected"):
                self._set_connected(False)
                self.runtime_summary.setText(
                    "Локальний API недоступний. Переконайся, що сервер B-12 запущений."
                )
            else:
                self._set_connected(True)
                self._render_approvals(result.get("approvals", []))
                if not self._loaded and not self._bootstrap_inflight:
                    self.bootstrap()
                status = result.get("status", {})
                self.runtime_summary.setText(
                    "B-12 працює · "
                    f"активні ходи: {status.get('active_turns', 0)} · "
                    f"підтвердження: {status.get('pending_approvals', 0)} · "
                    f"збережені snapshots: {status.get('snapshots', 0)}"
                )
        elif tag == "consent":
            self.status_label.setText("◈  НАЛАШТУВАННЯ ПАМ’ЯТІ ОНОВЛЕНО")
        elif tag == "cancel":
            self._active_turn_id = None
            self.pending_turn_id = None
            self.cancel_button.setEnabled(False)
            self._sync_send_state()
            self._sync_session_selector()
            self.status_label.setText("◈  ХІД ЗУПИНЕНО")
        elif tag == "memory_search":
            self._render_memory(result)
        elif tag in {"memory_add", "memory_forget"}:
            self.memory_text.clear()
            self.refresh_memory()
        elif tag == "voice_status":
            self._voice_muted = bool(result.get("muted"))
            self.voice_summary.setText(
                "Мікрофон не записується цим застосунком · "
                + ("блокування ввімкнене" if self._voice_muted else "блокування вимкнене")
            )
            self.voice_mute_button.setText(
                "ЗНЯТИ БЛОКУВАННЯ" if self._voice_muted else "ЗАБЛОКУВАТИ МІКРОФОН"
            )
            self.voice_mute_button.setEnabled(True)
        elif tag == "voice_mute":
            self._voice_muted = bool(result.get("muted"))
            self.request_voice_status()
        if tag == "sessions" and self._current_session:
            self._load_history(self._current_session)

    @Slot(str, str)
    def _on_job_error(self, tag: str, code: str) -> None:
        if tag == "poll":
            self._poll_inflight = False
            self._set_connected(False)
            return
        if tag == "bootstrap":
            self._bootstrap_inflight = False
            self._loaded = False
            self._set_connected(False)
            return
        if tag.startswith("history:") and tag.partition(":")[2] == self._current_session:
            self._history_loading_session = None
            self._history_loaded_session = None
            self._sync_send_state()
            self._sync_approval_actions()
        self.status_label.setText(f"⚠  {code.upper()}")
        self.status_label.setProperty("error", "true")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if tag in {"chat", "resume"}:
            if self._active_turn_id == "starting":
                self._active_turn_id = None
            self.cancel_button.setEnabled(bool(self._active_turn_id))
            self._sync_send_state()
            self._sync_session_selector()
            self.phase_changed.emit("error", code)
            self._append_entry("ЗВ’ЯЗОК", f"Запит не завершився: {code}")
        elif tag.startswith("decision:"):
            self._decision_inflight.discard(tag.partition(":")[2])
            if self._active_turn_id == "starting":
                self._active_turn_id = None
            self._sync_send_state()
            self._sync_session_selector()
            self._sync_approval_actions()
            self.refresh_approvals()

    def _set_connected(self, connected: bool) -> None:
        self.status_label.setText("●  API B-12 ONLINE" if connected else "○  API B-12 OFFLINE")
        self.status_label.setProperty("online", "true" if connected else "false")
        self.status_label.setProperty("error", "false")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def bootstrap(self) -> None:
        if self._bootstrap_inflight:
            return
        self._bootstrap_inflight = True

        def load():
            identity = self.client.me()
            sessions = self.client.sessions()
            if not sessions:
                sessions = [self.client.new_session()]
            return {"me": identity, "sessions": sessions}

        self._start_job("bootstrap", load)

    def _set_sessions(self, sessions: list[str]) -> None:
        current = self._current_session
        self.session_box.blockSignals(True)
        self.session_box.clear()
        for index, session_id in enumerate(sessions, start=1):
            self.session_box.addItem(f"РОЗМОВА {index:02d}  ·  {session_id[:8]}", session_id)
        target = next(
            (i for i in range(self.session_box.count()) if self.session_box.itemData(i) == current),
            -1,
        )
        if target < 0 and self.session_box.count():
            target = self.session_box.count() - 1
        if target >= 0:
            self.session_box.setCurrentIndex(target)
            self._current_session = self.session_box.itemData(target)
        self.session_box.blockSignals(False)
        self._sync_send_state()
        self._sync_session_selector()
        self._sync_approval_actions()

    def _session_selected(self, index: int) -> None:
        session_id = self.session_box.itemData(index)
        if session_id and session_id != self._current_session:
            self._current_session = session_id
            self._sync_send_state()
            self._sync_approval_actions()
            self._load_history(session_id)

    def _current_session_has_pending_approval(self) -> bool:
        return bool(self._current_session) and any(
            session_id == self._current_session for session_id in self._approval_sessions.values()
        )

    def _sync_send_state(self) -> None:
        can_send = (
            self._active_turn_id is None
            and self.pending_turn_id is None
            and not self._current_session_has_pending_approval()
            and (
                self._current_session is None
                or self._history_loading_session != self._current_session
            )
        )
        self.send_button.setEnabled(can_send)

    def _sync_session_selector(self) -> None:
        unlocked = self._active_turn_id is None and self.pending_turn_id is None
        self.session_box.setEnabled(self.session_box.count() > 0 and unlocked)
        self.new_session_button.setEnabled(unlocked)

    def _sync_approval_actions(self) -> None:
        history_ready = bool(self._current_session) and (
            self._history_loaded_session == self._current_session
            and self._history_loading_session != self._current_session
        )
        for operation_id, card in self._approval_cards.items():
            session_id = self._approval_sessions.get(operation_id)
            turn_id = self._approval_turns.get(operation_id)
            turn_matches = self._active_turn_id is None and (
                self.pending_turn_id is None or turn_id == self.pending_turn_id
            )
            enabled = (
                session_id is not None
                and session_id == self._current_session
                and history_ready
                and turn_matches
                and operation_id not in self._decision_inflight
            )
            for button in card.findChildren(QPushButton):
                button.setEnabled(enabled)

    def _load_history(self, session_id: str) -> None:
        self._history_loading_session = session_id
        self._history_loaded_session = None
        self._sync_send_state()
        self._sync_approval_actions()
        self._start_job(f"history:{session_id}", partial(self.client.history, session_id))

    def _set_history(self, messages: list[dict]) -> None:
        self._entries.clear()
        self._tool_entries.clear()
        self._assistant_index = None
        for item in messages:
            role = item.get("role")
            if role == "user":
                self._append_entry("ТИ", item.get("content", ""))
            elif role == "assistant" and item.get("content"):
                self._append_entry("B-12", item["content"])
            elif role == "tool":
                self._append_entry(
                    f"ІНСТРУМЕНТ · {item.get('tool_name', 'tool')}", item.get("content", "")
                )
        self._render_transcript()

    def create_session(self) -> None:
        if self._active_turn_id or self.pending_turn_id:
            return
        self._start_job("new_session", self.client.new_session)

    def _composer_changed(self) -> None:
        if (
            self._active_turn_id
            or self.pending_turn_id
            or self._current_session_has_pending_approval()
        ):
            return
        phase = "typing" if self.composer.toPlainText().strip() else "idle"
        self.phase_changed.emit(phase, "")

    def send_prompt(self) -> None:
        text = self.composer.toPlainText().strip()
        if (
            not text
            or not self._current_session
            or self._active_turn_id
            or self._current_session_has_pending_approval()
        ):
            return
        if self.pending_turn_id:
            self.status_label.setText("◈  СПЕРШУ ВИРІШИ ПОТОЧНЕ ПІДТВЕРДЖЕННЯ")
            return
        self._append_entry("ТИ", text)
        self.composer.clear()
        self._assistant_index = None
        self._active_turn_id = "starting"
        self.send_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._sync_session_selector()
        self.phase_changed.emit("thinking", "")
        session_id = self._current_session
        persist = self.persist_toggle.isChecked()
        self._start_job(
            "chat",
            lambda emit: self.client.stream_turn(session_id, text, persist=persist, on_event=emit),
            streaming=True,
        )

    def cancel_turn(self) -> None:
        if self._active_turn_id and self._active_turn_id != "starting":
            turn_id = self._active_turn_id
            self._start_job("cancel", partial(self.client.cancel, turn_id))

    def handle_turn_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "turn_started":
            self._active_turn_id = event.get("turn_id")
            self.pending_turn_id = self._active_turn_id
            self._sync_session_selector()
            self.phase_changed.emit("thinking", "")
        elif kind == "text_delta":
            self.phase_changed.emit("speaking", "")
            if self._assistant_index is None:
                self._assistant_index = self._append_entry("B-12", "")
            role, current = self._entries[self._assistant_index]
            self._entries[self._assistant_index] = (role, current + str(event.get("text", "")))
            self._render_transcript()
        elif kind == "tool_started":
            name = str(event.get("name", "tool"))
            self.phase_changed.emit("working", name)
            args = json.dumps(event.get("arguments", {}), ensure_ascii=False, indent=2)
            index = self._append_entry(f"ІНСТРУМЕНТ · {name}", f"Аргументи:\n\n{args}")
            self._tool_entries[str(event.get("call_id", ""))] = index
        elif kind == "tool_result":
            index = self._tool_entries.get(str(event.get("call_id", "")))
            if index is not None:
                role, current = self._entries[index]
                outcome = json.dumps(
                    {"status": event.get("status"), "content": event.get("content")},
                    ensure_ascii=False,
                    indent=2,
                )
                self._entries[index] = (role, current + "\n\nРезультат:\n\n" + outcome)
                self._render_transcript()
        elif kind == "approval_pending":
            operation_id = str(event.get("operation_id", ""))
            self.phase_changed.emit("approval", str(event.get("name", "")))
            self.pending_turn_id = self._active_turn_id
            self.status_label.setText(f"◈  ПОТРІБНЕ ПІДТВЕРДЖЕННЯ · {event.get('name', 'дія')}")
            self._approval_turns[operation_id] = self.pending_turn_id
            self._approval_sessions[operation_id] = event.get("session_id") or self._current_session
            self._sync_session_selector()
            call_id = str(event.get("call_id", ""))
            tool_index = self._tool_entries.get(call_id)
            arguments = None
            if tool_index is not None:
                _, tool_text = self._entries[tool_index]
                arguments = tool_text.partition("Аргументи:\n\n")[2].partition(
                    "\n\nРезультат:\n\n"
                )[0]
            self._upsert_approval(
                {
                    "operation_id": operation_id,
                    "name": event.get("name", "дія"),
                    "turn_id": self.pending_turn_id,
                    "session_id": self._approval_sessions.get(operation_id),
                    "arguments": arguments,
                }
            )
            self._sync_approval_actions()
        elif kind == "result":
            self._finish_turn(event)
        elif kind == "error":
            self.phase_changed.emit("error", str(event.get("error", "internal_error")))
            self._append_entry("ПОМИЛКА", str(event.get("error", "internal_error")))
            self._active_turn_id = None
            self.pending_turn_id = None
            self.cancel_button.setEnabled(False)
            self._sync_send_state()
            self._sync_session_selector()

    def _finish_turn(self, result: dict) -> None:
        state = result.get("state", "failed")
        turn_id = result.get("turn_id") or self._active_turn_id
        if result.get("content") and self._assistant_index is None:
            self._append_entry("B-12", str(result["content"]))
        if state == "awaiting_approval":
            self.pending_turn_id = turn_id
            self._active_turn_id = None
        else:
            self._active_turn_id = None
            self.pending_turn_id = None
        phase = PHASE_FOR_RESULT.get(state, "error")
        self.phase_changed.emit(phase, str(result.get("error_code") or ""))
        self.status_label.setText(
            "◈  ПІДТВЕРДЖЕННЯ ОЧІКУЄ НА ТЕБЕ"
            if state == "awaiting_approval"
            else f"◈  ХІД {state.upper()}"
        )
        self.send_button.setEnabled(state != "awaiting_approval")
        self._sync_send_state()
        self.cancel_button.setEnabled(False)
        self._sync_session_selector()
        self._sync_approval_actions()
        self._render_transcript()
        if self._auto_poll:
            self.refresh_approvals()

    def _append_entry(self, role: str, text: str) -> int:
        self._entries.append((role, text))
        self._render_transcript()
        return len(self._entries) - 1

    def _render_transcript(self) -> None:
        blocks = []
        for role, text in self._entries:
            safe = html.escape(text, quote=False) if text else "…"
            safe = safe.replace("![", r"!\[")
            blocks.append(f"### {html.escape(role)}\n\n{safe}")
        self.transcript.setMarkdown("\n\n---\n\n".join(blocks))
        scrollbar = self.transcript.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _upsert_approval(self, approval: dict) -> None:
        operation_id = str(approval.get("operation_id", ""))
        if not operation_id:
            return
        card = self._approval_cards.get(operation_id)
        if card is None:
            card = QFrame()
            card.setObjectName("approvalCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(8, 5, 8, 5)
            info = QLabel()
            info.setTextFormat(Qt.TextFormat.PlainText)
            info.setToolTip(operation_id)
            info.setWordWrap(True)
            row.addWidget(info, 1)
            approve = QPushButton("ДОЗВОЛИТИ")
            approve.setObjectName("approve")
            deny = QPushButton("ВІДХИЛИТИ")
            deny.setObjectName("deny")
            approve.clicked.connect(
                lambda checked=False, op=operation_id: self._decide_approval(op, True)
            )
            deny.clicked.connect(
                lambda checked=False, op=operation_id: self._decide_approval(op, False)
            )
            row.addWidget(approve)
            row.addWidget(deny)
            self.approval_layout.addWidget(card)
            self._approval_cards[operation_id] = card
        info = card.findChild(QLabel)
        if approval.get("session_id") != self._current_session:
            context_note = "Перейди до відповідної розмови, щоб переглянути контекст і вирішити."
        elif self._history_loaded_session != self._current_session:
            context_note = "Історія цієї розмови ще не завантажена; підтвердження поки заблоковано."
        elif approval.get("arguments") is not None:
            context_note = "Параметри виклику видно вище в розмові."
        else:
            context_note = "API не надає параметри цього запиту. Перевір контекст перед рішенням."
        info.setText(
            f"{approval.get('name', 'дія')}  ·  {operation_id[-8:]}\n"
            f"B-12 очікує на точне рішення власника.\n{context_note}"
        )
        self.approvals_title.setText(f"ПІДТВЕРДЖЕННЯ  ·  {len(self._approval_cards)}")

    def _render_approvals(self, approvals: list[dict]) -> None:
        active = {str(item.get("operation_id")): item for item in approvals}
        for operation_id in tuple(self._approval_cards):
            if operation_id not in active:
                self._remove_approval_card(operation_id)
        for operation_id, item in active.items():
            self._approval_turns[operation_id] = item.get("turn_id")
            self._approval_sessions[operation_id] = item.get("session_id")
            self._upsert_approval(item)
        self.approvals_title.setText(f"ПІДТВЕРДЖЕННЯ  ·  {len(self._approval_cards)}")
        self._sync_send_state()
        self._sync_approval_actions()

    def _remove_approval_card(self, operation_id: str) -> None:
        card = self._approval_cards.pop(operation_id, None)
        if card is not None:
            self.approval_layout.removeWidget(card)
            card.deleteLater()
        self._approval_sessions.pop(operation_id, None)
        self._approval_turns.pop(operation_id, None)
        self.approvals_title.setText(f"ПІДТВЕРДЖЕННЯ  ·  {len(self._approval_cards)}")
        self._sync_send_state()
        self._sync_approval_actions()

    def pending_approval_ids(self) -> list[str]:
        return list(self._approval_cards)

    def _decide_approval(self, operation_id: str, approve: bool) -> None:
        if operation_id in self._decision_inflight:
            return
        session_id = self._approval_sessions.get(operation_id)
        turn_id = self._approval_turns.get(operation_id)
        if (
            not self._current_session
            or session_id != self._current_session
            or self._history_loaded_session != self._current_session
            or self._history_loading_session == self._current_session
            or self._active_turn_id is not None
            or (self.pending_turn_id is not None and turn_id != self.pending_turn_id)
        ):
            return
        self._decision_inflight.add(operation_id)
        self._active_turn_id = "starting"
        self._sync_session_selector()
        self._sync_approval_actions()
        self._sync_send_state()
        self.approval_requested.emit(operation_id, approve)
        card = self._approval_cards.get(operation_id)
        if card:
            for button in card.findChildren(QPushButton):
                button.setEnabled(False)
        self._start_job(
            f"decision:{operation_id}",
            lambda: self.client.decide(operation_id, approve=approve),
        )

    def refresh_approvals(self) -> None:
        self._start_job("approvals", self.client.approvals)

    def refresh_dashboard(self) -> None:
        if self._poll_inflight:
            return
        self._poll_inflight = True

        def poll():
            if not self.client.health():
                return {"connected": False}
            return {
                "connected": True,
                "approvals": self.client.approvals(),
                "status": self.client.status(),
            }

        self._start_job("poll", poll)

    def set_consent(self, consent: bool) -> None:
        if self._loaded:
            self._start_job("consent", partial(self.client.set_consent, consent))

    def _set_cat_phase(self, phase: str, detail: str) -> None:
        self.setProperty("petPhase", phase)
        self.setProperty("petDetail", detail)

    def refresh_memory(self) -> None:
        query = self.memory_search.text().strip()
        operation = (
            partial(self.client.memory_search, query) if query else self.client.memory_records
        )
        self._start_job("memory_search", operation)

    def _render_memory(self, records: list[dict]) -> None:
        self.memory_list.clear()
        if not records:
            self.memory_list.addItem("Підтверджених записів немає.")
            return
        for record in records[:100]:
            item = QListWidgetItem()
            self.memory_list.addItem(item)
            card = QFrame()
            card.setObjectName("memoryCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(8, 5, 8, 5)
            label = QLabel(str(record.get("text", "")))
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            row.addWidget(label, 1)
            forget = QPushButton("ЗАБУТИ")
            memory_id = str(record.get("id", ""))
            forget.clicked.connect(partial(self.forget_memory, memory_id))
            row.addWidget(forget)
            item.setSizeHint(card.sizeHint())
            self.memory_list.setItemWidget(item, card)

    def add_memory(self) -> None:
        text = self.memory_text.text().strip()
        if text:
            self._start_job("memory_add", partial(self.client.memory_add, text))

    def forget_memory(self, memory_id: str) -> None:
        if memory_id:
            self._start_job("memory_forget", partial(self.client.memory_forget, memory_id))

    def request_voice_status(self) -> None:
        self._start_job("voice_status", self.client.voice_status)

    def toggle_voice_mute(self) -> None:
        if self._voice_muted is None:
            self.request_voice_status()
            return
        self._start_job("voice_mute", partial(self.client.set_voice_muted, not self._voice_muted))

    def set_voice_muted(self, muted: bool) -> None:
        """Set the existing B-12 control flag; this does not start audio capture."""
        self._start_job("voice_mute", partial(self.client.set_voice_muted, muted))
