import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea

from b12.desktop.chat import ChatWindow


class NoNetworkClient:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected synchronous API call: {name}")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_empty_approval_area_uses_dark_theme(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window.resize(1024, 800)
    window.show()
    qapp.processEvents()
    try:
        approval_scroll = window.findChild(QScrollArea)
        assert approval_scroll is not None
        center = approval_scroll.viewport().mapTo(
            window, approval_scroll.viewport().rect().center()
        )
        pixel = window.grab().toImage().pixelColor(center)
        assert pixel.name() == "#0a1020"
    finally:
        window.close()


def test_turn_events_update_cat_phase_and_safe_transcript(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    phases = []
    window.phase_changed.connect(lambda phase, detail: phases.append((phase, detail)))

    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-1"})
    window.handle_turn_event(
        {
            "type": "tool_started",
            "name": "file_read",
            "call_id": "c1",
            "arguments": {"path": "/tmp/x"},
        }
    )
    window.handle_turn_event({"type": "text_delta", "text": "<img src='file:///etc/passwd'>"})

    assert phases[:2] == [("thinking", ""), ("working", "file_read")]
    assert "file_read" in window.transcript.toPlainText()
    assert "<img src='file:///etc/passwd'>" in window.transcript.toPlainText()
    assert window.pending_turn_id == "turn-1"
    window.close()


def test_transcript_never_interprets_markdown_images_as_resources(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window.handle_turn_event(
        {
            "type": "text_delta",
            "text": "![secret](file:///etc/passwd) ![remote](https://example.invalid/x.png)",
        }
    )

    assert "<img" not in window.transcript.toHtml().lower()
    assert "![secret](file:///etc/passwd)" in window.transcript.toPlainText()
    window.close()


def test_approval_pending_displays_exact_operation_id_without_auto_deciding(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    decisions = []
    window.approval_requested.connect(
        lambda operation_id, approve: decisions.append((operation_id, approve))
    )

    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-7"})
    window.handle_turn_event(
        {"type": "approval_pending", "operation_id": "op-exact-7", "name": "shell_exec"}
    )

    assert window.pending_approval_ids() == ["op-exact-7"]
    assert decisions == []
    assert window.status_label.text().lower().find("підтвердж") >= 0
    assert "API не надає параметри" in window._approval_cards["op-exact-7"].findChild(
        type(window.status_label)
    ).text()
    window.close()


def test_live_approval_points_to_tool_arguments_in_transcript(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-live"
    window._history_loaded_session = "session-live"
    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-live"})
    window.handle_turn_event(
        {
            "type": "tool_started",
            "name": "file_read",
            "call_id": "call-live",
            "arguments": {"path": "/tmp/report.md", "offset": 64},
        }
    )
    window.handle_turn_event(
        {
            "type": "approval_pending",
            "operation_id": "op-live",
            "call_id": "call-live",
            "name": "file_write",
        }
    )

    label = window._approval_cards["op-live"].findChild(type(window.status_label))
    assert "Параметри виклику видно вище" in label.text()
    assert "/tmp/report.md" in window.transcript.toPlainText()
    window.close()


def test_approval_button_sends_exact_pending_operation_id(qapp):
    class RecordingClient:
        calls = []

        def decide(self, operation_id, *, approve):
            self.calls.append((operation_id, approve))
            return {"operation_id": operation_id, "approved": approve}

    client = RecordingClient()
    window = ChatWindow(client, auto_load=False, auto_poll=False)
    window._current_session = "session-8"
    window._history_loaded_session = "session-8"
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append(
        (tag, operation, streaming)
    )
    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-8"})
    window.handle_turn_event(
        {"type": "approval_pending", "operation_id": "op-exact-8", "name": "shell_exec"}
    )
    window.handle_turn_event(
        {"type": "result", "turn_id": "turn-8", "state": "awaiting_approval"}
    )
    [approve, deny] = window._approval_cards["op-exact-8"].findChildren(QPushButton)
    approve.click()
    assert jobs[0][0] == "decision:op-exact-8"
    jobs[0][1]()
    assert client.calls == [("op-exact-8", True)]
    info = window._approval_cards["op-exact-8"].findChildren(type(window.status_label))[0]
    assert info.textFormat().name == "PlainText"
    assert info.toolTip() == "op-exact-8"
    window._render_approvals(
        [{"operation_id": "op-exact-8", "turn_id": "turn-8", "session_id": "session-8"}]
    )
    assert all(
        not button.isEnabled()
        for button in window._approval_cards["op-exact-8"].findChildren(QPushButton)
    )
    window.close()


def test_memory_text_is_plain_text(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._render_memory([{"id": "memory-1", "text": "<img src='file:///etc/passwd'>"}])
    card = window.memory_list.itemWidget(window.memory_list.item(0))
    label = card.findChildren(type(window.status_label))[0]

    assert label.textFormat().name == "PlainText"
    assert label.text() == "<img src='file:///etc/passwd'>"
    window.close()


def test_stream_error_cancel_waits_for_authoritative_turn_status(qapp):
    class Client:
        def cancel(self, turn_id):
            return {"cancelled": turn_id}

        def turn_status(self, turn_id):
            return {"turn_id": turn_id, "active": False}

        def history(self, session_id):
            return []

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-recover"
    window._history_loaded_session = "session-recover"
    window._active_turn_id = "turn-recover"
    window.pending_turn_id = "turn-recover"
    window.send_button.setEnabled(False)

    window._on_job_error("chat", "server_unavailable")

    assert window._active_turn_id == "turn-recover"
    assert window.cancel_button.isEnabled()
    assert not window.send_button.isEnabled()

    window.cancel_turn()
    cancel_tag, cancel_operation = jobs[-1]
    assert cancel_tag.startswith("cancel:")
    window._on_job_result(cancel_tag, cancel_operation())
    assert window._active_turn_id == "turn-recover"
    assert not window.send_button.isEnabled()

    status_tag, status_operation = jobs[-1]
    assert status_tag.startswith("turn_status:")
    window._on_job_result(status_tag, status_operation())

    assert window._active_turn_id is None
    assert window.pending_turn_id is None
    history_tag, history_operation = jobs[-1]
    assert history_tag.startswith("history:")
    window._on_job_result(history_tag, history_operation())
    assert window.send_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    window.close()


def test_stream_error_waits_for_cancel_ack_before_requesting_turn_status(qapp):
    class Client:
        def cancel(self, turn_id):
            return {"cancelled": turn_id}

        def turn_status(self, turn_id):
            return {"turn_id": turn_id, "active": False}

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._active_turn_id = "turn-delayed-cancel"
    window.pending_turn_id = "turn-delayed-cancel"
    window._stream_generation = 1
    window.cancel_turn()
    cancel_tag, cancel_operation = jobs[-1]

    window._on_job_error("chat:1", "server_unavailable")

    assert window._stream_lost_turn_id == "turn-delayed-cancel"
    assert all(not tag.startswith("turn_status:") for tag, _ in jobs)
    assert window._active_turn_id == "turn-delayed-cancel"

    window._on_job_result(cancel_tag, cancel_operation())
    status_tag, status_operation = jobs[-1]
    assert status_tag.startswith("turn_status:")
    window._on_job_result(status_tag, status_operation())
    assert window._active_turn_id is None
    window.close()


def test_failed_recovery_history_load_keeps_session_locked(qapp):
    class Client:
        def history(self, session_id):
            return []

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-recovered"
    window._history_loaded_session = "session-recovered"
    window._entries = [("ТИ", "старий контекст")]
    window._render_transcript()

    window._load_history("session-recovered")
    history_tag = jobs[-1][0]
    assert window._history_loaded_session is None
    window._on_job_error(history_tag, "server_unavailable")

    assert window._history_loaded_session is None
    assert not window.send_button.isEnabled()
    window.close()


def test_recovery_status_keeps_live_turn_locked_until_server_finishes(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-recover"
    window._history_loaded_session = "session-recover"
    window._active_turn_id = "turn-recover"
    window._stream_lost_turn_id = "turn-recover"
    window._cancel_acknowledged_for = "turn-recover"
    window._turn_status_sequence = 1
    window._start_job = lambda *args, **kwargs: None

    window._on_job_result(
        "turn_status:1:turn-recover", {"turn_id": "turn-recover", "active": True}
    )

    assert window._active_turn_id == "turn-recover"
    assert not window.send_button.isEnabled()
    assert window.cancel_button.isEnabled()
    window.close()


def test_inactive_status_without_cancel_ack_cannot_release_lost_turn(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._turn_status_sequence = 1
    window._stream_lost_turn_id = "turn-pending-cancel"
    window._active_turn_id = "turn-pending-cancel"
    window.pending_turn_id = "turn-pending-cancel"
    window.send_button.setEnabled(False)

    window._on_job_result(
        "turn_status:1:turn-pending-cancel",
        {"turn_id": "turn-pending-cancel", "active": False},
    )

    assert window._active_turn_id == "turn-pending-cancel"
    assert window.pending_turn_id == "turn-pending-cancel"
    assert not window.send_button.isEnabled()
    window.close()


def test_terminal_error_event_clears_pending_turn(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-stale"
    window._history_loaded_session = "session-stale"
    window._active_turn_id = "turn-stale"
    window.pending_turn_id = "turn-stale"
    window.send_button.setEnabled(False)
    window.cancel_button.setEnabled(True)

    window.handle_turn_event({"type": "error", "error": "not_waiting"})

    assert window._active_turn_id is None
    assert window.pending_turn_id is None
    assert window.send_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    window.close()


def test_approval_resume_exposes_cancel_for_same_turn(qapp):
    class RecordingClient:
        def approvals(self):
            return []

    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window.client = RecordingClient()
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append(
        (tag, operation, streaming)
    )
    window.pending_turn_id = "turn-resume"
    window._current_session = "session-resume"
    window._history_loaded_session = "session-resume"
    window._approval_turns["op-resume"] = "turn-resume"
    window._approval_sessions["op-resume"] = "session-resume"
    window._on_job_result("decision:op-resume", {"approved": True})

    assert window._active_turn_id == "turn-resume"
    assert window.pending_turn_id == "turn-resume"
    assert window.cancel_button.isEnabled()
    assert not window.send_button.isEnabled()
    resume = next(job for job in jobs if job[0].startswith("resume:"))
    assert resume[2] is True
    window.close()


def test_restored_approval_blocks_new_turn_in_its_session(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append(tag)
    window._current_session = "session-pending"
    window._render_approvals(
        [
            {
                "operation_id": "op-pending",
                "turn_id": "turn-pending",
                "session_id": "session-pending",
                "name": "file_write",
            }
        ]
    )
    window.composer.setPlainText("ще одне завдання")

    window.send_prompt()

    assert jobs == []
    assert not window.send_button.isEnabled()
    window.close()


def test_approval_in_another_session_does_not_block_current_session(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append(tag)
    window._current_session = "session-current"
    window._history_loaded_session = "session-current"
    window._render_approvals(
        [
            {
                "operation_id": "op-other",
                "turn_id": "turn-other",
                "session_id": "session-other",
                "name": "file_write",
            }
        ]
    )
    window.composer.setPlainText("нове завдання")

    window.send_prompt()

    assert len(jobs) == 1 and jobs[0].startswith("chat:")
    window.close()


def test_chat_bootstrap_retries_after_api_recovers(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append(tag)
    window._bootstrap_inflight = True

    window._on_job_error("bootstrap", "server_unavailable")
    window._on_job_result(
        "poll",
        {"connected": True, "approvals": [], "status": {"active_turns": 0}},
    )

    assert window._bootstrap_inflight
    assert jobs.count("bootstrap") == 1
    window._on_job_result(
        "poll",
        {"connected": True, "approvals": [], "status": {"active_turns": 0}},
    )
    assert jobs.count("bootstrap") == 1
    window.close()


def test_session_selection_is_locked_during_a_live_turn(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window.session_box.addItem("РОЗМОВА 01", "session-1")
    window.session_box.setEnabled(True)

    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-1"})
    assert not window.session_box.isEnabled()

    window.handle_turn_event({"type": "result", "turn_id": "turn-1", "state": "completed"})
    assert window.session_box.isEnabled()
    window.close()


def test_approval_buttons_wait_for_the_matching_session_history(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window.client = type("Client", (), {"history": lambda self, session_id: []})()
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-current"
    window.session_box.addItem("РОЗМОВА 01", "session-current")
    window.session_box.setCurrentIndex(0)
    window._render_approvals(
        [
            {
                "operation_id": "op-other-session",
                "turn_id": "turn-other",
                "session_id": "session-other",
                "name": "file_write",
            }
        ]
    )
    card = window._approval_cards["op-other-session"]
    assert all(not button.isEnabled() for button in card.findChildren(QPushButton))
    assert "Перейди до відповідної розмови" in card.findChild(type(window.status_label)).text()

    window.session_box.addItem("РОЗМОВА 02", "session-other")
    window._session_selected(1)
    assert not all(button.isEnabled() for button in card.findChildren(QPushButton))
    window._on_job_result("history:session-other", [])
    assert all(button.isEnabled() for button in card.findChildren(QPushButton))
    window.close()


def test_failed_history_load_keeps_approval_controls_disabled(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window.client = type("Client", (), {"history": lambda self, session_id: []})()
    window._start_job = lambda *args, **kwargs: None
    window._current_session = "session-approval"
    approval = {
        "operation_id": "op-history-error",
        "turn_id": "turn-history-error",
        "session_id": "session-approval",
    }
    window._render_approvals([approval])
    window._load_history("session-approval")

    window._on_job_error("history:session-approval", "server_unavailable")

    assert all(
        not button.isEnabled()
        for button in window._approval_cards["op-history-error"].findChildren(QPushButton)
    )
    window.close()


def test_failed_new_session_history_load_schedules_bootstrap_retry(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append(tag)
    window._current_session = "session-new"
    window.session_box.blockSignals(True)
    window.session_box.addItem("old", "session-old")
    window.session_box.addItem("new", "session-new")
    window.session_box.setCurrentIndex(1)
    window.session_box.blockSignals(False)
    window._history_loading_session = "session-new"
    window._history_loaded_session = None
    window._history_request_sequence = 1
    window._session_change_inflight = True
    window._session_before_change = "session-old"
    window._session_before_change_history_loaded = False
    window._loaded = True

    window._on_job_error("history:1:session-new", "server_unavailable")

    assert window._current_session == "session-old"
    assert window._history_loaded_session is None
    assert not window._loaded
    window._on_job_result(
        "poll",
        {"connected": True, "approvals": [], "status": {"active_turns": 0}},
    )
    assert "bootstrap" in jobs
    assert not window.send_button.isEnabled()
    window.close()


def test_approval_from_another_live_turn_waits_until_current_turn_finishes(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda *args, **kwargs: jobs.append(args)
    window._current_session = "session-shared"
    window._history_loaded_session = "session-shared"
    window._active_turn_id = "turn-active"
    window._render_approvals(
        [
            {
                "operation_id": "op-other-turn",
                "turn_id": "turn-waiting",
                "session_id": "session-shared",
                "name": "file_write",
            }
        ]
    )

    assert all(
        not button.isEnabled()
        for button in window._approval_cards["op-other-turn"].findChildren(QPushButton)
    )
    window._decide_approval("op-other-turn", True)
    assert jobs == []
    assert "op-other-turn" not in window._decision_inflight
    window.close()


def test_new_session_cannot_change_context_during_live_turn(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append(tag)
    window._active_turn_id = "turn-live"
    window._sync_session_selector()

    assert not window.new_session_button.isEnabled()
    window.create_session()
    assert jobs == []
    window.close()


def test_new_session_request_blocks_send_until_new_history_loads(qapp):
    class Client:
        def new_session(self):
            return "session-new"

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-old"
    window._history_loaded_session = "session-old"
    window.session_box.addItem("РОЗМОВА 01", "session-old")
    window.session_box.setCurrentIndex(0)
    window.create_session()
    window.composer.setPlainText("не відправляти у стару розмову")

    window.send_prompt()

    assert [tag for tag, _ in jobs] == ["new_session"]
    window._on_job_result("new_session", jobs[0][1]())
    assert window._current_session == "session-new"
    window.send_prompt()
    assert [tag for tag, _ in jobs] == ["new_session", "bootstrap"]
    assert window._history_loaded_session != "session-new"
    window.close()


def test_new_session_bootstrap_failure_restores_previous_context(qapp):
    class Client:
        def new_session(self):
            return "session-new"

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-old"
    window._history_loaded_session = "session-old"
    window.session_box.addItem("РОЗМОВА 01", "session-old")
    window.session_box.setCurrentIndex(0)
    window.create_session()
    window._on_job_result("new_session", jobs[0][1]())
    assert window._current_session == "session-new"
    assert window._session_change_inflight

    window._on_job_error("bootstrap", "server_unavailable")

    assert window._current_session == "session-old"
    assert window._history_loaded_session == "session-old"
    assert window.session_box.currentData() == "session-old"
    assert window.send_button.isEnabled()
    window.close()


def test_new_session_is_disabled_while_selected_history_loads(qapp):
    class Client:
        def new_session(self):
            return "session-new"

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-loading"
    window._history_loading_session = "session-loading"
    window.session_box.addItem("РОЗМОВА 01", "session-loading")
    window._sync_session_selector()

    assert not window.new_session_button.isEnabled()
    window.create_session()
    assert jobs == []
    window.close()


def test_new_session_is_disabled_during_initial_bootstrap(qapp):
    class Client:
        def bootstrap(self):
            return {"sessions": [], "me": {"consent": False}}

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window.bootstrap()

    assert not window.new_session_button.isEnabled()
    window.create_session()
    assert [tag for tag, _ in jobs] == ["bootstrap"]
    window.close()


def test_session_change_failure_does_not_mark_unloaded_history_ready(qapp):
    class Client:
        def new_session(self):
            return "session-new"

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-old"
    window.session_box.addItem("РОЗМОВА 01", "session-old")
    window.session_box.setCurrentIndex(0)
    window.create_session()
    window._on_job_result("new_session", jobs[0][1]())
    window._on_job_error("bootstrap", "server_unavailable")

    assert window._current_session == "session-old"
    assert window._history_loaded_session is None
    assert not window.send_button.isEnabled()
    window.close()


def test_old_approval_snapshot_cannot_erase_a_new_live_approval(qapp):
    class Client:
        def health(self):
            return True

        def approvals(self):
            return []

        def status(self):
            return {}

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-live"
    window._history_loaded_session = "session-live"
    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-live"})
    window.refresh_dashboard()
    snapshot_tag = jobs[0][0]
    window.handle_turn_event(
        {
            "type": "approval_pending",
            "operation_id": "op-live-new",
            "turn_id": "turn-live",
            "session_id": "session-live",
        }
    )
    window.handle_turn_event(
        {"type": "result", "turn_id": "turn-live", "state": "awaiting_approval"}
    )

    window._on_job_result(
        snapshot_tag,
        {"connected": True, "approvals": [], "status": {}},
    )

    assert "op-live-new" in window._approval_cards
    assert window.pending_turn_id == "turn-live"
    assert window._approval_turns["op-live-new"] == "turn-live"
    window.close()


def test_older_history_reply_for_same_session_is_ignored(qapp):
    class Client:
        def history(self, session_id):
            return []

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-repeat"
    window._load_history("session-repeat")
    first_tag = jobs[-1][0]
    window._load_history("session-repeat")
    second_tag = jobs[-1][0]
    assert first_tag != second_tag

    window._on_job_result(first_tag, [{"role": "assistant", "content": "старий зріз"}])

    assert window._history_loaded_session is None
    assert window._history_loading_session == "session-repeat"
    assert "старий зріз" not in window.transcript.toPlainText()
    window._on_job_result(second_tag, [{"role": "assistant", "content": "актуальний зріз"}])
    assert window._history_loaded_session == "session-repeat"
    assert "актуальний зріз" in window.transcript.toPlainText()
    window.close()


def test_history_reply_during_live_turn_is_deferred(qapp):
    class Client:
        def history(self, session_id):
            return []

        def sessions(self):
            return ["session-live"]

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-live"
    window._load_history("session-live")
    history_tag = jobs[-1][0]
    window._active_turn_id = "turn-live"
    window.handle_turn_event({"type": "text_delta", "text": "новий текст ходу"})

    window._on_job_result(
        history_tag,
        [{"role": "assistant", "content": "старий текст з історії"}],
    )

    assert "новий текст ходу" in window.transcript.toPlainText()
    assert "старий текст з історії" not in window.transcript.toPlainText()
    assert window._history_reload_deferred
    window.handle_turn_event({"type": "result", "turn_id": "turn-live", "state": "completed"})
    assert jobs[-1][0].startswith("history:")
    window.close()


def test_poll_snapshot_preserves_metadata_for_inflight_decision(qapp):
    class Client:
        def approvals(self):
            return []

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-decision"
    window._history_loaded_session = "session-decision"
    approval = {
        "operation_id": "op-inflight",
        "turn_id": "turn-inflight",
        "session_id": "session-decision",
    }
    window._render_approvals([approval])
    window._decide_approval("op-inflight", True)

    window._render_approvals([])
    assert window._approval_turns["op-inflight"] == "turn-inflight"
    assert window._approval_sessions["op-inflight"] == "session-decision"

    window._on_job_result("decision:op-inflight", {"approved": True})

    assert window._active_turn_id == "turn-inflight"
    assert any(tag.startswith("resume:") for tag, _ in jobs)
    window.close()


def test_late_cancel_response_cannot_clear_new_turn(qapp):
    class Client:
        def cancel(self, turn_id):
            return {"cancelled": turn_id}

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._active_turn_id = "turn-old"
    window.pending_turn_id = "turn-old"
    window.cancel_turn()
    cancel_tag = jobs[-1][0]

    window.handle_turn_event(
        {"type": "result", "turn_id": "turn-old", "state": "completed"}
    )
    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-new"})
    window._on_job_result(cancel_tag, {"cancelled": "turn-old"})

    assert window._active_turn_id == "turn-new"
    assert window.pending_turn_id == "turn-new"
    assert not window.send_button.isEnabled()
    window.close()


def test_late_recovery_status_cannot_clear_a_new_turn(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._turn_status_sequence = 1
    window._stream_lost_turn_id = "turn-old"
    window._active_turn_id = "turn-old"

    window._stream_lost_turn_id = None
    window._active_turn_id = "turn-new"
    window.pending_turn_id = "turn-new"
    window.send_button.setEnabled(False)
    window._on_job_result(
        "turn_status:1:turn-old", {"turn_id": "turn-old", "active": False}
    )

    assert window._active_turn_id == "turn-new"
    assert window.pending_turn_id == "turn-new"
    assert not window.send_button.isEnabled()
    window.close()


def test_events_from_superseded_stream_are_ignored(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-streams"
    window._history_loaded_session = "session-streams"
    window.composer.setPlainText("old request")
    window.send_prompt()
    old_stream_tag = jobs[-1][0]
    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-old"})
    window.handle_turn_event({"type": "result", "turn_id": "turn-old", "state": "completed"})

    window.composer.setPlainText("new request")
    window.send_prompt()
    new_stream_tag = jobs[-1][0]
    assert old_stream_tag != new_stream_tag
    window.handle_turn_event({"type": "turn_started", "turn_id": "turn-new"})
    window._on_job_event(old_stream_tag, {"type": "text_delta", "text": "late old text"})
    window._on_job_result(
        old_stream_tag,
        {"turn_id": "turn-old", "state": "completed", "content": "late old result"},
    )

    assert window._active_turn_id == "turn-new"
    assert "late old text" not in window.transcript.toPlainText()
    assert "late old result" not in window.transcript.toPlainText()
    window.close()


def test_stale_history_error_does_not_replace_current_status(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-same"
    window._history_request_sequence = 2
    window.status_label.setText("АКТУАЛЬНИЙ СТАН")

    window._on_job_error("history:1:session-same", "server_unavailable")

    assert window.status_label.text() == "АКТУАЛЬНИЙ СТАН"
    window.close()


def test_expired_approval_failure_unlocks_its_session(qapp):
    class Client:
        def approvals(self):
            return []

    window = ChatWindow(Client(), auto_load=False, auto_poll=False)
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    window._current_session = "session-expired"
    window._history_loaded_session = "session-expired"
    window.session_box.addItem("РОЗМОВА 01", "session-expired")
    window.session_box.setCurrentIndex(0)
    window.pending_turn_id = "turn-expired"
    window._approval_turns["op-expired"] = "turn-expired"
    window._approval_sessions["op-expired"] = "session-expired"
    window._upsert_approval(
        {"operation_id": "op-expired", "turn_id": "turn-expired", "session_id": "session-expired"}
    )
    window._sync_approval_actions()
    window._decide_approval("op-expired", True)

    window._on_job_error("decision:op-expired", "approval_not_pending")
    window._on_job_result("approvals", [])

    assert window.pending_turn_id is None
    assert window._active_turn_id is None
    assert window.session_box.isEnabled()
    assert window.new_session_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    window.close()


def test_poll_removing_pending_approval_clears_stale_turn_lock(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-expired"
    window._history_loaded_session = "session-expired"
    window.pending_turn_id = "turn-expired"
    window.session_box.addItem("РОЗМОВА 01", "session-expired")

    window._render_approvals([])

    assert window.pending_turn_id is None
    assert window.session_box.isEnabled()
    assert window.new_session_button.isEnabled()
    window.close()


def test_late_history_response_cannot_replace_a_newer_session(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-new"
    window._history_loading_session = "session-new"
    window._on_job_result(
        "history:session-old", [{"role": "assistant", "content": "старий transcript"}]
    )

    assert window._history_loading_session == "session-new"
    assert "старий transcript" not in window.transcript.toPlainText()
    window.close()


def test_failed_approval_request_refresh_reenables_still_pending_card(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window.client = type("Client", (), {"approvals": lambda self: []})()
    window._current_session = "s"
    window._history_loaded_session = "s"
    jobs = []
    window._start_job = lambda tag, operation, streaming=False: jobs.append((tag, operation))
    approval = {"operation_id": "op-failed", "turn_id": "turn-failed", "session_id": "s"}
    window._render_approvals([approval])
    window._decide_approval("op-failed", True)

    window._on_job_error("decision:op-failed", "approval_not_pending")
    window._render_approvals([approval])

    assert all(
        button.isEnabled()
        for button in window._approval_cards["op-failed"].findChildren(QPushButton)
    )
    window.close()


def test_completed_result_moves_pet_to_success(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    phases = []
    window.phase_changed.connect(lambda phase, detail: phases.append(phase))
    window.handle_turn_event(
        {"type": "result", "turn_id": "turn-2", "state": "completed", "content": "Готово"}
    )
    assert phases[-1] == "success"
    assert "Готово" in window.transcript.toPlainText()
    window.close()
