---
name: bg-teach
description: Generate grounded, offline-ready board game teaching guides from official rulebook PDFs. Use when the user asks to create, update, or compile a board game teach guide, rulebook summary, Pass-Around player aid, or guide.json into a single-file HTML guide.
---

# bg-teach

Turn an official publisher rulebook PDF plus compliant errata and FAQ sources into a schema-validated `guide.json` and a self-contained single-file Variant C HTML teaching guide.

Read [`references/pedagogy.md`](references/pedagogy.md) and [`references/schema.md`](references/schema.md) before authoring `guide.json`. If `references/style-profile.md` exists, apply its voice overrides on top of the neutral default in [`references/pedagogy.md`](references/pedagogy.md).

## Pass 1 — Rulebook Acquisition & Page-Mapped Extraction

Accept either a local rulebook PDF path or an official publisher PDF URL.

1. Extract rule text page by page. When selectable text is missing, garbled, or layout-dependent (diagrams, player boards, callout boxes), inspect rendered page images multimodally instead of guessing.
2. Build an explicit map between printed rulebook page numbers and PDF page indices (covers, tables of contents, and glossaries often shift PDF page indices). Cite printed rulebook page numbers in `(Rulebook p. X)`.
3. Keep copyright boundaries clean: store the official publisher URL (`links.official_pdf_url` and `links.official_pdf_label`, both `null` only when an out-of-print local-only PDF is supplied) and optional local sidecar path (`links.pdf_local_path` and `links.pdf_local_label`, required non-null when `official_pdf_url` is `null`). Never embed a PDF or crop publisher artwork into output files.
4. Fail loudly on illegible spreads or unresolved contradictions: list unreadable pages to the user, or record genuine rulebook discrepancies with a unique `id` inside `stage5_reference.verify_before_table[]` rather than inventing a resolution.

Done when every rule mechanic, player-count setup delta, icon, and scoring condition has an exact printed page reference or an explicit `verify_before_table[]` entry.

## Pass 2 — Compliant Errata & FAQ Research

Gather post-print clarifications using compliant primary and open-licensed sources only, applying this precedence order:

`Publisher Errata / Living Rulebook > Printed Rulebook > Publisher FAQ > Owner notes.md > BG.SE`

1. Search official publisher errata sheets, living rulebooks, and official publisher FAQ pages.
2. Search Board & Card Games Stack Exchange (`boardgames.stackexchange.com`) for unanswered edge-case rulings. For every cited question, record `(BG.SE #<id>)` and emit a matching object in `stage5_reference.cc_by_sa[]` with author, `CC BY-SA 4.0` license, and attribution note.
3. Honor BoardGameGeek and Reddit terms strictly: keep BGG forums, BGG XML API threads, and Reddit outside LLM ingestion context. Always emit a browser-only BGG Rules Forum search URL in `links.bgg_search_url` paired with `links.bgg_search_label` (`"Search BGG Rules Forum (Browser Only)"`) so the host can inspect threads manually and record local rulings in `notes.md`.
4. Accept optional user-supplied local transcripts or a local `notes.md` addendum when provided by the user.

Done when all compliant errata diffs (`errata_list[]`) and CC BY-SA attributions (`cc_by_sa[]`) are recorded with zero BGG or Reddit content ingested.

## Pass 3 — `guide.json` Emission, Inline SVGs & Deterministic Compilation

1. Structure the teach along the 5-stage cognitive funnel in [`references/pedagogy.md`](references/pedagogy.md) and conform strictly to [`references/schema.md`](references/schema.md) (`schema_version: "bg-teach-v1"`, `status: "draft"`).
2. Write every rule-bearing record with non-empty `citations` matching the citation grammar. Wire `errata_ref` (matching an `id` in `errata_list[]`) on `stage2_setup` items and `stage3_turn` phases/subactions, and wire `verify_ref` (matching an `id` in `verify_before_table[]`) plus optional `verify_players` integer player-count lists on `stage2_setup` items. Ensure `stage1_hook.win_trigger_by_players` and all parameterized `stage2_setup` `deltas` contain keys for every integer from `meta.min_players` through `meta.max_players`.
3. Author raw inline `<svg>` markup for `stage3_turn.turn_flow_svg` (recommended `viewBox="0 0 680 210"`, required `viewBox`, `<title>`, `<desc>`) and optional `stage5_reference.iconography[].svg` using Tessera CSS variables (`var(--surface-2)`, `var(--text)`, `var(--accent)`, `var(--accent-strong)`, `var(--info)`, `var(--ok)`, `var(--border)`) so all three themes (`Felt`, `Ledger`, `Dim Table`) stay legible. Avoid `<script>`, `<foreignObject>`, `<iframe>`, `on*` handlers, and unsafe URIs.
4. Run the deterministic Python 3 compiler (`scripts/compile.py`) with up to 2 validation-repair rounds on stderr feedback:
   - Validation only: `python3 scripts/compile.py <guide.json> --validate-only`
   - Local build with optional notes: `python3 scripts/compile.py <guide.json> [--notes <notes.md>] -o <out.html>`
   - Shareable build (strips `pdf_local_path`/`pdf_local_label`): `python3 scripts/compile.py <guide.json> --shared -o <out-shared.html>`
   - Recompile existing HTML into updated template (zero LLM calls): `python3 scripts/compile.py --from-html <in.html> -o <out.html>`
5. **Chat-only fallback (no shell/Python runner available):** Output the validated `guide.json` block and instruct the user to open `assets/template.html` in a browser, paste the JSON into the **Manual Guide Loader** box, and click **Load Guide JSON** (or paste into `<script id="guide-data" type="application/json">` replacing `<!-- BG_TEACH_GUIDE_JSON -->`).
6. Report the generated file path(s), note `status: "draft"`, summarize any `Verify Before Table` ambiguities clearly so the teacher checks them before game night, and share the browser-only BGG search link for any unresolved community questions.

Done when `scripts/compile.py` exits `0` (or valid `bg-teach-v1` JSON is delivered in chat-only mode) and every `Verify Before Table` item has been surfaced to the user.
