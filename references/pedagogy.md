# `bg-teach` Teaching Pedagogy & Voice Guide

Teach games in the order new players build a mental model—goal first, setup without guesswork, clean turn rhythm, a guided opening round, and edge cases deferred until needed.

## 1. The 5-Stage Cognitive Funnel

### Stage 1 — Hook & Win State
- **Physical cue (`HOLD UP`):** Hold up the iconic scoring token, board goal, or victory card (`physical_cue`) before reading a word.
- **Pitch (`pitch_aloud`):** Two to three spoken sentences explaining *who players are*, *what they do on the board*, and *why the tension matters*.
- **Win condition (`win_summary` + `win_trigger_by_players`):** State clearly what wins the game and the exact trigger threshold for the current player count (`min_players..max_players`).

### Stage 2 — Component-Guided Setup
- Separate `shared_board[]` from `per_player[]` kits so the host builds the table centerpiece before handing players pieces.
- Give exact per-player-count instructions (`deltas`) whenever counts vary, or mark `All` (`deltas: null`, `static_text`) when invariant.
- Attach `errata_ref` directly to any setup item modified by official errata so mistakes never happen during setup.
- Attach `verify_ref` (and optional `verify_players`) to any setup step with a physical component or printing ambiguity.

### Stage 3 — Plain-English Turn Anatomy
- Open with a one-sentence summary of the turn loop (`stage3_turn.summary`).
- Break turns into numbered `phases[]`, each with:
  - `physical_cue`: concrete component(s) the teacher holds up while explaining that phase (`HOLD UP`).
  - `say_aloud`: conversational, plain-English spoken explanation for the teacher.
  - `player_summary`: ultra-terse action reminder rendered on **Pass-Around Player Aid** cards (free of teacher narration or cues).
  - Optional `subactions[]` for mutually exclusive choices inside a phase, wired with `errata_ref` where applicable.
- Pair phases with a clean `turn_flow_svg` diagram (`viewBox="0 0 680 210"`, theme CSS tokens only) and nullable `free_action` if an optional once-per-turn bonus exists.

### Stage 4 — Guided First Round
- Replace hypothetical edge-case lecturing with 3–5 concrete `stage4_first_round[]` **beats** (`Beat 1..N`).
- Each beat pairs a physical table demonstration (`physical_cue`, e.g., *"Move Seat 1 Sloop to Timber Pier"*) with an open-handed spoken narration (`say_aloud`) demonstrating one real decision and its immediate payoff.

### Stage 5 — Deferred Edge Cases, Errata & Scoring
- Surface `verify_before_table[]` callouts up front for the teacher's pre-game check (automatically stripped in Pass-Around mode).
- Present `errata_list[]` as **Printed → Corrected** diffs so players who skimmed the rulebook understand what changed.
- Include optional `top_gotchas[]` for the 2–4 rules new players most commonly misplay in their first game.
- Defer situational `edge_cases[]`, local `owner_notes` (`notes.md`), `iconography[]`, `scoring` rows + `tiebreakers`, and `Source Precedence & CC BY-SA` attribution to Stage 5 and Drawer search.

## 2. Teaching Voice & Selectable Presets

- **Neutral default:** Clear, warm, spoken English using active verbs and exact component names printed on the board/cards. Avoid copying dense rulebook legalese verbatim; translate mechanics into concrete cause-and-effect ("Pay 1 Timber + 1 Silver to light a Beacon" rather than "Upon expending requisite resources...").
- **Three selectable presets** (selected by user request or inside `references/style-profile.md`):
  - **`crisp`** — Tight, high-signal phrasing; 1–2 short sentences per cue; strips flavor filler for experienced Euro/strategy tables.
  - **`conversational`** — Warm, table-friendly cadence with natural transitions and brief thematic anchors for mixed or gateway groups.
  - **`brisk`** — Minimal spoken prose and bulleted action verbs for rapid refreshers when most players have played before.

## 3. Optional `references/style-profile.md` Override

Users who want persistent personal voice preferences (default preset, spoken script cadence, `HOLD UP` style, or setup phrasing conventions) can copy [`references/style-profile.example.md`](style-profile.example.md) to `references/style-profile.md` without modifying `SKILL.md`.
