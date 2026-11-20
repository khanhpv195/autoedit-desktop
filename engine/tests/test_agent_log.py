import json
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage
from autoedit.agent.log import serialize_message


def test_assistant_message_serialised_with_tool_input():
    m = AssistantMessage(content=[TextBlock("Mình cắt"), ToolUseBlock("1", "mcp__autoedit__set_edl", {"edl": {"keep": []}})],
                         model="m")
    rec = serialize_message(m)
    assert rec["type"] == "sdk" and rec["kind"] == "AssistantMessage"
    assert "set_edl" in json.dumps(rec) and "Mình cắt" in json.dumps(rec, ensure_ascii=False)


def test_image_data_is_replaced_by_placeholder():
    b64 = "A" * 5000
    m = UserMessage(content=[ToolResultBlock("1", [{"type": "text", "text": "frames"},
                                                    {"type": "image", "data": b64, "mimeType": "image/jpeg"},
                                                    {"type": "image", "source": {"type": "base64", "data": b64}}])])
    s = json.dumps(serialize_message(m))
    assert b64 not in s and "image omitted" in s and "frames" in s


def test_result_message_keeps_usage_and_subtype():
    r = ResultMessage(subtype="error_max_turns", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=15,
                      session_id="s", usage={"input_tokens": 10})
    rec = serialize_message(r)
    assert rec["subtype"] == "error_max_turns" and rec["usage"] == {"input_tokens": 10}


def test_secrets_are_redacted():
    from claude_agent_sdk import SystemMessage
    m = SystemMessage(subtype="init", data={"env": {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-secret"},
                                            "api_key": "sk-ant-api-secret", "output_tokens": 3})
    s = json.dumps(serialize_message(m))
    assert "secret" not in s and '"output_tokens": 3' in s
