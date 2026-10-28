"""Terminal UI driven headlessly against a scripted client (no network, no model)."""

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
