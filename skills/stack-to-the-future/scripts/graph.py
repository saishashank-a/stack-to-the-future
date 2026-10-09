"""Import and call graphs. Nodes are files (imports) or "path::qualified.symbol" (calls)."""
import networkx as nx


def node(path: str, symbol: str) -> str:
    return f"{path}::{symbol}"


def call_graph(calls: list[dict]) -> nx.DiGraph:
    g = nx.DiGraph()
    for c in calls:
        g.add_edge(node(c["file"], c["caller"]), node(c["target_file"], c["target_symbol"]))
    return g


def import_graph(imports: list[dict]) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_edges_from((i["file"], i["target"]) for i in imports if i["target"] and i["target"] != i["file"])
    return g


def reachable(g: nx.DiGraph, n: str) -> set[str]:
    return nx.descendants(g, n) if n in g else set()


def neighbourhood(g: nx.DiGraph, n: str) -> set[str]:
    """n, what n calls, and each caller of n with what it calls: where the guard on a state change usually sits."""
    if n not in g:
        return {n}
    near = {n, *g.successors(n)}
    for caller in g.predecessors(n):
        near |= {caller, *g.successors(caller)}
    return near
