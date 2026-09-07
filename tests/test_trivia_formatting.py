import pytest

from toaster import trivia


@pytest.mark.asyncio
async def test_trivia_prepends_label(monkeypatch):
    monkeypatch.setattr(trivia, "load_trivia_config", lambda: {"history_size": 5})
    monkeypatch.setattr(trivia, "_save_history", lambda history, limit: None)
    monkeypatch.setattr(
        trivia,
        "get_gemini_response_with_key",
        lambda *_args, **_kwargs: ("Sure! Here is a trivia question: Which team won the 2023 World Series?", None),
    )

    result = await trivia.generate_and_store_trivia()

    assert result == "Trivia time: Which team won the 2023 World Series?"
