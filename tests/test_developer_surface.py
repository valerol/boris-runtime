from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = (
    PROJECT_ROOT
    / "mcp_server"
    / "ui"
    / "developer_surface_v2.html"
)
def test_operator_resume_uses_direct_server_semantic_route():
    source = SURFACE_PATH.read_text(encoding="utf-8")

    assert 'data-surface-version="2.4"' in source
    assert 'sendRequest("tools/call"' in source
    assert 'name: "boris.execute"' in source
    assert "continuation_token: hold.continuation_token" in source
    assert "operator_input: operatorInput" in source
    assert "ui/message" not in source
    assert "ui/update-model-context" not in source
    assert "sendFollowUpMessage" not in source
    assert "CHATGPT_HOST_ONLY" not in source
