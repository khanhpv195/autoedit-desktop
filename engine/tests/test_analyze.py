import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage
from autoedit.agent.analyze import run_analyze, build_analyze_message, CARDS_SCHEMA
from autoedit.errors import AgentFailed, RateLimited
from autoedit.prep import Prepared
from autoedit.prep.probe import MediaInfo
from autoedit.resources import agent_dir
from autoedit.transcript import Word

CARD = {"title": "Giá sốc mở đầu", "hook": "CHỈ 189K", "outline": ["Giá", "Swatch", "Giỏ hàng"],
        "prompt": "Mở bằng câu giá 189K, cắt gọn phần chào, kết bằng giỏ hàng"}


def prep(tmp_path):
    from PIL import Image
    kf = tmp_path / "kf_0.jpg"; Image.new("RGB", (54, 96), "red").save(kf)
    return Prepared(info=MediaInfo(20, 1080, 1920, 30, False, True), normalized=tmp_path / "n.mp4",
                    words=[Word("son", 1.0, 1.3), Word("189K", 1.4, 2.0)], keyframes=[kf])


def res(structured, is_error=False):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error,
                         num_turns=1, session_id="s", structured_output=structured)


def test_message_has_transcript_library_and_image(tmp_path):
    m = build_analyze_message(prep(tmp_path), "my-pham", agent_dir(), exclude=["Cũ"])
    text = m["message"]["content"][0]["text"]
    assert "[1.00-2.00] son 189K" in text and "Swatch thật" in text and "Cũ" in text
    assert m["message"]["content"][1]["type"] == "image"


async def test_returns_three_cards(tmp_path):
    seen = {}
    async def q(prompt, options):
        seen["fmt"] = options.output_format
        async for m in prompt:
            seen["msg"] = m
        yield res({"cards": [CARD, CARD, CARD]})
    cards = await run_analyze(prep(tmp_path), "my-pham", agent_dir(), query_fn=q)
    assert len(cards) == 3 and cards[0]["hook"] == "CHỈ 189K"
    assert seen["fmt"] == {"type": "json_schema", "schema": CARDS_SCHEMA}


async def test_bad_output_raises(tmp_path):
    async def q(prompt, options):
        yield res({"cards": [CARD]})
    with pytest.raises(AgentFailed):
        await run_analyze(prep(tmp_path), "chung", agent_dir(), query_fn=q)


async def test_rate_limit(tmp_path):
    async def q(prompt, options):
        yield AssistantMessage(content=[], model="m", error="rate_limit")
    with pytest.raises(RateLimited):
        await run_analyze(prep(tmp_path), "chung", agent_dir(), query_fn=q)
