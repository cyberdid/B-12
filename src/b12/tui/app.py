# ruff: noqa: E501  (the CSS block below is one rule per line on purpose)
"""B-12 terminal UI: sessions, conversation, approvals and memory in one console.

Design: a monospace console with square frames, role tags and inverse video for the selected
session. Colors are fixed (dark terminal). The app talks only to the loopback API.
"""

import json
from dataclasses import dataclass, field

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Collapsible, Input, Markdown, Static

from b12.tui.client import ApiClient

CSS = """
Screen { background: #07090d; color: #cdeee9; }
#top { height: 1; background: #07090d; color: #5f7f7b; padding: 0 1; }
#main { height: 1fr; }
#sidebar { width: 26; border-right: solid #173338; padding: 0 1; background: #090d12; }
#sidebar Static.head { color: #5f7f7b; margin-top: 1; }
#sidebar Button { width: 100%; margin: 0; min-width: 0; height: 1; border: none; background: transparent; color: #cdeee9; text-align: left; }
#sidebar Button.current { background: #00e5ff; color: #04161a; }
#sidebar Button#new { background: transparent; color: #00e5ff; margin-bottom: 1; }
#chat { width: 1fr; padding: 0 2; }
.msg-user { color: #ff3c9e; margin: 1 0 0 0; }
.msg-tag { color: #00e5ff; margin-top: 1; }
.msg-state { color: #ffcc33; }
Markdown { margin: 0; padding: 0; background: #07090d; }
Collapsible { margin: 0 0 0 2; padding: 0; border-top: none; border-bottom: none; background: #07090d; }
CollapsibleTitle { color: #5f7f7b; background: #07090d; }
#panel { width: 40; border-left: solid #173338; padding: 0 1; background: #090d12; display: none; }
#panel.open { display: block; }
#panel Static.head { color: #ff3c9e; margin-top: 1; }
.item { color: #cdeee9; margin: 0 0 1 0; }
.item Button { min-width: 8; height: 1; margin-right: 1; border: none; }
#bar { height: 3; dock: bottom; border-top: solid #173338; padding: 0 1; background: #090d12; }
#bar Checkbox { width: auto; margin-right: 2; color: #5f7f7b; background: transparent; border: none; }
#prompt { width: 1fr; border: solid #173338; background: #07090d; color: #cdeee9; }
#prompt:focus { border: solid #00e5ff; }
#send { min-width: 10; border: none; background: #ff3c9e; color: #0a0309; }
"""

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
    TITLE = "B-12"
    BINDINGS = [
        Binding("ctrl+n", "new_session", "Нова розмова"),
        Binding("ctrl+p", "toggle_panel", "Панель"),
        Binding("escape", "cancel", "Зупинити"),
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
        yield Static("// B-12 · термінал", id="top")
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Button("+ нова розмова", id="new")
                yield Static("СЕСІЇ", classes="head")
                yield Vertical(id="sessions")
            yield VerticalScroll(id="chat")
            with Vertical(id="panel"):
                yield Static("ПІДТВЕРДЖЕННЯ", classes="head")
                yield Vertical(id="approvals")
                yield Static("ПАМ'ЯТЬ", classes="head")
                yield Input(placeholder="пошук у пам'яті", id="mem-query")
                yield Vertical(id="memories")
        with Horizontal(id="bar"):
            yield Checkbox("ПАМ'ЯТЬ", value=True, id="consent")
            yield Checkbox("НЕ ЗУПИНЯТИСЯ", value=self.persist_default, id="persist")
            yield Input(placeholder="напишіть повідомлення і натисніть Enter", id="prompt")
            yield Button("НАДІСЛАТИ", id="send")

    async def on_mount(self) -> None:
        me = await self.client.me()
        self.query_one("#consent", Checkbox).value = bool(me.get("consent"))
        await self.load_sessions()
        await self.refresh_approvals()
        await self.refresh_memories()
        self.query_one("#prompt", Input).focus()

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
        for message in await self.client.history(self.current):
            role = message.get("role")
            if role == "user":
                await self.add_user(message.get("content") or "")
            elif role == "assistant" and message.get("content"):
                await self.add_assistant(message["content"])
            elif role == "tool":
                await self.add_tool_from_history(message)
        chat.scroll_end(animate=False)

    async def action_new_session(self) -> None:
        session_id = await self.client.new_session()
        await self.load_sessions(session_id)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "new":
            await self.action_new_session()
        elif button_id == "send":
            await self.submit_prompt()
        elif button_id.startswith("s-"):
            await self.load_sessions(button_id[2:])
        elif button_id.startswith("ok-"):
            await self.decide(button_id[3:], True)
        elif button_id.startswith("no-"):
            await self.decide(button_id[3:], False)
        elif button_id.startswith("forget-"):
            await self.forget(button_id[7:])

    # ---- panel --------------------------------------------------------------
    def action_toggle_panel(self) -> None:
        self.query_one("#panel").toggle_class("open")

    async def refresh_approvals(self) -> None:
        box = self.query_one("#approvals", Vertical)
        await box.remove_children()
        items = await self.client.approvals()
        if items:
            self.query_one("#panel").add_class("open")
        if not items:
            await box.mount(Static("нема дій, що очікують", classes="item"))
        for item in items:
            op = item["operation_id"]
            await box.mount(
                Static(f"{item.get('name', 'дія')}  {op[:8]}", classes="item"),
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

    async def forget(self, memory_id: str) -> None:
        await self.client.memory_forget(memory_id)
        await self.refresh_memories(self.query_one("#mem-query", Input).value.strip())

    async def decide(self, operation_id: str, approve: bool) -> None:
        await self.client.decide(operation_id, approve)
        await self.refresh_approvals()
        turn_id, self.waiting_turn = self.waiting_turn, None
        if turn_id:
            self.stream_resume(turn_id)

    # ---- chat ---------------------------------------------------------------
    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
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
        self.stream_chat(text)

    @work(exclusive=False)
    async def stream_chat(self, text: str) -> None:
        persist = self.query_one("#persist", Checkbox).value
        try:
            stream = self.client.chat(self.current, text, persist=persist)
            await self.consume(stream)
        finally:
            self.turn = None
            await self.refresh_approvals()

    @work(exclusive=False)
    async def stream_resume(self, turn_id: str) -> None:
        self.turn = self.turn or Turn(session_id=self.current, turn_id=turn_id)
        try:
            await self.consume(self.client.resume(turn_id))
        finally:
            self.turn = None
            await self.refresh_approvals()

    async def consume(self, stream) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        md = None
        async for event in stream:
            kind = event.get("type")
            if kind == "turn_started":
                self.turn.turn_id = event.get("turn_id")
            elif kind == "text_delta":
                if md is None:
                    md = await self.add_assistant("")
                    self.turn.streamed = ""
                self.turn.streamed += event.get("text", "")
                await md.update(self.turn.streamed)
                chat.scroll_end(animate=False)
            elif kind == "tool_started":
                md = None
                self.turn.streamed = ""
                self.turn.tools[event["call_id"]] = await self.add_tool(event)
            elif kind == "tool_result":
                node = self.turn.tools.get(event.get("call_id"))
                if node is not None:
                    node.title = f"$ {event.get('name')}  → {event.get('status')}"
            elif kind == "approval_pending":
                self.waiting_turn = self.turn.turn_id
                await self.add_state(f"ОЧІКУЄ ПІДТВЕРДЖЕННЯ: {event.get('name')}")
                await self.refresh_approvals()
            elif kind == "result":
                await self.finish(event)
            elif kind == "error":
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
        if state != "completed":
            label = CHAT_INTENT.get(state, state.upper())
            reason = f" ({result['error_code']})" if result.get("error_code") else ""
            await self.add_state(f"{label}{reason}".strip())

    async def action_cancel(self) -> None:
        if self.turn and self.turn.turn_id:
            await self.client.cancel(self.turn.turn_id)

    # ---- widgets ------------------------------------------------------------
    async def add_user(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(Static(f"[ ТИ ]\n{escape(text)}", classes="msg-user"))
        chat.scroll_end(animate=False)

    async def add_assistant(self, text: str) -> Markdown:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(Static("[ B-12 ]", classes="msg-tag"))
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
            title=f"$ {event.get('name')}  {summary}".rstrip(),
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
                title=f"$ {message.get('tool_name')}  → {status}",
                collapsed=True,
            )
        )

    async def add_state(self, text: str) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(Static(escape(text), classes="msg-state"))


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
