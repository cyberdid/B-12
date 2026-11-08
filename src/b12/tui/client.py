"""HTTP client for the loopback B-12 API. Only the owner token is needed; no model code here."""

import base64
import json
from collections.abc import AsyncIterator, Iterable

import httpx

from b12.tui.voice import MAX_RECORD_SECONDS, MAX_WAV_BYTES, VoiceError


def parse_ndjson(lines: Iterable[str]) -> list[dict]:
    """Decode NDJSON event lines, skipping blanks. Malformed lines raise ValueError."""
    return [json.loads(line) for line in lines if line.strip()]


class ApiClient:
    def __init__(
        self, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(30.0, read=None),
            transport=transport,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def _json(self, method: str, path: str, **kwargs):
        response = await self.http.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def me(self) -> dict:
        return await self._json("GET", "/api/me")

    async def sessions(self) -> list[str]:
        return await self._json("GET", "/api/sessions")

    async def new_session(self) -> str:
        return (await self._json("POST", "/api/sessions", json={}))["session_id"]

    async def history(self, session_id: str) -> list[dict]:
        return await self._json("GET", f"/api/sessions/{session_id}/history")

    async def approvals(self) -> list[dict]:
        return await self._json("GET", "/api/approvals")

    async def decide(self, operation_id: str, approve: bool) -> dict:
        return await self._json("POST", f"/api/approvals/{operation_id}", json={"approve": approve})

    async def memory_records(self, limit: int = 200) -> list[dict]:
        return await self._json("GET", f"/api/memory/records?limit={limit}")

    async def memory_search(self, query: str) -> list[dict]:
        return await self._json("GET", "/api/memory", params={"q": query})

    async def memory_add(self, text: str) -> dict:
        return await self._json("POST", "/api/memory", json={"text": text})

    async def memory_forget(self, memory_id: str) -> dict:
        return await self._json("DELETE", f"/api/memory/{memory_id}")

    async def set_consent(self, consent: bool) -> dict:
        return await self._json("POST", "/api/control/consent", json={"consent": consent})

    async def cancel(self, turn_id: str) -> None:
        await self._json("POST", f"/api/turns/{turn_id}/cancel", json={})

    async def voice_status(self) -> dict:
        return await self._json("GET", "/api/voice/status", timeout=10.0)

    async def voice_mute(self, muted: bool) -> dict:
        if not isinstance(muted, bool):
            raise VoiceError("invalid_mute_state")
        return await self._json("POST", "/api/voice/mute", json={"muted": muted}, timeout=10.0)

    async def voice_asr(
        self, pcm: bytes, sample_rate: int = 16000, language: str = "auto"
    ) -> dict:
        if (
            not isinstance(pcm, bytes)
            or not isinstance(sample_rate, int)
            or isinstance(sample_rate, bool)
            or not 8000 <= sample_rate <= 48000
            or not 2 <= len(pcm) <= min(675_000, sample_rate * 2 * MAX_RECORD_SECONDS)
            or len(pcm) % 2
        ):
            raise VoiceError("invalid_voice_audio")
        if language not in ("auto", "uk", "en"):
            raise VoiceError("invalid_voice_language")
        return await self._json(
            "POST",
            "/api/voice/asr",
            json={
                "audio_b64": base64.b64encode(pcm).decode("ascii"),
                "sample_rate": sample_rate,
                "language": language,
            },
            timeout=httpx.Timeout(120.0, connect=5.0),
        )

    async def voice_tts(self, text: str, lang: str = "auto") -> bytes:
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise VoiceError("invalid_speech_text")
        if lang not in ("auto", "uk", "en"):
            raise VoiceError("invalid_voice_language")
        async with self.http.stream(
            "POST",
            "/api/voice/tts",
            json={"text": text, "lang": lang},
            timeout=httpx.Timeout(180.0, connect=5.0),
        ) as response:
            response.raise_for_status()
            wav = bytearray()
            try:
                async for chunk in response.aiter_bytes():
                    if len(wav) + len(chunk) > MAX_WAV_BYTES:
                        raise VoiceError("voice_response_too_large")
                    wav.extend(chunk)
                return bytes(wav)
            finally:
                wav.clear()

    async def chat(
        self, session_id: str, text: str, *, persist: bool, timeout_s: float = 600
    ) -> AsyncIterator[dict]:
        effective_timeout = max(timeout_s, 1800.0) if persist else timeout_s
        body = {
            "session_id": session_id,
            "text": text,
            "persist": persist,
            "timeout_s": effective_timeout,
        }
        async with self.http.stream("POST", "/api/chat", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    yield json.loads(line)

    async def resume(self, turn_id: str) -> AsyncIterator[dict]:
        async with self.http.stream("POST", f"/api/turns/{turn_id}/resume", json={}) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    yield json.loads(line)
