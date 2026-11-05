"""Terminal UI driven headlessly against a scripted client (no network, no model)."""

import asyncio

import pytest

from b12.tui.app import B12App, _summary
from b12.tui.client import parse_ndjson


class FakeClient:
    def __init__(self, events):
        self.events = events
        self.sent = []
        self.decided = []
        self.resumed = []

    async def me(self):
        return {"consent": True, "owner": True}

    async def health(self):
        return True

    async def sessions(self):
        return ["s-1", "s-2"]

    async def new_session(self):
        return "s-3"

    async def history(self, session_id):
        return [{"role": "user", "content": "привіт"}, {"role": "assistant", "content": "вітаю"}]

    async def approvals(self):
        return []

    async def memory_records(self, limit=200):
        return [{"id": "m-1", "text": "факт про шафку"}]

    async def memory_search(self, query):
        return []

    async def memory_forget(self, memory_id):
        return {"state": "complete"}

    async def set_consent(self, consent):
        return {"consent": consent}

    async def decide(self, operation_id, approve):
        self.decided.append((operation_id, approve))
        return {}

    async def cancel(self, turn_id):
        return None

    async def chat(self, session_id, text, *, persist, timeout_s=600):
        self.sent.append((session_id, text, persist))
        for event in self.events:
            yield event

    async def resume(self, turn_id):
        self.resumed.append(turn_id)
        for event in [{"type": "result", "state": "completed", "content": "готово"}]:
            yield event


STREAM = [
    {"type": "turn_started", "turn_id": "t-1", "session_id": "s-1"},
    {"type": "text_delta", "text": "Перевіряю "},
    {"type": "text_delta", "text": "файли."},
    {"type": "tool_started", "call_id": "c-1", "name": "file_list", "arguments": {"path": "/x"}},
    {"type": "tool_result", "call_id": "c-1", "name": "file_list", "status": "completed"},
    {
        "type": "result",
        "state": "completed",
        "content": "Файли перелічено.",
        "tool_results": [{"call_id": "c-1", "content": {"entries": ["a.py/"]}}],
    },
]


async def test_session_history_and_a_streamed_turn_render(tmp_path):
    client = FakeClient(STREAM)
    app = B12App(client)
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt")
        prompt.value = "перелічи теку"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert client.sent == [("s-2", "перелічи теку", False)]  # newest session opens first
        texts = [str(w.render()) for w in app.query("Static")]
        assert any("ТИ" in t for t in texts)
        assert app.waiting_turn is None and app.turn is None


async def test_approval_pauses_the_turn_and_decision_resumes_it():
    events = [
        {"type": "turn_started", "turn_id": "t-9", "session_id": "s-1"},
        {
            "type": "approval_pending",
            "call_id": "c-2",
            "name": "shell_exec",
            "operation_id": "op-1",
        },
        {"type": "result", "state": "awaiting_approval", "content": ""},
    ]
    client = FakeClient(events)
    app = B12App(client)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt").value = "видали кеш"
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert app.waiting_turn == "t-9"
        await app.decide("op-1", True)
        await pilot.pause(0.3)
        assert client.decided == [("op-1", True)] and client.resumed == ["t-9"]
        assert app.waiting_turn is None


def test_ndjson_and_summary_helpers():
    assert parse_ndjson(['{"a": 1}', "", '{"b": 2}']) == [{"a": 1}, {"b": 2}]
    assert _summary({"path": "  /tmp/x \n y  "}) == "/tmp/x y"
    assert _summary({}) == ""
    assert _summary({"text": "x" * 200}).endswith("…")


def test_tui_command_runs_on_the_cli_event_loop(monkeypatch, tmp_path):
    """Regression: `b12 tui` crashed inside a running asyncio loop."""
    from b12 import cli
    from b12.tui import app as tui_app

    state = tmp_path / "state"
    (state / "api").mkdir(parents=True)
    (state / "api" / "owner.token").write_text("tok")
    started = {}

    async def fake_run_async(self, *args, **kwargs):
        started["ran"] = True

    monkeypatch.setattr(tui_app.B12App, "run_async", fake_run_async)
    import httpx

    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: httpx.Response(200, request=httpx.Request("GET", "http://x"))
    )
    monkeypatch.setenv("B12_STATE_DIR", str(state))
    assert cli.main(["tui", "--url", "http://127.0.0.1:1"]) == 0
    assert started == {"ran": True}


