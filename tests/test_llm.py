import io
import json
import urllib.error

import pytest

from medrag.llm import (
    EvrenLLM,
    LLMError,
    ThinkStripper,
    parse_extra_params,
    sse_delta,
    sse_parts,
    strip_think,
)

MSG = [{"role": "user", "content": "x"}]


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


def test_empty_then_ok_is_retried():
    answers = iter([
        {"choices": [{"message": {"content": None}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"content": "Tamam"}}]},
    ])
    llm = EvrenLLM("http://x/v1", api_key="K", post=lambda payload: next(answers))
    assert llm.complete([{"role": "user", "content": "x"}]) == "Tamam"


def test_error_mentions_refusal_and_model():
    resp = {
        "choices": [{"message": {"content": None, "refusal": "yardımcı olamam"}, "finish_reason": "stop"}],
        "usage": {"evren": {"routed_model": "m1"}},
    }
    with pytest.raises(LLMError, match="yardımcı olamam.*m1"):
        make(resp).complete([{"role": "user", "content": "x"}])


def test_malformed_response():
    with pytest.raises(LLMError):
        make({"oops": 1}).complete([{"role": "user", "content": "x"}])


def test_sse_delta_handles_all_chunk_shapes():
    assert sse_delta('data: {"choices": [{"delta": {"content": "Merhaba"}}]}') == "Merhaba"
    assert sse_delta('data: {"choices": [{"delta": {"role": "assistant"}}]}') is None
    # son parça: kullanım bilgisi, 'choices' boş
    assert sse_delta('data: {"choices": [], "usage": {"total_tokens": 5}}') is None
    assert sse_delta("data: [DONE]") is None
    assert sse_delta(": keep-alive") is None
    assert sse_delta("data: {bozuk json") is None


# --- Düşünen modeller, ek parametreler, yeniden deneme ---


class FakeResp:
    def __init__(self, body=b"", lines=()):
        self.body, self.lines = body, list(lines)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body

    def __iter__(self):
        return iter(self.lines)


def test_inline_think_blocks_are_stripped_from_content():
    llm = make({"choices": [{"message": {"content": "<think>önce düşün</think>\nCevap burada."}}]})
    assert llm.complete(MSG) == "Cevap burada."
    assert strip_think("düşünce</think>Nihai") == "Nihai"
    assert strip_think("<think>yarım kaldı") == ""


def test_reasoning_only_answer_is_not_used_by_default():
    resp = {"choices": [{"message": {"content": "", "reasoning": "KARAR: EVET"}, "finish_reason": "stop"}]}
    with pytest.raises(LLMError, match="reasoning_chars=11"):
        make(resp).complete(MSG)


def test_reasoning_fallback_only_when_caller_accepts_it():
    resp = {"choices": [{"message": {"content": None, "reasoning_content": "taslak\nKARAR: HAYIR"}}]}

    def final_only(text):
        last = text.strip().splitlines()[-1]
        return last if last.startswith("KARAR:") else None

    assert make(resp).complete(MSG, reasoning_fallback=final_only) == "KARAR: HAYIR"
    assert make(resp).complete_detailed(MSG, reasoning_fallback=final_only).reasoning.startswith("taslak")
    with pytest.raises(LLMError):  # geri çağrı reddederse taslak cevap sayılmaz
        make(resp).complete(MSG, reasoning_fallback=lambda text: None)


def test_length_truncation_doubles_max_tokens_on_retry():
    seen = []
    answers = iter([
        {"choices": [{"message": {"content": None, "reasoning": "uzun düşünce"}, "finish_reason": "length"}]},
        {"choices": [{"message": {"content": "Tamam"}, "finish_reason": "stop"}]},
    ])

    def post(payload):
        seen.append(payload["max_tokens"])
        return next(answers)

    llm = EvrenLLM("http://x/v1", api_key="K", post=post)
    assert llm.complete(MSG, max_tokens=300) == "Tamam"
    assert seen == [300, 600]


