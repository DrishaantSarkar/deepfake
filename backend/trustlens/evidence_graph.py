"""Small, report-local graph of evidence relationships actually produced."""

from __future__ import annotations

import re
from typing import Any


GRAPH_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def build_evidence_graph(report: dict[str, Any]) -> dict[str, Any]:
    """Build stable report-local links without implying retained artifacts."""
    report_id = report["report_id"]
    source = report["source"]
    source_node = f"source:{source['source_id']}"
    report_node = f"report:{report_id}"
    assessment_node = f"assessment:{report_id}"
    nodes: list[dict[str, Any]] = [
        {"id": source_node, "type": "source", "sha256": source["sha256"], "media_type": source["media_type"]},
        {"id": report_node, "type": "report", "report_id": report_id},
        {"id": assessment_node, "type": "assessment", "status": report["analysis"]["status"]},
    ]
    edges: list[dict[str, str]] = [
        {"from": report_node, "to": source_node, "relationship": "DESCRIBES"},
        {"from": report_node, "to": assessment_node, "relationship": "CONTAINS"},
        {"from": assessment_node, "to": source_node, "relationship": "DERIVED_FROM"},
    ]
    result = report["analysis"].get("result")
    if isinstance(result, dict):
        for frame in result.get("frames", []):
            frame_node = f"frame:{report_id}:{frame['sample_index']}"
            nodes.append({
                "id": frame_node,
                "type": "sampled_frame",
                "sample_index": frame["sample_index"],
                "timestamp_seconds": frame.get("timestamp_seconds"),
                "sha256": frame["sha256"],
                "artifact_status": "NOT_RETAINED",
            })
            edges.extend((
                {"from": frame_node, "to": source_node, "relationship": "DERIVED_FROM"},
                {"from": assessment_node, "to": frame_node, "relationship": "ASSESSES"},
            ))
    graph = {"schema_version": GRAPH_SCHEMA_VERSION, "nodes": nodes, "edges": edges}
    validate_evidence_graph(graph)
    return graph


def validate_evidence_graph(
    graph: Any, *, source_id: str | None = None,
    source_sha256: str | None = None, report_id: str | None = None,
) -> None:
    """Validate graph structure, referential integrity, and evidence hashes."""
    if not isinstance(graph, dict) or graph.get("schema_version") != GRAPH_SCHEMA_VERSION:
        raise ValueError("Evidence graph schema_version is unsupported.")
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Evidence graph nodes and edges must be lists.")
    ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"] or node["id"] in ids:
            raise ValueError("Evidence graph node IDs must be unique nonempty strings.")
        ids.add(node["id"])
        if node.get("type") in {"source", "sampled_frame"} and not _SHA256.fullmatch(str(node.get("sha256", ""))):
            raise ValueError("Evidence graph evidence nodes require a lowercase SHA-256 digest.")
        if node.get("type") == "sampled_frame" and node.get("artifact_status") != "NOT_RETAINED":
            raise ValueError("Sampled frame graph nodes must report their current retention state.")
    edge_keys: set[tuple[str, str, str]] = set()
    for edge in edges:
        if not isinstance(edge, dict) or any(not isinstance(edge.get(key), str) for key in ("from", "to", "relationship")):
            raise ValueError("Evidence graph edges must identify endpoints and relationship.")
        key = (edge["from"], edge["to"], edge["relationship"])
        if edge["from"] not in ids or edge["to"] not in ids or key in edge_keys:
            raise ValueError("Evidence graph edges must reference existing nodes without duplicates.")
        edge_keys.add(key)
    if source_id is not None:
        source_nodes = [node for node in nodes if node.get("type") == "source"]
        if len(source_nodes) != 1 or source_nodes[0].get("id") != f"source:{source_id}" or source_nodes[0].get("sha256") != source_sha256:
            raise ValueError("Evidence graph source must match the report source identity and digest.")
    if report_id is not None:
        expected = {f"report:{report_id}", f"assessment:{report_id}"}
        if not expected.issubset(ids):
            raise ValueError("Evidence graph must contain the report and its assessment nodes.")