async def test_tool_arguments_and_results_with_brackets_do_not_crash_the_app():
    """Regression: a shell argument like `[1]` or `]` in a tool call broke Textual's markup."""
    events = [
        {"type": "turn_started", "turn_id": "t-5", "session_id": "s-1"},
        {
            "type": "tool_started",
            "call_id": "c-9",
            "name": "shell_exec",
            "arguments": {"command": 'ffmpeg -af "[in]highpass=f=200[/out]"'},
        },
        {"type": "tool_result", "call_id": "c-9", "name": "shell_exec", "status": "completed"},
        {
            "type": "result",
            "state": "completed",
            "content": "готово",
            "tool_results": [{"call_id": "c-9", "content": {"text": "[...] ] [/x] done"}}],
        },
    ]
    app = B12App(FakeClient(events))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#prompt").value = "обробити"
        await pilot.press("enter")
        await pilot.pause(0.5)
        assert app.turn is None
        from rich.text import Text
        from textual.widgets import Collapsible

        for node in app.query(Collapsible):
            Text.from_markup(node.title)  # raises if the title would crash rendering
        assert app.is_running


def test_tui_reports_an_unreachable_server_without_a_traceback(monkeypatch, tmp_path, capsys):
    """Regression: starting `b12 tui` with no server printed a Python traceback."""
    from b12 import cli

    state = tmp_path / "state"
    (state / "api").mkdir(parents=True)
    (state / "api" / "owner.token").write_text("tok")
    monkeypatch.setenv("B12_STATE_DIR", str(state))
    assert cli.main(["tui", "--url", "http://127.0.0.1:9"]) == 1
    out = capsys.readouterr().out
    assert "server_unavailable" in out and "Traceback" not in out


async def test_switch_labels_show_their_state_in_words():
    """Regression: both checkboxes drew the same glyph, so the owner could not see which was on."""
    from textual.widgets import Checkbox

    app = B12App(FakeClient(STREAM))
    async with app.run_test() as pilot:
        await pilot.pause()
        persist = app.query_one("#persist", Checkbox)
        assert "ВИМК" in str(persist.label)
        persist.value = True
        await pilot.pause()
        assert "ВКЛ" in str(persist.label)


async def test_cybercat_follows_mouse_and_can_be_petted_without_sending_a_message():
    app = B12App(FakeClient([]))
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        pet = app.query_one("#pet")
        app.action_toggle_motion()
        await pilot.hover("#pet", offset=(2, 3))
        await pilot.pause()
        assert pet.look_x < 0
        await pilot.hover("#pet", offset=(pet.size.width - 3, 3))
        await pilot.pause()
        assert pet.look_x > 0
        await pilot.click("#pet")
        await pilot.pause()
        assert "мур" in pet.status_text.plain.casefold()
        assert app.focused.id == "prompt"
        assert app.client.sent == []


async def test_cybercat_reacts_to_typing_model_tool_and_final_response():
    class LiveClient(FakeClient):
        def __init__(self):
            super().__init__([])
            self.queue = asyncio.Queue()

        async def chat(self, *args, **kwargs):
            yield {"type": "turn_started", "turn_id": "live-1"}
            while True:
                event = await self.queue.get()
                yield event
                if event["type"] == "result":
                    return

    client = LiveClient()
    app = B12App(client)
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        pet = app.query_one("#pet")
        app.query_one("#prompt").value = "досліди теку"
        await pilot.pause()
        assert pet.phase == "typing"
        await pilot.press("enter")
        await pilot.pause()
        assert pet.phase == "thinking"
        await client.queue.put(
            {"type": "tool_started", "call_id": "c", "name": "file_list", "arguments": {}}
        )
        await pilot.pause()
        assert pet.phase == "working" and "file_list" in pet.status_text.plain
        await client.queue.put({"type": "text_delta", "text": "Знайшов файли."})
        await pilot.pause()
        assert pet.phase == "speaking"
        await client.queue.put(
            {"type": "result", "state": "completed", "content": "Знайшов файли."}
        )
        await pilot.pause()
        assert pet.phase == "success" and app.turn is None


@pytest.mark.parametrize("size", [(80, 24), (120, 36), (160, 48)])
async def test_chat_composer_and_cat_remain_visible_at_terminal_sizes(size):
    app = B12App(FakeClient([]))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        prompt, pet = app.query_one("#prompt"), app.query_one("#pet")
        assert prompt.region.width >= 20 and pet.region.width >= 20
        assert prompt.region.bottom <= size[1] and pet.region.bottom <= size[1]
        assert app.query_one("#send").region.right <= size[0]
        assert app.query_one("#sidebar").display is (size[0] >= 110)


async def test_animation_can_pause_without_disabling_mouse_interaction():
    app = B12App(FakeClient([]))
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        pet = app.query_one("#pet")
        await pilot.press("f8")
        frame = pet.frame
        await pilot.pause(0.3)
        assert pet.frame == frame
        await pilot.click("#pet")
        await pilot.pause()
        assert "мур" in pet.status_text.plain.casefold()


async def test_pet_shortcut_preserves_draft_and_control_panel_shortcut_opens_panel():
    app = B12App(FakeClient([]))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt")
        prompt.value = "не загуби цю думку"
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert prompt.value == "не загуби цю думку"
        assert "мур" in app.query_one("#pet").status_text.plain.casefold()
        await pilot.press("ctrl+p")
        await pilot.pause()
        assert app.query_one("#panel").has_class("open")
        assert app.query_one("#pet").region.height > 0
        assert app.query_one("#mem-query").region.y < 24
        assert app.client.sent == []


