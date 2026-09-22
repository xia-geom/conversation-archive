"""Versioned declarative review controls. Data selects controls, never executable code.

This module does not read archives, call models, or authorize corrections.
Semantic effects belong to separately tested writers, not to form labels.
"""
from __future__ import annotations

from copy import deepcopy
import re

VERSION = "review-controls-1.0"
CONTROL_TYPES = frozenset({"choice", "multi_choice", "text", "groups"})
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


class ControlError(ValueError):
    """The declared form or submitted value is not supported."""


def need(condition, message):
    if not condition:
        raise ControlError(message)


def _text(value, limit=2000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def validate_form(form):
    need(isinstance(form, dict) and set(form) == {"version", "fields"}
         and form["version"] == VERSION, "Unsupported form version or fields")
    fields = form["fields"]
    need(isinstance(fields, list) and 1 <= len(fields) <= 24, "A form needs 1–24 fields")
    seen = {}
    for field in fields:
        need(isinstance(field, dict), "Invalid form field")
        required = {"id", "type", "label", "required"}
        optional = {"help", "options", "max_length", "visible_when", "items", "targets"}
        need(required <= set(field) <= required | optional, "Unknown form field keys")
        key, kind = field["id"], field["type"]
        need(isinstance(key, str) and _ID.fullmatch(key) and key not in seen,
             "Invalid or duplicate field ID")
        need(isinstance(kind, str) and kind in CONTROL_TYPES, "Unsupported form control")
        need(_text(field["label"]) and type(field["required"]) is bool, "Invalid field label or required flag")
        need("help" not in field or _text(field["help"], 4000), "Invalid field help")
        if "visible_when" in field:
            when = field["visible_when"]
            need(isinstance(when, dict) and set(when) == {"field", "equals"}, "Invalid display condition")
            parent = seen.get(when["field"]) if isinstance(when["field"], str) else None
            need(parent is not None and parent["type"] == "choice"
                 and when["equals"] in [o["value"] for o in parent["options"]],
                 "Conditions must refer to a preceding choice")
        allowed = required | {"help", "visible_when"}
        if kind in {"choice", "multi_choice"}:
            allowed |= {"options"}
            options = field.get("options")
            need(isinstance(options, list) and 1 <= len(options) <= 100, "Invalid choice options")
            values = []
            for opt in options:
                need(isinstance(opt, dict) and set(opt) == {"value", "label"}
                     and _text(opt["value"], 100) and _text(opt["label"]), "Invalid choice option")
                values.append(opt["value"])
            need(len(values) == len(set(values)), "Duplicate choice option")
        elif kind == "text":
            allowed |= {"max_length"}
            need(type(field.get("max_length")) is int and 1 <= field["max_length"] <= 10000,
                 "A text field needs a bounded max_length")
        else:
            allowed |= {"items", "targets"}
            items, targets = field.get("items"), field.get("targets")
            need(isinstance(items, list) and 1 <= len(items) <= 100
                 and isinstance(targets, list) and len(targets) <= 100, "Invalid grouping scope")
            for seq in (items, targets):
                ids = []
                for item in seq:
                    need(isinstance(item, dict) and set(item) == {"id", "label"}
                         and _text(item["id"], 200) and _text(item["label"]), "Invalid group item or target")
                    ids.append(item["id"])
                need(len(ids) == len(set(ids)), "Duplicate group item or target")
        need(set(field) <= allowed, "A control has fields belonging to another type")
        seen[key] = field
    return deepcopy(form)


def visible(field, values):
    when = field.get("visible_when")
    return when is None or values.get(when["field"]) == when["equals"]


def validate_groups(field, value):
    need(isinstance(value, dict) and set(value) == {"groups", "unknown"}, "Invalid group answer")
    groups, unknown = value["groups"], value["unknown"]
    need(isinstance(groups, list) and isinstance(unknown, list), "Invalid groups or unknowns")
    item_ids = {x["id"] for x in field["items"]}
    target_ids = {x["id"] for x in field["targets"]}
    assigned, used_targets = list(unknown), []
    need(all(isinstance(x, str) for x in unknown), "Invalid unknown reference")
    for group in groups:
        need(isinstance(group, dict) and set(group) == {"label", "target", "items"}, "Invalid group record")
        need(_text(group["label"], 200) and isinstance(group["items"], list) and bool(group["items"])
             and all(isinstance(x, str) for x in group["items"]), "Empty group or invalid members")
        target = group["target"]
        need(target is None or isinstance(target, str) and target in target_ids, "Unknown target identity")
        if target is not None:
            used_targets.append(target)
        assigned.extend(group["items"])
    need(len(assigned) == len(set(assigned)) and set(assigned) == item_ids,
         "Every displayed reference must occur exactly once, in a group or as unknown")
    need(len(used_targets) == len(set(used_targets)), "Two groups cannot select the same identity")


def validate_values(form, values):
    """Return exact values, with no coercion, inferred defaults, or semantic parsing."""
    form = validate_form(form)
    need(isinstance(values, dict), "Form values must be an object")
    by_id = {f["id"]: f for f in form["fields"]}
    need(set(values) <= set(by_id), "Unknown form answer field")
    for field in form["fields"]:
        key, kind = field["id"], field["type"]
        if not visible(field, values):
            need(key not in values, "A hidden field cannot contribute an answer")
            continue
        if key not in values:
            need(not field["required"], "A required answer is missing")
            continue
        value = values[key]
        if kind == "text":
            need(isinstance(value, str) and len(value) <= field["max_length"]
                 and (not field["required"] or bool(value.strip())), "Invalid text answer")
        elif kind == "choice":
            need(isinstance(value, str) and value in [o["value"] for o in field["options"]], "Invalid choice answer")
        elif kind == "multi_choice":
            need(isinstance(value, list) and all(isinstance(x, str) for x in value)
                 and len(value) == len(set(value))
                 and set(value) <= {o["value"] for o in field["options"]}
                 and (not field["required"] or bool(value)), "Invalid multiple-choice answer")
        else:
            validate_groups(field, value)
    return deepcopy(values)


def identity_form(scope):
    """Build controls from a frozen, checked mention scope, not from free text."""
    return validate_form({"version": VERSION, "fields": [{
        "id": "identity", "type": "groups", "label": "Assign references to identity groups",
        "required": True,
        "help": "Only references in the same group are joined. Unknown makes no identity claim. Existing assignments are not erased.",
        "items": [{"id": m["mention_id"], "label": m["entry_id"] + " · " + m["quote"]}
                  for m in scope["mentions"]],
        "targets": [{"id": e["entity_id"], "label": e["label"]} for e in scope["entities"]],
    }]})
