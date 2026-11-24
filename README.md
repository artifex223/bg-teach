# bg-teach

A portable Agent Skill and zero-dependency Python 3 compiler that turns an official board game rulebook PDF plus compliant errata and FAQ sources into a self-contained, offline-ready single-file HTML teaching guide.

## Features

- **5-Stage Cognitive Funnel:** Hook & Win State, Parameterized Setup Checklists, Plain-English Turn Anatomy with `HOLD UP` physical cues, Guided First Round, and Deferred Edge Cases / Errata / Scoring.
- **Grounded Citations & Integrity:** Every rule-bearing record enforces inline citations (`(Rulebook p. X)`, `(Publisher Errata ...)`, `(Publisher FAQ ...)`, `(Living Rulebook ...)`, `(BG.SE #id)`, `(Owner notes.md)`) and `Verify Before Table` callouts for genuine rulebook ambiguities.
- **Copyright & TOS Compliant:** Links the official publisher PDF URL (and optional private local sidecar path stripped in `--shared` builds) without embedding copyrighted PDFs or cropped publisher artwork. Automated research uses official publisher errata/FAQs and CC BY-SA Board & Card Games Stack Exchange while prohibiting BGG or Reddit LLM ingestion (emitting a browser-only BGG Rules Forum search link instead).
- **Deterministic Compiler Seam (`scripts/compile.py`):** Validates `guide.json` against the `bg-teach-v1` schema, sanitizes raw inline `<svg>` diagrams, deterministically merges local `notes.md` addenda, and injects JSON into the Variant C `assets/template.html` data island—allowing manual edits, `--shared` builds, and `--from-html` template upgrades with zero LLM calls.
- **Table-Side Ergonomics:** Three themes (`Felt`, `Ledger`, `Dim Table`), dynamic player-count deltas persisted in `localStorage`, live Search & Table Settings drawer, Wake Lock toggle, and one-tap **Pass-Around Player Aid** mode that strips teacher-only scripts and notes.

## Installation (Open Agent Skills)

Clone this repository into your agent's skills directory (for example `~/.agents/skills/bg-teach` or `.claude/skills/bg-teach`), or upload the skill folder (`SKILL.md`, `references/`, `assets/`, `scripts/`) directly in environments such as Claude, Antigravity, Codex, or ChatGPT.

```bash
git clone https://github.com/artifex223/bg-teach.git
```

## Compiler CLI Usage

Requires Python 3.10+ (standard library only; zero external dependencies):

```bash
python3 scripts/compile.py <guide.json> -o <out.html>
```

Full CLI signature:

```text
python3 scripts/compile.py (<guide.json> | --from-html <in.html>) (-o <out.html> | --validate-only) [--template assets/template.html] [--notes notes.md] [--shared] [--strip-notes]
```

Common workflows:

```bash
# Validate a guide.json intermediate without writing HTML
python3 scripts/compile.py my-game.guide.json --validate-only

# Compile with local house rulings and notes merged deterministically
python3 scripts/compile.py my-game.guide.json --notes my-game.notes.md -o dist/my-game.html

# Compile a shareable HTML file (strips links.pdf_local_path and links.pdf_local_label)
python3 scripts/compile.py my-game.guide.json --shared -o dist/my-game-shared.html

# Upgrade an existing compiled guide into the latest template with zero LLM calls
python3 scripts/compile.py --from-html dist/my-game.html -o dist/my-game-v2.html
```

Exit codes: `0` on success, `2` on validation errors (structured error list printed to stderr), `1` on I/O, JSON, or CLI usage errors.

## Manual JSON-Paste Fallback (Chat-Only Environments)

If you generate `guide.json` inside a chat UI that cannot execute `scripts/compile.py` locally:

1. Open `assets/template.html` directly in a browser.
2. When no compiled JSON payload is present, the template displays a paste form.
3. Paste the `guide.json` output from chat and click **Load Guide JSON** (or manually replace `<!-- BG_TEACH_GUIDE_JSON -->` inside `<script id="guide-data" type="application/json">` and save a copy).

## Development & Tests

```bash
python3 -m unittest discover -s tests
```

## License

MIT — see [LICENSE](LICENSE).
