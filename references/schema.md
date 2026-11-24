# `bg-teach-v1` Normative Schema & Addendum Contract

This document is the normative specification for `guide.json`, inline `<svg>` safety, citation validation, source precedence, and deterministic `notes.md` merging enforced by `scripts/compile.py`.

## 1. Top-Level Envelope (`bg-teach-v1`)

| Field | Type | Required | Rules |
|---|---|---|---|
| `schema_version` | `string` | Yes | Must equal `"bg-teach-v1"`. |
| `status` | `string` | Yes | Must be `"draft"` or `"verified"`. New guides start as `"draft"` until live table verification. |
| `bgg_id` | `int \| null` | Yes | Positive integer (`> 0`, not boolean) or `null`. Optional Phase 2 library hook. |
| `game_uuid` | `string \| null` | Yes | Non-empty string or `null`. Optional Phase 2 library hook; drives `localStorage` key `bg-teach:v1:<game_uuid-or-slug>`. |
| `meta` | `object` | Yes | Game metadata and player bounds. |
| `links` | `object` | Yes | Official PDF, optional private local PDF, and browser-only BGG search links. |
| `stage1_hook` | `object` | Yes | Stage 1 pitch, physical cue, win summary, and per-player-count win triggers. |
| `stage2_setup` | `object` | Yes | Parameterized setup checklists (`shared_board[]`, `per_player[]`). |
| `stage3_turn` | `object` | Yes | Turn overview, inline `turn_flow_svg`, ordered `phases[]`, and nullable `free_action`. |
| `stage4_first_round` | `array` | Yes | Non-empty list of Guided First Round beats. |
| `stage5_reference` | `object` | Yes | Edge cases, errata, ambiguities, owner notes, iconography, scoring, precedence, and CC BY-SA attributions. |

## 2. Section Contracts

### `meta`

```json
{
  "title": "Lantern Harbor",
  "subtitle": "Coastal Charter & Beacon Route-Building",
  "publisher": "Tideglass Games",
  "weight": 2.6,
  "min_players": 2,
  "max_players": 5,
  "playtime_min": 60,
  "teach_time_min": 8
}
```

- `title`, `subtitle`, `publisher`: non-empty strings.
- `weight`: number `> 0` (float or int, not boolean).
- `min_players`, `max_players`: integers (not boolean) satisfying `1 <= min_players <= max_players <= 12`.
- `playtime_min`, `teach_time_min`: integers `> 0` (not boolean).

### `links`

```json
{
  "official_pdf_url": "https://example.com/rulebook.pdf",
  "official_pdf_label": "Official Publisher PDF",
  "pdf_local_path": "./sidecar/rulebook.pdf",
  "pdf_local_label": "Local PDF (private sidecar)",
  "bgg_search_url": "https://boardgamegeek.com/geeksearch.php?action=search&objecttype=boardgame&q=...",
  "bgg_search_label": "Search BGG Rules Forum (Browser Only)"
}
```

- `official_pdf_url`, `official_pdf_label`, `pdf_local_path`, `pdf_local_label`: string or `null`.
- Before `--shared` is applied, at least one of `official_pdf_url` or `pdf_local_path` must be a non-empty string (supports out-of-print games with only a local scanned PDF).
- When `official_pdf_url` is non-empty, `official_pdf_label` must be a non-empty string.
- When `pdf_local_path` is non-empty, `pdf_local_label` must be a non-empty string.
- `bgg_search_url` and `bgg_search_label`: required non-empty strings. Never embed a PDF or scrape BGG in automated context.
- Compiling with `--shared` sets `links.pdf_local_path = null` and `links.pdf_local_label = null` in the emitted HTML.

### `stage1_hook`

- `title` (`string`), `physical_cue` (`string`), `pitch_aloud` (`string`), `win_summary` (`string`): all non-empty strings.
- `win_trigger_by_players`: object containing a non-empty string value for every integer key from `str(meta.min_players)` through `str(meta.max_players)`.
- `citations`: non-empty valid citation list.

### `stage2_setup`

Contains `shared_board` (array) and `per_player` (array); at least one item total across both arrays. Each item is an object:

- `id` (`string`), `name` (`string`): non-empty strings; IDs should be unique across setup items.
- Parameterized delta rule:
  - Either `deltas` is an object containing a non-empty string for every integer key `str(meta.min_players)` through `str(meta.max_players)`, OR
  - `deltas` is `null` and `static_text` is a non-empty string.
- `citations`: non-empty valid citation list.
- `errata_ref` (optional `string`): if present and non-null, must match an `id` in `stage5_reference.errata_list[]`.
- `verify_ref` (optional `string`): if present and non-null, must match an `id` in `stage5_reference.verify_before_table[]`.
- `verify_players` (optional `int[]`): if present and non-null, must be a non-empty list of integers (not boolean) within `[meta.min_players, meta.max_players]`. When omitted on an item with `verify_ref`, the template flags `Verify` for all player counts.

### `stage3_turn`

- `summary`: non-empty string.
- `turn_flow_svg`: required raw inline `<svg>...</svg>` string passing SVG safety validation plus `viewBox`, `<title>`, and `<desc>`.
- `phases`: non-empty array of phase objects:
  - `id` (`string`), `step` (`int > 0`), `name` (`string`), `physical_cue` (`string`), `say_aloud` (`string`), `player_summary` (`string`), `citations` (non-empty valid citation list).
  - `errata_ref` (optional `string`): if present and non-null, must match an `id` in `stage5_reference.errata_list[]`.
  - `subactions` (optional `array`): if present, list of `{ name, detail, citations, errata_ref? }` where `errata_ref` (if present and non-null) resolves against `stage5_reference.errata_list[]`.
