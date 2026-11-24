import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILE_SCRIPT = REPO_ROOT / "scripts" / "compile.py"
FIXTURE_JSON = REPO_ROOT / "tests" / "fixtures" / "lantern-harbor.guide.json"
FIXTURE_NOTES = REPO_ROOT / "tests" / "fixtures" / "lantern-harbor.notes.md"

MINIMAL_TEMPLATE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Test Template</title></head>
<body>
<div id="app"></div>
<script id="guide-data" type="application/json"><!-- BG_TEACH_GUIDE_JSON --></script>
</body>
</html>
"""


class TestCompileCLI(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.template = self.tmp / "template.html"
        self.template.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        self.base_guide = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_guide(self, data, name="guide.json"):
        path = self.tmp / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _run_compile(self, *args):
        return subprocess.run(
            [sys.executable, str(COMPILE_SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_validate_only_fixture_exits_0(self):
        res = self._run_compile(str(FIXTURE_JSON), "--validate-only")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_compile_writes_self_contained_html(self):
        out_html = self.tmp / "out.html"
        res = self._run_compile(
            str(FIXTURE_JSON),
            "-o",
            str(out_html),
            "--template",
            str(self.template),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        html = out_html.read_text(encoding="utf-8")
        self.assertNotIn("<!-- BG_TEACH_GUIDE_JSON -->", html)
        self.assertIn("Lantern Harbor", html)
        self.assertIn('"schema_version": "bg-teach-v1"', html)

    def test_missing_or_malformed_citations_exit_2(self):
        # Empty citations list
        d1 = copy.deepcopy(self.base_guide)
        d1["stage1_hook"]["citations"] = []
        p1 = self._write_guide(d1, "empty_cite.json")
        r1 = self._run_compile(str(p1), "--validate-only")
        self.assertEqual(r1.returncode, 2, r1.stderr)
        self.assertIn("citations", r1.stderr)

        # Malformed citation string (also check trailing newline is rejected)
        d2 = copy.deepcopy(self.base_guide)
        d2["stage4_first_round"][0]["citations"] = ["Rulebook page 7"]
        p2 = self._write_guide(d2, "bad_cite.json")
        r2 = self._run_compile(str(p2), "--validate-only")
        self.assertEqual(r2.returncode, 2, r2.stderr)
        self.assertIn("stage4_first_round", r2.stderr)

        # Subaction invalid source citation
        d3 = copy.deepcopy(self.base_guide)
        d3["stage3_turn"]["phases"][1]["subactions"][0]["citations"] = ["(BGG Forum #12)"]
        p3 = self._write_guide(d3, "bgg_cite.json")
        r3 = self._run_compile(str(p3), "--validate-only")
        self.assertEqual(r3.returncode, 2, r3.stderr)
        self.assertIn("subactions", r3.stderr)

        # Trailing newline in citation
        d4 = copy.deepcopy(self.base_guide)
        d4["stage1_hook"]["citations"] = ["(Rulebook p. 2)\n"]
        p4 = self._write_guide(d4, "nl_cite.json")
        r4 = self._run_compile(str(p4), "--validate-only")
        self.assertEqual(r4.returncode, 2, r4.stderr)
        self.assertIn("stage1_hook.citations", r4.stderr)

    def test_bg_se_requires_matching_cc_by_sa_entry(self):
        d = copy.deepcopy(self.base_guide)
        d["stage5_reference"]["edge_cases"][0]["citations"].append("(BG.SE #99999)")
        p = self._write_guide(d, "missing_cc.json")
        res = self._run_compile(str(p), "--validate-only")
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("BG.SE #99999", res.stderr)

    def test_empty_cc_by_sa_allowed_when_no_bg_se_cited(self):
        d = copy.deepcopy(self.base_guide)
        d["stage3_turn"]["free_action"]["citations"] = ["(Rulebook p. 10)"]
        d["stage5_reference"]["edge_cases"][1]["citations"] = ["(Rulebook p. 10)"]
        d["stage5_reference"]["iconography"][3]["citations"] = ["(Rulebook p. 10)"]
        d["stage5_reference"]["cc_by_sa"] = []
        p = self._write_guide(d, "no_bgse.json")
        res = self._run_compile(str(p), "--validate-only")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_cc_by_sa_and_verify_before_table_must_be_lists(self):
        d1 = copy.deepcopy(self.base_guide)
        d1["stage5_reference"]["verify_before_table"] = d1["stage5_reference"]["verify_before_table"][0]
        r1 = self._run_compile(str(self._write_guide(d1, "v_obj.json")), "--validate-only")
        self.assertEqual(r1.returncode, 2, r1.stderr)
        self.assertIn("verify_before_table", r1.stderr)

        d2 = copy.deepcopy(self.base_guide)
        d2["stage5_reference"]["cc_by_sa"] = d2["stage5_reference"]["cc_by_sa"][0]
        r2 = self._run_compile(str(self._write_guide(d2, "cc_obj.json")), "--validate-only")
        self.assertEqual(r2.returncode, 2, r2.stderr)
        self.assertIn("cc_by_sa", r2.stderr)

    def test_dangling_errata_and_verify_refs_exit_2(self):
        d1 = copy.deepcopy(self.base_guide)
        d1["stage2_setup"]["shared_board"][1]["errata_ref"] = "err-does-not-exist"
        r1 = self._run_compile(str(self._write_guide(d1, "bad_err_ref.json")), "--validate-only")
        self.assertEqual(r1.returncode, 2, r1.stderr)
        self.assertIn("err-does-not-exist", r1.stderr)

        d2 = copy.deepcopy(self.base_guide)
        d2["stage3_turn"]["phases"][1]["subactions"][1]["errata_ref"] = "err-missing-sub"
        r2 = self._run_compile(str(self._write_guide(d2, "bad_sub_err.json")), "--validate-only")
        self.assertEqual(r2.returncode, 2, r2.stderr)
        self.assertIn("err-missing-sub", r2.stderr)

        d3 = copy.deepcopy(self.base_guide)
        d3["stage2_setup"]["shared_board"][0]["verify_ref"] = "v-missing"
        r3 = self._run_compile(str(self._write_guide(d3, "bad_verify_ref.json")), "--validate-only")
        self.assertEqual(r3.returncode, 2, r3.stderr)
        self.assertIn("v-missing", r3.stderr)

        d4 = copy.deepcopy(self.base_guide)
        d4["stage3_turn"]["phases"][0]["errata_ref"] = "err-phase-missing"
        r4 = self._run_compile(str(self._write_guide(d4, "bad_phase_err.json")), "--validate-only")
        self.assertEqual(r4.returncode, 2, r4.stderr)
        self.assertIn("err-phase-missing", r4.stderr)

    def test_duplicate_ids_and_verify_players_bounds_exit_2(self):
        d1 = copy.deepcopy(self.base_guide)
        d1["stage2_setup"]["per_player"][0]["id"] = "s-board"
        r1 = self._run_compile(str(self._write_guide(d1, "dup_setup_id.json")), "--validate-only")
        self.assertEqual(r1.returncode, 2, r1.stderr)
        self.assertIn("duplicate", r1.stderr)

        d2 = copy.deepcopy(self.base_guide)
        d2["stage5_reference"]["errata_list"].append(copy.deepcopy(d2["stage5_reference"]["errata_list"][0]))
        r2 = self._run_compile(str(self._write_guide(d2, "dup_err_id.json")), "--validate-only")
        self.assertEqual(r2.returncode, 2, r2.stderr)
        self.assertIn("duplicate", r2.stderr)

        d3 = copy.deepcopy(self.base_guide)
        d3["stage5_reference"]["verify_before_table"].append(copy.deepcopy(d3["stage5_reference"]["verify_before_table"][0]))
        r3 = self._run_compile(str(self._write_guide(d3, "dup_verify_id.json")), "--validate-only")
        self.assertEqual(r3.returncode, 2, r3.stderr)
        self.assertIn("duplicate", r3.stderr)

        for bad_vp in ([], [True], [6]):
            d4 = copy.deepcopy(self.base_guide)
            d4["stage2_setup"]["shared_board"][0]["verify_players"] = bad_vp
            r4 = self._run_compile(str(self._write_guide(d4, f"vp_{len(bad_vp)}.json")), "--validate-only")
            self.assertEqual(r4.returncode, 2, r4.stderr)
            self.assertIn("verify_players", r4.stderr)

    def test_unsafe_svg_payloads_exit_2(self):
        bad_svgs = [
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>d</desc><script>alert(1)</script></svg>', "script"),
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>d</desc><foreignObject><div>hi</div></foreignObject></svg>', "foreignObject"),
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>d</desc><iframe src="https://evil.invalid"/></svg>', "iframe"),
            ('<svg viewBox="0 0 100 100" ONLOAD="alert(1)"><title>t</title><desc>d</desc><rect width="10" height="10"/></svg>', "ONLOAD"),
            ('<svg xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100"><title>t</title><desc>d</desc><a xlink:href="javascript:alert(1)"><rect width="10" height="10"/></a></svg>', "javascript:"),
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>d</desc><a href="&#106;ava&#10;script:alert(1)"><rect width="10" height="10"/></a></svg>', "javascript:"),
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>d</desc><image src="javascript:alert(1)"/></svg>', "javascript:"),
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>d</desc><a href="data:text/html,&lt;script&gt;1&lt;/script&gt;"><rect width="10" height="10"/></a></svg>', "data:text/html"),
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>d</desc><image src="data:text/html,evil"/></svg>', "data:text/html"),
            ('<svg><title>t</title><desc>d</desc><rect width="10" height="10"/></svg>', "viewBox"),
            ('<svg viewBox="0 0 100 100"><desc>d</desc><rect width="10" height="10"/></svg>', "<title>"),
            ('<svg viewBox="0 0 100 100"><title>   </title><desc>d</desc><rect width="10" height="10"/></svg>', "<title>"),
            ('<svg viewBox="0 0 100 100"><title>t</title><rect width="10" height="10"/></svg>', "<desc>"),
            ('<svg viewBox="0 0 100 100"><title>t</title><desc>  </desc><rect width="10" height="10"/></svg>', "<desc>"),
            ('<div>not svg</div>', "root element must be <svg>"),
            ('<svg viewBox="0 0 100 100"><unclosed></svg>', "invalid XML"),
        ]
        for idx, (svg, expected_msg) in enumerate(bad_svgs):
            d = copy.deepcopy(self.base_guide)
            d["stage3_turn"]["turn_flow_svg"] = svg
            p = self._write_guide(d, f"bad_flow_{idx}.json")
            res = self._run_compile(str(p), "--validate-only")
            self.assertEqual(res.returncode, 2, f"Expected exit 2 for svg index {idx}: {svg}")
            self.assertIn(expected_msg, res.stderr)

        # Iconography SVG sanitization
        d_icon = copy.deepcopy(self.base_guide)
        d_icon["stage5_reference"]["iconography"][0]["svg"] = '<svg viewBox="0 0 24 24" onclick="alert(1)"><circle cx="12" cy="12" r="8"/></svg>'
        r_icon = self._run_compile(str(self._write_guide(d_icon, "bad_icon_svg.json")), "--validate-only")
        self.assertEqual(r_icon.returncode, 2, r_icon.stderr)
        self.assertIn("onclick", r_icon.stderr)

    def test_missing_player_count_deltas_and_invalid_bounds_exit_2(self):
        d1 = copy.deepcopy(self.base_guide)
        del d1["stage2_setup"]["shared_board"][0]["deltas"]["4"]
        r1 = self._run_compile(str(self._write_guide(d1, "missing_delta.json")), "--validate-only")
        self.assertEqual(r1.returncode, 2, r1.stderr)
        self.assertIn("deltas", r1.stderr)

        d2 = copy.deepcopy(self.base_guide)
        del d2["stage1_hook"]["win_trigger_by_players"]["3"]
        r2 = self._run_compile(str(self._write_guide(d2, "missing_win.json")), "--validate-only")
        self.assertEqual(r2.returncode, 2, r2.stderr)
        self.assertIn("win_trigger_by_players", r2.stderr)

        d3 = copy.deepcopy(self.base_guide)
        d3["stage2_setup"]["shared_board"][4]["static_text"] = ""
        r3 = self._run_compile(str(self._write_guide(d3, "empty_static.json")), "--validate-only")
        self.assertEqual(r3.returncode, 2, r3.stderr)
        self.assertIn("static_text", r3.stderr)

        d4 = copy.deepcopy(self.base_guide)
        d4["meta"]["min_players"] = 5
        d4["meta"]["max_players"] = 4
        r4 = self._run_compile(str(self._write_guide(d4, "bad_bounds.json")), "--validate-only")
        self.assertEqual(r4.returncode, 2, r4.stderr)
        self.assertIn("min_players", r4.stderr)

        # Reject non-null errors on optional non-nullable arrays, omitted required nullable fields,
        # missing link labels, booleans, out-of-range bounds, zero weight, and non-dict root.
        bad_cases = [
            ("subactions_null", lambda g: g["stage3_turn"]["phases"][1].__setitem__("subactions", None), "subactions"),
            ("top_gotchas_null", lambda g: g["stage5_reference"].__setitem__("top_gotchas", None), "top_gotchas"),
            ("omit_bgg_id", lambda g: g.pop("bgg_id"), "bgg_id"),
            ("omit_game_uuid", lambda g: g.pop("game_uuid"), "game_uuid"),
            ("omit_free_action", lambda g: g["stage3_turn"].pop("free_action"), "free_action"),
            ("omit_owner_notes", lambda g: g["stage5_reference"].pop("owner_notes"), "owner_notes"),
            ("missing_official_label", lambda g: g["links"].__setitem__("official_pdf_label", None), "official_pdf_label"),
            ("missing_local_label", lambda g: g["links"].__setitem__("pdf_local_label", None), "pdf_local_label"),
            ("bool_bgg_id", lambda g: g.__setitem__("bgg_id", True), "bgg_id"),
            ("bool_min_players", lambda g: g["meta"].__setitem__("min_players", True), "min_players"),
            ("max_players_13", lambda g: g["meta"].__setitem__("max_players", 13), "max_players"),
            ("zero_weight", lambda g: g["meta"].__setitem__("weight", 0), "weight"),
        ]
        for label, mutator, expected in bad_cases:
            dc = copy.deepcopy(self.base_guide)
            mutator(dc)
            rc = self._run_compile(str(self._write_guide(dc, f"{label}.json")), "--validate-only")
            self.assertEqual(rc.returncode, 2, f"{label}: {rc.stderr}")
            self.assertIn(expected, rc.stderr)

        r_root = self._run_compile(str(self._write_guide([], "root_list.json")), "--validate-only")
        self.assertEqual(r_root.returncode, 2, r_root.stderr)
        self.assertIn("root", r_root.stderr)

    def test_nullable_and_optional_fields_validate_cleanly(self):
        d = copy.deepcopy(self.base_guide)
        d["stage3_turn"]["free_action"] = None
        d["stage2_setup"]["shared_board"][0].pop("verify_ref", None)
        d["stage2_setup"]["shared_board"][0].pop("verify_players", None)
        d["stage5_reference"]["verify_before_table"] = []
        d["stage5_reference"]["owner_notes"] = None
        d["stage5_reference"].pop("top_gotchas", None)
        d["stage3_turn"]["phases"][1].pop("subactions", None)
        d["stage3_turn"]["phases"][1]["citations"] = ["(Rulebook p. 9)", "(Publisher Errata v1.2)"]
        d["stage5_reference"]["iconography"][0].pop("svg", None)
        # Keep local PDF while setting official PDF URL/label to null
        d["links"]["official_pdf_url"] = None
        d["links"]["official_pdf_label"] = None
        p = self._write_guide(d, "nullable_ok.json")
        res = self._run_compile(str(p), "--validate-only")
        self.assertEqual(res.returncode, 0, res.stderr)

        # --shared works on local-PDF-only guide (validated before stripping local path)
        local_only_shared = self.tmp / "local_only_shared.html"
        res_local_shared = self._run_compile(
            str(p),
            "--template",
            str(self.template),
            "--shared",
            "-o",
            str(local_only_shared),
        )
        self.assertEqual(res_local_shared.returncode, 0, res_local_shared.stderr)
        local_shared_data = self._extract_island(local_only_shared.read_text(encoding="utf-8"))
        self.assertIsNone(local_shared_data["links"]["pdf_local_path"])
        self.assertIsNone(local_shared_data["links"]["pdf_local_label"])

        # Reject when BOTH official_pdf_url and pdf_local_path are null
        d_nolinks = copy.deepcopy(d)
        d_nolinks["links"]["pdf_local_path"] = None
        d_nolinks["links"]["pdf_local_label"] = None
        res2 = self._run_compile(str(self._write_guide(d_nolinks, "no_pdfs.json")), "--validate-only")
        self.assertEqual(res2.returncode, 2, res2.stderr)
        self.assertIn("links", res2.stderr)

    def test_notes_merge_shared_and_strip_notes(self):
        nested_notes = self.tmp / "nested.notes.md"
        nested_notes.write_text(
            "<!-- secret comment -->\n## House Rulings\n- Top level bullet.\n  - Indented sub-bullet ignored.\n\n* Second top bullet.\n",
            encoding="utf-8",
        )
        out_nested = self.tmp / "nested.html"
        r_nested = self._run_compile(
            str(FIXTURE_JSON),
            "--template",
            str(self.template),
            "--notes",
            str(nested_notes),
            "-o",
            str(out_nested),
        )
        self.assertEqual(r_nested.returncode, 0, r_nested.stderr)
        nested_data = self._extract_island(out_nested.read_text(encoding="utf-8"))
        self.assertEqual(
            nested_data["stage5_reference"]["owner_notes"]["entries"],
            ["House Rulings: Top level bullet.", "House Rulings: Second top bullet."],
        )

        out_html = self.tmp / "merged.html"
        res = self._run_compile(
            str(FIXTURE_JSON),
            "--template",
            str(self.template),
            "--notes",
            str(FIXTURE_NOTES),
            "-o",
            str(out_html),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        recompiled_json = self._extract_island(out_html.read_text(encoding="utf-8"))
        notes = recompiled_json["stage5_reference"]["owner_notes"]
        self.assertEqual(notes["file"], "lantern-harbor.notes.md")
        self.assertEqual(len(notes["entries"]), 3)
        self.assertTrue(notes["entries"][0].startswith("House Rulings: "))
        self.assertTrue(notes["entries"][2].startswith("BGG Notes: "))
        self.assertNotIn("HTML comments and blank lines", "\n".join(notes["entries"]))

        shared_html = self.tmp / "shared.html"
        res_shared = self._run_compile(
            str(FIXTURE_JSON),
            "--template",
            str(self.template),
            "--notes",
            str(FIXTURE_NOTES),
            "--shared",
            "--strip-notes",
            "-o",
            str(shared_html),
        )
        self.assertEqual(res_shared.returncode, 0, res_shared.stderr)
        shared_data = self._extract_island(shared_html.read_text(encoding="utf-8"))
        self.assertIsNone(shared_data["links"]["pdf_local_path"])
        self.assertIsNone(shared_data["links"]["pdf_local_label"])
        self.assertEqual(shared_data["links"]["official_pdf_url"], self.base_guide["links"]["official_pdf_url"])
        self.assertIsNone(shared_data["stage5_reference"]["owner_notes"])

    def test_from_html_round_trip_and_script_escaping(self):
        d = copy.deepcopy(self.base_guide)
        d["stage1_hook"]["pitch_aloud"] = "Beware </script><script>alert(1)</script>\u2028\u2029 in rules."
        in_json = self._write_guide(d, "escape.json")

        out1 = self.tmp / "first.html"
        r1 = self._run_compile(str(in_json), "--template", str(self.template), "-o", str(out1))
        self.assertEqual(r1.returncode, 0, r1.stderr)
        raw_html1 = out1.read_text(encoding="utf-8")
        self.assertNotIn("</script><script>", raw_html1)
        self.assertIn("<\\/script>", raw_html1)
        self.assertNotIn("\u2028", raw_html1)
        self.assertNotIn("\u2029", raw_html1)

        tpl2 = self.tmp / "template_v2.html"
        tpl2.write_text(MINIMAL_TEMPLATE.replace("Test Template", "Template V2"), encoding="utf-8")
        out2 = self.tmp / "second.html"
        r2 = self._run_compile("--from-html", str(out1), "--template", str(tpl2), "-o", str(out2))
        self.assertEqual(r2.returncode, 0, r2.stderr)
        raw_html2 = out2.read_text(encoding="utf-8")
        self.assertIn("Template V2", raw_html2)
        self.assertEqual(self._extract_island(raw_html1), self._extract_island(raw_html2))
        self.assertEqual(self._extract_island(raw_html2)["stage1_hook"]["pitch_aloud"], d["stage1_hook"]["pitch_aloud"])

    def test_io_and_cli_usage_errors_exit_1(self):
        r_missing = self._run_compile(str(self.tmp / "missing.json"), "--validate-only")
        self.assertEqual(r_missing.returncode, 1)

        bad_json = self.tmp / "bad.json"
        bad_json.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(self._run_compile(str(bad_json), "--validate-only").returncode, 1)

        inf_json = self.tmp / "inf.json"
        inf_data = json.dumps(self.base_guide).replace("2.6", "Infinity")
        inf_json.write_text(inf_data, encoding="utf-8")
        self.assertEqual(self._run_compile(str(inf_json), "--validate-only").returncode, 1)

        self.assertEqual(
            self._run_compile(
                str(FIXTURE_JSON), "--notes", str(self.tmp / "missing.md"), "--validate-only"
            ).returncode,
            1,
        )
        self.assertEqual(
            self._run_compile(
                str(FIXTURE_JSON), "--template", str(self.tmp / "missing.html"), "-o", str(self.tmp / "o.html")
            ).returncode,
            1,
        )
        no_marker_tpl = self.tmp / "no_marker.html"
        no_marker_tpl.write_text("<html><body></body></html>", encoding="utf-8")
        self.assertEqual(
            self._run_compile(
                str(FIXTURE_JSON), "--template", str(no_marker_tpl), "-o", str(self.tmp / "o.html")
            ).returncode,
            1,
        )

        no_island_html = self.tmp / "no_island.html"
        no_island_html.write_text("<html><body>hi</body></html>", encoding="utf-8")
        self.assertEqual(self._run_compile("--from-html", str(no_island_html), "--validate-only").returncode, 1)

        # Uncompiled template still containing placeholder
        self.assertEqual(self._run_compile("--from-html", str(self.template), "--validate-only").returncode, 1)

        r_usage = self._run_compile(str(FIXTURE_JSON))  # missing -o / --validate-only
        self.assertEqual(r_usage.returncode, 1)

        r_unknown = self._run_compile(str(FIXTURE_JSON), "--validate-only", "--bogus-flag")
        self.assertEqual(r_unknown.returncode, 1)

        r_both_in = self._run_compile(str(FIXTURE_JSON), "--from-html", str(self.template), "--validate-only")
        self.assertEqual(r_both_in.returncode, 1)

        r_both_out = self._run_compile(str(FIXTURE_JSON), "-o", str(self.tmp / "x.html"), "--validate-only")
        self.assertEqual(r_both_out.returncode, 1)

    @staticmethod
    def _extract_island(html_text):
        start_marker = '<script id="guide-data" type="application/json">'
        start = html_text.index(start_marker) + len(start_marker)
        end = html_text.index("</script>", start)
        return json.loads(html_text[start:end])


if __name__ == "__main__":
    unittest.main()
