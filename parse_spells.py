"""
Build a clean Dofus Unity class-spells dataset (French only).

Downloads missing raw release files, joins spells/spell_levels/spell_variants/
breeds/translations/effects/spell_states, formats effect descriptions using
French templates with full name resolution for spell and state references,
and writes spells_clean.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any


DATA_DIR = Path(os.environ.get("DOFUS_DATA_DIR") or os.environ.get("TEMP") or ".")
OUT_FILE = Path(__file__).with_name("spells_clean.json")
RELEASE_API = "https://api.github.com/repos/dofusdude/dofus3-main/releases/latest"

RAW_FILES = [
    "spells.json",
    "spell_levels.json",
    "spell_variants.json",
    "breeds.json",
    "fr.json",
    "spell_states.json",
    "monsters.json",
]

ELEMENTS = {
    -1: None,
    0: "Neutre",
    1: "Terre",
    2: "Feu",
    3: "Eau",
    4: "Air",
    5: "Neutre",
}

ZONE_SHAPES = {
    0: "point",
    35: "point",
    65: "point",   # A
    67: "cercle",  # C
    97: "cercle",
    80: "cercle",  # P
    42: "croix",
    43: "croix",
    45: "croix",
    81: "croix",
    85: "croix",
    88: "croix",   # X
    70: "ligne",
    71: "ligne",
    76: "ligne",   # L
    82: "ligne",
    84: "ligne",   # T
    108: "ligne",
    86: "cône",    # V
    79: "anneau",  # O
}

# ── Trigger event label mapping ───────────────────────────────────────────────
# Maps raw trigger codes to short French labels shown in the UI.
# Compound triggers (A|B) are split and each token looked up individually.
# Maps raw trigger codes to (short French label, uncertain) shown in the UI.
# Compound triggers (A|B) are split and each token looked up individually.
# "uncertain=True" = best-effort interpretation, not fully confirmed — the
# UI marks these with a small "†".
#
# Corrected several outright-wrong prior guesses, found by cross-referencing
# Ankama's own descriptionFr against real effect context:
#   - DE/DF/DW/DA were "au téléport ennemi"/"fin effet"/"quand poussé loin"/
#     "quand attiré" (four unrelated concepts) but all four appear together
#     in "Bouclier Élémentaire", one per elemental resistance line — they're
#     clearly "D" + English element initial ("dégâts [Terre/Feu/Eau/Air]
#     subis"). DN (Neutral) was missing entirely; added it on the same basis.
#   - DM was "au déplacement" but its only real example is a damage-reflect
#     effect ("Couronne d'Épines" — renvoie 100% des dommages subis) — "DM"
#     reads as "Dégâts" not "Déplacement".
#   - TE was "fin tour ennemi" but its example ("Libation") heals the CASTER
#     at the end of the caster's own next turn — narrowed to "fin de tour".
#   - PT ("traverse un portail") was entirely unmapped despite clear evidence
#     in "Coalition" ("soigne la cible lorsqu'elle traverse un portail").
TRIGGER_LABELS: dict[str, tuple[str, bool] | None] = {
    "I":    None,           # on cast — implicit, don't show
    "TE":   ("fin de tour", True),
    "TB":   ("début de tour", False),
    "D":    ("sur attaque subie", True),
    "DM":   ("dégâts subis", True),
    "X":    ("quand touché", True),
    "H":    ("début combat", True),
    "PD":   ("fin combat", True),
    "DBE":  ("esquive / embuscade", True),
    "DIS":  ("quand poussé", True),
    "DR":   ("désenvoûtement", True),
    "MA":   ("attaque mortelle", True),
    "CC":   ("coup critique", False),
    "CPT":  ("coup critique", True),
    "CCMPARR": ("critique ou parade", True),
    "CMPARR": ("parade", True),
    "MS":   ("fin de l'état", True),
    "DA":   ("dégâts Air subis", False),
    "DE":   ("dégâts Terre subis", False),
    "DF":   ("dégâts Feu subis", False),
    "DW":   ("dégâts Eau subis", False),
    "DN":   ("dégâts Neutre subis", False),
    "DIS|DR": ("poussé / désenvoûté", True),
    "DIS|DM": ("poussé / dégâts subis", True),
    "DM|XDM": ("dégâts subis", True),
    "PD|XPD": ("fin combat", True),
    "TB|XDTB": ("début de tour", False),
    "D|XD": ("sur attaque subie", True),
    "I|TB": ("début de tour", False),
    "MPA":  ("retrait de PA", True),
    "TP":   ("au téléport", True),
    "PT":   ("traverse un portail", False),
    "M":    ("au déplacement", True),
    "V":    ("quand vu", True),
    "VA":   ("attaqué à distance", True),
    "VM":   ("touché en mêlée", True),
    "VE":   ("esquivé", True),
    "LPU":  ("perte de PV", True),
    "DTB":  ("début tour allié", True),
    "DTE":  ("début tour ennemi", True),
    "DV":   ("fin de vie", True),
    "DT":   ("condition spéciale", True),
    "PO":   ("condition spéciale", True),
    "CPD":  ("condition spéciale", True),
    "CMPAS": ("cible affectée par état lié", True),
    "MPA|M|TP": ("PA retiré / déplacement / téléport", True),
}

# ── Dispellable label mapping ─────────────────────────────────────────────────
# 1 = standard (don't show), 2 = non-dispellable, 3 = permanent/unremovable
DISPELLABLE_LABELS: dict[int, str | None] = {
    1: None,              # default — omit
    2: "non dissipable",
    3: "permanent",
}

# ── targetMask letter-token → French target label ─────────────────────────────
# ── targetMask letter-token → (French label, uncertain) ───────────────────────
# "uncertain=True" means the label is a best-effort interpretation that could
# not be fully confirmed against real spell text — the UI marks these with a
# small "†" so people don't mistake an educated guess for verified fact.
#
# Confirmed via cross-referencing Ankama's own descriptionFr/textFr against
# isolated or narrow-context token usage (see /docs/label-audit.md for the
# full research notes). Corrected several outright-wrong prior guesses:
#   - h was "héros ennemi" but only ever observed applying buffs to the
#     caster's OWN freshly-summoned creature — clearly an ally-side token.
#   - T/r/R were "porteurs"/"montures" but only ever co-occur with
#     teleport/portal mechanics (Xélor téléfrag, Eliotrope portails).
#   - O was "cible précédente" but every example is about the target's
#     *attacker* (retaliation-style effects), not a previous target.
TARGET_TOKENS: dict[str, tuple[str, bool]] = {
    "A":  ("ennemis", False),
    "a":  ("alliés", False),
    "C":  ("soi-même", False),
    "c":  ("soi-même", False),
    "g":  ("glyphes", False),
    "j":  ("invocation alliée", False),
    "J":  ("invocation ennemie", False),
    "s":  ("arbre", False),
    "p":  ("pièges", False),
    "i":  ("invocation du lanceur", True),
    "K":  ("cible projetée", True),
    "U":  ("invocation à instance unique", True),
    "P":  ("entité désignée (état lié)", True),
    "T":  ("téléportation", True),
    "r":  ("portails", True),
    "R":  ("portails", True),
    "O":  ("attaquant(s) de la cible", True),
    "h":  ("entité alliée liée", True),
    # Confirmed as a family (all co-occur in "bonus vs invocations" spells)
    # but the precise sub-category each letter denotes is unconfirmed.
    "L":  ("invocation (catégorie 1)", True),
    "M":  ("invocation (catégorie 2)", True),
    "l":  ("invocation (catégorie 3)", True),
    "m":  ("invocation (catégorie 4)", True),
    "H":  ("invocation (catégorie spéciale)", True),
    "I":  ("invocation (générique)", True),
    "D":  ("catégorie spéciale (non confirmée)", True),
    "d":  ("catégorie spéciale, alliée (non confirmée)", True),
    "x":  ("objet invocable", True),
}

# ── Area visual badge strings ─────────────────────────────────────────────────
# Returns a compact string like "⊕ r2" or "＋ r1" — None for trivial zones.
def area_badge(area: dict[str, Any]) -> str | None:
    """
    Compact text caption for a zone (e.g. "zone r2", "croix r1"). Exported
    alongside the raw area {type, shape, size} object, which the frontend
    uses to render an actual square-grid icon (Dofus is cell-based — no
    dot/circle glyphs here, even in this plain-text fallback).
    """
    atype = area.get("type")
    size  = area.get("size") or 0
    shape = area.get("shape")

    if not atype or atype == "point" or size == 0:
        return None          # single-cell hit, no badge needed
    if size >= 10:
        return "zone globale"   # map-wide (size=63 etc.)
    if atype == "cercle":
        return f"zone r{size}"
    if atype == "croix":
        if shape == 88:      # X diagonal
            return f"croix (X) r{size}"
        return f"croix r{size}"
    if atype == "ligne":
        return f"ligne r{size}"
    if atype == "cône":
        return f"cône r{size}"
    if atype == "anneau":
        return f"anneau r{size}"
    return None


def decode_targets(mask: str) -> str | None:
    """
    Decode the primary target tokens from a targetMask string into French.
    Returns a compact string like "ennemis · alliés" or None if trivial/unknown.
    Ignores state/entity filter tokens (E/e/F/f prefixed).
    Uncertain labels (unconfirmed against real spell text) get a trailing "†".
    """
    if not mask:
        return None
    seen: list[str] = []
    used: set[str] = set()
    for tok in mask.split(","):
        tok = tok.strip().lstrip("*")
        # Skip state/entity refs
        if re.match(r'^[EeFf]\d+', tok):
            continue
        entry = TARGET_TOKENS.get(tok)
        if not entry:
            continue
        label, uncertain = entry
        display = f"{label}\u2009†" if uncertain else label
        if display not in used:
            seen.append(display)
            used.add(display)
    return " · ".join(seen) if seen else None
FLAG_LINE_OF_SIGHT = 4
FLAG_REQUIRES_FREE_CELL = 8
FLAG_RANGE_MODIFIABLE = 64

# EffectIds whose min field is a spell ID reference (template just prints #1).
# The raw spell ID is substituted with the spell's French name.
SPELL_REF_MIN_EFFECT_IDS: frozenset[int] = frozenset({
    281,   # "sort : +N Portée maximale"
    285,   # "sort : -N PA"
    290,   # "sort : +N lancer(s) par tour"
    291,   # "sort : +N lancer(s) par cible"
    293,   # "sort : +N dégâts de base"
    296,   # "sort : +N PA"
    792,   # "Invoque X" / summon-type — min = spell id
    1017,  # summon-type — min = spell id
    1019,  # summon-type — min = spell id
    1036,  # "sort : -N de relance"
    1045,  # "sort : relance fixée à N"
    1160,  # "Applique les effets de X" — min = spell id
    2160,  # spell ref — min = spell id
    2794,  # spell ref — min = spell id
    2935,  # "sort : +N soins de base"
    2960,  # spell ref — min = spell id
})

# EffectIds whose min field is a MONSTER/INVOCATION ID reference.
# The monster ID is substituted with the monster's French name.
MONSTER_REF_MIN_EFFECT_IDS: frozenset[int] = frozenset({
    181,   # "Invoque : X" — min = monster id
    405,   # "Tue la cible et remplace par l'invocation : X" — min = monster id
    1008,  # summon-type — min = monster id
    1011,  # summon-type — min = monster id
    2796,  # "Tue la cible et remplace par l'invocation : X" — min = monster id
})

# EffectIds whose spell reference is carried in the max field (template uses #2).
# Template: 406 -> "Enlève les effets du sort #2"  — max = spell id
# Note: effectId 1406 looks similar but max is a rank number, not a spell id.
# Normal template substitution handles 1406 fine.
SPELL_REF_MAX_EFFECT_IDS: frozenset[int] = frozenset({
    406,
})

# EffectIds that apply or remove a game state — value = state id.
STATE_APPLY_EFFECT_IDS: frozenset[int] = frozenset({
    950,   # "État X (N tour)" — applies state
    951,   # "Enlève l'état X" — removes state
    952,   # "Désactive l'état X" — deactivates state
})

# EffectIds whose value field is a SPELL LEVEL ID.
# Resolution: value → spell_level → spellId → spell French name.
# 3792 = "Applique les effets de [niveau de sort]" (Pandawa-style level reference)
# 3793 = "Tue la cible et remplace par les effets de [niveau de sort]"
SPELL_LEVEL_REF_VALUE_EFFECT_IDS: frozenset[int] = frozenset({
    3792,
    3793,
})


def log(message: str) -> None:
    print(message, flush=True)


def download_missing(data_dir: Path) -> None:
    project_root = Path(__file__).parent
    # A file is not missing if it exists in data_dir OR in the project root
    missing = [
        name for name in RAW_FILES
        if not (data_dir / name).exists() and not (project_root / name).exists()
    ]
    if not missing:
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    log(f"Missing {len(missing)} raw files; reading latest release asset list...")
    req = urllib.request.Request(RELEASE_API, headers={"User-Agent": "parse_spells/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        release = json.load(response)

    assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
    for name in missing:
        url = assets.get(name)
        if not url:
            raise RuntimeError(f"{name} is missing locally and was not found in latest release assets")

        target = data_dir / name
        log(f"Downloading {name}...")
        req2 = urllib.request.Request(url, headers={"User-Agent": "parse_spells/1.0"})
        with urllib.request.urlopen(req2, timeout=120) as response, target.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)


def load_json(data_dir: Path, filename: str) -> dict[str, Any]:
    path = data_dir / filename
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def arr(value: Any) -> list[Any]:
    if isinstance(value, dict):
        value = value.get("Array")
    return value if isinstance(value, list) else []


def extract_refs(raw: dict[str, Any]) -> dict[int, dict[str, Any]]:
    objects = raw.get("objectsById", {})
    keys = arr(objects.get("m_keys"))
    values = arr(objects.get("m_values"))
    rid_to_id = {value.get("rid"): key for key, value in zip(keys, values) if isinstance(value, dict)}

    result: dict[int, dict[str, Any]] = {}
    for ref in arr(raw.get("references", {}).get("RefIds")):
        if not isinstance(ref, dict):
            continue
        data = ref.get("data")
        game_id = rid_to_id.get(ref.get("rid"))
        if game_id is not None and isinstance(data, dict) and len(data) > 1:
            result[int(game_id)] = data
    return result


def build_fr_translations(raw_fr: dict[str, Any]) -> dict[str, str]:
    """Return flat {text_id_str: fr_text} from fr.json (handles wrapped or flat)."""
    entries = raw_fr.get("entries", raw_fr)
    return {str(k): str(v) for k, v in entries.items() if v not in ("", None)}


def build_effects_map(effects_raw: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Return {effect_id: effect_data} from effects.json."""
    return extract_refs(effects_raw)


