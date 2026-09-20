"""Readable packets must retain source boundaries, branches and Unicode."""

import unittest
from conversation_archive.reconcile_cli import render_packet


class RenderingTests(unittest.TestCase):
    def packet(self, selected="a"):
        graph = [
            dict(node_id="root", parent_id=None, message_record_id=None),
            dict(node_id="a", parent_id="root", message_record_id="one"),
            dict(node_id="b", parent_id="root", message_record_id="two"),
        ]
        return dict(
            packet_id="P0001-0001",
            conversation=dict(
                title="Invented",
                original_id="chat",
                record_id="conv:one",
                current_node_id=selected,
                graph=graph,
            ),
            range_convention="start inclusive/end exclusive",
            pieces=[
                dict(
                    text="你好\n```\nfin",
                    role="user",
                    kind="transcription_text",
                    original_message_id="id",
                    message_record_id="two",
                    node_id="b",
                    parent_id="root",
                    position=4,
                    created_at_raw=None,
                    segment_index=0,
                    start=25,
                    end=35,
                    piece_id="piece:two",
                    provenance=dict(sha256="abc"),
                    json_pointer="/0/parts/0",
                    already_covered=False,
                    attachments=[dict(availability="missing")],
                )
            ],
        )

    def test_fence_and_branch_boundary(self):
        out = render_packet(self.packet())
        self.assertIn("````text\n你好\n```\nfin\n````", out)
        self.assertIn("outside exported selected path", out)
        self.assertIn("Branch point `root` → `a`, `b`", out)
        self.assertIn("exact character range [25, 35)", out)
        self.assertIn("transcription_text", out)
        self.assertIn('"missing"', out)
        self.assertIn("not a review decision", out)

    def test_unknown_selection_and_no_pending(self):
        self.assertIn("selection unknown", render_packet(self.packet(None)))
        self.assertIn(
            "not a claim of complete integration",
            render_packet(dict(status="no_pending_packet")),
        )
