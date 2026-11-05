"""Working notes for one turn: findings the model writes down while it reads, so they survive the
trimming of old tool results. The agent keeps them in turn state; nothing here touches memory."""

from pydantic import Field

from b12.tools._common import Args

NOTE_MAX_CHARS = 600
NOTES_MAX = 60


class NoteArgs(Args):
    text: str = Field(min_length=1, max_length=NOTE_MAX_CHARS)


async def note_add(args: NoteArgs) -> dict:  # the agent intercepts note_add; this is a fallback
    return {"saved": True}


def register(registry):
    registry.register(
        "note_add",
        "Записати знахідку з прочитаного: файл, номер рядка і що саме не так. Нотатки живуть до "
        "кінця ходу й не втрачаються, коли старі результати стискаються.",
        NoteArgs,
        note_add,
        "turn.notes",
    )
