import httpx
import pytest

from b12.desktop.client import DesktopApiClient, DesktopApiError


def test_requests_use_owner_bearer_token_and_selected_api_url():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"owner": True})

    client = DesktopApiClient(
        "http://127.0.0.1:18712",
        "owner-secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.me() == {"owner": True}
    finally:
        client.close()

    assert requests[0].url == "http://127.0.0.1:18712/api/me"
    assert requests[0].headers["authorization"] == "Bearer owner-secret"


def test_stream_turn_emits_events_and_returns_the_final_result():
    lines = (
        '{"type":"turn_started","turn_id":"t-1"}\n'
        '{"type":"text_delta","text":"Привіт"}\n'
        '{"type":"result","state":"completed","content":"Привіт"}\n'
    )

    def handler(request):
        assert request.url.path == "/api/chat"
        assert (
            request.read()
            == ('{"session_id":"s-1","text":"Привіт","persist":false,"timeout_s":600.0}').encode()
        )
        return httpx.Response(200, text=lines)

    client = DesktopApiClient(
        "http://127.0.0.1:8712", "token", transport=httpx.MockTransport(handler)
    )
    events = []
    try:
        result = client.stream_turn("s-1", "Привіт", persist=False, on_event=events.append)
    finally:
        client.close()

    assert [event["type"] for event in events] == ["turn_started", "text_delta", "result"]
    assert result == {"type": "result", "state": "completed", "content": "Привіт"}


def test_stream_turn_rejects_malformed_ndjson():
    client = DesktopApiClient(
        "http://127.0.0.1:8712",
        "token",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not-json\n")),
    )
    try:
        with pytest.raises(DesktopApiError, match="invalid_stream_event"):
            client.stream_turn("s-1", "hello", persist=False, on_event=lambda event: None)
    finally:
        client.close()


def test_http_api_error_uses_server_error_code():
    client = DesktopApiClient(
        "http://127.0.0.1:8712",
        "token",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(409, json={"detail": "approval_not_pending"})
        ),
    )
    try:
        with pytest.raises(DesktopApiError) as caught:
            client.decide("op-1", approve=True)
    finally:
        client.close()

    assert caught.value.code == "approval_not_pending"
    assert caught.value.status_code == 409


def test_stream_http_error_preserves_server_error_code():
    class ErrorBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"detail":"turn_not_waiting"}'

        def close(self):
            pass

    client = DesktopApiClient(
        "http://127.0.0.1:8712",
        "token",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                409,
                headers={"content-type": "application/json"},
                stream=ErrorBody(),
            )
        ),
    )
    try:
        with pytest.raises(DesktopApiError) as caught:
            client.resume("turn-1", lambda event: None)
    finally:
        client.close()

    assert caught.value.code == "turn_not_waiting"
    assert caught.value.status_code == 409


def test_opaque_identifiers_remain_one_encoded_path_segment():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"operation_id": "ok", "approved": True})

    client = DesktopApiClient(
        "http://127.0.0.1:8712", "token", transport=httpx.MockTransport(handler)
    )
    try:
        client.decide("op/with?reserved", approve=True)
    finally:
        client.close()

    assert requests[0].url.raw_path == b"/api/approvals/op%2Fwith%3Freserved"


def test_turn_status_is_scoped_to_the_exact_opaque_turn_id():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"turn_id": "turn/one", "active": False})

    client = DesktopApiClient(
        "http://127.0.0.1:8712", "token", transport=httpx.MockTransport(handler)
    )
    try:
        assert client.turn_status("turn/one") == {"turn_id": "turn/one", "active": False}
    finally:
        client.close()

    assert requests[0].url.raw_path == b"/api/turns/turn%2Fone/status"


def test_transport_failure_is_reported_as_server_unavailable():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    client = DesktopApiClient(
        "http://127.0.0.1:8712", "token", transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(DesktopApiError) as caught:
            client.sessions()
    finally:
        client.close()

    assert caught.value.code == "server_unavailable"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://127.0.0.1:8712/path",
        "http://user:password@127.0.0.1:8712",
        "http://127.0.0.1:8712?token=secret",
    ],
)
def test_client_rejects_non_loopback_or_credential_bearing_api_urls(url):
    with pytest.raises(ValueError):
        DesktopApiClient(url, "token")


def test_health_returns_false_when_loopback_server_is_offline():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    client = DesktopApiClient(
        "http://127.0.0.1:8712", "token", transport=httpx.MockTransport(handler)
    )
    try:
        assert client.health() is False
    finally:
        client.close()
