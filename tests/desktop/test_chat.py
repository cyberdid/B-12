import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton

from b12.desktop.chat import ChatWindow


class NoNetworkClient:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected synchronous API call: {name}")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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


def test_stream_error_keeps_recovery_cancel_and_cancel_result_unlocks_composer(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-recover"
    window._active_turn_id = "turn-recover"
    window.pending_turn_id = "turn-recover"
    window.send_button.setEnabled(False)

    window._on_job_error("chat", "server_unavailable")

    assert window._active_turn_id == "turn-recover"
    assert window.cancel_button.isEnabled()
    assert not window.send_button.isEnabled()

    window._on_job_result("cancel", {"cancelled": "turn-recover"})
    assert window._active_turn_id is None
    assert window.pending_turn_id is None
    assert window.send_button.isEnabled()
    assert not window.cancel_button.isEnabled()
    window.close()


def test_terminal_error_event_clears_pending_turn(qapp):
    window = ChatWindow(NoNetworkClient(), auto_load=False, auto_poll=False)
    window._current_session = "session-stale"
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
    resume = next(job for job in jobs if job[0] == "resume")
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

    assert jobs == ["chat"]
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
    window._history_loaded_session = "session-approval"
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
