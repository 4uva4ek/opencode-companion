"""Standard sets of generation parameters, so a person picks a name instead of typing eight numbers.

A preset answers every field of a model's behaviour at once, in the same words the config uses. That
includes the fields it says nothing about: ``None`` is the field's way of holding its tongue, so
applying a preset takes that word out of the entry and the provider answers for it again. Applying a
preset is therefore not a nudge at the numbers standing there — it is the whole answer for every
field the preset lists, which is what makes the result of a click predictable.

The bounds are not here. They belong to the fields themselves, in ``window.MODEL_PARAMS``, because a
field has to refuse a wrong number whether it was typed, slid or filled in from a preset. What is
here is only what has been checked against those bounds: every number below is one its own field
accepts, so a preset can never be the reason a window refuses to apply. A template saved by a person
is read as its author left it — the fields are what refuse a number they cannot say — and one saved
before some future field existed simply says nothing about that field, which is the same answer as
an empty row.

Reasoning effort is left to the server in every shipped set: a level asked for of a model that
cannot reason is a request a server may refuse outright, which is a worse price for a shorter answer
than the few tokens it saves. The field is there to take off its tick by hand for a model that can.

The five below are shipped, and a person's own sets live in a file beside the opencode config —
opencode never reads that file, and only the own ones can be deleted: what came with the app is the
same for everyone who runs it, and a list where anyone's click can quietly remove five entries is a
list that loses its meaning.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import config_dir
from .i18n import tr

STATE_NAME = "model-sync-presets.json"


class PresetError(Exception):
    """A template cannot be named, or cannot be saved under that name."""


@dataclass(frozen=True)
class Preset:
    """One named answer for every behaviour field, and the two sentences that explain it."""

    id: str
    values: dict[str, Any]
    # A shipped set carries no words of its own: it is named in both interface languages and reads
    # them from the keys of its id. One a person saved carries the words they typed, in whatever
    # language they typed them in, and translating those would be inventing something for them.
    name_text: str | None = None
    hint_text: str | None = None
    custom: bool = False

    @property
    def name(self) -> str:
        """A shipped set reads its name in the interface language; yours keeps the words you typed."""
        return self.name_text if self.custom else tr(f"preset.{self.id}.name")

    @property
    def description(self) -> str:
        """An empty description is an answer of its own, not a key to go looking a word up by."""
        return (self.hint_text or "") if self.custom else tr(f"preset.{self.id}.hint")


# None everywhere it appears below: the seed, the stop sequences and the reasoning level are words a
# preset has no business choosing for a model it has never met. Only `brief` names an output limit,
# and its description is where that limit is admitted to, because the same number that shortens an
# answer also cuts a long file edit short.
PRESETS: tuple[Preset, ...] = (
    Preset("exact", {
        "temperature": 0, "topP": 1, "topK": 1, "minP": 0,
        "presencePenalty": 0, "frequencyPenalty": 0,
        "maxOutputTokens": None, "seed": None, "stopSequences": None, "reasoningEffort": None,
    }),
    Preset("code", {
        "temperature": 0.3, "topP": 0.9, "topK": 40, "minP": 0,
        "presencePenalty": 0, "frequencyPenalty": 0,
        "maxOutputTokens": None, "seed": None, "stopSequences": None, "reasoningEffort": None,
    }),
    Preset("everyday", {
        "temperature": 0.6, "topP": 0.95, "topK": 40, "minP": 0,
        "presencePenalty": 0, "frequencyPenalty": 0,
        "maxOutputTokens": None, "seed": None, "stopSequences": None, "reasoningEffort": None,
    }),
    Preset("brief", {
        "temperature": 0.4, "topP": 0.9, "topK": 40, "minP": 0.05,
        "presencePenalty": 0, "frequencyPenalty": 0,
        "maxOutputTokens": 2048, "seed": None, "stopSequences": None, "reasoningEffort": None,
    }),
    Preset("creative", {
        "temperature": 1.1, "topP": 0.98, "topK": 120, "minP": 0,
        "presencePenalty": 0.3, "frequencyPenalty": 0.3,
        "maxOutputTokens": None, "seed": None, "stopSequences": None, "reasoningEffort": None,
    }),
)


def preset(preset_id: str | None) -> Preset | None:
    """The shipped set under that name, or None for the entry that stands for "no template"."""
    return next((item for item in PRESETS if item.id == preset_id), None)


def one(preset_id: str | None, own: Sequence[Preset] = ()) -> Preset | None:
    """A template under that name, whether it came with Companion or was saved by the person."""
    return next((item for item in (*PRESETS, *own) if item.id == preset_id), None)


# ---- the templates a person saved for themselves ----


def file_for(directory: Path, env: Mapping[str, str] | None = None) -> Path:
    """Where the templates of a config kept in that directory are read from and written to.

    The environment answers first, because that is how every other file of this application is
    moved; the directory is the answer when it does not, so that a config living elsewhere carries
    its own templates with it — opencode never reads the file, and a template describes the models
    that stand in the config beside it.
    """
    env = os.environ if env is None else env
    if env.get("OPENCODE_MODEL_SYNC_PRESETS"):
        return Path(env["OPENCODE_MODEL_SYNC_PRESETS"])
    return directory / STATE_NAME


def state_path(env: Mapping[str, str] | None = None) -> Path:
    """The default place: beside the config this application edits.

    The same directory and the same kind of environment override as the workspace state file,
    because two files of one application have no business disagreeing about where it keeps things.
    """
    env = os.environ if env is None else env
    return file_for(config_dir(env), env)


def _ident(name: str) -> str:
    """A standing id for a name a person typed, in any alphabet.

    The slug of a Russian name comes out empty, so the name is hashed instead. The id is what the
    list and the delete button pass to each other, and it never stands in the way of reading.
    """
    return "u-" + hashlib.sha1(name.strip().casefold().encode("utf-8")).hexdigest()[:10]


def kept(value: Any) -> bool:
    """What even a hand-edited file is allowed to say: a number, a word, a list of words, nothing.

    A map in the place of a number would land in a field that has no way to show it, and the field
    would then hand over a number nobody typed. Such a word is dropped, which is the same as the
    field saying nothing.
    """
    if value is None or isinstance(value, bool):
        return value is None
    if isinstance(value, (int, float, str)):
        return True
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def load(path: Path | None = None) -> list[Preset]:
    """The own templates, in the order they were saved; a file that cannot be read is no templates.

    A broken file is neither fatal nor quietly repaired: reading says nothing, and the next save
    writes what reading found plus the new one.
    """
    path = path or state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("presets") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    found: dict[str, Preset] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        raw = item.get("values") if isinstance(item.get("values"), dict) else {}
        hint = item.get("description")
        ident = str(item.get("id") or _ident(name))
        # A file poked at by hand can name two templates the same: the first one is what is offered.
        found.setdefault(ident, Preset(
            id=ident,
            values={key: value for key, value in raw.items() if kept(value)},
            name_text=name.strip(),
            hint_text=hint.strip() if isinstance(hint, str) else "",
            custom=True,
        ))
    return list(found.values())


def write(items: Sequence[Preset], path: Path | None = None) -> None:
    """The file as it is left on disk: one list, in the order it is offered in."""
    path = path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"presets": [{"id": item.id, "name": item.name_text, "description": item.hint_text,
                         "values": item.values} for item in items]}
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save(name: str, description: str, values: dict[str, Any],
         path: Path | None = None) -> tuple[Preset, bool]:
    """Adds a template, or rewrites the own one that already bears that name.

    Saving under the name of a *shipped* template leaves the shipped one where it is and adds another
    entry of that name: a name a person typed is theirs to reuse, and the five that came with the app
    are not theirs to lose. Two own templates with one name would be one template nobody could delete
    by half, so those are replaced instead. Returns the template and whether one was rewritten.
    """
    name = name.strip()
    if not name:
        raise PresetError(tr("model.presetsNameNeeded"))
    path = path or state_path()
    written = {key: value for key, value in values.items() if kept(value)}
    preset = Preset(_ident(name), written, name, description.strip(), custom=True)
    current = load(path)
    same = [position for position, item in enumerate(current)
            if item.name_text.casefold() == name.casefold()]
    standing = [item for position, item in enumerate(current) if position not in set(same)]
    # A rewritten template keeps the place it had in the list: a name that jumps to the bottom of
    # the row every time it is saved is a name the eyes lose.
    standing.insert(same[0] if same else len(standing), preset)
    write(standing, path)
    return preset, bool(same)


def remove(preset_id: str, path: Path | None = None) -> Preset:
    """Takes an own template out of the file, and refuses a shipped one.

    The refusal lives here rather than only in whether a button is enabled, so that a window left
    open from before, or any other way in, cannot remove what came with the application: the five are
    the same for everyone who runs it, and a list from which one click quietly removes five entries
    is a list that has stopped meaning anything.
    """
    if preset(preset_id):
        raise PresetError(tr("model.presetsBuiltIn"))
    path = path or state_path()
    current = load(path)
    target = next((item for item in current if item.id == preset_id), None)
    if target is None:
        raise PresetError(tr("model.presetsGone"))
    write([item for item in current if item.id != preset_id], path)
    return target
