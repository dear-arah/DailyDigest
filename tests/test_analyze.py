import json

import pytest

from radar.analyze import AnalysisError, analyze, build_messages, parse_analysis
from radar.llm.chain import FallbackChain
from radar.llm.providers import ProviderError
from radar.models import Item

CONTEXT = "Agora offers a Conversational AI Engine."


class FakeProvider:
    def __init__(self, name, result=None, error=None):
        self.name = name
        self.result = result
        self.error = error

    def complete(self, system, user):
        if self.error:
            raise self.error
        return self.result


def make_item():
    return Item(
        title="Voice agent launch",
        url="https://example.com/a",
        text="A vendor released a realtime voice agent SDK.",
        published=None,
        source="Vendor Blog",
        tier=1,
    )


def payload(**overrides):
    data = {
        "summary": "A vendor shipped an SDK.",
        "score": 7,
        "tag": "threat",
        "product": "Conversational AI Engine",
        "angle": "Competes directly with the engine.",
    }
    data.update(overrides)
    return json.dumps(data)


def test_build_messages_includes_context_and_item_text():
    system, user = build_messages(make_item(), CONTEXT)

    assert CONTEXT in system
    assert "JSON" in system
    assert "Voice agent launch" in user
    assert "A vendor released a realtime voice agent SDK." in user
    assert "https://example.com/a" in user
    assert "Official" in user


def test_parse_plain_json():
    result = parse_analysis(payload())

    assert result.summary == "A vendor shipped an SDK."
    assert result.score == 7
    assert result.tag == "threat"
    assert result.product == "Conversational AI Engine"
    assert result.angle == "Competes directly with the engine."


def test_parse_fenced_json_with_prose():
    raw = f"Sure, here it is:\n```json\n{payload()}\n```\nHope that helps."

    assert parse_analysis(raw).score == 7


def test_parse_clamps_score_15_to_10():
    assert parse_analysis(payload(score=15)).score == 10
    assert parse_analysis(payload(score=-3)).score == 0


def test_parse_accepts_numeric_string_score():
    assert parse_analysis(payload(score="8")).score == 8


def test_parse_rejects_non_numeric_score():
    with pytest.raises(AnalysisError):
        parse_analysis(payload(score="high"))


def test_parse_rejects_unknown_tag():
    with pytest.raises(AnalysisError):
        parse_analysis(payload(tag="breaking"))


def test_parse_accepts_capitalized_tag():
    assert parse_analysis(payload(tag="Threat")).tag == "threat"
    assert parse_analysis(payload(tag=" FYI ")).tag == "fyi"


def test_parse_rejects_null_field():
    with pytest.raises(AnalysisError):
        parse_analysis(payload(summary=None))


def test_parse_rejects_missing_field():
    data = json.loads(payload())
    del data["angle"]

    with pytest.raises(AnalysisError):
        parse_analysis(json.dumps(data))


def test_parse_rejects_text_without_json():
    with pytest.raises(AnalysisError):
        parse_analysis("I could not analyze this.")


def test_parse_truncates_summary_and_angle():
    result = parse_analysis(payload(summary="s" * 900, angle="a" * 700))

    assert len(result.summary) == 600
    assert len(result.angle) == 400


def test_analyze_returns_analysis_from_chain():
    chain = FallbackChain([FakeProvider("a", result=payload())])

    result = analyze(make_item(), chain, CONTEXT)

    assert result is not None and result.tag == "threat"


def test_analyze_falls_through_on_unparseable_output():
    chain = FallbackChain([FakeProvider("a", result="no json here"), FakeProvider("b", result=payload(score=4))])

    result = analyze(make_item(), chain, CONTEXT)

    assert result is not None and result.score == 4


def test_analyze_returns_none_when_chain_fails():
    chain = FallbackChain([FakeProvider("a", error=ProviderError("down"))])

    assert analyze(make_item(), chain, CONTEXT) is None