async def test_small_terminal_can_open_navigation_and_return_to_chat():
    app = B12App(FakeClient([]))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert app.query_one("#sidebar").display
        await pilot.click("#s-s-1")
        await pilot.pause()
        assert app.current == "s-1"
        assert not app.query_one("#sidebar").display
        assert app.focused.id == "prompt"


async def test_offline_preview_is_labelled_and_responds_without_a_server():
    from b12.tui.preview import PreviewApp, PreviewClient

    app = PreviewApp(PreviewClient())
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert "ДЕМО" in app.query_one("#top").render().plain
        app.query_one("#prompt").value = "привіт, кіберкоте"
        await pilot.press("enter")
        await pilot.pause(0.15)
        assert app.query_one("#pet").phase == "thinking"
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.turn is None
        assert "офлайн" in str(await app.client.history(app.current)).casefold()


async def test_new_tui_uses_real_api_events_and_displays_a_real_tool_result(api, tmp_path):
    import httpx
    from textual.widgets import Collapsible

    from b12.tui.client import ApiClient

    state, _, token, service, _ = api
    target = tmp_path / "tui-tool-proof.txt"
    state["script"] = [
        {"tool_calls": [("file_write", {"path": str(target), "text": "через новий TUI"})]},
        {"content": "Файл записано."},
    ]
    client = ApiClient("http://testserver", token, transport=httpx.ASGITransport(app=service))
    try:
        app = B12App(client)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app.query_one("#prompt").value = "запиши тестовий файл"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert target.read_text() == "через новий TUI"
            assert app.query_one("#pet").phase == "success"
            assert any("file_write" in str(card.title) for card in app.query(Collapsible))
            assert app.turn is None
    finally:
        await client.close()


async def test_opening_long_history_shows_latest_messages_in_compact_layout():
    class LongHistory(FakeClient):
        async def history(self, _):
            return [
                {"role": "assistant", "content": f"Повідомлення {i}. " + "текст " * 25}
                for i in range(12)
            ]

    app = B12App(LongHistory([]))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        chat = app.query_one("#chat")
        assert chat.max_scroll_y > 0
        assert chat.scroll_y == chat.max_scroll_y


async def test_lost_server_leaves_the_cat_in_error_state_without_closing_the_tui():
    import httpx

    class Disconnected(FakeClient):
        checks = 0

        async def approvals(self):
            self.checks += 1
            if self.checks > 1:
                raise httpx.ConnectError("offline")
            return []

        async def chat(self, *args, **kwargs):
            raise httpx.ConnectError("offline")
            yield  # make this an async event iterator

    app = B12App(Disconnected([]))
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        app.query_one("#prompt").value = "ти тут?"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.is_running and app.turn is None
        assert app.query_one("#pet").phase == "error"
        assert "OFFLINE" in app.query_one("#top").render().plain


async def test_raster_companion_renders_changed_gaze_and_releases_frames_on_exit():
    from rich.console import Console

    app = B12App(FakeClient([]))
    async with app.run_test(size=(140, 44)) as pilot:
        await pilot.pause()
        pet = app.query_one("#pet")
        assert hasattr(pet, "portrait"), "the approved raster cat is not connected to the TUI"
        await pilot.press("f8")
        console = Console(
            width=pet.size.width, force_terminal=True, color_system="truecolor", no_color=False
        )
        await pilot.hover("#pet", offset=(2, pet.size.height // 2))
        await pilot.pause()
        with console.capture() as left:
            console.print(pet.render())
        await pilot.hover("#pet", offset=(pet.size.width - 3, pet.size.height // 2))
        await pilot.pause()
        with console.capture() as right:
            console.print(pet.render())
        assert left.get() != right.get()  # actual visible image, not just a state property
        assert app.client.sent == []
        portrait = pet.portrait
        assert portrait.cache
    assert not portrait.cache


async def test_link_indicator_follows_the_server_while_idle():
    class Flaky(FakeClient):
        up = True

        async def health(self):  # same contract as ApiClient.health: False on transport failure
            return self.up

    client = Flaky([])
    app = B12App(client)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        assert "LOCAL LINK" in app.query_one("#top").render().plain
        client.up = False
        await app.check_link()
        await pilot.pause()
        assert "OFFLINE" in app.query_one("#top").render().plain
        client.up = True
        await app.check_link()
        await pilot.pause()
        assert "LOCAL LINK" in app.query_one("#top").render().plain


async def test_api_client_reports_a_stopped_server_as_offline_instead_of_raising():
    from b12.tui.client import ApiClient

    client = ApiClient("http://127.0.0.1:1", "token")
    try:
        assert await client.health() is False
    finally:
        await client.close()
