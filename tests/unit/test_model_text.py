"""Reasoning-channel residue from a model reply never reaches the history."""

from b12.model import strip_channel_residue


def test_gemma_channel_residue_is_removed():
    # Seen live (gemma4:12b): this text went back into history, where Ollama counted
    # <channel|> as a special token and admission refused the request (context_mismatch).
    assert strip_channel_residue("thought\n<channel|>") == ""
    assert strip_channel_residue("Виправляю.\n\nthought\n<channel|>") == "Виправляю."
    assert strip_channel_residue("<|channel>thought\nДобре.") == "Добре."


def test_ordinary_text_is_kept():
    for text in ("I thought about it.", "Channel 5 is fine.", "Перший рядок.\n\nДругий."):
        assert strip_channel_residue(text) == text
