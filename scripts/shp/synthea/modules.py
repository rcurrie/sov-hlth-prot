"""Static validation for Synthea Generic Module Framework (GMF) JSON modules.

Synthea itself can only be run with a JVM; this validator lets us catch the
common authoring mistakes (dangling transitions, distributions that don't sum
to 1, references to non-existent states) without a Synthea build in the loop.
It is intentionally conservative: it checks structure and references, not
clinical semantics.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from . import config

KNOWN_STATE_TYPES = {
    "Initial", "Terminal", "Simple", "Guard", "Delay", "Encounter",
    "EncounterEnd", "ConditionOnset", "ConditionEnd", "AllergyOnset",
    "AllergyEnd", "MedicationOrder", "MedicationEnd", "CarePlanStart",
    "CarePlanEnd", "Procedure", "Observation", "MultiObservation",
    "DiagnosticReport", "Symptom", "SetAttribute", "Counter", "VitalSign",
    "Death", "ImagingStudy", "Device", "DeviceEnd", "SupplyList",
}
TRANSITION_KEYS = {
    "direct_transition", "distributed_transition", "conditional_transition",
    "complex_transition",
}
# Only Terminal legitimately needs no outgoing transition. Synthea *does* require
# Death states to declare a transition (it raises "has no transition" otherwise).
TERMINALISH = {"Terminal"}


def _transition_targets(state: dict) -> list[str]:
    targets: list[str] = []
    if "direct_transition" in state:
        targets.append(state["direct_transition"])
    for t in state.get("distributed_transition", []):
        targets.append(t["transition"])
    for t in state.get("conditional_transition", []):
        targets.append(t["transition"])
    for t in state.get("complex_transition", []):
        if "transition" in t:
            targets.append(t["transition"])
        for d in t.get("distributions", []):
            targets.append(d["transition"])
    return targets


def validate_module(obj: dict) -> list[str]:
    """Return a list of error strings (empty == valid)."""
    errors: list[str] = []
    states = obj.get("states")
    if not isinstance(states, dict):
        return ["module has no 'states' object"]
    if "Initial" not in states:
        errors.append("missing required 'Initial' state")

    names = set(states)
    referenced: set[str] = set()

    for name, state in states.items():
        stype = state.get("type")
        if stype not in KNOWN_STATE_TYPES:
            errors.append(f"[{name}] unknown state type: {stype!r}")

        # transition existence
        has_transition = any(k in state for k in TRANSITION_KEYS)
        if not has_transition and stype not in TERMINALISH:
            errors.append(f"[{name}] non-terminal state has no transition")

        targets = _transition_targets(state)
        referenced.update(targets)
        for tgt in targets:
            if tgt not in names:
                errors.append(f"[{name}] transition to unknown state {tgt!r}")

        # distributed transitions should sum to ~1.0
        dist = state.get("distributed_transition")
        if dist:
            total = sum(t.get("distribution", 0) for t in dist)
            if not math.isclose(total, 1.0, abs_tol=1e-6):
                errors.append(f"[{name}] distributed_transition sums to {total}, not 1.0")

        # reference integrity for *_onset back-references
        for ref_key in ("condition_onset", "allergy_onset", "medication_order",
                        "careplan", "target_encounter"):
            ref = state.get(ref_key)
            if ref and ref not in names:
                errors.append(f"[{name}] {ref_key} -> unknown state {ref!r}")

        # codes shape
        for code in state.get("codes", []):
            if not {"system", "code", "display"} <= set(code):
                errors.append(f"[{name}] code missing system/code/display: {code}")

    # unreachable states (besides Initial)
    reachable = {"Initial"}
    frontier = ["Initial"]
    while frontier:
        cur = frontier.pop()
        for tgt in _transition_targets(states.get(cur, {})):
            if tgt not in reachable:
                reachable.add(tgt)
                frontier.append(tgt)
    for name in names - reachable:
        errors.append(f"[{name}] state is unreachable from Initial")

    return errors


def validate_file(path: Path) -> list[str]:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    return validate_module(obj)


def validate_all(modules_dir: Path | None = None) -> dict[str, list[str]]:
    modules_dir = modules_dir or config.MODULES_DIR
    return {p.name: validate_file(p) for p in sorted(modules_dir.glob("*.json"))}