def build_state_names(states_raw: dict[str, Any], fr_texts: dict[str, str]) -> dict[int, str]:
    """
    Return {state_id: french_name} by joining spell_states.json nameId → fr.json.
    Names are stripped of all Dofus rich-text markup.
    """
    states_by_id = extract_refs(states_raw)
    result: dict[int, str] = {}
    for state_id, state in states_by_id.items():
        name_id = state.get("nameId")
        if name_id:
            name = fr_texts.get(str(name_id), "")
            if name:
                result[state_id] = _strip_markup(name)
    return result


def build_spell_names(spells_by_id: dict[int, dict[str, Any]], fr_texts: dict[str, str]) -> dict[int, str]:
    """
    Return {spell_id: french_name} for all spells.
    Names are stripped of all Dofus rich-text markup so they can be safely
    embedded in effect descriptions.
    """
    result: dict[int, str] = {}
    for spell_id, spell in spells_by_id.items():
        name_id = spell.get("nameId")
        if name_id:
            name = fr_texts.get(str(name_id), "")
            if name:
                result[spell_id] = _strip_markup(name)
    return result


def build_monster_names(monsters_by_id: dict[int, dict[str, Any]], fr_texts: dict[str, str]) -> dict[int, str]:
    """
    Return {monster_id: french_name} for all monsters/invocations.
    Names are stripped of all Dofus rich-text markup so they can be safely
    embedded in effect descriptions.
    """
    result: dict[int, str] = {}
    for monster_id, monster in monsters_by_id.items():
        name_id = monster.get("nameId")
        if name_id:
            name = fr_texts.get(str(name_id), "")
            if name:
                result[monster_id] = _strip_markup(name)
    return result


