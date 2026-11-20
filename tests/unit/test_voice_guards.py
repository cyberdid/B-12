"""Deterministic voice guards: phantom ASR text, whole-utterance stop phrases, interruption note."""

import pytest

from b12.audio.voice_guards import interruption_note, is_phantom_transcript, is_stop_phrase


@pytest.mark.parametrize(
    "text",
    [
        "Стоп.",
        "стоп!",
        "Досить",
        "стоп, стоп",
        "Стоп, стоп, стоп, стоп!",
        "Stop",
        "Капрі, стоп!",
        "  замовкни  ",
    ],
)
def test_whole_utterance_stop_phrases_stop(text):
    assert is_stop_phrase(text)


@pytest.mark.parametrize(
    "text",
    [
        "стоп, краще розкажи про погоду",
        "Не зупиняйся, продовжуй",
        "досить про це, що з комітом?",
        "",
        "автостоп",
    ],
)
def test_sentences_that_only_contain_a_stop_word_are_requests(text):
    assert not is_stop_phrase(text)


@pytest.mark.parametrize(
    "text",
    [
        "Дякую за перегляд!",
        "Продовження далі...",
        "Субтитри зробив DimaTorzok",
        "Thank you for watching.",
        "Спасибо за просмотр!",
        "так так так так",
    ],
)
def test_known_phantoms_and_repeats_are_dropped(text):
    assert is_phantom_transcript(text)


@pytest.mark.parametrize(
    "text",
    [
        "Дякую за перегляд вчорашнього звіту, що там далі?",
        "Так, так, роби",
        "Який сьогодні день?",
        "thank you, now open the file",
        "Субтитри зроби для цього відео",
        "Субтитри створи українською",
        "Корректор орфографии не работает",
        "До зустрічі!",
        "Thank you!",
        "You.",
    ],
)
def test_real_requests_are_kept(text):
    assert not is_phantom_transcript(text)


def test_interruption_note_names_the_request_and_what_was_spoken():
    note = interruption_note("Розкажи про погоду", "Погода сьогодні хмарна.")
    assert note.startswith("[службова примітка")
    assert "«Розкажи про погоду»" in note and "«Погода сьогодні хмарна.»" in note
    assert "перервано" in note


def test_interruption_note_before_any_speech_and_after_a_stop_phrase():
    note = interruption_note("Що нового?", "", stopped=True)
    assert "стоп-фразою" in note and "не встигла" in note


def test_interruption_note_clips_long_text():
    note = interruption_note("x" * 1000, "y" * 1000)
    assert len(note) < 700