- `free_action`: nullable (`{ name, detail, citations } | null`).

### `stage4_first_round`

Non-empty array of beat objects:
- `beat` (`int > 0`), `title` (`string`), `physical_cue` (`string`), `say_aloud` (`string`), `citations` (non-empty valid citation list).

### `stage5_reference`

- `top_gotchas` (optional `array`): defaults to `[]` if omitted. Items: `{ title, detail, citations }`.
- `edge_cases` (`array`): list of `{ id, title, detail, citations }`.
- `errata_list` (`array`): list of `{ id, title, location, printed, corrected, citations }` with unique non-empty `id` values.
- `verify_before_table` (`array`, never a single object; `[]` when no ambiguities exist): list of `{ id, title, detail, citations }` with unique non-empty `id` values.
- `owner_notes` (`object | null`): either `null` or `{ "file": "<non-empty filename>", "entries": ["<non-empty string>", ...] }`. `--strip-notes` sets this to `null`.
- `iconography` (`array`): list of `{ id, name, effect, svg?, citations }`. When `svg` is present and non-null, it must pass SVG safety validation.
- `scoring` (`object`): `{ "rows": [{ "source": string, "points": string, "citations": [...] }], "tiebreakers": string }` (`rows` non-empty, `tiebreakers` non-empty).
- `precedence` (`string`): canonical source precedence order.
- `cc_by_sa` (`array`, never a single object; `[]` when no BG.SE citations appear): list of `{ citation, author, license, note }` where every field is a non-empty string.

## 3. Mandatory Citation Grammar & Referential Integrity

Every present rule-bearing record must carry a non-empty `citations` array of strings matching:

```regex
^\((Rulebook p\. \d+(?:[–-]\d+)?|Publisher Errata[^)]*|Publisher FAQ[^)]*|Living Rulebook[^)]*|BG\.SE #\d+|Owner notes\.md)\)$
```

Rule-bearing records checked by `scripts/compile.py`:
- `stage1_hook`
- Each item in `stage2_setup.shared_board[]` and `stage2_setup.per_player[]`
- Each phase in `stage3_turn.phases[]`, each present item in `phases[].subactions[]`, and `stage3_turn.free_action` when non-null
- Each beat in `stage4_first_round[]`
- Each item in present `stage5_reference.top_gotchas[]`, `edge_cases[]`, `errata_list[]`, `verify_before_table[]`, `iconography[]`, and `scoring.rows[]`

Cross-references and attribution:
1. Every distinct `(BG.SE #<id>)` string cited in any `citations` list anywhere in `guide.json` must have a matching object in `stage5_reference.cc_by_sa[]` whose `citation` equals `(BG.SE #<id>)`.
2. Every `errata_ref` must match an `id` in `stage5_reference.errata_list[]`.
3. Every `verify_ref` must match an `id` in `stage5_reference.verify_before_table[]`.

## 4. Source Precedence

Canonical order stored in `stage5_reference.precedence`:

```text
Publisher Errata / Living Rulebook > Printed Rulebook > Publisher FAQ > Owner notes.md > BG.SE
```

When two sources conflict, surface the higher-precedence ruling as authoritative (using `errata_list[]` with before/after diffs when contradicting printed rules) or record a `verify_before_table[]` callout when genuine ambiguity remains.

## 5. Inline `<svg>` Safety & Styling Rules

All inline `<svg>` strings (`stage3_turn.turn_flow_svg` and optional `stage5_reference.iconography[].svg`) are parsed as XML by `xml.etree.ElementTree`:

- Root element local tag name must be `svg`.
- Disallowed elements (case-insensitive local name): `<script>`, `<foreignObject>`, `<iframe>`.
- Disallowed attributes: any attribute whose local name starts with `on` (case-insensitive, e.g., `onload`, `onclick`, `onmouseover`).
- Disallowed URIs: any `href`, `xlink:href`, or `src` attribute whose stripped lowercase value (ignoring whitespace/control characters) begins with `javascript:` or `data:text/html`.
- `stage3_turn.turn_flow_svg` additionally requires:
  - A non-empty `viewBox` attribute (recommended `viewBox="0 0 680 210"` for crisp 3-phase flow without clipping).
  - Non-empty accessible `<title>` and `<desc>` elements.
- Styling: use Tessera CSS custom properties (`var(--surface-2)`, `var(--surface-1)`, `var(--bg)`, `var(--border)`, `var(--border-strong)`, `var(--text)`, `var(--text-muted)`, `var(--accent)`, `var(--accent-strong)`, `var(--accent-soft)`, `var(--info)`, `var(--ok)`, `var(--warn)`, `var(--bad)`, `var(--font-display)`, `var(--font-body)`, `var(--font-mono)`) instead of hardcoded hex colors so all three themes (`felt`, `ledger`, `dim`) render legibly.

## 6. `notes.md` Addendum Format

`scripts/compile.py --notes <path>` merges local owner notes deterministically with zero LLM calls:

- Reads UTF-8 Markdown.
- Strips HTML comments (`<!-- ... -->`, multiline) and blank lines.
- Tracks the active Markdown heading (`## Heading` or `### Heading`, stripped of `#` markers).
- Extracts top-level bullet lines beginning with `- ` or `* ` (stripped and normalized).
  - When inside a heading section, formats the entry as `"<Heading>: <bullet text>"`.
  - Before any heading, stores `"<bullet text>"` directly.
- Writes `stage5_reference.owner_notes = { "file": "<basename of path>", "entries": [...] }`.
