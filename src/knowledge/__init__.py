"""knowledge: a knowledge graph any agent can query and add to, and people can explore.

The library is the tool. Every capability is a function here; results are plain dicts and lists.

    import knowledge as kg
    kg.ingest("research", documents=kg.load_documents("./notes"), method="cooccurrence")
    kg.path("research", "delegation", "human agency")

Model-backed: ingest (method "llm"), ask, report, questions, reconcile. Everything else needs no model.
"""

from .errors import ToolError
from .help import VERSION as __version__
from .lib import (add, analyze, ask, choose_view, communities, context, contradictions, doctor, events, evidence, export,
                  gaps, graph_data, graphs, host_task, ingest, manifest, path, questions, reconcile, relate, report, search,
                  show, stats, supersede, timeline, visualize)
from .store import Graph, open_graph
from .text import load_documents, split_text


def skill() -> str:
    """The tool's skill, as `knowledge --help` prints it."""
    from .help import skill as _skill

    return _skill()


def capability_skill(name: str) -> str:
    """One capability's skill, as `knowledge <capability> --help` prints it."""
    from .help import capability_skill as _capability_skill

    return _capability_skill(name)


def short_help() -> str:
    """The user summary, as `knowledge -h` prints it."""
    from .help import short_help as _short_help

    return _short_help()


__all__ = ["ToolError", "__version__", "add", "analyze", "ask", "choose_view", "communities", "context", "contradictions",
           "doctor", "events", "evidence", "export", "gaps", "graph_data", "graphs", "host_task", "ingest", "manifest", "path",
           "questions", "reconcile", "relate", "report", "search", "show", "stats", "supersede", "timeline",
           "visualize", "Graph", "open_graph", "load_documents", "split_text", "skill", "capability_skill", "short_help"]
