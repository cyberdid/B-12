"""Reasoning-channel residue from a model reply never reaches the history."""

from b12.model import strip_channel_residue


def test_gemma_channel_residue_is_removed():
    # Seen live (gemma4:12b): this text went back into history, where Ollama counted
    # <channel|> as a special token and admission refused the request (context_mismatch).
    assert strip_channel_residue("thought\n<channel|>") == ""
    assert strip_channel_residue("Виправляю.\n\nthought\n<channel|>") == "Виправляю."


def test_gemma_reasoning_block_is_removed_with_its_text():
    # gemma4 template: `<|channel>thought\n<reasoning>\n<channel|><answer>`; its own
    # strip_thinking drops everything from `<|channel>` to `<channel|>`.
    assert (
        strip_channel_residue("<|channel>thought\nПитає про полив.\n<channel|>Раз на 2 дні.")
        == "Раз на 2 дні."
    )
    assert (
        strip_channel_residue("Ось.\n<|channel>thought\nміркую\n<channel|>\nДалі текст.")
        == "Ось.\nДалі текст."
    )
    # Ollama may drop the opener token and leave the channel name on its own line.
    assert strip_channel_residue("thought\nміркую про полив\n<channel|>Раз на 2 дні.") == (
        "Раз на 2 дні."
    )


def test_unclosed_gemma_reasoning_is_dropped():
    # No closer (the output budget ended inside reasoning): like the template, keep only
    # the text before the opener.
    assert strip_channel_residue("<|channel>thought\nміркую, міркую") == ""
    assert strip_channel_residue("Добре.\n<|channel>thought\nміркую") == "Добре."


def test_ordinary_text_is_kept():
    for text in (
        "I thought about it.",
        "Channel 5 is fine.",
        "Перший рядок.\n\nДругий.",
        "My first thought\nwas wrong.",
    ):
        assert strip_channel_residue(text) == text
