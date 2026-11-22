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


async def test_not_logged_in_maps_to_no_auth(tmp_path):
    from claude_agent_sdk import ResultError
    from autoedit.errors import NoAuth
    async def q(prompt, options):
        yield AssistantMessage(content=[], model="m")
        raise ResultError("e", {"result": "Not logged in · Please run /login"})
    with pytest.raises(NoAuth):
        await run_analyze(prep(tmp_path), "chung", agent_dir(), query_fn=q)


async def test_rate_limit_variants(tmp_path):
    import time
    from claude_agent_sdk import RateLimitEvent, RateLimitInfo, ResultError
    async def rejected(prompt, options):
        yield RateLimitEvent(rate_limit_info=RateLimitInfo(status="rejected", resets_at=int(time.time()) + 60),
                             uuid="u", session_id="s")
    with pytest.raises(RateLimited) as e:
        await run_analyze(prep(tmp_path), "chung", agent_dir(), query_fn=rejected)
    assert e.value.retry_at
    async def raised(prompt, options):
        yield AssistantMessage(content=[], model="m")
        raise ResultError("e", {"api_error_status": 429})
    with pytest.raises(RateLimited):
        await run_analyze(prep(tmp_path), "chung", agent_dir(), query_fn=raised)


def test_no_images_means_no_image_broll_in_instructions(tmp_path):
    text = build_analyze_message(prep(tmp_path), "thoi-trang", agent_dir(), exclude=[])["message"]["content"][0]["text"]
    assert "b-roll ảnh sản phẩm" not in text
    assert "Không có ảnh sản phẩm" in text


def test_silent_clip_plus_talking_clip_asks_for_a_full_speech_card(tmp_path):
    p = prep(tmp_path)
    p.spans = [("a", 0.0, 10.0), ("b", 10.0, 30.0)]
    p.words = [Word("Mà", 10.2, 10.4), Word("quần", 10.4, 10.8), Word("đẹp", 11.0, 11.3), Word("nhà", 28.0, 28.3)]
    text = build_analyze_message(p, "thoi-trang", agent_dir(), exclude=[])["message"]["content"][0]["text"]
    assert "Giữ trọn lời" in text and "lồng tiếng clip 2 đầy đủ đến từ cuối cùng 'nhà'" in text
    assert "bỏ tiếng clip 1" in text and "3.5 s cuối" in text
    assert 'Clip 1 "a": 0.00-10.00s, no speech' in text and "last word 'nhà'" in text


def test_single_clip_has_no_full_speech_card(tmp_path):
    text = build_analyze_message(prep(tmp_path), "my-pham", agent_dir(), exclude=[])["message"]["content"][0]["text"]
    assert "Giữ trọn lời" not in text and "Keep the speaker's order" in text
