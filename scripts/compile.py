#!/usr/bin/env python3
"""Zero-dependency Python 3 compiler and validator for bg-teach-v1 guides."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

SCHEMA_VERSION = "bg-teach-v1"
PLACEHOLDER = "<!-- BG_TEACH_GUIDE_JSON -->"

CITATION_RE = re.compile(
    r"^\((Rulebook p\. \d+(?:[–-]\d+)?|Publisher Errata[^)]*|Publisher FAQ[^)]*|Living Rulebook[^)]*|BG\.SE #\d+|Owner notes\.md)\)$"
)
BG_SE_RE = re.compile(r"^\(BG\.SE #\d+\)$")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^[-*]\s+(.+?)\s*$")

FORBIDDEN_SVG_TAGS = {"script", "foreignobject", "iframe"}
URI_ATTRS = {"href", "src"}


class _ExitOneArgumentParser(argparse.ArgumentParser):
    """Ensure CLI syntax/usage errors exit 1, reserving exit 2 for validation."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


class _GuideIslandExtractor(HTMLParser):
    """Extract raw JSON text inside <script id="guide-data" ...>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._in_target = False
        self._chunks: list[str] = []
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script" or self.found:
            return
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if attr_map.get("id") == "guide-data":
            self._in_target = True
            self.found = True

    def handle_data(self, data: str) -> None:
        if self._in_target:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_target:
            self._in_target = False

    def payload(self) -> str:
        return "".join(self._chunks)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def parse_notes_md(notes_path: Path) -> dict[str, object]:
    """Deterministically parse a UTF-8 Markdown addendum file into owner_notes."""
    raw = notes_path.read_text(encoding="utf-8")
    cleaned = HTML_COMMENT_RE.sub("", raw)
    heading = ""
    entries: list[str] = []
    for line in cleaned.splitlines():
        raw_line = line.rstrip()
        stripped = raw_line.strip()
        if not stripped:
            continue
        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            heading = heading_match.group(1).strip()
            continue
        bullet_match = BULLET_RE.match(raw_line)
        if bullet_match:
            body = bullet_match.group(1).strip()
            entries.append(f"{heading}: {body}" if heading else body)
    return {"file": notes_path.name, "entries": entries}


def validate_svg(
    svg_text: object,
    path: str,
    errors: list[str],
    *,
    require_flow_a11y: bool,
) -> None:
    """Validate and sanitize inline <svg> markup via xml.etree.ElementTree."""
    if not _is_nonempty_str(svg_text):
        errors.append(f"{path}: must be a non-empty inline <svg> string")
        return

    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        errors.append(f"{path}: invalid XML in inline <svg> ({exc})")
        return

    if _local_name(root.tag) != "svg":
        errors.append(f"{path}: root element must be <svg>, got <{root.tag}>")
        return

    has_title = False
    has_desc = False
    for elem in root.iter():
        raw_tag = elem.tag.rsplit("}", 1)[-1]
        tag_name = raw_tag.lower()
        if tag_name in FORBIDDEN_SVG_TAGS:
            errors.append(f"{path}: forbidden element <{raw_tag}> inside <svg>")
        if tag_name == "title" and "".join(elem.itertext()).strip():
            has_title = True
        if tag_name == "desc" and "".join(elem.itertext()).strip():
            has_desc = True

        for attr_name, attr_val in elem.attrib.items():
            attr_local = _local_name(attr_name)
            if attr_local.startswith("on"):
                errors.append(f"{path}: forbidden event handler attribute '{attr_name}'")
            if attr_local in URI_ATTRS:
                normalized = re.sub(r"[\x00-\x20]+", "", attr_val).lower()
                for forbidden_scheme in ("javascript:", "data:text/html"):
                    if normalized.startswith(forbidden_scheme):
                        errors.append(
                            f"{path}: forbidden URI scheme '{forbidden_scheme}' in attribute '{attr_name}'"
                        )
                        break

    if require_flow_a11y:
        if not _is_nonempty_str(root.attrib.get("viewBox")):
            errors.append(f"{path}: turn_flow_svg requires a non-empty viewBox attribute")
        if not has_title:
            errors.append(f"{path}: turn_flow_svg requires a non-empty <title> element")
        if not has_desc:
            errors.append(f"{path}: turn_flow_svg requires a non-empty <desc> element")


def _check_citations(
    record: dict[str, object],
    path: str,
    errors: list[str],
    cited_bgse: set[str],
) -> None:
    citations = record.get("citations")
    if not isinstance(citations, list) or not citations:
        errors.append(f"{path}.citations: must be a non-empty list of citations")
        return
    for idx, cite in enumerate(citations):
        if not isinstance(cite, str) or CITATION_RE.fullmatch(cite) is None:
            errors.append(f"{path}.citations[{idx}]: invalid citation {cite!r}")
            continue
        if BG_SE_RE.fullmatch(cite):
            cited_bgse.add(cite)


def _check_required_str(obj: dict[str, object], key: str, path: str, errors: list[str]) -> None:
    if not _is_nonempty_str(obj.get(key)):
        errors.append(f"{path}.{key}: must be a non-empty string")


def _check_player_map(
    mapping: object,
    player_keys: list[str],
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(mapping, dict):
        errors.append(f"{path}: must be an object keyed by player count")
        return
    for key in player_keys:
        if not _is_nonempty_str(mapping.get(key)):
            errors.append(f"{path}.{key}: missing or empty text for {key} players")


def validate_guide(data: object) -> list[str]:
    """Validate a bg-teach-v1 guide object and return structured error messages."""
    errors: list[str] = []
    cited_bgse: set[str] = set()

    if not isinstance(data, dict):
        return ["root: guide payload must be a JSON object"]

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: expected {SCHEMA_VERSION!r}, got {data.get('schema_version')!r}")

    if data.get("status") not in ("draft", "verified"):
        errors.append(f"status: expected 'draft' or 'verified', got {data.get('status')!r}")

    if "bgg_id" not in data:
        errors.append("bgg_id: required field (positive integer or null)")
    else:
        bgg_id = data["bgg_id"]
        if bgg_id is not None and not (_is_int(bgg_id) and bgg_id > 0):
            errors.append("bgg_id: must be a positive integer or null")

    if "game_uuid" not in data:
        errors.append("game_uuid: required field (non-empty string or null)")
    else:
        game_uuid = data["game_uuid"]
        if game_uuid is not None and not _is_nonempty_str(game_uuid):
            errors.append("game_uuid: must be a non-empty string or null")

    # meta
    meta = data.get("meta")
    min_players = 1
    max_players = 1
    valid_bounds = False
    if not isinstance(meta, dict):
        errors.append("meta: must be an object")
    else:
        for field in ("title", "subtitle", "publisher"):
            _check_required_str(meta, field, "meta", errors)
        weight = meta.get("weight")
        if not (_is_number(weight) and weight > 0):
            errors.append("meta.weight: must be a number > 0")
        for field in ("playtime_min", "teach_time_min"):
            val = meta.get(field)
            if not (_is_int(val) and val > 0):
                errors.append(f"meta.{field}: must be an integer > 0")
        p_min = meta.get("min_players")
        p_max = meta.get("max_players")
        if not _is_int(p_min) or not _is_int(p_max):
            errors.append("meta.min_players/max_players: must be integers")
        elif p_min < 1 or p_max > 12 or p_min > p_max:
            errors.append("meta.min_players/max_players: must satisfy 1 <= min_players <= max_players <= 12")
        else:
            min_players = p_min
            max_players = p_max
            valid_bounds = True

    player_keys = [str(n) for n in range(min_players, max_players + 1)] if valid_bounds else []

    # links
    links = data.get("links")
    if not isinstance(links, dict):
        errors.append("links: must be an object")
    else:
        for nullable_key in ("official_pdf_url", "official_pdf_label", "pdf_local_path", "pdf_local_label"):
            if nullable_key not in links:
                errors.append(f"links.{nullable_key}: required field (non-empty string or null)")
            else:
                val = links[nullable_key]
                if val is not None and not _is_nonempty_str(val):
                    errors.append(f"links.{nullable_key}: must be a non-empty string or null")
        _check_required_str(links, "bgg_search_url", "links", errors)
        _check_required_str(links, "bgg_search_label", "links", errors)
        has_official = _is_nonempty_str(links.get("official_pdf_url"))
        has_local = _is_nonempty_str(links.get("pdf_local_path"))
        if not has_official and not has_local:
            errors.append("links: at least one of official_pdf_url or pdf_local_path must be non-null")
        if has_official and not _is_nonempty_str(links.get("official_pdf_label")):
            errors.append("links.official_pdf_label: required when official_pdf_url is set")
        if has_local and not _is_nonempty_str(links.get("pdf_local_label")):
            errors.append("links.pdf_local_label: required when pdf_local_path is set")

    # Pre-validate stage5_reference errata_list and verify_before_table for cross-stage IDs
    stage5 = data.get("stage5_reference")
    errata_ids: set[str] = set()
    verify_ids: set[str] = set()
    if isinstance(stage5, dict):
        errata_list = stage5.get("errata_list")
        if isinstance(errata_list, list):
            for idx, item in enumerate(errata_list):
                if isinstance(item, dict) and _is_nonempty_str(item.get("id")):
                    eid = item["id"]
                    if eid in errata_ids:
                        errors.append(f"stage5_reference.errata_list[{idx}].id: duplicate id {eid!r}")
                    errata_ids.add(eid)
        verify_list = stage5.get("verify_before_table")
        if isinstance(verify_list, list):
            for idx, item in enumerate(verify_list):
                if isinstance(item, dict) and _is_nonempty_str(item.get("id")):
                    vid = item["id"]
                    if vid in verify_ids:
                        errors.append(f"stage5_reference.verify_before_table[{idx}].id: duplicate id {vid!r}")
                    verify_ids.add(vid)

    # stage1_hook
    stage1 = data.get("stage1_hook")
    if not isinstance(stage1, dict):
        errors.append("stage1_hook: must be an object")
    else:
        for field in ("title", "physical_cue", "pitch_aloud", "win_summary"):
            _check_required_str(stage1, field, "stage1_hook", errors)
        if valid_bounds:
            _check_player_map(
                stage1.get("win_trigger_by_players"),
                player_keys,
                "stage1_hook.win_trigger_by_players",
                errors,
            )
        _check_citations(stage1, "stage1_hook", errors, cited_bgse)

    # stage2_setup
    stage2 = data.get("stage2_setup")
    if not isinstance(stage2, dict):
        errors.append("stage2_setup: must be an object")
    else:
        shared_board = stage2.get("shared_board")
        per_player = stage2.get("per_player")
        if not isinstance(shared_board, list):
            errors.append("stage2_setup.shared_board: must be a list")
        if not isinstance(per_player, list):
            errors.append("stage2_setup.per_player: must be a list")
        if isinstance(shared_board, list) and isinstance(per_player, list) and not (shared_board or per_player):
            errors.append("stage2_setup: must contain at least one setup item")

        seen_setup_ids: set[str] = set()
        for group_name in ("shared_board", "per_player"):
            items = stage2.get(group_name)
            if not isinstance(items, list):
                continue
            for idx, item in enumerate(items):
                item_path = f"stage2_setup.{group_name}[{idx}]"
                if not isinstance(item, dict):
                    errors.append(f"{item_path}: must be an object")
                    continue
                _check_required_str(item, "id", item_path, errors)
                _check_required_str(item, "name", item_path, errors)
                item_id = item.get("id")
                if _is_nonempty_str(item_id):
                    if item_id in seen_setup_ids:
                        errors.append(f"{item_path}.id: duplicate setup item id {item_id!r}")
                    seen_setup_ids.add(item_id)

                if "deltas" not in item:
                    errors.append(f"{item_path}.deltas: required (player-count map or null)")
                else:
                    deltas = item.get("deltas")
                    if deltas is None:
                        _check_required_str(item, "static_text", item_path, errors)
                    elif valid_bounds:
                        _check_player_map(deltas, player_keys, f"{item_path}.deltas", errors)

                errata_ref = item.get("errata_ref")
                if errata_ref is not None:
                    if not _is_nonempty_str(errata_ref) or errata_ref not in errata_ids:
                        errors.append(f"{item_path}.errata_ref: unknown errata id {errata_ref!r}")

                verify_ref = item.get("verify_ref")
                if verify_ref is not None:
                    if not _is_nonempty_str(verify_ref) or verify_ref not in verify_ids:
                        errors.append(f"{item_path}.verify_ref: unknown verify id {verify_ref!r}")

                verify_players = item.get("verify_players")
                if verify_players is not None:
                    if not isinstance(verify_players, list) or not verify_players:
                        errors.append(f"{item_path}.verify_players: must be a non-empty list of player counts")
                    elif valid_bounds:
                        for v_idx, p_val in enumerate(verify_players):
                            if not _is_int(p_val) or p_val < min_players or p_val > max_players:
                                errors.append(
                                    f"{item_path}.verify_players[{v_idx}]: {p_val!r} outside {min_players}..{max_players}"
                                )

                _check_citations(item, item_path, errors, cited_bgse)

    # stage3_turn
    stage3 = data.get("stage3_turn")
    if not isinstance(stage3, dict):
        errors.append("stage3_turn: must be an object")
    else:
        _check_required_str(stage3, "summary", "stage3_turn", errors)
        validate_svg(
            stage3.get("turn_flow_svg"),
            "stage3_turn.turn_flow_svg",
            errors,
            require_flow_a11y=True,
        )
        phases = stage3.get("phases")
        if not isinstance(phases, list) or not phases:
            errors.append("stage3_turn.phases: must be a non-empty list")
        else:
            for idx, phase in enumerate(phases):
                p_path = f"stage3_turn.phases[{idx}]"
                if not isinstance(phase, dict):
                    errors.append(f"{p_path}: must be an object")
                    continue
                if not (_is_int(phase.get("step")) and phase["step"] > 0):
                    errors.append(f"{p_path}.step: must be an integer > 0")
                for field in ("id", "name", "physical_cue", "say_aloud", "player_summary"):
                    _check_required_str(phase, field, p_path, errors)
                errata_ref = phase.get("errata_ref")
                if errata_ref is not None:
                    if not _is_nonempty_str(errata_ref) or errata_ref not in errata_ids:
                        errors.append(f"{p_path}.errata_ref: unknown errata id {errata_ref!r}")
                if "subactions" in phase:
                    subactions = phase["subactions"]
                    if not isinstance(subactions, list):
                        errors.append(f"{p_path}.subactions: must be a list")
                    else:
                        for s_idx, sub in enumerate(subactions):
                            s_path = f"{p_path}.subactions[{s_idx}]"
                            if not isinstance(sub, dict):
                                errors.append(f"{s_path}: must be an object")
                                continue
                            _check_required_str(sub, "name", s_path, errors)
                            _check_required_str(sub, "detail", s_path, errors)
                            sub_err = sub.get("errata_ref")
                            if sub_err is not None:
                                if not _is_nonempty_str(sub_err) or sub_err not in errata_ids:
                                    errors.append(f"{s_path}.errata_ref: unknown errata id {sub_err!r}")
                            _check_citations(sub, s_path, errors, cited_bgse)
                _check_citations(phase, p_path, errors, cited_bgse)

        if "free_action" not in stage3:
            errors.append("stage3_turn.free_action: required field (object or null)")
        else:
            free_action = stage3["free_action"]
            if free_action is not None:
                if not isinstance(free_action, dict):
                    errors.append("stage3_turn.free_action: must be an object or null")
                else:
                    _check_required_str(free_action, "name", "stage3_turn.free_action", errors)
                    _check_required_str(free_action, "detail", "stage3_turn.free_action", errors)
                    _check_citations(free_action, "stage3_turn.free_action", errors, cited_bgse)

    # stage4_first_round
    stage4 = data.get("stage4_first_round")
    if not isinstance(stage4, list) or not stage4:
        errors.append("stage4_first_round: must be a non-empty list")
    else:
        for idx, beat in enumerate(stage4):
            b_path = f"stage4_first_round[{idx}]"
            if not isinstance(beat, dict):
                errors.append(f"{b_path}: must be an object")
                continue
            if not (_is_int(beat.get("beat")) and beat["beat"] > 0):
                errors.append(f"{b_path}.beat: must be an integer > 0")
            for field in ("title", "physical_cue", "say_aloud"):
                _check_required_str(beat, field, b_path, errors)
            _check_citations(beat, b_path, errors, cited_bgse)

    # stage5_reference
    if not isinstance(stage5, dict):
        errors.append("stage5_reference: must be an object")
    else:
        if "top_gotchas" in stage5:
            top_gotchas = stage5["top_gotchas"]
            if not isinstance(top_gotchas, list):
                errors.append("stage5_reference.top_gotchas: must be a list")
            else:
                for idx, g in enumerate(top_gotchas):
                    g_path = f"stage5_reference.top_gotchas[{idx}]"
                    if not isinstance(g, dict):
                        errors.append(f"{g_path}: must be an object")
                        continue
                    _check_required_str(g, "title", g_path, errors)
                    _check_required_str(g, "detail", g_path, errors)
                    _check_citations(g, g_path, errors, cited_bgse)

        edge_cases = stage5.get("edge_cases")
        if not isinstance(edge_cases, list):
            errors.append("stage5_reference.edge_cases: must be a list")
        else:
            for idx, ec in enumerate(edge_cases):
                e_path = f"stage5_reference.edge_cases[{idx}]"
                if not isinstance(ec, dict):
                    errors.append(f"{e_path}: must be an object")
                    continue
                for field in ("id", "title", "detail"):
                    _check_required_str(ec, field, e_path, errors)
                _check_citations(ec, e_path, errors, cited_bgse)

        errata_list = stage5.get("errata_list")
        if not isinstance(errata_list, list):
            errors.append("stage5_reference.errata_list: must be a list")
        else:
            for idx, err in enumerate(errata_list):
                er_path = f"stage5_reference.errata_list[{idx}]"
                if not isinstance(err, dict):
                    errors.append(f"{er_path}: must be an object")
                    continue
                for field in ("id", "title", "location", "printed", "corrected"):
                    _check_required_str(err, field, er_path, errors)
                _check_citations(err, er_path, errors, cited_bgse)

        verify_list = stage5.get("verify_before_table")
        if not isinstance(verify_list, list):
            errors.append("stage5_reference.verify_before_table: must be a list")
        else:
            for idx, item in enumerate(verify_list):
                v_path = f"stage5_reference.verify_before_table[{idx}]"
                if not isinstance(item, dict):
                    errors.append(f"{v_path}: must be an object")
                    continue
                for field in ("id", "title", "detail"):
                    _check_required_str(item, field, v_path, errors)
                _check_citations(item, v_path, errors, cited_bgse)

        if "owner_notes" not in stage5:
            errors.append("stage5_reference.owner_notes: required field (object or null)")
        else:
            owner_notes = stage5["owner_notes"]
            if owner_notes is not None:
                if not isinstance(owner_notes, dict):
                    errors.append("stage5_reference.owner_notes: must be an object or null")
                else:
                    _check_required_str(owner_notes, "file", "stage5_reference.owner_notes", errors)
                    entries = owner_notes.get("entries")
                    if not isinstance(entries, list):
                        errors.append("stage5_reference.owner_notes.entries: must be a list")
                    else:
                        for idx, entry in enumerate(entries):
                            if not _is_nonempty_str(entry):
                                errors.append(f"stage5_reference.owner_notes.entries[{idx}]: must be a non-empty string")

        iconography = stage5.get("iconography")
        if not isinstance(iconography, list):
            errors.append("stage5_reference.iconography: must be a list")
        else:
            for idx, ic in enumerate(iconography):
                ic_path = f"stage5_reference.iconography[{idx}]"
                if not isinstance(ic, dict):
                    errors.append(f"{ic_path}: must be an object")
                    continue
                for field in ("id", "name", "effect"):
                    _check_required_str(ic, field, ic_path, errors)
                if "svg" in ic and ic["svg"] is not None:
                    validate_svg(ic["svg"], f"{ic_path}.svg", errors, require_flow_a11y=False)
                _check_citations(ic, ic_path, errors, cited_bgse)

        scoring = stage5.get("scoring")
        if not isinstance(scoring, dict):
            errors.append("stage5_reference.scoring: must be an object")
        else:
            rows = scoring.get("rows")
            if not isinstance(rows, list) or not rows:
                errors.append("stage5_reference.scoring.rows: must be a non-empty list")
            else:
                for idx, row in enumerate(rows):
                    r_path = f"stage5_reference.scoring.rows[{idx}]"
                    if not isinstance(row, dict):
                        errors.append(f"{r_path}: must be an object")
                        continue
                    _check_required_str(row, "source", r_path, errors)
                    _check_required_str(row, "points", r_path, errors)
                    _check_citations(row, r_path, errors, cited_bgse)
            _check_required_str(scoring, "tiebreakers", "stage5_reference.scoring", errors)

        _check_required_str(stage5, "precedence", "stage5_reference", errors)

        cc_by_sa = stage5.get("cc_by_sa")
        present_cc: set[str] = set()
        if not isinstance(cc_by_sa, list):
            errors.append("stage5_reference.cc_by_sa: must be a list")
        else:
            for idx, attr in enumerate(cc_by_sa):
                c_path = f"stage5_reference.cc_by_sa[{idx}]"
                if not isinstance(attr, dict):
                    errors.append(f"{c_path}: must be an object")
                    continue
                for field in ("citation", "author", "license", "note"):
                    _check_required_str(attr, field, c_path, errors)
                cite_val = attr.get("citation")
                if isinstance(cite_val, str):
                    if BG_SE_RE.fullmatch(cite_val) is None:
                        errors.append(f"{c_path}.citation: must match '(BG.SE #<id>)', got {cite_val!r}")
                    else:
                        present_cc.add(cite_val)

        for missing_cite in sorted(cited_bgse - present_cc):
            errors.append(
                f"stage5_reference.cc_by_sa: missing attribution entry for cited {missing_cite}"
            )

    return errors


def _reject_json_constant(val: str) -> None:
    raise ValueError(f"non-standard JSON constant {val!r} is not allowed")


def _load_json_strict(raw_text: str) -> object:
    return json.loads(raw_text, parse_constant=_reject_json_constant)


def extract_json_from_html(html_path: Path) -> object:
    """Extract and parse <script id="guide-data"> from a compiled HTML guide."""
    html_text = html_path.read_text(encoding="utf-8")
    extractor = _GuideIslandExtractor()
    extractor.feed(html_text)
    extractor.close()
    if not extractor.found:
        raise ValueError(f"missing <script id=\"guide-data\"> element in {html_path}")
    raw_payload = extractor.payload().strip()
    if not raw_payload or raw_payload == PLACEHOLDER:
        raise ValueError(f"<script id=\"guide-data\"> in {html_path} does not contain compiled JSON")
    return _load_json_strict(raw_payload)


def escape_json_for_html(data: dict[str, object]) -> str:
    """Serialize JSON safely for embedding inside HTML <script type="application/json">."""
    serialized = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    return (
        serialized.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_parser() -> _ExitOneArgumentParser:
    default_template = Path(__file__).resolve().parent.parent / "assets" / "template.html"
    parser = _ExitOneArgumentParser(
        prog="compile.py",
        description="Validate and compile a bg-teach-v1 guide.json into a single-file Variant C HTML guide.",
    )
    parser.add_argument("guide_json", nargs="?", help="Path to guide.json input file")
    parser.add_argument("--from-html", dest="from_html", help="Recompile JSON extracted from an existing compiled HTML file")
    parser.add_argument("-o", "--output", dest="output_html", help="Output compiled HTML file path")
    parser.add_argument("--validate-only", action="store_true", help="Validate without emitting HTML")
    parser.add_argument("--template", default=str(default_template), help="Path to assets/template.html")
    parser.add_argument("--notes", help="Path to local UTF-8 Markdown notes.md addendum")
    parser.add_argument("--shared", action="store_true", help="Strip private local PDF path/label from output")
    parser.add_argument("--strip-notes", action="store_true", help="Strip owner_notes from output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.guide_json) == bool(args.from_html):
        parser.error("provide exactly one of <guide.json> or --from-html <in.html>")
    if bool(args.output_html) == bool(args.validate_only):
        parser.error("provide exactly one of -o <out.html> or --validate-only")

    try:
        if args.from_html:
            data = extract_json_from_html(Path(args.from_html))
        else:
            raw_json = Path(args.guide_json).read_text(encoding="utf-8")
            data = _load_json_strict(raw_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"compile.py: input error: {exc}", file=sys.stderr)
        return 1

    if args.notes:
        try:
            merged_notes = parse_notes_md(Path(args.notes))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"compile.py: notes error: {exc}", file=sys.stderr)
            return 1
        if isinstance(data, dict) and isinstance(data.get("stage5_reference"), dict):
            data["stage5_reference"]["owner_notes"] = merged_notes

    errors = validate_guide(data)
    if errors:
        print("Validation failed:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 2

    assert isinstance(data, dict)
    if args.shared:
        data["links"]["pdf_local_path"] = None
        data["links"]["pdf_local_label"] = None
    if args.strip_notes:
        data["stage5_reference"]["owner_notes"] = None

    if args.validate_only:
        return 0

    template_path = Path(args.template)
    try:
        template_text = template_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"compile.py: template read error: {exc}", file=sys.stderr)
        return 1

    if PLACEHOLDER not in template_text:
        print(
            f"compile.py: template error: missing {PLACEHOLDER!r} placeholder in {template_path}",
            file=sys.stderr,
        )
        return 1

    compiled_html = template_text.replace(PLACEHOLDER, escape_json_for_html(data), 1)
    out_path = Path(args.output_html)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(compiled_html, encoding="utf-8")
    except OSError as exc:
        print(f"compile.py: output write error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
