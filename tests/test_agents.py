import json
from pathlib import Path

import pytest

from opencode_model_sync import agents, i18n
from opencode_model_sync.agents import Agent, Worker
from opencode_model_sync.config import ConfigError, OpencodeConfig


@pytest.fixture(autouse=True)
def english():
    i18n.set_language("en")


def load(tmp_path: Path, data: dict) -> OpencodeConfig:
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return OpencodeConfig.load(path)


def saved(config: OpencodeConfig) -> dict:
    config.save()
    return json.loads(config.path.read_text(encoding="utf-8"))


def test_the_old_agent_map_is_no_agent_at_all(tmp_path):
    """The app speaks one map. The old key is nobody's agent, and a write leaves it on disk alone."""
    config = load(tmp_path, {"agent": {"coder": {"mode": "subagent", "prompt": "old words"}}})
    assert agents.agents(config) == []
    assert agents.agent(config, "coder") is None
    agents.save_agent(config, Agent(name="writer", description="d"))
    data = saved(config)
    assert data["agent"] == {"coder": {"mode": "subagent", "prompt": "old words"}}
    assert "prompt" not in data["agents"]["writer"]


def test_reads_the_map_and_its_rule_list(tmp_path):
    config = load(
        tmp_path,
        {
            "agents": {
                "coder": {
                    "mode": "subagent",
                    "model": {"providerID": "p", "model": "m", "variant": "high"},
                    "description": "d",
                    "steps": 12,
                    "permissions": [{"action": "edit", "resource": "*", "effect": "deny"}],
                },
                "lead": {"mode": "primary", "system": "plan first"},
            }
        },
    )
    by_name = {item.name: item for item in agents.agents(config)}
    assert by_name["coder"].model == "p/m#high"
    assert by_name["coder"].access == {"edit": "deny", "bash": None, "webfetch": None}
    assert by_name["coder"].steps == 12
    assert by_name["lead"].prompt == "plan first"
    assert by_name["lead"].steps is None


def test_team_writes_planner_and_restricted_subagents(tmp_path):
    config = load(tmp_path, {"$schema": "x", "theme": "dark"})
    members = agents.team(
        "planner",
        "anthropic/claude-opus-5-5",
        [Worker("coder", "coder", "opencode/glm-5.3-flash-free"), Worker("tester", "tester", None)],
        delegate_only=True,
    )
    agents.save_team(config, members, make_default=True)
    data = saved(config)

    assert data["theme"] == "dark"
    assert data["default_agent"] == "planner"
    planner = data["agents"]["planner"]
    assert planner["mode"] == "primary"
    assert planner["model"] == "anthropic/claude-opus-5-5"
    assert planner["permissions"] == [
        {"action": "edit", "resource": "*", "effect": "deny"},
        {"action": "bash", "resource": "*", "effect": "deny"},
        {"action": "task", "resource": "*", "effect": "deny"},
        {"action": "task", "resource": "coder", "effect": "allow"},
        {"action": "task", "resource": "tester", "effect": "allow"},
    ]
    assert "- coder: " in planner["system"] and "- tester: " in planner["system"]
    assert data["agents"]["coder"] == {
        "description": i18n.tr("role.coder.description"),
        "mode": "subagent",
        "model": "opencode/glm-5.3-flash-free",
        "system": i18n.tr("role.coder.prompt"),
    }
    assert {"action": "edit", "resource": "*", "effect": "deny"} in data["agents"]["tester"]["permissions"]
    assert "model" not in data["agents"]["tester"]


def test_team_keeps_settings_it_does_not_manage(tmp_path):
    config = load(tmp_path, {"agents": {"coder": {"mode": "subagent", "color": "#112233", "steps": 7}}})
    agents.save_team(config, agents.team("lead", None, [Worker("coder", "coder", "a/b")], True), make_default=False)
    coder = saved(config)["agents"]["coder"]
    assert coder["color"] == "#112233" and coder["steps"] == 7 and coder["model"] == "a/b"


def test_save_writes_steps_and_drops_the_deprecated_word(tmp_path):
    config = load(tmp_path, {"agents": {"x": {"mode": "all", "maxSteps": 30, "temperature": 0.5}}})
    item = agents.agent(config, "x")
    assert item.steps is None, "the deprecated word is not read"
    item.description = "desc"
    item.steps = 25
    agents.save_agent(config, item, "x")
    entry = saved(config)["agents"]["x"]
    assert entry["steps"] == 25
    assert "maxSteps" not in entry and "temperature" not in entry


