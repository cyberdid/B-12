"""`b12 serve` treats SIGTERM as a normal stop: graceful shutdown, exit code 0."""

import signal

import uvicorn


def test_sigterm_is_not_raised_again_after_graceful_shutdown():
    from b12.cli import GracefulServer

    seen = []
    previous = signal.signal(signal.SIGTERM, lambda sig, frame: seen.append(sig))
    try:
        server = GracefulServer(uvicorn.Config(app=lambda scope, receive, send: None))
        with server.capture_signals():
            server.handle_exit(signal.SIGTERM, None)
        assert server.should_exit
        assert seen == []  # uvicorn alone would re-raise SIGTERM here: exit code -15
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_sigint_keeps_uvicorn_behaviour():
    from b12.cli import GracefulServer

    seen = []
    previous = signal.signal(signal.SIGINT, lambda sig, frame: seen.append(sig))
    try:
        server = GracefulServer(uvicorn.Config(app=lambda scope, receive, send: None))
        with server.capture_signals():
            server.handle_exit(signal.SIGINT, None)
        assert seen == [signal.SIGINT]
    finally:
        signal.signal(signal.SIGINT, previous)
