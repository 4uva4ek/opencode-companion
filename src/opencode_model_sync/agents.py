"""Agents in the opencode config, and building a team of one planner and several workers.

opencode keeps agents in the ``agents`` map: ``system`` carries the instructions, ``disabled``
switches an agent off, and ``permissions`` is an ordered rule list where every rule names an action,
a resource and an effect. This app manages the ``*`` rules of edit, bash, webfetch and task; rules
it does not manage, or that a plain switch cannot spell, are kept exactly as written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .config import ConfigError, OpencodeConfig
from .i18n import tr

AGENTS = "agents"
BUILT_IN = ("build", "plan", "general", "explore")
BUILT_IN_SUBAGENTS = ("general", "explore")
MODES = ("primary", "subagent", "all")
ACCESS = ("allow", "ask", "deny")
CUSTOM = "custom"  # a rule a plain switch cannot spell; the switch waits, the rule stays
# Actions this app shows as access switches.
PERMISSIONS = ("edit", "bash", "webfetch")
ROLES = ("coder", "tester", "reviewer", "researcher", "custom")
# Edit and bash access per role; None leaves opencode's default.
ROLE_ACCESS = {
    "coder": (None, None),
    "tester": ("deny", None),
    "reviewer": ("deny", "deny"),
    "researcher": ("deny", "deny"),
    "custom": (None, None),
}
# Words of the old agent map; editing an agent replaces them with their ``agents`` spellings.
SUPERSEDED = ("prompt", "disable", "temperature", "permission", "tools", "options", "maxSteps")


@dataclass
class Agent:
    name: str
    mode: str = "all"
    model: str | None = None
    description: str = ""
    prompt: str = ""
    disabled: bool = False
    # "allow", "ask", "deny", CUSTOM, or None for opencode's default.
    access: dict[str, str | None] = field(default_factory=lambda: dict.fromkeys(PERMISSIONS))
    # Subagents this agent may hand work to; None means any.
    delegates: list[str] | None = None
    custom_task: bool = False
    # Agentic iterations before opencode forces a text-only answer; None is its default.
    steps: int | None = None
    # Rules this app keeps as written: other actions, and managed ones spelled beyond a switch.
    kept_rules: list[dict[str, Any]] = field(default_factory=list)

    @property
    def can_delegate(self) -> bool:
        return self.mode != "subagent"

    @property
    def has_custom_access(self) -> bool:
        return any(value == CUSTOM for value in self.access.values())


@dataclass
class Worker:
    role: str
    name: str
    model: str | None = None


def valid_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name))


def agents(config: OpencodeConfig) -> list[Agent]:
    entries = _as_object(config.data.get(AGENTS))
    result = [_agent(name, entry) for name, entry in entries.items() if isinstance(entry, dict)]
    order = {"primary": 0, "all": 1, "subagent": 2}
    return sorted(result, key=lambda agent: (order.get(agent.mode, 1), agent.name.lower()))


def agent(config: OpencodeConfig, name: str) -> Agent | None:
    return next((item for item in agents(config) if item.name == name), None)


def subagent_names(config: OpencodeConfig) -> list[str]:
    """Agents another agent can hand work to: the configured ones plus opencode's built-in subagents."""
    names = [item.name for item in agents(config) if item.mode != "primary" and not item.disabled]
    return sorted(set(names) | set(BUILT_IN_SUBAGENTS), key=str.lower)


def save_agent(config: OpencodeConfig, item: Agent, previous: str | None = None) -> None:
    """Write an agent; ``previous`` is its name before the edit, for renames."""
    if not valid_name(item.name):
        raise ConfigError(tr("error.badAgentName"))
    if item.name != previous and agent(config, item.name):
        raise ConfigError(tr("error.agentExists", name=item.name))
    old = agent(config, previous) if previous else None
    entries = config.data.setdefault(AGENTS, {})
    entry = dict(entries.pop(previous, {})) if old else {}
    for key in SUPERSEDED:
        entry.pop(key, None)

    _set(entry, "description", item.description.strip() or None)
    _set(entry, "mode", item.mode)
    _set(entry, "model", (item.model or "").strip() or None)
    _set(entry, "system", item.prompt.strip() or None)
    _set(entry, "disabled", True if item.disabled else None)
    _set(entry, "steps", item.steps)
    _set(entry, "permissions", _permissions(item) or None)
    entries[item.name] = entry
    if previous and previous != item.name:
        _rename_references(config, previous, item.name)


def remove_agent(config: OpencodeConfig, name: str) -> None:
    entries = _as_object(config.data.get(AGENTS))
    entries.pop(name, None)
    if not entries:
        config.data.pop(AGENTS, None)
    _rename_references(config, name, None)


def team(planner: str, planner_model: str | None, workers: list[Worker], delegate_only: bool) -> list[Agent]:
    """A primary planner that may only hand work to the listed workers, and the workers as subagents."""
    members = []
    for worker in workers:
        edit, bash = ROLE_ACCESS[worker.role]
        members.append(
            Agent(
                name=worker.name,
                mode="subagent",
                model=worker.model or None,
                description=tr(f"role.{worker.role}.description"),
                prompt=tr(f"role.{worker.role}.prompt"),
                access={"edit": edit, "bash": bash, "webfetch": None},
            )
        )
    roster = "\n".join(f"- {member.name}: {member.description}" for member in members)
    lead = Agent(
        name=planner,
        mode="primary",
        model=planner_model or None,
        description=tr("team.plannerDescription"),
        prompt=tr("team.plannerPrompt" if delegate_only else "team.plannerPromptHands", workers=roster),
        access={"edit": "deny", "bash": "deny", "webfetch": None} if delegate_only else dict.fromkeys(PERMISSIONS),
        delegates=[member.name for member in members],
    )
    return [lead, *members]


