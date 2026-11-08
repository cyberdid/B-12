"""B-12 terminal UI: sessions, conversation, approvals and memory in one console.

Neon conversation workspace with an animated local cybercat companion. The app talks
only to the loopback API; pet interactions never invoke a model or tool.
"""

import json
from dataclasses import dataclass, field

import httpx
from rich.markup import escape
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Collapsible, Footer, Input, Markdown, Static

from b12.tui.chrome import NeonHeader, Welcome
from b12.tui.client import ApiClient
from b12.tui.pet import CyberCat
from b12.tui.theme import CSS

CHAT_INTENT = {"completed": "", "failed": "ПОМИЛКА", "cancelled": "СКАСОВАНО"}


@dataclass
class Turn:
    session_id: str
    turn_id: str | None = None
    tools: dict = field(default_factory=dict)
    streamed: str = ""
    shown: bool = False


class B12App(App):
    CSS = CSS
    TITLE = "Capri"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+n", "new_session", "Нова розмова"),
        Binding("ctrl+p", "toggle_panel", "Панель"),
        Binding("escape", "cancel", "Зупинити"),
        Binding("ctrl+k", "pet", "Погладити", priority=True),
        Binding("f2", "toggle_nav", "Розмови", show=False),
        Binding("f8", "toggle_motion", "Анімації"),
        Binding("ctrl+q", "quit", "Вихід"),
    ]

    def __init__(self, client: ApiClient, persist_default: bool = False):
        super().__init__()
        self.client = client
        self.current: str | None = None
        self.turn: Turn | None = None
        self.waiting_turn: str | None = None  # a turn paused for an owner decision
        self.persist_default = persist_default

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
                    yield Static("ЗВ’ЯЗОК ІЗ CAPRI", id="chat-title")
                    yield Static("// CHAT", id="channel-tag")
                yield VerticalScroll(id="chat")
                with Vertical(id="bar"):
                    yield Static("ТВОЯ ДУМКА  /  Enter — надіслати", id="compose-label")
                    with Horizontal(id="compose-line"):
                        yield Input(placeholder="Напиши Capri…", id="prompt")
                        yield Button("НАДІСЛАТИ", id="send")
                    with Horizontal(id="compose-options"):
                        yield Checkbox("ПАМ'ЯТЬ", value=True, id="consent")
                        yield Checkbox("НЕ ЗУПИНЯТИСЯ", value=self.persist_default, id="persist")
            with Vertical(id="right-rail"):
                with Vertical(id="companion"):
                    yield Static("COMPANION  /  01", id="companion-title")
                    yield Static("CAPRI  ·  КІБЕРКІТ", id="companion-name")
                    yield CyberCat(id="pet")
                    yield Static("мишка · клік · Ctrl+K", id="pet-hint")
                with VerticalScroll(id="panel"):
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
        self.query_one("#prompt", Input).focus()

    def _sync_layout(self, width: int, height: int):
        self.screen.set_class(width < 110, "compact-nav")
        self.screen.set_class(width < 90, "narrow")
        self.screen.set_class(height < 30, "short")
        for button in self.query("#send"):
            button.label = "↑" if width < 90 else "НАДІСЛАТИ"
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
        session_id = await self.client.new_session()
        await self.load_sessions(session_id)
        self.query_one("#prompt", Input).focus()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "new":
            await self.action_new_session()
        elif button_id == "send":
            await self.submit_prompt()
        elif button_id.startswith("s-"):
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
            self.stream_resume(turn_id)

    # ---- chat ---------------------------------------------------------------
    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        # The glyph is the same for both states in this widget; the label says it in words.
        event.checkbox.label = _switch_label(event.checkbox.id, event.value)
        if event.checkbox.id == "consent":
            await self.client.set_consent(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "prompt":
            await self.submit_prompt()

    async def submit_prompt(self) -> None:
        prompt = self.query_one("#prompt", Input)
        text = prompt.value.strip()
        if not text or self.turn is not None or self.waiting_turn is not None:
            return
        prompt.value = ""
        await self.add_user(text)
        self.turn = Turn(session_id=self.current)
        self._pet_phase("thinking")
        self.stream_chat(text)

    @work(exclusive=False)
    async def stream_chat(self, text: str) -> None:
        persist = self.query_one("#persist", Checkbox).value
        try:
            stream = self.client.chat(self.current, text, persist=persist)
            await self.consume(stream)
        except httpx.HTTPError as error:
            self.query_one(NeonHeader).set_connected(False)
            self._pet_phase("error")
            await self.add_state(f"СЕРВЕР НЕДОСТУПНИЙ: {escape(str(error))}")
        finally:
            await self._stream_finished()

    @work(exclusive=False)
    async def stream_resume(self, turn_id: str) -> None:
        self.turn = self.turn or Turn(session_id=self.current, turn_id=turn_id)
        try:
            await self.consume(self.client.resume(turn_id))
        except httpx.HTTPError as error:
            self._pet_phase("error")
            await self.add_state(f"СЕРВЕР НЕДОСТУПНИЙ: {escape(str(error))}")
        finally:
            await self._stream_finished()

    async def _stream_finished(self):
        self.turn = None
        try:
            await self.refresh_approvals()
        except httpx.HTTPError:
            self.query_one(NeonHeader).set_connected(False)
            self._pet_phase("error")

    async def consume(self, stream) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        md = None
        async for event in stream:
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
                self._pet_phase("working", event.get("name", ""))
                md = None
                self.turn.streamed = ""
                self.turn.tools[event["call_id"]] = await self.add_tool(event)
            elif kind == "tool_result":
                node = self.turn.tools.get(event.get("call_id"))
                if node is not None:
                    node.title = escape(f"$ {event.get('name')}  → {event.get('status')}")
            elif kind == "approval_pending":
                self._pet_phase("approval")
                self.waiting_turn = self.turn.turn_id
                await self.add_state(f"ОЧІКУЄ ПІДТВЕРДЖЕННЯ: {event.get('name')}")
                await self.refresh_approvals()
            elif kind == "result":
                await self.finish(event)
            elif kind == "error":
                self._pet_phase("error")
                await self.add_state(f"ПОМИЛКА: {event.get('error')}")
            chat.scroll_end(animate=False)

    async def finish(self, result: dict) -> None:
        for outcome in result.get("tool_results") or []:
            node = self.turn.tools.get(outcome.get("call_id")) if self.turn else None
            if node is not None:
                node.query_one(Static).update(_pretty(outcome.get("content")))
        if result.get("content") and not (self.turn and self.turn.shown):
            await self.add_assistant(result["content"])
        state = result.get("state", "")
        self._pet_phase(
            {"completed": "success", "awaiting_approval": "approval", "cancelled": "cancelled"}.get(
                state, "error"
            )
        )
        if state != "completed":
            label = CHAT_INTENT.get(state, state.upper())
            reason = f" ({result['error_code']})" if result.get("error_code") else ""
            await self.add_state(f"{label}{reason}".strip())

    async def action_cancel(self) -> None:
        if self.turn and self.turn.turn_id:
            self._pet_phase("cancelled")
            await self.client.cancel(self.turn.turn_id)

    # ---- widgets ------------------------------------------------------------
    async def add_user(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        for welcome in chat.query(Welcome):
            await welcome.remove()
        await chat.mount(Static(f"[ ТИ ]\n{escape(text)}", classes="msg-user"))
        chat.scroll_end(animate=False)

    async def add_assistant(self, text: str) -> Markdown:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(Static("◆ CAPRI   /   відповідь", classes="msg-tag", markup=False))
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


_SWITCH_NAMES = {"consent": "ПАМ'ЯТЬ", "persist": "НЕ ЗУПИНЯТИСЯ"}


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
