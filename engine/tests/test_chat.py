import json

import pytest
from claude_agent_sdk import ResultMessage

from autoedit.agent.chat import CHAT_SCHEMA, build_chat_message, clean_reply, load_history, run_chat_turn
from autoedit.errors import AgentFailed, BadInput
from autoedit.prep import Prepared
from autoedit.prep.probe import MediaInfo
from autoedit.project import Project
from autoedit.resources import agent_dir
from autoedit.transcript import Word

PLAN = {"summary": ["Thời lượng: ~30s — khách yêu cầu", "Hook: Chân vòng kiềng vẫn đẹp"],
        "prompt": "Cắt còn khoảng 30s, mở bằng câu 'chân vòng kiềng' (88.4s), kết bằng giỏ hàng.",
        "target_seconds": [33, 27], "length_source": "customer", "length_reason": "khách muốn 30s",
        "hook": "Chân vòng kiềng vẫn đẹp", "cta": "BẤM GIỎ HÀNG 👇"}


def project(tmp_path, **over):
    (tmp_path / "input").mkdir(exist_ok=True)
    (tmp_path / "input" / "c.mp4").write_bytes(b"x")
    data = {"niche": "thoi-trang", "clips": ["c.mp4"], "cta_text": "MUA NGAY"} | over
    (tmp_path / "project.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return Project.load(tmp_path)


def prep(tmp_path):
    return Prepared(info=MediaInfo(30, 1080, 1920, 30, False, True), normalized=tmp_path / "n.mp4",
                    words=[Word("chân", 1.0, 1.3), Word("vòng", 1.3, 1.6), Word("kiềng", 1.6, 2.0)], keyframes=[])


def res(structured):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                         num_turns=1, session_id="s", structured_output=structured)


def fake(*turns, seen=None):
    it = iter(turns)

    async def q(prompt, options):
        async for m in prompt:
            if seen is not None:
                seen.append((m["message"]["content"][0]["text"], options.output_format))
        yield res(next(it))
    return q


async def test_opening_turn_then_plan_round_trip(tmp_path):
    p, seen = project(tmp_path), []
    q = fake({"reply": "Clip có 1 người nói 1 câu. Anh muốn dài bao nhiêu?", "suggestions": ["Giữ trọn lời", " ", "Rút ~30s"],
              "plan": None},
             {"reply": "Đây là kế hoạch, anh bấm Bắt đầu edit nhé.", "suggestions": ["x"], "plan": PLAN}, seen=seen)
    first = await run_chat_turn(p, prep(tmp_path), "", agent_dir(), query_fn=q, now=lambda: 100.0)
    assert first["role"] == "assistant" and first["plan"] is None
    assert first["suggestions"] == ["Giữ trọn lời", "Rút ~30s"]
    assert [m["role"] for m in load_history(tmp_path)] == ["assistant"]     # no empty customer bubble
    text, fmt = seen[0]
    assert fmt == {"type": "json_schema", "schema": CHAT_SCHEMA}
    assert "opening turn" in text and "[1.00-2.00] chân vòng kiềng" in text and "Default CTA text: MUA NGAY" in text
    assert "hook card never covers the speaker's face" in text and "bottom-left for the last 3.5 s" in text

    second = await run_chat_turn(p, prep(tmp_path), "  cắt còn 30s  ", agent_dir(), query_fn=q, now=lambda: 101.0)
    assert second["plan"]["target_seconds"] == [27.0, 33.0]            # sorted
    assert second["suggestions"] == []                                   # a plan replaces quick replies
    hist = load_history(tmp_path)
    assert [(m["role"], m.get("text")) for m in hist][1] == ("user", "cắt còn 30s")
    assert hist[2]["plan"]["prompt"].startswith("Cắt còn khoảng 30s")
    # the second turn sends the whole conversation back
    assert "BẠN: Clip có 1 người nói 1 câu." in seen[1][0] and "New customer message: cắt còn 30s" in seen[1][0]


async def test_history_survives_reload_and_bad_files(tmp_path):
    p = project(tmp_path)
    (tmp_path / "chat.json").write_text("{broken", encoding="utf-8")
    assert load_history(tmp_path) == []
    await run_chat_turn(p, prep(tmp_path), "xin chào", agent_dir(),
                        query_fn=fake({"reply": "Chào anh", "suggestions": [], "plan": None}))
    data = json.loads((tmp_path / "chat.json").read_text(encoding="utf-8"))
    assert data["v"] == 1 and [m["text"] for m in data["messages"]] == ["xin chào", "Chào anh"]


async def test_failed_turn_saves_nothing(tmp_path):
    p = project(tmp_path)
    with pytest.raises(AgentFailed):
        await run_chat_turn(p, prep(tmp_path), "hello", agent_dir(),
                            query_fn=fake({"reply": "", "suggestions": [], "plan": None}))
    assert load_history(tmp_path) == []


async def test_empty_message_only_opens(tmp_path):
    p = project(tmp_path)
    await run_chat_turn(p, prep(tmp_path), "", agent_dir(),
                        query_fn=fake({"reply": "Chào", "suggestions": [], "plan": None}))
    with pytest.raises(BadInput):
        await run_chat_turn(p, prep(tmp_path), "   ", agent_dir(), query_fn=fake({}))
    with pytest.raises(BadInput):
        await run_chat_turn(p, prep(tmp_path), "x" * 2001, agent_dir(), query_fn=fake({}))


@pytest.mark.parametrize("plan", [
    {**PLAN, "prompt": " "},
    {**PLAN, "target_seconds": [30]},
    {**PLAN, "target_seconds": [0, 0]},
    {**PLAN, "target_seconds": ["30", 40]},
    "làm đi",
])
def test_broken_plan_is_an_error(plan):
    with pytest.raises(AgentFailed):
        clean_reply({"reply": "ok", "suggestions": [], "plan": plan})


def test_clean_reply_tidies():
    out = clean_reply({"reply": " ok ", "suggestions": ["a" * 80, "b", "c", "d", "e"],
                       "plan": {**PLAN, "length_source": "weird", "cta": "x" * 40}})
    assert out["reply"] == "ok" and out["suggestions"] == []
    assert out["plan"]["length_source"] == "ai" and len(out["plan"]["cta"]) == 30
    out = clean_reply({"reply": "ok", "suggestions": ["a" * 80, "b", "c", "d", "e"], "plan": None})
    assert out["suggestions"] == ["a" * 60, "b", "c", "d"]


def test_message_mentions_full_speech_offer_and_voiceover(tmp_path):
    p = project(tmp_path, voiceover={"enabled": True, "voice_id": "v", "voice_name": "Mai"},
                product_info="Quần ống rộng 159K")
    pr = prep(tmp_path)
    pr.spans = [("a.mp4", 0.0, 10.0), ("b.mp4", 10.0, 30.0)]
    pr.words = [Word("x", 12.0, 12.3), Word("y", 12.3, 12.6), Word("nhà", 13.0, 13.4)]
    text = build_chat_message(p, pr, [], "", agent_dir())["message"]["content"][0]["text"]
    assert 'offer "Giữ trọn lời" first' in text and "'nhà'" in text
    assert "Lồng tiếng AI: bật" in text and "Quần ống rộng 159K" in text
    assert "card 1 MUST" not in text
