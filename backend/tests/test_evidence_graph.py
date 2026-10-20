import unittest

from trustlens.evidence_graph import build_evidence_graph, validate_evidence_graph


class EvidenceGraphTests(unittest.TestCase):
    def report(self):
        return {
            "report_id": "report-uuid",
            "source": {"source_id": "video-source", "sha256": "a" * 64, "media_type": "video"},
            "analysis": {
                "status": "PARTIAL",
                "result": {"frames": [{"sample_index": 0, "timestamp_seconds": 1.25, "sha256": "b" * 64}]},
            },
        }

    def test_graph_links_sampled_frame_without_claiming_retention(self):
        graph = build_evidence_graph(self.report())
        frame = next(node for node in graph["nodes"] if node["type"] == "sampled_frame")
        self.assertEqual(frame["timestamp_seconds"], 1.25)
        self.assertEqual(frame["artifact_status"], "NOT_RETAINED")
        self.assertTrue(any(edge["relationship"] == "DERIVED_FROM" and edge["from"] == frame["id"] for edge in graph["edges"]))

    def test_graph_rejects_duplicate_ids_and_invalid_digest(self):
        graph = build_evidence_graph(self.report())
        invalid_digest = {**graph, "nodes": [dict(node) for node in graph["nodes"]]}
        next(node for node in invalid_digest["nodes"] if node["type"] == "sampled_frame")["sha256"] = "bad"
        with self.assertRaises(ValueError):
            validate_evidence_graph(invalid_digest)
        duplicate = {**graph, "nodes": graph["nodes"] + [dict(graph["nodes"][0])]}
        with self.assertRaises(ValueError):
            validate_evidence_graph(duplicate)


if __name__ == "__main__":
    unittest.main()