def test_a_switch_off_custom_replaces_the_rules_it_shadows(tmp_path):
    config = load(
        tmp_path,
        {
            "agents": {
                "x": {
                    "mode": "all",
                    "permissions": [
                        {"action": "edit", "resource": "src/**", "effect": "allow"},
                        {"action": "bash", "resource": "*", "effect": "ask"},
                        {"action": "read", "resource": "*.env", "effect": "deny"},
                    ],
                }
            }
        },
    )
    item = agents.agent(config, "x")
    assert item.access == {"edit": "custom", "bash": "ask", "webfetch": None}
    assert item.has_custom_access
    item.access["edit"] = "allow"
    item.description = "desc"
    agents.save_agent(config, item, "x")
    rules = saved(config)["agents"]["x"]["permissions"]
    assert {"action": "edit", "resource": "src/**", "effect": "allow"} not in rules, "the switch replaced what it spelled"
    assert {"action": "read", "resource": "*.env", "effect": "deny"} in rules, "an action with no switch is kept"
    assert {"action": "edit", "resource": "*", "effect": "allow"} in rules
    assert rules.count({"action": "bash", "resource": "*", "effect": "ask"}) == 1


def test_rename_updates_delegation_and_default(tmp_path):
    config = load(
        tmp_path,
        {
            "default_agent": "coder",
            "agents": {
                "lead": {
                    "mode": "primary",
                    "permissions": [
                        {"action": "task", "resource": "*", "effect": "deny"},
                        {"action": "task", "resource": "coder", "effect": "allow"},
                    ],
                },
                "coder": {"mode": "subagent", "description": "d"},
            },
        },
    )
    item = agents.agent(config, "coder")
    item.name = "dev"
    agents.save_agent(config, item, "coder")
    data = saved(config)
    assert "coder" not in data["agents"] and "dev" in data["agents"]
    assert data["agents"]["lead"]["permissions"] == [
        {"action": "task", "resource": "*", "effect": "deny"},
        {"action": "task", "resource": "dev", "effect": "allow"},
    ]
    assert data["default_agent"] == "dev"


def test_remove_agent_cleans_references(tmp_path):
    config = load(
        tmp_path,
        {
            "default_agent": "lead",
            "agents": {
                "lead": {
                    "mode": "primary",
                    "permissions": [
                        {"action": "task", "resource": "*", "effect": "deny"},
                        {"action": "task", "resource": "coder", "effect": "allow"},
                    ],
                },
                "coder": {"mode": "subagent"},
            },
        },
    )
    agents.remove_agent(config, "coder")
    assert saved(config)["agents"]["lead"]["permissions"] == [{"action": "task", "resource": "*", "effect": "deny"}]
    agents.remove_agent(config, "lead")
    data = saved(config)
    assert "default_agent" not in data
    assert "agents" not in data, "an empty map leaves no trace"


def test_task_patterns_are_not_rewritten(tmp_path):
    rules = [
        {"action": "task", "resource": "*", "effect": "ask"},
        {"action": "task", "resource": "review-*", "effect": "allow"},
    ]
    config = load(tmp_path, {"agents": {"lead": {"mode": "primary", "permissions": rules}}})
    item = agents.agent(config, "lead")
    assert item.custom_task and item.delegates is None
    item.delegates = ["general"]
    agents.save_agent(config, item, "lead")
    assert saved(config)["agents"]["lead"]["permissions"] == rules, "a list the switches cannot spell is kept as written"


def test_delegation_switch_writes_and_clears_the_rule_list(tmp_path):
    config = load(tmp_path, {"agents": {"lead": {"mode": "primary", "description": "d"}}})
    item = agents.agent(config, "lead")
    item.delegates = ["coder", "explore"]
    agents.save_agent(config, item, "lead")
    assert saved(config)["agents"]["lead"]["permissions"] == [
        {"action": "task", "resource": "*", "effect": "deny"},
        {"action": "task", "resource": "coder", "effect": "allow"},
        {"action": "task", "resource": "explore", "effect": "allow"},
    ]
    item = agents.agent(OpencodeConfig.load(config.path), "lead")
    assert item.delegates == ["coder", "explore"] and not item.custom_task
    item.delegates = None
    agents.save_agent(config, item, "lead")
    assert "permissions" not in saved(config)["agents"]["lead"], "no switch, no rules"


def test_subagent_cannot_delegate(tmp_path):
    config = load(tmp_path, {"agents": {"coder": {"mode": "subagent", "description": "d"}}})
    item = agents.agent(config, "coder")
    item.delegates = ["general"]
    agents.save_agent(config, item, "coder")
    assert "permissions" not in saved(config)["agents"]["coder"]


def test_names_are_validated(tmp_path):
    config = load(tmp_path, {"agents": {"a": {}}})
    with pytest.raises(ConfigError):
        agents.save_agent(config, Agent(name="bad name"))
    with pytest.raises(ConfigError):
        agents.save_agent(config, Agent(name="a"))
    with pytest.raises(ConfigError):
        agents.save_team(config, [Agent(name="b", description="d"), Agent(name="b", description="d")], make_default=False)


def test_subagent_names_include_built_ins(tmp_path):
    config = load(
        tmp_path,
        {"agents": {"lead": {"mode": "primary"}, "coder": {"mode": "subagent"}, "off": {"mode": "subagent", "disabled": True}}},
    )
    assert agents.subagent_names(config) == ["coder", "explore", "general"]