def _strip_markup(text: str) -> str:
    """Strip all Dofus rich-text markup from a plain string (name/value, not a template)."""
    if not text:
        return text
    # Remove color tags
    text = re.sub(r"<color=[^>]+>", "", text)
    text = re.sub(r"</color>", "", text)
    # Resolve {{spell,ID,rank::name}} → name
    text = re.sub(r"\{\{spell,\d+,\d+::([^}]+)\}\}", r"\1", text)
    # Remove remaining {{...}} blocks
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    # Remove sprite tags
    text = re.sub(r"<sprite[^>]*>", "", text)
    # Remove <br> line-break tags
    text = re.sub(r"<br\s*/?>", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    return text.strip()


def _clean_template(template: str) -> str:
    """Strip all Dofus rich-text markup from a template string without substituting #N vars."""
    text = re.sub(r"<sprite[^>]*>", "", template)
    text = re.sub(r"<color=[^>]+>", "", text)
    text = re.sub(r"</color>", "", text)
    text = re.sub(r"\{\{spell,\d+,\d+::([^}]+)\}\}", r"\1", text)
    text = re.sub(r"#1\s*\{\{[^}]*\}\}\s*#2", "#1", text)  # collapse range block to just #1
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    return text


def format_effect_text(template: str, min_val: int, max_val: int, value: int, duration: int) -> str:
    """
    Substitute Dofus template variables into a human-readable French string.

    Template syntax (Dofus):
      #1  -> diceNum (min)
      #2  -> diceSide (max)
      #3  -> value
      #4  -> duration
      #1{{~1~2 à }}#2  -> "min à max" when max differs, or just "min" otherwise
      <sprite ...>     -> removed (icon sprite)
      <color=#xxxxxx>...</color> -> removed (rich-text color markup)
      {{spell,ID,rank::name}}    -> replaced with name (inline spell reference)
    """
    # Remove sprite tags
    text = re.sub(r"<sprite[^>]*>", "", template)

    # Remove color markup — keep the inner text, strip the tags
    text = re.sub(r"<color=[^>]+>", "", text)
    text = re.sub(r"</color>", "", text)

    # Resolve {{spell,ID,rank::name}} → name
    text = re.sub(r"\{\{spell,\d+,\d+::([^}]+)\}\}", r"\1", text)

    # Handle the range pattern #1{{~1~2 à }}#2 as a single unit.
    def replace_range_block(m: re.Match) -> str:
        if max_val and max_val != min_val:
            return f"{min_val} à {max_val}"
        return str(min_val)

    text = re.sub(r"#1\s*\{\{[^}]*\}\}\s*#2", replace_range_block, text)

    # Remove any remaining {{...}} conditionals
    text = re.sub(r"\{\{[^}]*\}\}", "", text)

    # Substitute remaining standalone #N placeholders in one pass
    subs: dict[str, str] = {
        "#1": str(min_val),
        "#2": str(max_val),
        "#3": str(value),
        "#4": str(duration),
    }

    def sub_placeholder(m: re.Match) -> str:
        return subs.get(m.group(0), m.group(0))

    text = re.sub(r"#[1-4](?!\d)", sub_placeholder, text)

    # Collapse multiple spaces into one
    text = re.sub(r"  +", " ", text)

    return text.strip()


def resolve_effect_text(
    effect: dict[str, Any],
    effects_map: dict[int, dict[str, Any]],
    fr_texts: dict[str, str],
    spell_names: dict[int, str],
    state_names: dict[int, str],
    monster_names: dict[int, str],
    level_spell_names: dict[int, str],
) -> str | None:
    """
    Resolve a full human-readable French description for an effect line.

    Resolution order:
      1. State-reference effects (effectId in STATE_APPLY_EFFECT_IDS):
         Replace state ID in value with its French name.
      2. Monster/invocation-reference effects (value field):
         Replace monster/state ID in value with its French name.
      3. Monster/invocation-reference effects (min field):
         Replace monster ID in min with its French name.
      4. Spell-reference effects (effectId in SPELL_REF_*_EFFECT_IDS):
         Replace spell ID (from min or value field) with the spell's French name.
      5. Normal template substitution via effects.json descriptionId → fr.json.
      6. Fallback to theoreticalDescriptionId if descriptionId yields nothing.
    """
    effect_id = effect.get("effectId")
    if effect_id is None:
        return None

    min_val = effect.get("diceNum") or 0
    max_val = effect.get("diceSide") or 0
    value = effect.get("value") or 0
    duration = effect.get("duration") or 0

    # ── 1. State-reference effects ────────────────────────────────────────────
    if effect_id in STATE_APPLY_EFFECT_IDS:
        state_id = int(value)
        state_name = state_names.get(state_id, f"État {state_id}")

        effect_data = effects_map.get(effect_id)
        if effect_data:
            desc_id = effect_data.get("descriptionId")
            template = fr_texts.get(str(desc_id)) if desc_id else None
            if template:
                # Pass state_name as the value so #3 → state name via format_effect_text.
                # We pass a sentinel string; format_effect_text handles all tag cleanup.
                # Override #3 by treating the state name as an opaque string value.
                # Use direct substitution after format_effect_text cleans the template.
                cleaned = _clean_template(template)
                cleaned = cleaned.replace("#3", state_name)
                cleaned = re.sub(r"#[124](?!\d)", lambda m: {"#1": str(min_val), "#2": str(max_val), "#4": str(duration)}.get(m.group(0), m.group(0)), cleaned)
                cleaned = re.sub(r"  +", " ", cleaned).strip()
                if duration and duration > 0 and "tour" not in cleaned.lower():
                    cleaned = f"{cleaned} ({duration} tour{'s' if duration > 1 else ''})"
                return cleaned

        # Fallback if no template
        if effect_id == 950:
            base = state_name
        elif effect_id == 951:
            base = f"Enlève l'état {state_name}"
        else:
            base = f"Désactive l'état {state_name}"
        if duration and duration > 0:
            base = f"{base} ({duration} tour{'s' if duration > 1 else ''})"
        return base

    # ── 2a. Spell-level-reference effects (value = spell level id) ───────────
    # Effects 3792/3793: value holds a spell_level id; resolve to parent spell name.
    if effect_id in SPELL_LEVEL_REF_VALUE_EFFECT_IDS:
        level_id = int(value)
        spell_name = level_spell_names.get(level_id)
        if not spell_name:
            return None

        if effect_id == 3793:
            return f"Tue la cible et remplace par : {spell_name}"
        return f"Applique les effets de : {spell_name}"

    # ── 2b. Monster-reference effects (min field) ─────────────────────────────
    if effect_id in MONSTER_REF_MIN_EFFECT_IDS:
        monster_id = int(min_val)
        monster_name = monster_names.get(monster_id)
        
        if not monster_name:
            return None  # Unknown monster id — suppress
        
        effect_data = effects_map.get(effect_id)
        if effect_data:
            desc_id = effect_data.get("descriptionId")
            template = fr_texts.get(str(desc_id)) if desc_id else None
            if template:
                cleaned = _clean_template(template)
                cleaned = cleaned.replace("#1", monster_name)
                cleaned = re.sub(r"#[234](?!\d)", lambda m: {"#2": str(max_val), "#3": str(value), "#4": str(duration)}.get(m.group(0), m.group(0)), cleaned)
                cleaned = re.sub(r"  +", " ", cleaned).strip()
                return cleaned
        
        # Fallback
        return f"Invoque : {monster_name}"

    # ── 2a. Spell-reference effects (spell id in min field) ───────────────────
    if effect_id in SPELL_REF_MIN_EFFECT_IDS:
        spell_id = int(min_val)
        spell_name = spell_names.get(spell_id)
        if not spell_name:
            return None  # Unknown spell id — suppress

        effect_data = effects_map.get(effect_id)
        if effect_data:
            desc_id = effect_data.get("descriptionId")
            template = fr_texts.get(str(desc_id)) if desc_id else None
            if template:
                cleaned = _clean_template(template)
                cleaned = cleaned.replace("#1", spell_name)
                cleaned = re.sub(r"#[234](?!\d)", lambda m: {"#2": str(max_val), "#3": str(value), "#4": str(duration)}.get(m.group(0), m.group(0)), cleaned)
                cleaned = re.sub(r"  +", " ", cleaned).strip()
                if duration and duration > 0 and "tour" not in cleaned.lower():
                    cleaned = f"{cleaned} ({duration} tour{'s' if duration > 1 else ''})"
                return cleaned
        return spell_name

    # ── 2b. Spell-reference effects (spell id in max field, template uses #2) ──
    if effect_id in SPELL_REF_MAX_EFFECT_IDS:
        spell_id = int(max_val)
        spell_name = spell_names.get(spell_id)
        spell_label = spell_name or f"sort {spell_id}"

        effect_data = effects_map.get(effect_id)
        if effect_data:
            desc_id = effect_data.get("descriptionId")
            template = fr_texts.get(str(desc_id)) if desc_id else None
            if template:
                cleaned = _clean_template(template)
                cleaned = cleaned.replace("#2", spell_label)
                cleaned = re.sub(r"#[134](?!\d)", lambda m: {"#1": str(min_val), "#3": str(value), "#4": str(duration)}.get(m.group(0), m.group(0)), cleaned)
                return re.sub(r"  +", " ", cleaned).strip()
        if spell_name:
            return f"Enlève les effets du sort {spell_name}"
        return None

    # ── 3. Normal template resolution ─────────────────────────────────────────
    effect_data = effects_map.get(effect_id)
    if not effect_data:
        return None

    desc_id = effect_data.get("descriptionId")
    template = fr_texts.get(str(desc_id)) if desc_id else None

    # ── 4. Fallback to theoreticalDescriptionId ───────────────────────────────
    if not template:
        theo_id = effect_data.get("theoreticalDescriptionId")
        if theo_id and str(theo_id) != "0":
            template = fr_texts.get(str(theo_id))

    if not template:
        return None

    formatted = format_effect_text(template, min_val, max_val, value, duration)

    # Guard: if the result is a bare integer it means the template resolved to
    # a raw ID (e.g. "#1" where min is a spell/entity id not yet handled).
    # Suppress rather than show garbage.
    if re.fullmatch(r"-?\d+", formatted.strip()):
        return None

    # Append duration when > 0 and not already embedded
    if duration and duration > 0 and "#4" not in template and "tour" not in template.lower():
        formatted = f"{formatted} ({duration} tour{'s' if duration > 1 else ''})"

    return formatted


# SpellLevel.m_flags bit positions
FLAG_CAST_IN_LINE    = 1
FLAG_LINE_OF_SIGHT   = 4
FLAG_REQUIRES_FREE_CELL = 8
FLAG_RANGE_MODIFIABLE = 64


def decode_flags(flags: int | None) -> dict[str, bool]:
    flags = int(flags or 0)
    return {
        "lineOfSight": bool(flags & FLAG_LINE_OF_SIGHT),
        "castInLine": bool(flags & FLAG_CAST_IN_LINE),
        "requiresFreeCell": bool(flags & FLAG_REQUIRES_FREE_CELL),
        "rangeModifiable": bool(flags & FLAG_RANGE_MODIFIABLE),
    }
def clean_area(effect: dict[str, Any]) -> dict[str, Any]:
    zone = effect.get("zoneDescr") if isinstance(effect.get("zoneDescr"), dict) else {}
    shape = zone.get("shape")
    return {
        "type": ZONE_SHAPES.get(shape, "point"),
        "shape": shape,
        "size": zone.get("param1", 0),
        "param2": zone.get("param2", 0),
        "param3": zone.get("param3", 0),
    }


def decode_conditions(
    effect: dict[str, Any],
    state_names: dict[int, str],
) -> list[str]:
    """
    Decode targetMask state tokens and triggers into human-readable French condition strings.

    Returns a list of condition strings, e.g.:
      ["si Glyphe de Feu", "fin de tour"]

    Only non-trivial conditions are returned:
      - triggers='I' (on cast) is omitted — it's the default, not a condition
      - state tokens common to ALL effects in a group are omitted (done at group level)

    Uncertain labels (unconfirmed against real spell text) get a trailing "†".
    """
    conditions: list[str] = []

    def _mark(label: str, uncertain: bool) -> str:
        return f"{label}\u2009†" if uncertain else label

    # ── Trigger label ─────────────────────────────────────────────────────────
    trig = (effect.get("triggers") or "").strip()
    if trig and trig != "I":
        # Handle EOFF<id> — state expiry trigger
        if trig.startswith("EOFF"):
            sid = int(trig[4:]) if trig[4:].isdigit() else None
            if sid and sid in state_names:
                conditions.append(f"fin de {state_names[sid]}")
            else:
                conditions.append("fin d'effet")
        # Handle EON<id> — state onset trigger (state applied)
        elif trig.startswith("EON"):
            sid = int(trig[3:]) if trig[3:].isdigit() else None
            if sid and sid in state_names:
                conditions.append(f"application de {state_names[sid]}\u2009†")
            else:
                conditions.append("application d'un état\u2009†")
        else:
            entry = TRIGGER_LABELS.get(trig)
            if entry:
                conditions.append(_mark(*entry))
            elif "|" in trig:
                # Try to decode compound triggers
                parts = [TRIGGER_LABELS.get(t.strip()) for t in trig.split("|")]
                decoded = [_mark(*p) for p in parts if p]
                if decoded:
                    conditions.append(" / ".join(decoded))

    # ── Delay ─────────────────────────────────────────────────────────────────
    delay = effect.get("delay") or 0
    if delay and delay > 0:
        conditions.append(f"après {delay} tour{'s' if delay > 1 else ''}")

    return conditions


def extract_state_conditions(
    effect: dict[str, Any],
    state_names: dict[int, str],
) -> list[tuple[int, str, bool]]:
    """
    Extract state conditions from targetMask.
    Returns list of (state_id, state_name, required) tuples.
    required=True  → *E1234 or E1234 — entity must have this state
    required=False → *e1234 or e1234 — entity must NOT have this state
    """
    mask = effect.get("targetMask") or ""
    result = []
    for token in mask.split(","):
        token = token.strip()
        m = re.match(r'^\*?([Ee])(\d+)$', token)
        if not m:
            continue
        case_letter, sid_str = m.group(1), m.group(2)
        sid = int(sid_str)
        name = state_names.get(sid)
        if not name:
            continue
        required = case_letter == "E"
        result.append((sid, name, required))
    return result


def deduplicate_effects(
    effects: list[dict[str, Any]],
    state_names: dict[int, str],
) -> list[dict[str, Any]]:
    """
    Group effects with identical textFr:
      1. Fully identical effects (all fields match) → keep one, no conditions added
      2. Effects that differ only in targetMask state tokens or trigger →
         keep one canonical effect, merge the differing state conditions into
         a `conditions` field: list of {label: str, negate: bool}

    Effects that differ in area, delay, or other substantive fields are kept
    separate (they are genuinely different actions).
    """
    if not effects:
        return effects

    # Group by textFr (None-text effects pass through unchanged)
    from collections import OrderedDict
    groups: dict[str, list[dict[str, Any]]] = OrderedDict()
    no_text: list[dict[str, Any]] = []

    for e in effects:
        text = e.get("textFr")
        if text is None:
            no_text.append(e)
        else:
            groups.setdefault(text, []).append(e)

    result: list[dict[str, Any]] = []

    for text, group in groups.items():
        if len(group) == 1:
            # Only one — just decode its own conditions
            e = dict(group[0])
            conds = decode_conditions(e, state_names)
            state_conds = extract_state_conditions(e, state_names)
            if state_conds or conds:
                e["conditions"] = _build_condition_list(state_conds, conds)
            result.append(e)
            continue

        # Multiple effects with same text — classify
        # Check if they're fully identical (same area, delay, trigger, mask)
        def sig(e: dict) -> tuple:
            area = e.get("area", {})
            return (
                e.get("targetMask", ""),
                e.get("triggers", ""),
                area.get("type"),
                area.get("size"),
                e.get("delay", 0),
                e.get("dispellable"),
                e.get("value"),
            )

        sigs = [sig(e) for e in group]
        if len(set(sigs)) == 1:
            # All fully identical — deduplicate, keep first, no conditions
            result.append(group[0])
            continue

        # Check if they differ only in targetMask state tokens / triggers
        # (area, delay, dispellable, value must all be the same)
        def non_mask_sig(e: dict) -> tuple:
            area = e.get("area", {})
            return (area.get("type"), area.get("size"), e.get("delay", 0), e.get("value"))

        non_mask_sigs = [non_mask_sig(e) for e in group]
        if len(set(non_mask_sigs)) > 1:
            # Area/delay/value differ → genuinely separate effects, keep all
            for e in group:
                ec = dict(e)
                conds = decode_conditions(ec, state_names)
                state_conds = extract_state_conditions(ec, state_names)
                if state_conds or conds:
                    ec["conditions"] = _build_condition_list(state_conds, conds)
                result.append(ec)
            continue

        # Same area/delay/value, different mask/triggers.
        # Find state tokens common to ALL masks vs unique per effect.
        all_state_sets = [
            set((sid, name, req) for sid, name, req in extract_state_conditions(e, state_names))
            for e in group
        ]
        common_states = all_state_sets[0].copy()
        for s in all_state_sets[1:]:
            common_states &= s

        # Collect per-effect unique state conditions
        all_trigger_labels = [decode_conditions(e, state_names) for e in group]

        # Merge: one canonical effect with merged conditions
        canonical = dict(group[0])

        # Build merged condition list: common states first, then per-effect variants
        # "si A ou si B ou si C" for state conditions
        unique_per_effect: list[list[tuple]] = [
            [(sid, name, req) for sid, name, req in st_set - common_states]
            for st_set in all_state_sets
        ]

        # Collect all unique state conditions across effects (deduped)
        all_unique_states: list[tuple] = []
        seen_sids: set[int] = set()
        for per_eff in unique_per_effect:
            for sid, name, req in per_eff:
                if sid not in seen_sids:
                    all_unique_states.append((sid, name, req))
                    seen_sids.add(sid)

        # Collect all unique trigger labels (deduped)
        all_trigger_flat: list[str] = []
        seen_trigs: set[str] = set()
        for trig_list in all_trigger_labels:
            for t in trig_list:
                if t not in seen_trigs:
                    all_trigger_flat.append(t)
                    seen_trigs.add(t)

        condition_entries = _build_condition_list(
            list(common_states) + all_unique_states,
            all_trigger_flat,
        )
        if condition_entries:
            canonical["conditions"] = condition_entries

        result.append(canonical)

    # Re-append no-text effects unchanged
    result.extend(no_text)
    return result


def _build_condition_list(
    state_conds: list[tuple[int, str, bool]],
    trigger_labels: list[str],
) -> list[dict[str, Any]]:
    """
    Build the `conditions` list stored on each effect in the output JSON.
    Each entry: {"type": "state"|"trigger", "label": str, "negate": bool}
    """
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sid, name, required in state_conds:
        key = f"state:{sid}:{required}"
        if key not in seen:
            entries.append({"type": "state", "label": name, "negate": not required})
            seen.add(key)
    for label in trigger_labels:
        key = f"trig:{label}"
        if key not in seen:
            entries.append({"type": "trigger", "label": label, "negate": False})
            seen.add(key)
    return entries


def clean_effect(
    effect: dict[str, Any],
    effects_map: dict[int, dict[str, Any]],
    fr_texts: dict[str, str],
    spell_names: dict[int, str],
    state_names: dict[int, str],
    monster_names: dict[int, str],
    level_spell_names: dict[int, str],
) -> dict[str, Any]:
    element_id = effect.get("effectElement")
    text = resolve_effect_text(effect, effects_map, fr_texts, spell_names, state_names, monster_names, level_spell_names)
    area = clean_area(effect)
    return {
        "effectId": effect.get("effectId"),
        "element": ELEMENTS.get(element_id, f"unknown:{element_id}" if element_id is not None else None),
        "elementId": element_id,
        "min": effect.get("diceNum"),
        "max": effect.get("diceSide"),
        "value": effect.get("value"),
        "duration": effect.get("duration"),
        "delay": effect.get("delay"),
        "dispellable": effect.get("dispellable"),
        "dispellableLabel": DISPELLABLE_LABELS.get(effect.get("dispellable") or 1),
        "targetMask": effect.get("targetMask"),
        "triggers": effect.get("triggers"),
        "area": area,
        "areaBadge": area_badge(area),
        "textFr": text,
    }


def clean_level(
    level_id: int,
    level: dict[str, Any],
    effects_map: dict[int, dict[str, Any]],
    fr_texts: dict[str, str],
    spell_names: dict[int, str],
    state_names: dict[int, str],
    monster_names: dict[int, str],
    level_spell_names: dict[int, str],
) -> dict[str, Any]:
    flags = decode_flags(level.get("m_flags"))

    # Build effects first so we can derive targets from them
    cleaned_effects = deduplicate_effects([
        clean_effect(e, effects_map, fr_texts, spell_names, state_names, monster_names, level_spell_names)
        for e in arr(level.get("effects"))
        if isinstance(e, dict)
    ], state_names)

    cleaned_crits = deduplicate_effects([
        clean_effect(e, effects_map, fr_texts, spell_names, state_names, monster_names, level_spell_names)
        for e in arr(level.get("criticalEffect"))
        if isinstance(e, dict)
    ], state_names)

    # Derive targets: union of decoded target tokens across all effects with textFr.
    # Prefer the mask of the primary damage/heal effect (non-self targeting) over
    # buff-to-caster effects (mask='C' only), to reflect what the spell actually hits.
    all_target_labels: list[str] = []
    seen_labels: set[str] = set()
    # First pass: non-caster-only effects
    for e in cleaned_effects:
        if not e.get("textFr"):
            continue
        mask = e.get("targetMask") or ""
        if mask in ("C", "c"):
            continue  # skip pure self-buffs in first pass
        decoded = decode_targets(mask)
        if decoded:
            for part in decoded.split(" · "):
                if part not in seen_labels:
                    all_target_labels.append(part)
                    seen_labels.add(part)
    # Second pass: caster-only if nothing found yet
    if not all_target_labels:
        for e in cleaned_effects:
            if not e.get("textFr"):
                continue
            decoded = decode_targets(e.get("targetMask") or "")
            if decoded:
                for part in decoded.split(" · "):
                    if part not in seen_labels:
                        all_target_labels.append(part)
                        seen_labels.add(part)
                break

    targets = " · ".join(all_target_labels) if all_target_labels else None

    return {
        "id": level_id,
        "grade": level.get("grade"),
        "requiredLevel": level.get("minPlayerLevel"),
        "pa": level.get("apCost"),
        "range": {
            "min": level.get("minRange"),
            "max": level.get("range"),
            "modifiable": flags["rangeModifiable"],
        },
        "lineOfSight": flags["lineOfSight"],
        "castInLine": flags["castInLine"],
        "requiresFreeCell": flags["requiresFreeCell"],
        "castsPerTurn": level.get("maxCastPerTurn"),
        "castsPerTarget": level.get("maxCastPerTarget"),
        "cooldown": level.get("globalCooldown"),
        "initialCooldown": level.get("initialCooldown"),
        "minCastInterval": level.get("minCastInterval"),
        "stackLimit": level.get("maxStack"),
        "criticalRate": level.get("criticalHitProbability"),
        "targets": targets,
        "effects": cleaned_effects,
        "criticalEffects": cleaned_crits,
        "rawFlags": level.get("m_flags"),
    }


def build_variant_maps(
    variants_by_id: dict[int, dict[str, Any]],
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    variant_of: dict[int, int] = {}
    variant_to_base: dict[int, int] = {}
    spell_to_variant_group: dict[int, int] = {}

    for group_id, variant in variants_by_id.items():
        spell_ids = arr(variant.get("spellIds"))
        if len(spell_ids) < 2:
            legacy_base = variant.get("spell")
            legacy_variant = variant.get("spellVariant")
            spell_ids = [legacy_base, legacy_variant] if legacy_base and legacy_variant else []
        if len(spell_ids) < 2:
            continue

        base, alt = int(spell_ids[0]), int(spell_ids[1])
        variant_of[base] = alt
        variant_of[alt] = base
        variant_to_base[alt] = base
        spell_to_variant_group[base] = group_id
        spell_to_variant_group[alt] = group_id

    return variant_of, variant_to_base, spell_to_variant_group


def build_dataset(data_dir: Path) -> list[dict[str, Any]]:
    # Load French translations
    raw_fr = load_json(data_dir, "fr.json")
    fr_texts = build_fr_translations(raw_fr)

    # Load effects map
    effects_raw = load_json(Path(__file__).parent, "effects.json")
    if not effects_raw:
        effects_raw = load_json(data_dir, "effects.json")
    effects_map = build_effects_map(effects_raw)

    # Load spell states for state-name resolution.
    # spell_states.json may live in the project root (downloaded there) or in data_dir.
    states_raw = load_json(Path(__file__).parent, "spell_states.json")
    if not states_raw:
        states_raw = load_json(data_dir, "spell_states.json")
    state_names = build_state_names(states_raw, fr_texts)
    log(f"  Loaded {len(state_names)} state names")

    # Load monsters for invocation-name resolution
    monsters_raw = load_json(data_dir, "monsters.json")
    monsters_by_id = extract_refs(monsters_raw) if monsters_raw else {}
    monster_names = build_monster_names(monsters_by_id, fr_texts)
    log(f"  Loaded {len(monster_names)} monster/invocation names for reference resolution")

    spells_by_id = extract_refs(load_json(data_dir, "spells.json"))
    levels_by_id = extract_refs(load_json(data_dir, "spell_levels.json"))
    variants_by_id = extract_refs(load_json(data_dir, "spell_variants.json"))
    breeds_by_id = extract_refs(load_json(data_dir, "breeds.json"))

    # Build spell name map (all spells, not just class spells) for reference resolution
    spell_names = build_spell_names(spells_by_id, fr_texts)
    log(f"  Loaded {len(spell_names)} spell names for reference resolution")

    # Build level_id → spell_name map (for effects 3792/3793 which carry a spell level id)
    level_spell_names: dict[int, str] = {}
    for lid, lv in levels_by_id.items():
        sid = lv.get("spellId")
        if sid:
            name = spell_names.get(int(sid))
            if name:
                level_spell_names[lid] = name
    log(f"  Loaded {len(level_spell_names)} level→spell name entries")

    variant_of, variant_to_base, spell_to_variant_group = build_variant_maps(variants_by_id)
    class_spell_ids: set[int] = set()
    spell_to_breed: dict[int, int] = {}
    breed_names: dict[int, str] = {}

    for breed_id, breed in breeds_by_id.items():
        base_ids = [int(spell_id) for spell_id in arr(breed.get("breedSpellsId"))]
        if len(base_ids) != 22:
            continue
        short_name_id = breed.get("shortNameId")
        breed_names[breed_id] = fr_texts.get(str(short_name_id), "") if short_name_id else ""
        for spell_id in base_ids:
            class_spell_ids.add(spell_id)
            spell_to_breed[spell_id] = breed_id
            variant_id = variant_of.get(spell_id)
            if variant_id:
                class_spell_ids.add(variant_id)
                spell_to_breed[variant_id] = breed_id

    clean_spells = []
    for spell_id in sorted(class_spell_ids):
        spell = spells_by_id.get(spell_id)
        if not spell:
            continue
        breed_id = spell_to_breed.get(spell_id)
        level_ids = [int(level_id) for level_id in arr(spell.get("spellLevels"))]
        levels = [
            clean_level(level_id, levels_by_id[level_id], effects_map, fr_texts, spell_names, state_names, monster_names, level_spell_names)
            for level_id in level_ids
            if level_id in levels_by_id
        ]

        name_id = spell.get("nameId")
        desc_id = spell.get("descriptionId")
        name_fr = fr_texts.get(str(name_id), "") if name_id else ""
        desc_fr = fr_texts.get(str(desc_id), "") if desc_id else ""

        icon_id = spell.get("iconId")
        class_name_fr = breed_names.get(breed_id, "")

        clean_spells.append(
            {
                "id": spell_id,
                "ankamaId": spell.get("id", spell_id),
                "nameFr": name_fr,
                "descriptionFr": desc_fr,
                "iconId": icon_id,
                "imgUrl": f"/images/spells/img/spell/1x/sort_{icon_id}-48.png" if icon_id else None,
                "class": {
                    "breedId": breed_id,
                    "nameFr": class_name_fr,
                    "imgUrl": f"/images/classes/img/class_head/2x/Head_{breed_id * 10}-64.png",
                },
                "isVariant": spell_id in variant_to_base,
                "variantOf": variant_to_base.get(spell_id),
                "variantSpellId": variant_of.get(spell_id),
                "variantGroupId": spell_to_variant_group.get(spell_id),
                "levels": levels,
            }
        )

    return clean_spells


def validate_counts(spells: list[dict[str, Any]]) -> None:
    by_breed: dict[int, int] = {}
    for spell in spells:
        breed_id = spell["class"]["breedId"]
        by_breed[breed_id] = by_breed.get(breed_id, 0) + 1

    expected_breeds = 19
    expected_spells_per_breed = 44
    problems = [
        f"breed {breed_id}: {count} spells"
        for breed_id, count in sorted(by_breed.items())
        if count != expected_spells_per_breed
    ]
    if len(by_breed) != expected_breeds or problems:
        details = "; ".join(problems) if problems else "breed count mismatch"
        raise RuntimeError(
            f"Expected {expected_breeds} breeds x {expected_spells_per_breed} spells; "
            f"got {len(by_breed)} breeds, {len(spells)} spells. {details}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--no-strict-counts", action="store_true")
    args = parser.parse_args()

    if not args.no_download:
        download_missing(args.data_dir)

    log("Building clean spell dataset (French)...")
    spells = build_dataset(args.data_dir)
    if not args.no_strict_counts:
        validate_counts(spells)

    args.out.write_text(json.dumps(spells, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Wrote {len(spells)} spells to {args.out}")

    # Verify samples
    for spell_name in ("Bond", "Agitation", "Pression"):
        sample = next((s for s in spells if s.get("nameFr") == spell_name), None)
        if sample:
            log(f"\nSample — {spell_name} effects (grade 1):")
            for e in sample["levels"][0]["effects"]:
                log(f"  effectId={e['effectId']:>5} -> {e['textFr']!r}")
            if sample["levels"][0]["criticalEffects"]:
                log(f"  criticalEffects:")
                for e in sample["levels"][0]["criticalEffects"]:
                    log(f"  effectId={e['effectId']:>5} -> {e['textFr']!r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
