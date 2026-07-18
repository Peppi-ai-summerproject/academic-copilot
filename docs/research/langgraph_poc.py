"""Minimal LangGraph PoC - conceptual graph runner

This file demonstrates a tiny graph executor that runs Python callables as
nodes and passes a shared state dictionary between nodes.
"""

from typing import Callable, Dict, List


class Node:
    def __init__(self, name: str, fn: Callable[[Dict], Dict]):
        self.name = name
        self.fn = fn


class Graph:
    def __init__(self, nodes: List[Node], edges: Dict[str, List[str]]):
        self.nodes = {n.name: n for n in nodes}
        self.edges = edges

    def run(self, start: str) -> Dict:
        state: Dict = {}
        stack = [start]
        while stack:
            current = stack.pop(0)
            node = self.nodes[current]
            print(f"Running node: {node.name}")
            state = node.fn(state)
            for nxt in self.edges.get(current, []):
                stack.append(nxt)
        return state


# Example node functions

def node_a(state: Dict) -> Dict:
    state["a"] = "done"
    return state


def node_b(state: Dict) -> Dict:
    state["b"] = "done"
    return state


def demo() -> Dict:
    nodes = [Node("A", node_a), Node("B", node_b)]
    edges = {"A": ["B"], "B": []}
    g = Graph(nodes, edges)
    return g.run("A")


if __name__ == "__main__":
    print(demo())
