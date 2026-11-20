"""Small deterministic guards around a recognized utterance, applied before any agent turn.

- Phantom transcripts: Whisper writes stock phrases ("Дякую за перегляд!", "Субтитри зробив …")
  or one word repeated when it hears silence or noise. Such text never reaches the model.
- Stop phrase: an utterance that is only "стоп" / "досить" / "stop" stops B-12's speech and the
  running turn through the control path; it is not sent to the model. A longer sentence that
  merely contains the word ("стоп, краще розкажи про …") is an ordinary request.
- Interruption note: after a barge-in the next request carries a short data note, so the model
  knows its previous answer was cut off and what the user had asked; the cancelled turn itself
  is never persisted, so without the note the model has no trace of it.
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s']+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, apostrophes unified, punctuation dropped, whitespace collapsed."""
    text = unicodedata.normalize("NFC", text).lower()
    text = text.replace("’", "'").replace("ʼ", "'").replace("`", "'")
    text = _PUNCT.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


STOP_PHRASES = frozenset(
    {
        "стоп",
        "досить",
        "зупинись",
        "зупинися",
        "замовкни",
        "тихо",
        "капрі стоп",
        "стоп капрі",
        "stop",
        "capri stop",
    }
)


def is_stop_phrase(text: str, phrases: frozenset[str] = STOP_PHRASES) -> bool:
    """True only when the whole utterance is a stop phrase (one may repeat: "стоп стоп")."""
    norm = normalize(text)
    if not norm:
        return False
    if norm in phrases:
        return True
    words = norm.split()
    return len(words) <= 8 and len(set(words)) == 1 and words[0] in phrases


# Stock phrases Whisper emits on silence, music or noise (uk/ru/en video-subtitle residue).
# Matched against the whole normalized utterance, so real speech that contains them is kept.
_PHANTOM_EXACT = frozenset(
    {
        "дякую за перегляд",
        "дякую за увагу",
        "дякуємо за перегляд",
        "дякую що дивилися",
        "підписуйтесь на канал",
        "підписуйтеся на канал",
        "ставте лайки",
        "продовження далі",
        "продовження буде",
        "до нових зустрічей",
        "спасибо за просмотр",
        "спасибо за внимание",
        "продолжение следует",
        "подписывайтесь на канал",
        "thank you for watching",
        "thanks for watching",
        "please subscribe",
        "subscribe to the channel",
        "like and subscribe",
    }
)
_PHANTOM_PREFIX = (  # past-tense credit lines only: "субтитри зроби …" is a real request
    "субтитри зробив",
    "субтитри зробила",
    "субтитри створив",
    "субтитри створила",
    "субтитри створено",
    "субтитри підготував",
    "субтитри підготувала",
    "редактор субтитрів",
    "субтитры сделал",
    "субтитры создавал",
    "редактор субтитров",
    "корректор а егорова",
    "subtitles by",
    "transcribed by",
    "amara org",
)


def is_phantom_transcript(text: str) -> bool:
    """True for known silence/noise hallucinations and for one token repeated four or more times."""
    norm = normalize(text)
    if not norm:
        return False
    if norm in _PHANTOM_EXACT:
        return True
    if any(norm.startswith(prefix) for prefix in _PHANTOM_PREFIX):
        return True
    words = norm.split()
    return len(words) >= 4 and len(set(words)) == 1


def _clip(text: str, limit: int) -> str:
    text = _SPACES.sub(" ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def interruption_note(previous_request: str, spoken: str, *, stopped: bool = False) -> str:
    """Data note prepended to the next request after an interrupted voice answer."""
    how = "зупинено стоп-фразою" if stopped else "перервано: співрозмовник заговорив"
    lead = "[службова примітка, не репліка співрозмовника: "
    parts = [f"{lead}твою попередню голосову відповідь {how}"]
    if previous_request.strip():
        parts.append(f"; запит був: «{_clip(previous_request, 200)}»")
    if spoken.strip():
        parts.append(f"; до перерви прозвучав початок: «{_clip(spoken, 200)}»")
    else:
        parts.append("; відповісти ти ще не встигла")
    parts.append(". Не повторюй перервану відповідь, якщо про це не просять.]")
    return "".join(parts)
