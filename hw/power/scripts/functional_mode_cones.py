"""Conservative functional dependencies with only datatype held constant.

This is read-only classification of an unchanged multi-mode netlist. Runtime
functional inputs are never constrained in synthesis or its timing analysis.
Constant propagation uses Boolean identities; unresolved variable dependencies
are retained, so shared magnitude/decode gates are not guessed apart.
"""
from functools import lru_cache
import re

def mode_cone(graph,targets,datatype):
    """Exact constant propagation, conservative dependencies for variable gates."""
    @lru_cache(None)
    def visit(net):
        if net in ("1'b0","1'b1"):return int(net[-1]),frozenset()
        match=re.fullmatch(r'in_datatype\[(\d+)\]',net)
        if match:return (datatype>>int(match[1]))&1,frozenset()
        if net not in graph.nodes:return None,frozenset()
        cell,ast,pins=graph.nodes[net]
        def evaluate(node):
            if node[0]=='pin':
                if node[1] in ('0','1'):return int(node[1]),frozenset()
                return visit(pins[node[1]])
            left,lc=evaluate(node[1])
            if node[0]=='not':return (None if left is None else 1-left),lc
            right,rc=evaluate(node[2])
            if node[0]=='and':
                if left==0 or right==0:return 0,frozenset()
                if left==1:return right,rc
                if right==1:return left,lc
            if node[0]=='or':
                if left==1 or right==1:return 1,frozenset()
                if left==0:return right,rc
                if right==0:return left,lc
            if node[0]=='xor':
                if left is not None and right is not None:return left^right,frozenset()
                if left is not None:return None,rc
                if right is not None:return None,lc
            return None,lc|rc
        value,deps=evaluate(ast)
        return value,deps|{cell} if value is None else frozenset()
    return set().union(*(visit(t)[1] for t in targets))
