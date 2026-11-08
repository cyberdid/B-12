"""B-12 terminal UI: sessions, conversation, approvals and memory in one console.

Neon conversation workspace with an animated local cybercat companion. The app talks
only to the loopback API; pet interactions never invoke a model or tool.
"""

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from rich.markup import escape
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Collapsible, Footer, Input, Markdown, Static

from b12.tui.activity import ActivityStore
from b12.tui.chrome import NeonHeader, Welcome
from b12.tui.client import ApiClient
from b12.tui.pet import CyberCat
from b12.tui.theme import CSS
from b12.tui.voice import MAX_RECORD_SECONDS, PttRecorder, VoiceError, VoicePlayer

CHAT_INTENT = {"completed": "", "failed": "ПОМИЛКА", "cancelled": "СКАСОВАНО"}


@dataclass
class Turn:
    session_id: str
    turn_id: str | None = None
    tools: dict = field(default_factory=dict)
    streamed: str = ""
    shown: bool = False
    started_at: float = field(default_factory=time.monotonic)
    tool_calls: set[str] = field(default_factory=set)
    approval_ids: set[str] = field(default_factory=set)
    failure_events: int = 0
    event_count: int = 0
    state: str = "running"

    def report(self, state: str) -> str:
        elapsed = _duration(time.monotonic() - self.started_at)
        return (
            f"B-12 · {state} · {elapsed} · інструментів {len(self.tool_calls)} · "
            f"очікувань дозволу {len(self.approval_ids)} · сигналів збою {self.failure_events} · "
            f"подій {self.event_count}"
        )


