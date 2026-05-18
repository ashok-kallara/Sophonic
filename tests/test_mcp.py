"""Tests for MCP server: tool list, feature gating."""

from unittest.mock import patch


def test_all_tools_registered_when_all_features_on(use_fixture_vault):
    from sophonic.tools import build_registry

    reg = build_registry()
    names = set(reg.keys())

    # Core obsidian tools always present
    assert "obsidian_add_task" in names
    assert "obsidian_list_tasks" in names
    assert "obsidian_daily_note" in names
    assert "obsidian_rollover" in names
    assert "reminder_create" in names

    # Integration tools present when features on
    assert "gcal_events_today" in names
    assert "gmail_unread" in names
    assert "slack_unread" in names
    assert "zoom_transcripts" in names
    assert "zoom_save_transcript" in names


def test_google_tools_absent_when_feature_disabled(use_fixture_vault, monkeypatch):
    from sophonic.config import load_config
    load_config.cache_clear()
    monkeypatch.setenv("SOPHONIC_VAULT", str(use_fixture_vault))

    # Patch features before build_registry is called
    with patch("sophonic.tools.load_config") as mock_cfg:
        from sophonic.config import Config, FeaturesConfig
        cfg = Config()
        cfg.features.google = False
        mock_cfg.return_value = cfg

        from sophonic.tools import _REGISTRY
        _REGISTRY.clear()

        from sophonic.tools import build_registry
        reg = build_registry()

    gcal_tools = [k for k in reg if k.startswith("gcal_") or k.startswith("gmail_")]
    assert gcal_tools == []

    _REGISTRY.clear()
    load_config.cache_clear()


def test_tool_names_are_namespaced(use_fixture_vault):
    from sophonic.tools import build_registry

    reg = build_registry()
    prefixes = {name.split("_")[0] for name in reg}
    # All tools should be in one of the known namespaces
    assert prefixes <= {"obsidian", "gcal", "gmail", "slack", "zoom", "reminder"}


def test_mcp_instructions_contains_skill_index(use_fixture_vault):
    """The FastMCP server's instructions= should include skill names."""
    from unittest.mock import patch, MagicMock
    from sophonic import skills as _skills

    fake_skills = [
        _skills.SkillMeta(name="gcal", description="Calendar events", tools=[], body="gcal body"),
    ]

    captured = {}

    class FakeMCP:
        def __init__(self, name, instructions=""):
            captured["instructions"] = instructions
        def add_tool(self, fn, name, description=""):
            pass
        def prompt(self, name, description=""):
            def decorator(fn):
                return fn
            return decorator
        def run(self, transport):
            pass

    with patch("sophonic.mcp_server.FastMCP", FakeMCP), \
         patch.object(_skills, "discover", return_value=fake_skills), \
         patch("sophonic.tools.build_registry", return_value={}):
        from sophonic import mcp_server
        import importlib
        importlib.reload(mcp_server)
        mcp_server.main()

    assert "gcal" in captured["instructions"]
    assert "Calendar events" in captured["instructions"]


def test_mcp_skill_load_tool_registered(use_fixture_vault):
    """skill_load should be registered as a tool in the MCP server."""
    from unittest.mock import patch, MagicMock
    from sophonic import skills as _skills

    fake_skills = [
        _skills.SkillMeta(name="gcal", description="desc", tools=[], body=""),
    ]

    registered_tools = {}

    class FakeMCP:
        def __init__(self, name, instructions=""):
            pass
        def add_tool(self, fn, name, description=""):
            registered_tools[name] = fn
        def prompt(self, name, description=""):
            def decorator(fn):
                return fn
            return decorator
        def run(self, transport):
            pass

    with patch("sophonic.mcp_server.FastMCP", FakeMCP), \
         patch.object(_skills, "discover", return_value=fake_skills), \
         patch("sophonic.tools.build_registry", return_value={}):
        from sophonic import mcp_server
        import importlib
        importlib.reload(mcp_server)
        mcp_server.main()

    assert "skill_load" in registered_tools
