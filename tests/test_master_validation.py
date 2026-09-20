import unittest
from conversation_archive.master_validation import (
    master_snapshot,
    validate_master,
    validate_reports,
)

BASE = """---
entry_count: 1
distinct_retained_sources: 1
correction_count: 1
next_entry_id: "E0002"
next_source_id: "SRC-002"
next_correction_id: "COR0002"
---
<a id="e0001"></a>
## E0001 — An invented event
[entry](#e0001) [heading](#another-heading)
## Another heading
<a id="cor0001"></a>
### COR0001 — Clarification
<a id="src-001"></a>
## SRC-001 — Synthetic source
<!-- ARCHIVED_TEXT_BEGIN SRC-001-S001 -->
## E0001 — Historic copy, not active
[old unavailable link](#missing)
<!-- ARCHIVED_TEXT_END SRC-001-S001 -->
````text
```text
## E0001 — Nested historical heading
```
````
![invented data](data:image/png;base64,YQ==)
"""
REPORT = "# Changes\n\n## R0001 — Invented change\n\n| Before | After |\n| --- | --- |\n| A | B |\n"


class MasterValidationTests(unittest.TestCase):
    def codes(self, report):
        return {e["code"] for e in report["errors"]}

    def test_historical_and_nested_fences_are_not_active(self):
        r = validate_master(BASE, BASE)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["counts"], {"entries": 1, "sources": 1, "corrections": 1})

    def test_active_duplicate_and_broken_link(self):
        r = validate_master(BASE + "\n## E0001 — duplicate\n[x](#missing)\n")
        self.assertIn("duplicate_entries", self.codes(r))
        self.assertIn("broken_internal_link", self.codes(r))

    def test_counters_next_and_removed_ids(self):
        self.assertIn(
            "counter_mismatch",
            self.codes(
                validate_master(BASE.replace("entry_count: 1", "entry_count: 2"))
            ),
        )
        self.assertIn(
            "next_id_collision",
            self.codes(validate_master(BASE.replace('"E0002"', '"E0001"'))),
        )
        self.assertIn(
            "removed_entries",
            self.codes(
                validate_master(
                    BASE.replace("## E0001 — An invented event", "## No entry"), BASE
                )
            ),
        )

    def test_protected_fences_archive_and_embedded_bytes(self):
        for old, new in [
            ("Historic copy", "Changed copy"),
            ("Nested historical", "Changed historical"),
            ("YQ==", "Yg=="),
        ]:
            with self.subTest(old=old):
                self.assertIn(
                    "protected_material_changed",
                    self.codes(validate_master(BASE.replace(old, new), BASE)),
                )

    def test_owner_question_outside_fence_is_preserved(self):
        text = (
            BASE
            + '\n<a id="src-027"></a>\nQuestion: invented?\n```text\nyes\n```\n<a id="src-029"></a>\n'
        )
        self.assertIn(
            "protected_material_changed",
            self.codes(validate_master(text.replace("invented?", "changed?"), text)),
        )

    def test_unclosed_fence(self):
        self.assertIn(
            "unclosed_protected_block",
            self.codes(validate_master(BASE + "\n```text\n")),
        )

    def test_unicode_and_repeated_heading_slugs(self):
        text = BASE + "\n## 中文标题\n## 中文标题\n[x](#中文标题-1)\n"
        self.assertEqual(validate_master(text)["errors"], [])

    def test_report_ids_and_history(self):
        self.assertEqual(
            validate_reports(BASE, REPORT, REPORT, REPORT, REPORT)["errors"], []
        )
        self.assertIn(
            "report_id_mismatch",
            self.codes(
                validate_reports(BASE, REPORT, REPORT.replace("R0001", "R0002"))
            ),
        )
        self.assertIn(
            "report_history_changed",
            self.codes(
                validate_reports(
                    BASE, REPORT.replace("A |", "C |"), REPORT, REPORT, REPORT
                )
            ),
        )

    def test_simple_heading_comparison_and_missing_comparison(self):
        simple = "## R0001 — change\n### Before\n```text\nA\n```\n### After\n```text\nB\n```\n"
        self.assertEqual(validate_reports(BASE, REPORT, simple)["errors"], [])
        self.assertIn(
            "simple_comparison_missing",
            self.codes(validate_reports(BASE, REPORT, "## R0001 — no comparison\n")),
        )


if __name__ == "__main__":
    unittest.main()
