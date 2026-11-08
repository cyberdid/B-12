"""Offline visual preview: python -m b12.tui.preview. No API, model or host tools."""

import asyncio

from b12.tui.app import B12App
from b12.tui.chrome import NeonHeader


class PreviewClient:
    """Ephemeral sample conversations for trying the UI without configuring a backend."""

    def __init__(self):
        self.consent = True
        self.cancelled = False
        self.histories = {
            "preview-01": [
                {"role": "user", "content": "Привіт, Capri. Створімо щось неймовірне."},
                {
                    "role": "assistant",
                    "content": (
                        "Привіт! Неон увімкнено, кіберкіт прокинувся.\n\n"
                        "Це **офлайн-перегляд інтерфейсу**. Наведи на мене мишку, "
                        "погладь кліком або напиши повідомлення — покажу свої реакції."
                    ),
                },
            ]
        }
        self.records = [
            {"id": "preview-memory", "text": "Демонстраційна пам’ять: люблю неон і муркотіти."}
        ]

    async def me(self):
        return {"consent": self.consent, "owner": True}

    async def sessions(self):
        return list(self.histories)

    async def new_session(self):
        key = f"preview-{len(self.histories) + 1:02}"
        self.histories[key] = []
        return key

    async def history(self, session_id):
        return list(self.histories[session_id])

    async def approvals(self):
        return []

    async def memory_records(self, limit=200):
        return self.records[:limit]

    async def memory_search(self, query):
        return [r for r in self.records if query.casefold() in r["text"].casefold()]

    async def memory_forget(self, memory_id):
        self.records = [r for r in self.records if r["id"] != memory_id]
        return {"state": "complete"}

    async def set_consent(self, consent):
        self.consent = consent
        return {"consent": consent}

    async def cancel(self, turn_id):
        self.cancelled = True

    async def chat(self, session_id, text, *, persist, **kwargs):
        self.cancelled = False
        self.histories[session_id].append({"role": "user", "content": text})
        yield {"type": "turn_started", "turn_id": "preview-turn"}
        await asyncio.sleep(0.6)
        parts = [
            "Мурр! ",
            "У цьому офлайн-перегляді можна випробувати інтерфейс і мої анімації. ",
            "Для живої розмови запусти `b12 serve`, а потім `b12 tui`. ",
            "Я чекатиму на тебе праворуч. ♥",
        ]
        answer = ""
        for part in parts:
            if self.cancelled:
                yield {"type": "result", "state": "cancelled", "content": answer}
                return
            answer += part
            yield {"type": "text_delta", "text": part}
            await asyncio.sleep(0.16)
        self.histories[session_id].append({"role": "assistant", "content": answer})
        yield {"type": "result", "state": "completed", "content": answer}


class PreviewApp(B12App):
    TITLE = "Capri · Cybercat preview"

    async def on_mount(self):
        self.query_one(NeonHeader).preview = True
        await super().on_mount()


if __name__ == "__main__":
    PreviewApp(PreviewClient()).run()
