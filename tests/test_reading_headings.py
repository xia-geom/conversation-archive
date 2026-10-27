"""Public Markdown conventions must survive the organize-to-reading handoff."""
from pathlib import Path
import tempfile
import unittest

from conversation_archive import reading
from conversation_archive.demo import run_markdown_demo, synthetic_export
from conversation_archive.reading_document import Document, ReadingError, encoded, entry_blocks


class ReadingHeadingTests(unittest.TestCase):
    def test_mixed_entry_levels_have_independent_complete_bodies(self):
        first = """## E0001 — Garden

The owner reported planting mint.

### Source limits

The planting date is unknown.
"""
        second = """### E0002 — Museum

A visit was planned. [Source](#src-museum)

#### Exact account

````text
## E9001 — Historical heading
### E9002 — Another historical heading
````

<!-- ARCHIVED_TEXT_BEGIN old-account -->
### E9003 — Archived heading
<!-- ARCHIVED_TEXT_END old-account -->
"""
        third = """### E0003 — Train

The train was delayed.
"""
        fourth = """## E0004 — Library

The book was returned.
"""
        text = ("# Organized information\n\n" + first +
                '\n<a id="e0002"></a>\n' + second +
                '\n<a id="e0003"></a>\n' + third +
                '\n<a id="e0004"></a>\n' + fourth +
                '\n<a id="sources"></a>\n# Source archive\n\n'
                '<a id="src-museum"></a>\n## Source museum\n\n'
                'A museum visit was planned.\n')

        entries = entry_blocks(text)

        self.assertEqual(list(entries), ["E0001", "E0002", "E0003", "E0004"])
        for eid, expected in zip(entries, (first, second, third, fourth)):
            with self.subTest(entry_id=eid):
                self.assertEqual(entries[eid]["text"], expected)
                self.assertEqual(text[entries[eid]["start"]:entries[eid]["end"]].strip(), expected.strip())
        self.assertEqual(entries["E0002"]["refs"], ["src-museum"])

    def test_level_three_entry_stops_before_nonentry_sibling_heading(self):
        body = "### E0001 — Garden\n\nMint was planted.\n\n#### Details\n\nIn a pot.\n"
        text = ("# Archive\n\n## Gardening\n\n" + body +
                '\n<a id="unreviewed"></a>\n### General notes\n\n'
                'This is separate context, not part of the entry.\n')

        self.assertEqual(entry_blocks(text)["E0001"]["text"], body)

    def test_duplicate_ids_across_supported_heading_levels_are_rejected(self):
        with self.assertRaises(ReadingError):
            entry_blocks("## E0001 — Garden\n\nMint.\n\n### E0001 — Museum\n\nA plan.\n")

    def test_markdown_demo_supports_complete_review_revision_and_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            demo = root / "demo"
            run_markdown_demo(demo)
            document = demo / "organized.md"
            before = document.read_bytes()
            original_export = demo / "exports" / "invented.json"
            export_before = original_export.read_bytes()
            text = before.decode("utf-8")
            entry = text[text.index("### E0001 — Garden"):text.index("## Open questions")].strip()
            run = demo / ".state" / "reading"

            report = reading.prepare(document, run)
            packet = root / "entry-review.md"
            packet_report = reading.packet(run, ["E0001"], packet)

            self.assertEqual(report["entries"], 1)
            parsed = Document.read(document)
            self.assertEqual(parsed.entries["E0001"]["text"].strip(), entry)
            self.assertEqual(parsed.entries["E0001"]["refs"], ["src-0001"])
            self.assertEqual(list(parsed.sources), ["src-0001"])
            source = parsed.sources["src-0001"]
            result = packet.read_text(encoding="utf-8")
            exact_source = synthetic_export()[0]["mapping"]["u"]["message"]["content"]["parts"][0]
            self.assertIn(entry, result)
            self.assertEqual(packet_report["source_blocks_considered"], 1)
            self.assertIn(source["text"].strip(), result)
            self.assertEqual(text.count(exact_source), 1)
            self.assertNotIn(exact_source, entry)
            self.assertIn("Role: user (owner report).", result)
            self.assertIn('Source: ChatGPT message `shared-id`, export SHA-256', result)
            self.assertIn('JSON pointer `/0/mapping/u/message`', result)
            self.assertNotIn("## Open questions", result)

            answers = reading.read_json(run / "answers.template.json")
            self.assertEqual(answers["reviews"], [])
            claim = "The owner described planting mint as a completed action, rather than a future plan."
            replacement = parsed.entries["E0001"]["text"].replace("The owner reported planting mint.", claim)
            start = source["text"].index(exact_source)
            answers.update(
                reviewer="Predetermined synthetic reviewer",
                selection_note="This fixture retains the garden entry and its source. Introductory and open-question text repeats the scope and date limitation retained here.",
                reviews=[dict(
                    entry_id="E0001", basis=parsed.basis("E0001"), decision="revise",
                    reason="Clarify that the source reports a completed planting, not a plan.",
                    replacement=replacement,
                    checks=dict(
                        placement="The planting report belongs in the Garden entry.",
                        limitations="The event date remains uncertain; the export timestamp does not establish it.",
                        contradictions="No conflicting planting account appears in this invented conversation.",
                        attribution="The source is the user's own report, not an assistant suggestion or independent verification."),
                    witnesses=[dict(source_id="src-0001", source_sha256=source["sha256"],
                                    start=start, end=start + len(exact_source), quote=exact_source,
                                    claim=claim, relation="supports")])])
            answers_path = root / "answers.json"
            answers_path.write_bytes(encoded(answers))
            preview = root / "preview"
            checked = reading.check(run, answers_path, preview)

            self.assertEqual(checked["status"], "checked")
            receipt = reading.read_json(preview / "preview.json")
            self.assertEqual(receipt["evidence_access"], {"src-0001": "complete_available_block"})
            published = root / "reading-copy.md"
            self.assertEqual(reading.publish(run, answers_path, preview, published, approved=True)["status"], "published")
            final = Document.read(published)
            self.assertIn(claim, final.entries["E0001"]["text"])
            self.assertIn("Event date: not established by the message timestamp.", final.entries["E0001"]["text"])
            self.assertIn(source["text"], final.text)
            self.assertEqual(final.text.count(exact_source), 1)
            self.assertEqual(document.read_bytes(), before)
            self.assertEqual(original_export.read_bytes(), export_before)


if __name__ == "__main__":
    unittest.main()
