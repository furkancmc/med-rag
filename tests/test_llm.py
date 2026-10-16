import pytest

from medrag.llm import EvrenLLM, LLMError


def make(response):
    return EvrenLLM("http://x/v1", api_key="K", post=lambda payload: response)


def test_complete_returns_stripped_content():
    llm = make({"choices": [{"message": {"content": "  Merhaba \n"}}]})
    assert llm.complete([{"role": "user", "content": "x"}]) == "Merhaba"


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_content_is_a_clear_error(content):
    llm = make({"choices": [{"message": {"content": content}, "finish_reason": "length"}]})
    with pytest.raises(LLMError, match="length"):
        llm.complete([{"role": "user", "content": "x"}])


def test_malformed_response():
    with pytest.raises(LLMError):
        make({"oops": 1}).complete([{"role": "user", "content": "x"}])