def test_extra_params_are_merged_but_cannot_replace_messages_or_model():
    seen = {}

    def post(payload):
        seen.update(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    llm = EvrenLLM(
        "http://x/v1", "m1", api_key="K", post=post,
        extra_params={"chat_template_kwargs": {"enable_thinking": False}, "model": "kötü", "messages": []},
    )
    llm.complete(MSG, extra={"top_p": 0.5})
    assert seen["chat_template_kwargs"] == {"enable_thinking": False} and seen["top_p"] == 0.5
    assert seen["model"] == "m1" and seen["messages"] == MSG


def test_parse_extra_params():
    assert parse_extra_params("") == {} and parse_extra_params(None) == {}
    assert parse_extra_params('{"a": {"b": 1}}') == {"a": {"b": 1}}
    for bad in ("{bozuk", "[1, 2]"):
        with pytest.raises((ValueError, TypeError)):
            parse_extra_params(bad)


def test_content_given_as_part_list():
    parts = [{"type": "text", "text": "Parça"}, {"type": "text", "text": " iki"}]
    assert make({"choices": [{"message": {"content": parts}}]}).complete(MSG) == "Parça iki"


def test_http_retries_server_errors_then_succeeds_and_respects_retry_after():
    sleeps, calls = [], []
    err = urllib.error.HTTPError("http://x", 429, "slow", {"Retry-After": "2"}, io.BytesIO(b""))

    def opener(req, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise err
        if len(calls) == 2:
            raise TimeoutError("zaman aşımı")
        return FakeResp(body=json.dumps({"choices": [{"message": {"content": "iyi"}}]}).encode())

    llm = EvrenLLM("http://x/v1", api_key="K", opener=opener, sleep=sleeps.append, timeout=7)
    assert llm.complete(MSG) == "iyi"
    assert calls == [7, 7, 7] and sleeps == [2.0, 10.0]


def test_http_client_error_is_not_retried_and_network_failure_is_llm_error():
    calls = []

    def bad_request(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError("http://x", 400, "bad", {}, io.BytesIO(b""))

    llm = EvrenLLM("http://x/v1", api_key="K", opener=bad_request, sleep=lambda s: None)
    with pytest.raises(LLMError, match="HTTP 400"):
        llm.complete(MSG)
    assert len(calls) == 1

    def down(req, timeout):
        raise ConnectionResetError("koptu")

    llm = EvrenLLM("http://x/v1", api_key="K", opener=down, sleep=lambda s: None, max_retries=2)
    with pytest.raises(LLMError, match="ConnectionResetError"):
        llm.complete(MSG)


def sse(content=None, reasoning=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    return ("data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n").encode()


def test_stream_skips_reasoning_but_stream_parts_exposes_it():
    lines = [sse(reasoning="düşünüyor"), sse(content="Merhaba"), sse(content=" dünya"), b"data: [DONE]\n"]
    llm = EvrenLLM("http://x/v1", api_key="K", opener=lambda req, timeout: FakeResp(lines=lines))
    assert list(llm.stream(MSG)) == ["Merhaba", " dünya"]
    assert list(llm.stream_parts(MSG)) == [
        ("reasoning", "düşünüyor"), ("content", "Merhaba"), ("content", " dünya"),
    ]


def test_stream_payload_has_stream_flag_and_extra():
    seen = {}

    def opener(req, timeout):
        seen.update(json.loads(req.data))
        return FakeResp(lines=[sse(content="a")])

    llm = EvrenLLM("http://x/v1", api_key="K", opener=opener, extra_params={"reasoning_effort": "low"})
    assert list(llm.stream(MSG)) == ["a"]
    assert seen["stream"] is True and seen["reasoning_effort"] == "low"


def test_stream_strips_inline_think_even_when_tags_are_split():
    pieces = ["<th", "ink>gizli ", "düşünce</th", "ink>Gö", "rünen cevap"]
    lines = [sse(content=p) for p in pieces]
    llm = EvrenLLM("http://x/v1", api_key="K", opener=lambda req, timeout: FakeResp(lines=lines))
    assert "".join(llm.stream(MSG)) == "Görünen cevap"


def test_think_stripper_keeps_lookalike_text_and_flushes_tail():
    s = ThinkStripper()
    out = s.feed("a <b") + s.feed("> c") + s.flush()
    assert out == "a <b> c"


def test_stream_network_error_becomes_llm_error():
    def broken(req, timeout):
        raise TimeoutError("yok")

    llm = EvrenLLM("http://x/v1", api_key="K", opener=broken)
    with pytest.raises(LLMError):
        list(llm.stream(MSG))


def test_sse_parts_reasoning_fields():
    assert sse_parts('data: {"choices": [{"delta": {"reasoning": "r"}}]}') == (None, "r")
    assert sse_parts('data: {"choices": [{"delta": {"content": "c", "reasoning_content": "r"}}]}') == ("c", "r")


def test_with_model_keeps_url_and_key():
    llm = EvrenLLM("http://x/v1", "a", api_key="K", timeout=9)
    other = llm.with_model("b", timeout=3)
    assert other.model == "b" and other.url == llm.url and other.api_key == "K" and other.timeout == 3