class B12App(App):
    CSS = CSS
    TITLE = "B-12"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+n", "new_session", "Нова розмова"),
        Binding("ctrl+p", "toggle_panel", "Панель"),
        Binding("escape", "cancel", "Зупинити"),
        Binding("ctrl+k", "pet", "Погладити", priority=True),
        Binding("f2", "toggle_nav", "Розмови", show=False),
        Binding("f6", "stop_audio", "Стоп голос", show=False),
        Binding("f7", "ptt", "Мікрофон"),
        Binding("f8", "toggle_motion", "Анімації"),
        Binding("f9", "cycle_skin", "Персонаж"),
        Binding("ctrl+q", "quit", "Вихід"),
    ]

    def __init__(
        self,
        client: ApiClient,
        persist_default: bool = False,
        *,
        state_dir: Path | str | None = None,
        preview_mode: bool = False,
    ):
        super().__init__()
        self.client = client
        self.current: str | None = None
        self.turn: Turn | None = None
        self.waiting_turn: str | None = None  # a turn paused for an owner decision
        self.paused_turn: Turn | None = None
        self._stream_active = False
        self._resume_requested: str | None = None
        self._cancel_requested_turns: set[str] = set()
        self.persist_default = persist_default
        self.preview_mode = preview_mode
        self._closing = False
        self._activity_store = ActivityStore(state_dir) if state_dir and not preview_mode else None
        self._activity = deque(maxlen=100)
        self._activity_cursor = 0
        self._activity_lock = asyncio.Lock()
        self._activity_task: asyncio.Task | None = None
        self._activity_notice = ""
        self._external_live = False
        self._recorder: PttRecorder | None = None
        self._player: VoicePlayer | None = None
        self._capture_lock = asyncio.Lock()
        self._ptt_task: asyncio.Task | None = None
        self._voice_status_task: asyncio.Task | None = None
        self._asr_task: asyncio.Task | None = None
        self._mute_task: asyncio.Task | None = None
        self._speech_task: asyncio.Task | None = None
        self._ptt_generation = 0
        self._speech_generation = 0
        self._record_started: float | None = None
        self._record_timer = None
        self._mic_muted: bool | None = None

    # ---- layout -------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield NeonHeader(id="top")
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Static("◈  ТВОЯ ОРБІТА\n   LOCAL-FIRST", id="nav-brand")
                yield Button("＋ нова розмова", id="new")
                yield Static("РОЗМОВИ", classes="head")
                with VerticalScroll(id="session-scroll"):
                    yield Vertical(id="sessions")
                yield Static("F2  навігація\nТвій простір. Твої історії.", id="nav-note")
            with Vertical(id="conversation"):
                with Horizontal(id="chat-heading"):
                    yield Static("ЗВ’ЯЗОК ІЗ B-12", id="chat-title")
                    yield Static("// CHAT", id="channel-tag")
                yield Static("Готовий до розмови", id="turn-report", markup=False)
                yield VerticalScroll(id="chat")
                with Vertical(id="bar"):
                    yield Static("ТВОЯ ДУМКА  /  Enter — надіслати", id="compose-label")
                    with Horizontal(id="compose-line"):
                        yield Input(placeholder="Напиши B-12…", id="prompt")
                        yield Button("🎙 F7", id="ptt", disabled=self.preview_mode)
                        yield Button("НАДІСЛАТИ", id="send")
                    with Horizontal(id="compose-options"):
                        yield Checkbox("ПАМ'ЯТЬ", value=True, id="consent")
                        yield Checkbox("НЕ ЗУПИНЯТИСЯ", value=self.persist_default, id="persist")
                    yield Static(
                        "ДЕМО · голосові контролі неактивні"
                        if self.preview_mode
                        else "F7 · запис до 12 с → перевір текст → Надіслати",
                        id="voice-status",
                        markup=False,
                    )
            with Vertical(id="right-rail"):
                with Vertical(id="companion"):
                    yield Static("COMPANION  /  F9", id="companion-title")
                    yield Static("B-12  ·  КІБЕРКІТ", id="companion-name")
                    yield CyberCat(id="pet")
                    yield Static("мишка · клік · Ctrl+K · F9", id="pet-hint")
                    yield Static("HOOKS / очікую подій", id="activity-status", markup=False)
                with VerticalScroll(id="panel"):
                    yield Static("ГОЛОС" + (" / ДЕМО" if self.preview_mode else ""), classes="head")
                    yield Checkbox(
                        "ОЗВУЧУВАТИ", value=False, id="spoken", disabled=self.preview_mode
                    )
                    with Horizontal(id="audio-buttons"):
                        yield Button("СТАН МІКР.", id="mic-mute", disabled=self.preview_mode)
                        yield Button("■ СТОП / F6", id="stop-audio", disabled=self.preview_mode)
                    yield Static(
                        "АКТИВНІСТЬ АГЕНТІВ" + (" / ДЕМО" if self.preview_mode else ""),
                        classes="head",
                    )
                    yield Static("Лише локальні metadata", id="activity-report", markup=False)
                    with VerticalScroll(id="activity-timeline"):
                        yield Static("Немає подій", id="activity-lines", markup=False)
                    yield Button("ОЧИСТИТИ ACTIVITY", id="clear-activity")
                    yield Static("ПІДТВЕРДЖЕННЯ", classes="head")
                    yield Vertical(id="approvals")
                    yield Static("ПАМ'ЯТЬ", classes="head")
                    yield Input(placeholder="пошук у пам'яті", id="mem-query")
                    yield Vertical(id="memories")
        yield Footer()

    async def check_link(self) -> None:
        connected = await self.client.health()
        header = self.query_one(NeonHeader)
        if header.connected != connected:
            header.set_connected(connected)
            if not connected:
                self._pet_phase("error")

    async def on_mount(self) -> None:
        self._sync_layout(self.size.width, self.size.height)
        me = await self.client.me()
        self.query_one(NeonHeader).set_connected(True)
        self.set_interval(5, self.check_link)  # the indicator follows the server, even when idle
        self.query_one("#consent", Checkbox).value = bool(me.get("consent"))
        for box in self.query(Checkbox):
            box.label = _switch_label(box.id, box.value)
        await self.load_sessions()
        await self.refresh_approvals()
        await self.refresh_memories()
        if self._activity_store is not None:
            try:
                events = await asyncio.to_thread(self._activity_store.recent, 100)
                self._accept_activity(events, initial=True)
            except Exception:
                self._activity_notice = "Activity тимчасово недоступна"
        self._render_activity()
        self.set_interval(1.0, self._tick_ui)
        self.query_one("#prompt", Input).focus()

    async def on_unmount(self) -> None:
        self._closing = True
        if self._mute_task is not None:
            self._mute_task.cancel()
            await asyncio.gather(self._mute_task, return_exceptions=True)
        await self._cancel_capture()
        await self._stop_speech()
        if self._activity_task is not None:
            self._activity_task.cancel()
            await asyncio.gather(self._activity_task, return_exceptions=True)

    def _sync_layout(self, width: int, height: int):
        self.screen.set_class(width < 110, "compact-nav")
        self.screen.set_class(width < 90, "narrow")
        self.screen.set_class(height < 30, "short")
        for button in self.query("#send"):
            button.label = "↑" if width < 90 else "НАДІСЛАТИ"
        for button in self.query("#ptt"):
            if self._record_started is None:
                button.label = "🎙" if width < 90 else "🎙 F7"
        for label in self.query("#compose-label"):
            label.update(
                "F2 — розмови  /  Enter — надіслати"
                if width < 110
                else "ТВОЯ ДУМКА  /  Enter — надіслати"
            )

    def on_resize(self, event: events.Resize):
        self._sync_layout(event.size.width, event.size.height)

    def on_mouse_move(self, event: events.MouseMove):
        for pet in self.query(CyberCat):
            pet.track_pointer(event.screen_x, event.screen_y)

    def _pet_phase(self, phase: str, detail: str = ""):
        for pet in self.query(CyberCat):
            pet.set_phase(phase, detail)

    def action_pet(self):
        self.query_one(CyberCat).pat()

    def action_toggle_motion(self):
        pet = self.query_one(CyberCat)
        pet.motion = not pet.motion
        self.query_one("#pet-hint", Static).update(
            "рух увімкнено · F8" if pet.motion else "анімації на паузі · F8"
        )
        pet.refresh()

    def action_toggle_nav(self):
        self.screen.toggle_class("nav-open" if self.size.width < 110 else "nav-hidden")

    async def action_cycle_skin(self) -> None:
        pet = self.query_one(CyberCat)
        options = await asyncio.to_thread(pet.available_skins)
        if len(options) < 2:
            if pet.skin_id != "cybercat":
                had_error = bool(pet.skin_error)
                pet.set_skin("cybercat")
                self.query_one("#companion-name", Static).update(f"B-12  ·  {pet.skin_name}")
                self.query_one("#pet-hint", Static).update(
                    "Pack пошкоджений · повернувся кіберкіт"
                    if had_error
                    else "Pack недоступний · повернувся кіберкіт"
                )
                return
            message = (
                "Pack пошкоджений · перевір manifest"
                if pet.skin_error
                else "Capri: додай дозволений pack"
            )
            self.query_one("#pet-hint", Static).update(message)
            return
        ids = [option.id for option in options]
        position = ids.index(pet.skin_id) if pet.skin_id in ids else 0
        selected = pet.set_skin(ids[(position + 1) % len(ids)])
        self.query_one("#companion-name", Static).update(f"B-12  ·  {pet.skin_name}")
        self.query_one("#pet-hint", Static).update(
            "мишка · клік · Ctrl+K · F9" if selected else "Pack недоступний · кіберкіт поруч"
        )

    # ---- local activity -----------------------------------------------------
    def _presentation_busy(self) -> bool:
        draft = any(widget.value.strip() for widget in self.query("#prompt"))
        return bool(
            self.turn
            or self._stream_active
            or self.waiting_turn
            or draft
            or self._record_started is not None
            or (self._ptt_task is not None and not self._ptt_task.done())
            or (self._speech_task is not None and not self._speech_task.done())
        )

    def _tick_ui(self) -> None:
        if self._closing:
            return
        if self._activity_store is not None and self._activity_task is None:
            self._activity_task = asyncio.create_task(self._poll_activity())
        self._render_activity()
        if self.turn is not None:
            label = (
                "скасовується"
                if self.turn.turn_id in self._cancel_requested_turns
                else "очікує дозволу"
                if self.waiting_turn
                else "працює"
            )
            self.query_one("#turn-report", Static).update(self.turn.report(label))
        elif self.paused_turn is not None and self.waiting_turn is not None:
            self.query_one("#turn-report", Static).update(self.paused_turn.report("очікує дозволу"))
        if self._record_started is not None:
            seconds = min(MAX_RECORD_SECONDS, time.monotonic() - self._record_started)
            self._set_voice_status(f"● ЗАПИС {seconds:.0f}/12 с · F7 — завершити", recording=True)
            if self._recorder is not None and not self._recorder.recording:
                self.action_ptt()
        if self._external_live and self._activity and not self._presentation_busy():
            latest = self._activity[-1]
            age = max(0.0, time.time() - latest["timestamp"])
            if latest["kind"] not in ("turn_completed", "session_ended") and 15 <= age < 300:
                approval = latest["kind"] == "approval_requested"
                phase = "approval" if approval else "thinking"
                waiting = "Чекаю дозволу" if approval else "Чекаю події"
                self._pet_phase(phase, f"{waiting} · {_duration(age)}")
            elif age >= 300:
                self._external_live = False
                self._pet_phase("idle")

    async def _poll_activity(self) -> None:
        try:
            if self._activity_lock.locked() or self._activity_store is None:
                return
            async with self._activity_lock:
                events = await asyncio.to_thread(
                    self._activity_store.after, self._activity_cursor, 100
                )
                if not self._closing:
                    self._accept_activity(events)
        except Exception:
            self._activity_notice = "Activity тимчасово недоступна"
        finally:
            self._activity_task = None

    def _accept_activity(self, events: list[dict], *, initial: bool = False) -> None:
        if events:
            self._activity_notice = ""
        for event in events:
            if event["seq"] <= self._activity_cursor:
                continue
            self._activity.append(event)
            self._activity_cursor = event["seq"]
        if events and not initial and not self._presentation_busy():
            latest = events[-1]
            phase = {
                "session_started": "thinking",
                "prompt_submitted": "thinking",
                "model_completed": "thinking",
                "tool_started": "working",
                "tool_completed": "working",
                "approval_requested": "approval",
                "notification": "thinking",
                "tool_failed": "error",
                "turn_completed": "success",
                "session_ended": "success",
            }.get(latest["kind"], "idle")
            self._external_live = True
            detail = latest["tool"] or _ACTIVITY_NAMES.get(latest["kind"], "Подія агента")
            self._pet_phase(phase, f"{latest['source']} · {detail}")
        self._render_activity()
        if events:
            self.query_one("#activity-timeline", VerticalScroll).scroll_end(animate=False)

    def _render_activity(self) -> None:
        if self._closing:
            return
        prefix = "ДЕМО / " if self.preview_mode else ""
        if not self._activity:
            status = "HOOKS / очікую подій" if self._activity_store else "HOOKS / немає подій"
            self.query_one("#activity-status", Static).update(prefix + status)
            self.query_one("#activity-lines", Static).update("Немає подій")
            self.query_one("#activity-report", Static).update(
                prefix + (self._activity_notice or "Лише локальні metadata · Ctrl+P")
            )
            return
        latest = self._activity[-1]
        age = _duration(max(0.0, time.time() - latest["timestamp"]))
        self.query_one("#activity-status", Static).update(
            f"{prefix}{latest['source']} · остання подія {age} тому"
        )
        lines = []
        for event in self._activity:
            stamp = time.strftime("%H:%M:%S", time.localtime(event["timestamp"]))
            label = _ACTIVITY_NAMES.get(event["kind"], "подія")
            detail = " · ".join(value for value in (event["project"], event["tool"]) if value)
            lines.append(f"{stamp} {event['source']}\n{label}" + (f" · {detail}" if detail else ""))
        demo = "ДЕМО — синтетичні metadata\n\n" if self.preview_mode else ""
        self.query_one("#activity-lines", Static).update(demo + "\n\n".join(lines))
        group = [
            event
            for event in self._activity
            if event["source"] == latest["source"] and event["task_id"] == latest["task_id"]
        ]
        starts = sum(event["kind"] == "tool_started" for event in group)
        results = sum(event["kind"] in ("tool_completed", "tool_failed") for event in group)
        approvals = sum(event["kind"] == "approval_requested" for event in group)
        failures = sum(event["kind"] == "tool_failed" for event in group)
        interval = _duration(max(0.0, group[-1]["timestamp"] - group[0]["timestamp"]))
        terminal = latest["kind"] in ("turn_completed", "session_ended")
        boundary = "завершення повідомлено" if terminal else "завершення не повідомлено"
        self.query_one("#activity-report", Static).update(
            f"{prefix}Спостережене вікно {interval}\n"
            f"Стартів інстр. {starts} · результатів {results}\n"
            f"Дозволів {approvals} · збоїв {failures}\n{boundary}"
            + (f"\n{self._activity_notice}" if self._activity_notice else "")
        )

    async def clear_activity(self) -> None:
        async with self._activity_lock:
            if self._activity_store is not None:
                try:
                    await asyncio.to_thread(self._activity_store.clear)
                except Exception:
                    self._activity_notice = "Не вдалося очистити activity. Спробуй ще раз."
                    self._render_activity()
                    return
            self._activity.clear()
            self._activity_notice = "Activity очищено" if not self.preview_mode else "Демо очищено"
            self._external_live = False
            self._render_activity()

    # ---- explicit audio -----------------------------------------------------
    def _set_voice_status(self, text: str, *, recording: bool = False) -> None:
        if self._closing:
            return
        for widget in self.query("#voice-status"):
            widget.update(text)
            widget.set_class(recording, "recording")

    def _sync_audio_controls(self) -> None:
        if self._closing:
            return
        recording = self._record_started is not None
        for button in self.query("#ptt"):
            button.label = "■ F7" if recording else ("🎙" if self.size.width < 90 else "🎙 F7")
            button.set_class(recording, "recording")
            button.disabled = (
                self.preview_mode
                or bool(self._ptt_task is not None and not self._ptt_task.done() and not recording)
                or bool(self._mute_task is not None and not self._mute_task.done())
            )
        label = (
            "СТАН МІКР."
            if self._mic_muted is None
            else ("УВІМК. 🎙" if self._mic_muted else "ВИМК. 🎙")
        )
        for button in self.query("#mic-mute"):
            button.label = label

    def action_ptt(self) -> None:
        if self.preview_mode:
            self._set_voice_status("ДЕМО · мікрофон не запускається")
            return
        if self._ptt_task is not None and not self._ptt_task.done():
            return
        if self._mute_task is not None and not self._mute_task.done():
            return
        self._ptt_task = asyncio.create_task(self._toggle_ptt())
        self._sync_audio_controls()

    def _auto_stop_ptt(self, generation: int) -> None:
        if generation == self._ptt_generation and self._recorder and self._recorder.has_recording:
            self.action_ptt()

    def _stop_record_timer(self) -> None:
        if self._record_timer is not None:
            self._record_timer.stop()
            self._record_timer = None

    async def _toggle_ptt(self) -> None:
        generation = self._ptt_generation
        pcm = b""
        try:
            if generation != self._ptt_generation or self._closing:
                return
            if self._recorder is not None and self._recorder.has_recording:
                async with self._capture_lock:
                    if generation != self._ptt_generation or self._closing:
                        return
                    self._stop_record_timer()
                    self._record_started = None
                    pcm = await self._recorder.stop()
                    self._sync_audio_controls()
            else:
                _, stop_error = await self._stop_speech()
                if stop_error is not None:
                    raise stop_error
                self._set_voice_status("Перевіряю стан мікрофона…")
                status_task = asyncio.create_task(self.client.voice_status())
                self._voice_status_task = status_task
                try:
                    status = await status_task
                finally:
                    if self._voice_status_task is status_task:
                        self._voice_status_task = None
                if generation != self._ptt_generation or self._closing:
                    return
                self._mic_muted = bool(status.get("muted", True))
                if self._mic_muted:
                    raise VoiceError("microphone_muted")
                async with self._capture_lock:
                    if generation != self._ptt_generation or self._closing:
                        return
                    self._recorder = self._recorder or PttRecorder()
                    await self._recorder.start()
                    if generation != self._ptt_generation or self._closing:
                        await self._recorder.cancel()
                        return
                    self._external_live = False
                    self._record_started = time.monotonic()
                    self._record_timer = self.set_timer(
                        MAX_RECORD_SECONDS, lambda: self._auto_stop_ptt(generation)
                    )
                    self._set_voice_status("● ЗАПИС 0/12 с · F7 — завершити", recording=True)
                    if self.turn is None and self.waiting_turn is None:
                        self._pet_phase("typing", "Слухаю · запис до 12 секунд")
                    return
            if generation != self._ptt_generation or self._closing:
                return
            self._set_voice_status("Розпізнаю… текст з'явиться для перевірки")
            self._asr_task = asyncio.create_task(self.client.voice_asr(pcm))
            result = await self._asr_task
            if generation != self._ptt_generation or self._closing:
                return
            transcript = result.get("text")
            if not isinstance(transcript, str) or not transcript.strip():
                raise VoiceError("transcript_empty")
            prompt = self.query_one("#prompt", Input)
            parts = (prompt.value.rstrip(), transcript.strip())
            prompt.value = " ".join(part for part in parts if part)
            prompt.focus()
            self._set_voice_status("Текст у полі вводу · перевір і натисни Надіслати")
            if self.turn is None and self.waiting_turn is None:
                self._pet_phase("typing")
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self._set_voice_status(_voice_message(error))
        finally:
            pcm = b""
            self._asr_task = None
            self._ptt_task = None
            self._sync_audio_controls()

    async def _cancel_capture(self) -> VoiceError | None:
        self._ptt_generation += 1
        self._stop_record_timer()
        failure = None
        if self._voice_status_task is not None:
            self._voice_status_task.cancel()
        if self._asr_task is not None:
            self._asr_task.cancel()
        async with self._capture_lock:
            if self._recorder is not None:
                try:
                    await self._recorder.cancel()
                except VoiceError as error:
                    failure = error
                    self._set_voice_status(_voice_message(error))
            self._record_started = None
        task = self._ptt_task
        if task is not None and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)
        self._sync_audio_controls()
        return failure

    def action_toggle_mute(self) -> None:
        if self.preview_mode:
            self._set_voice_status("ДЕМО · стан мікрофона не змінюється")
            return
        if self._mute_task is None or self._mute_task.done():
            target = None if self._mic_muted is None else not self._mic_muted
            self._mute_task = asyncio.create_task(self._toggle_mute(target))
            self._sync_audio_controls()

    async def _toggle_mute(self, target: bool | None) -> None:
        try:
            failure = await self._cancel_capture()
            if target is None:
                # An unknown-state button only reads status. Unmute needs a second,
                # explicitly labelled action, never an inferred startup default.
                status = await self.client.voice_status()
                self._mic_muted = bool(status.get("muted", True))
            else:
                result = await self.client.voice_mute(target)
                self._mic_muted = bool(result.get("muted", target))
            message = "Мікрофон вимкнено" if self._mic_muted else "Мікрофон увімкнено · F7 — запис"
            if failure is not None:
                message += " · " + _voice_message(failure)
            self._set_voice_status(message)
        except Exception as error:
            self._set_voice_status(_voice_message(error))
        finally:
            self._mute_task = None
            self._sync_audio_controls()

    async def _stop_speech(self) -> tuple[int, VoiceError | None]:
        self._speech_generation += 1
        generation = self._speech_generation
        failure = None
        task, self._speech_task = self._speech_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._player is not None:
            try:
                await self._player.stop()
            except VoiceError as error:
                failure = error
                self._set_voice_status(_voice_message(error))
        return generation, failure

    async def action_stop_audio(self) -> None:
        if self.preview_mode:
            self._set_voice_status("ДЕМО · відтворення не запускається")
            return
        _, failure = await self._stop_speech()
        if failure is None:
            self._set_voice_status("Озвучення зупинено · F7 — запис")

    async def _queue_speech(self, text: str) -> None:
        if self.preview_mode or not self.query_one("#spoken", Checkbox).value:
            return
        if self._record_started is not None or (
            self._ptt_task is not None and not self._ptt_task.done()
        ):
            return  # Keep response audio out of an explicit microphone capture/ASR.
        generation, stop_error = await self._stop_speech()
        if (
            stop_error is not None
            or generation != self._speech_generation
            or self._closing
            or not self.query_one("#spoken", Checkbox).value
        ):
            return
        self._speech_task = asyncio.create_task(self._speak_reply(text, generation))

    async def _speak_reply(self, text: str, generation: int) -> None:
        try:
            for chunk in _speech_chunks(text):
                if (
                    generation != self._speech_generation
                    or self._closing
                    or not self.query_one("#spoken", Checkbox).value
                ):
                    return
                self._set_voice_status("Готую озвучення… F6 — зупинити")
                wav = await self.client.voice_tts(chunk)
                if (
                    generation != self._speech_generation
                    or self._closing
                    or not self.query_one("#spoken", Checkbox).value
                ):
                    return
                self._player = self._player or VoicePlayer()
                self._set_voice_status("Озвучую відповідь… F6 — зупинити")
                if self.turn is None and self.waiting_turn is None:
                    self._pet_phase("speaking")
                await self._player.play(wav)
                wav = b""
            if generation == self._speech_generation:
                self._set_voice_status("Озвучення завершено · F7 — запис")
                if self.turn is None and self.waiting_turn is None:
                    self._pet_phase("success")
        except asyncio.CancelledError:
            pass
        except Exception as error:
            if generation == self._speech_generation:
                self._set_voice_status(_voice_message(error))
        finally:
            if self._speech_task is asyncio.current_task():
                self._speech_task = None

    # ---- sessions -----------------------------------------------------------
    async def load_sessions(self, preferred: str | None = None) -> None:
        sessions = await self.client.sessions()
        if not sessions:
            sessions = [await self.client.new_session()]
        self.current = preferred if preferred in sessions else sessions[-1]
        box = self.query_one("#sessions", Vertical)
        await box.remove_children()
        for number, session_id in enumerate(sessions, start=1):
            button = Button(f"розмова {number}", id=f"s-{session_id}")
            if session_id == self.current:
                button.add_class("current")
            await box.mount(button)
        await self.load_history()

    async def load_history(self) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.remove_children()
        history = await self.client.history(self.current)
        if not history:
            await chat.mount(Welcome(id="welcome"))
        for message in history:
            role = message.get("role")
            if role == "user":
                await self.add_user(message.get("content") or "")
            elif role == "assistant" and message.get("content"):
                await self.add_assistant(message["content"])
            elif role == "tool":
                await self.add_tool_from_history(message)
        self.call_after_refresh(chat.scroll_end, animate=False)

    async def action_new_session(self) -> None:
        if self._stream_active or self.waiting_turn is not None:
            return
        await self._cancel_capture()
        await self._stop_speech()
        session_id = await self.client.new_session()
        await self.load_sessions(session_id)
        self.query_one("#prompt", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "new":
            await self.action_new_session()
        elif button_id == "send":
            await self.submit_prompt()
        elif button_id == "ptt":
            self.action_ptt()
        elif button_id == "mic-mute":
            self.action_toggle_mute()
        elif button_id == "stop-audio":
            await self.action_stop_audio()
        elif button_id == "clear-activity":
            await self.clear_activity()
        elif button_id.startswith("s-"):
            if self._stream_active or self.waiting_turn is not None:
                return
            await self._cancel_capture()
            await self._stop_speech()
            await self.load_sessions(button_id[2:])
            self.screen.remove_class("nav-open")
            self.query_one("#prompt", Input).focus()
        elif button_id.startswith("ok-"):
            await self.decide(button_id[3:], True)
        elif button_id.startswith("no-"):
            await self.decide(button_id[3:], False)
        elif button_id.startswith("forget-"):
            await self.forget(button_id[7:])

    # ---- panel --------------------------------------------------------------
    def action_toggle_panel(self) -> None:
        panel = self.query_one("#panel")
        panel.toggle_class("open")
        self.query_one("#right-rail").set_class(panel.has_class("open"), "controls-open")

    async def refresh_approvals(self) -> None:
        box = self.query_one("#approvals", Vertical)
        await box.remove_children()
        items = await self.client.approvals()
        if items:
            self.query_one("#panel").add_class("open")
            self.query_one("#right-rail").add_class("controls-open")
        if not items:
            await box.mount(Static("нема дій, що очікують", classes="item"))
        for item in items:
            op = item["operation_id"]
            await box.mount(
                Static(escape(f"{item.get('name', 'дія')}  {op[:8]}"), classes="item"),
                Horizontal(Button("ДОЗВОЛИТИ", id=f"ok-{op}"), Button("ВІДХИЛИТИ", id=f"no-{op}")),
            )

    async def refresh_memories(self, query: str = "") -> None:
        box = self.query_one("#memories", Vertical)
        await box.remove_children()
        records = (
            await self.client.memory_search(query) if query else await self.client.memory_records()
        )
        if not records:
            await box.mount(Static("пам'ять порожня", classes="item"))
        for record in records[:60]:
            text = record.get("text", "")
            short = text if len(text) < 120 else text[:117] + "…"
            await box.mount(
                Static(escape(short), classes="item"),
                Button("ЗАБУТИ", id=f"forget-{record['id']}"),
            )

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "mem-query":
            await self.refresh_memories(event.value.strip())
        elif event.input.id == "prompt" and self.turn is None and self.waiting_turn is None:
            self._pet_phase("typing" if event.value.strip() else "idle")

    async def forget(self, memory_id: str) -> None:
        await self.client.memory_forget(memory_id)
        await self.refresh_memories(self.query_one("#mem-query", Input).value.strip())

    async def decide(self, operation_id: str, approve: bool) -> None:
        await self.client.decide(operation_id, approve)
        await self.refresh_approvals()
        turn_id, self.waiting_turn = self.waiting_turn, None
        if turn_id:
            self._pet_phase("thinking")
            if self._stream_active:
                self._resume_requested = turn_id
            else:
                self._stream_active = True
                self.stream_resume(turn_id)

    # ---- chat ---------------------------------------------------------------
    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        # The glyph is the same for both states in this widget; the label says it in words.
        event.checkbox.label = _switch_label(event.checkbox.id, event.value)
        if event.checkbox.id == "consent":
            await self.client.set_consent(event.value)
        elif event.checkbox.id == "spoken":
            if self.preview_mode and event.value:
                event.checkbox.value = False
            elif not event.value:
                await self.action_stop_audio()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt":
            await self.submit_prompt()

    async def submit_prompt(self) -> None:
        prompt = self.query_one("#prompt", Input)
        text = prompt.value.strip()
        if not text or self.turn is not None or self.waiting_turn is not None:
            return
        await self._stop_speech()
        self._external_live = False
        prompt.value = ""
        self.turn = Turn(session_id=self.current)
        self.paused_turn = None
        self._stream_active = True
        await self.add_user(text)
        self._pet_phase("thinking")
        self.stream_chat(text)

    @work(exclusive=False)
    async def stream_chat(self, text: str) -> None:
        persist = self.query_one("#persist", Checkbox).value
        try:
            stream = self.client.chat(self.current, text, persist=persist)
            await self.consume(stream)
        except httpx.HTTPError as error:
            if self.turn is not None:
                self.turn.failure_events += 1
                self.turn.state = "failed"
                self.query_one("#turn-report", Static).update(self.turn.report("зв'язок втрачено"))
            self.query_one(NeonHeader).set_connected(False)
            self._pet_phase("error")
            await self.add_state(f"СЕРВЕР НЕДОСТУПНИЙ: {escape(str(error))}")
        finally:
            await self._stream_finished()

    @work(exclusive=False)
    async def stream_resume(self, turn_id: str) -> None:
        self._stream_active = True
        self.turn = self.paused_turn or self.turn or Turn(session_id=self.current, turn_id=turn_id)
        self.paused_turn = None
        self.turn.shown = False
        self.turn.streamed = ""
        self.turn.state = "running"
        try:
            await self.consume(self.client.resume(turn_id))
        except httpx.HTTPError as error:
            if self.turn is not None:
                self.turn.failure_events += 1
                self.turn.state = "failed"
                self.query_one("#turn-report", Static).update(self.turn.report("зв'язок втрачено"))
            self._pet_phase("error")
            await self.add_state(f"СЕРВЕР НЕДОСТУПНИЙ: {escape(str(error))}")
        finally:
            await self._stream_finished()

    async def _stream_finished(self):
        if self.turn is not None:
            turn_id = self.turn.turn_id
            cancel_requested = turn_id in self._cancel_requested_turns
            if self.turn.state == "awaiting_approval" and not cancel_requested:
                self.paused_turn = self.turn
            elif cancel_requested:
                if self.turn.state == "awaiting_approval":
                    self.turn.state = "cancelled"
                    report = self.turn.report("скасовано")
                    self.query_one("#turn-report", Static).update(report)
                    await self.add_turn_report(report)
                    await self.add_state("ХІД СКАСОВАНО")
                if self.waiting_turn == turn_id:
                    self.waiting_turn = None
                self._cancel_requested_turns.discard(turn_id)
        self.turn = None
        self._stream_active = False
        resume, self._resume_requested = self._resume_requested, None
        if self._closing:
            return
        if resume is not None:
            self._stream_active = True
            self.stream_resume(resume)
        try:
            await self.refresh_approvals()
        except httpx.HTTPError:
            self.query_one(NeonHeader).set_connected(False)
            self._pet_phase("error")

    async def consume(self, stream) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        md = None
        async for event in stream:
            if self.turn is None or self._closing:
                return
            self.turn.event_count += 1
            kind = event.get("type")
            if kind == "turn_started":
                self.query_one(NeonHeader).set_connected(True)
                self._pet_phase("thinking")
                self.turn.turn_id = event.get("turn_id")
            elif kind == "text_delta":
                self._pet_phase("speaking")
                if md is None:
                    md = await self.add_assistant("")
                    self.turn.streamed = ""
                self.turn.streamed += event.get("text", "")
                await md.update(self.turn.streamed)
                chat.scroll_end(animate=False)
            elif kind == "tool_started":
                self.turn.tool_calls.add(str(event["call_id"]))
                self._pet_phase("working", event.get("name", ""))
                md = None
                self.turn.streamed = ""
                self.turn.tools[event["call_id"]] = await self.add_tool(event)
            elif kind == "tool_result":
                if event.get("call_id"):
                    self.turn.tool_calls.add(str(event["call_id"]))
                if event.get("status") not in ("completed", "approval_pending"):
                    self.turn.failure_events += 1
                node = self.turn.tools.get(event.get("call_id"))
                if node is not None:
                    node.title = escape(f"$ {event.get('name')}  → {event.get('status')}")
            elif kind == "approval_pending":
                self.turn.approval_ids.add(
                    str(event.get("operation_id") or event.get("call_id") or self.turn.event_count)
                )
                if self.turn.turn_id in self._cancel_requested_turns:
                    self._pet_phase("cancelled")
                else:
                    self._pet_phase("approval")
                    self.waiting_turn = self.turn.turn_id
                    await self.add_state(f"ОЧІКУЄ ПІДТВЕРДЖЕННЯ: {event.get('name')}")
                    await self.refresh_approvals()
            elif kind == "result":
                if (
                    self.turn.turn_id in self._cancel_requested_turns
                    and event.get("state") == "awaiting_approval"
                ):
                    event = {**event, "state": "cancelled"}
                    if self.waiting_turn == self.turn.turn_id:
                        self.waiting_turn = None
                await self.finish(event)
            elif kind == "error":
                self.turn.failure_events += 1
                self._pet_phase("error")
                await self.add_state(f"ПОМИЛКА: {event.get('error')}")
            if kind != "result":
                label = (
                    "скасовується"
                    if self.turn.turn_id in self._cancel_requested_turns
                    else "очікує дозволу"
                    if self.waiting_turn
                    else "працює"
                )
                self.query_one("#turn-report", Static).update(self.turn.report(label))
            chat.scroll_end(animate=False)

    async def finish(self, result: dict) -> None:
        for outcome in result.get("tool_results") or []:
            node = self.turn.tools.get(outcome.get("call_id")) if self.turn else None
            if node is not None:
                node.query_one(Static).update(_pretty(outcome.get("content")))
        if result.get("content") and not (self.turn and self.turn.shown):
            await self.add_assistant(result["content"])
        state = result.get("state", "")
        if self.turn is not None:
            self.turn.state = state
            if state == "failed":
                self.turn.failure_events += 1
            report = self.turn.report(state)
            self.query_one("#turn-report", Static).update(report)
            await self.add_turn_report(report)
        self._pet_phase(
            {"completed": "success", "awaiting_approval": "approval", "cancelled": "cancelled"}.get(
                state, "error"
            )
        )
        if state != "completed":
            label = CHAT_INTENT.get(state, state.upper())
            reason = f" ({result['error_code']})" if result.get("error_code") else ""
            await self.add_state(f"{label}{reason}".strip())
        elif isinstance(result.get("content"), str) and result["content"].strip():
            await self._queue_speech(result["content"])

    async def action_cancel(self) -> None:
        await self._cancel_capture()
        await self._stop_speech()
        turn_id = self.turn.turn_id if self.turn is not None else None
        if turn_id is None:
            turn_id = (
                (self.paused_turn.turn_id or self.waiting_turn)
                if self.paused_turn is not None
                else self.waiting_turn
            )
        if turn_id:
            self._pet_phase("cancelled")
            await self.client.cancel(turn_id)
            active_turn = self.turn is not None and self.turn.turn_id == turn_id
            if self.turn is None and (
                self.paused_turn is not None or self.waiting_turn is not None
            ):
                paused = self.paused_turn
                self.waiting_turn = None
                self.paused_turn = None
                if paused is not None:
                    paused.state = "cancelled"
                    report = paused.report("скасовано")
                    self.query_one("#turn-report", Static).update(report)
                    await self.add_turn_report(report)
                await self.add_state("ХІД СКАСОВАНО")
                await self.refresh_approvals()
            elif active_turn:
                self._cancel_requested_turns.add(turn_id)
                if self.waiting_turn == turn_id:
                    self.waiting_turn = None

    # ---- widgets ------------------------------------------------------------
    async def add_user(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        for welcome in chat.query(Welcome):
            await welcome.remove()
        await chat.mount(Static(f"[ ТИ ]\n{escape(text)}", classes="msg-user"))
        chat.scroll_end(animate=False)

    async def add_assistant(self, text: str) -> Markdown:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(Static("◆ B-12   /   відповідь", classes="msg-tag", markup=False))
        md = Markdown(text)
        await chat.mount(md)
        if self.turn:
            self.turn.shown = True
        return md

    async def add_tool(self, event: dict) -> Collapsible:
        chat = self.query_one("#chat", VerticalScroll)
        summary = _summary(event.get("arguments") or {})
        node = Collapsible(
            Static(_pretty(event.get("arguments"))),
            title=escape(f"$ {event.get('name')}  {summary}".rstrip()),
            collapsed=True,
        )
        await chat.mount(node)
        return node

    async def add_tool_from_history(self, message: dict) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        try:
            outcome = json.loads(message.get("content") or "{}")
        except ValueError:
            outcome = {}
        status = outcome.get("status", "completed")
        await chat.mount(
            Collapsible(
                Static(_pretty(outcome.get("content"))),
                title=escape(f"$ {message.get('tool_name')}  → {status}"),
                collapsed=True,
            )
        )

    async def add_state(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(Static(escape(text), classes="msg-state"))

    async def add_turn_report(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(Static(text, classes="turn-summary", markup=False))


_ACTIVITY_NAMES = {
    "session_started": "сесію відкрито",
    "prompt_submitted": "почато хід",
    "model_completed": "виклик моделі завершено",
    "tool_started": "інструмент почав роботу",
    "tool_completed": "результат інструмента",
    "tool_failed": "збій інструмента",
    "approval_requested": "очікує дозволу",
    "notification": "повідомлення агента",
    "turn_completed": "хід завершено",
    "session_ended": "сесію закрито",
}

_SWITCH_NAMES = {"consent": "ПАМ'ЯТЬ", "persist": "НЕ ЗУПИНЯТИСЯ", "spoken": "ОЗВУЧУВАТИ"}


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total} с"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} хв {seconds:02} с"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} год {minutes:02} хв"


def _voice_message(error: Exception) -> str:
    if not isinstance(error, VoiceError):
        return "Голосовий API недоступний або відхилив дію. Перевір сервер і mute."
    messages = {
        "microphone_muted": "Мікрофон вимкнений · Ctrl+P → МІКР. для явного увімкнення",
        "audio_capture_unavailable": "Для запису потрібен pw-record або arecord",
        "audio_playback_unavailable": "Для звуку потрібен pw-play або aplay",
        "audio_capture_empty": "Запис порожній · спробуй ще раз",
        "audio_capture_failed": "Не вдалося записати мікрофон",
        "transcript_empty": "Мовлення не розпізнано · спробуй ще раз",
        "speech_word_too_long": "Озвучення зупинено: фрагмент без пробілів перевищує 4000 символів",
    }
    return messages.get(error.code, f"Голосова дія не виконана ({error.code})")


def _speech_chunks(text: str, limit: int = 4000):
    """Speak the entire reply in bounded requests, splitting only between words."""
    remaining = text.strip()
    while len(remaining) > limit:
        head = remaining[: limit + 1]
        split = max(head.rfind(". ") + 1, head.rfind("! ") + 1, head.rfind("? ") + 1)
        split = max(split, head.rfind("\n"))
        if split < limit // 2:
            split = max(head.rfind(" "), head.rfind("\t"))
        if split <= 0:
            raise VoiceError("speech_word_too_long")
        yield remaining[:split].strip()
        remaining = remaining[split:].lstrip()
    if remaining:
        yield remaining


def _switch_label(switch_id: str | None, value: bool) -> str:
    name = _SWITCH_NAMES.get(switch_id or "", switch_id or "")
    return f"{name}: {'ВКЛ' if value else 'ВИМК'}"


def _summary(arguments: dict) -> str:
    for key in ("path", "command", "executable", "query", "url", "memory_id", "text"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            flat = " ".join(value.split())
            return flat if len(flat) <= 60 else flat[:59] + "…"
    return ""


def _pretty(value) -> str:
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return escape(value["text"])
    return escape(json.dumps(value, ensure_ascii=False, indent=2) if value is not None else "")