def save_team(config: OpencodeConfig, members: list[Agent], make_default: bool) -> None:
    """Create or overwrite the team's agents; settings this app does not manage are kept."""
    names = [member.name for member in members]
    if len(set(names)) != len(names):
        raise ConfigError(tr("error.teamDuplicate"))
    for member in members:
        existing = agent(config, member.name)
        if existing:
            member.kept_rules = existing.kept_rules
            member.custom_task = existing.custom_task
            member.steps = existing.steps
            for key, value in existing.access.items():
                if value == CUSTOM:
                    member.access[key] = CUSTOM
        save_agent(config, member, member.name if existing else None)
    if make_default:
        config.data["default_agent"] = members[0].name


def default_agent(config: OpencodeConfig) -> str | None:
    value = config.data.get("default_agent")
    return value if isinstance(value, str) else None


def _agent(name: str, entry: dict[str, Any]) -> Agent:
    rules = [rule for rule in entry.get("permissions", []) if isinstance(rule, dict)] \
        if isinstance(entry.get("permissions"), list) else []
    return Agent(
        name=name,
        mode=_mode(entry),
        model=_model(entry.get("model")),
        description=str(entry.get("description") or ""),
        prompt=str(entry.get("system") or ""),
        disabled=entry.get("disabled") is True,
        steps=_steps(entry.get("steps")),
        **_read_rules(rules),
    )


def _steps(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _read_rules(rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Access switches and delegates out of a rule list; whatever a switch cannot spell is kept."""
    access: dict[str, str | None] = {}
    kept: list[dict[str, Any]] = []
    for key in PERMISSIONS:
        own = [rule for rule in rules if rule.get("action") == key]
        plain = [rule for rule in own if rule.get("resource", "*") == "*" and rule.get("effect") in ACCESS]
        if own and len(plain) == len(own):
            access[key] = plain[-1]["effect"] if plain else None
        else:
            access[key] = CUSTOM if own else None
            kept.extend(own)
    delegates, custom_task = _read_task([rule for rule in rules if rule.get("action") == "task"])
    if custom_task:
        kept.extend(rule for rule in rules if rule.get("action") == "task")
    kept.extend(rule for rule in rules if rule.get("action") not in (*PERMISSIONS, "task"))
    return {"access": access, "delegates": delegates, "custom_task": custom_task, "kept_rules": kept}


def _read_task(rules: list[dict[str, Any]]) -> tuple[list[str] | None, bool]:
    """Task rules this app can show as a list of allowed subagents, or a flag that it cannot."""
    if not rules:
        return None, False
    first = rules[0]
    if first.get("resource", "*") != "*" or first.get("effect") != "deny":
        return None, True
    allowed = [rule.get("resource") for rule in rules[1:]]
    if any(rule.get("effect") != "allow" or not isinstance(name, str) or not valid_name(name) for rule, name in zip(rules[1:], allowed)):
        return None, True
    return [name for name in allowed if isinstance(name, str)], False


def _permissions(item: Agent) -> list[dict[str, Any]]:
    """The managed rules of an agent, after the rules it carries untouched.

    A switch moved off CUSTOM replaces the rules it used to shadow: for a managed action the switch's
    word is the only one written.
    """
    spelled = {key for key in PERMISSIONS if item.access.get(key) in ACCESS}
    rules = [rule for rule in item.kept_rules if rule.get("action") not in spelled]
    for key in PERMISSIONS:
        value = item.access.get(key)
        if value in ACCESS:
            rules.append({"action": key, "resource": "*", "effect": value})
    if not item.custom_task and item.can_delegate and item.delegates is not None:
        rules.append({"action": "task", "resource": "*", "effect": "deny"})
        rules.extend({"action": "task", "resource": name, "effect": "allow"} for name in item.delegates)
    return rules


def _mode(entry: dict[str, Any]) -> str:
    mode = entry.get("mode")
    return mode if mode in MODES else "all"


def _model(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict) and value.get("providerID") and value.get("model"):
        variant = f"#{value['variant']}" if value.get("variant") else ""
        return f"{value['providerID']}/{value['model']}{variant}"
    return None


def _rename_references(config: OpencodeConfig, old: str, new: str | None) -> None:
    for entry in _as_object(config.data.get(AGENTS)).values():
        if not isinstance(entry, dict):
            continue
        rules = entry.get("permissions")
        if not isinstance(rules, list):
            continue
        if new is None:
            # The agent is gone; a rule naming it could never match a task again.
            kept = [rule for rule in rules
                    if not (isinstance(rule, dict) and rule.get("action") == "task" and rule.get("resource") == old)]
            if len(kept) != len(rules):
                _set(entry, "permissions", kept or None)
        else:
            for rule in rules:
                if isinstance(rule, dict) and rule.get("action") == "task" and rule.get("resource") == old:
                    rule["resource"] = new
    if config.data.get("default_agent") == old:
        _set(config.data, "default_agent", new)


def _set(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        target.pop(key, None)
    else:
        target[key] = value


def _as_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
