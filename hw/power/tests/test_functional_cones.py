"""Check Boolean syntax, bit arithmetic, cone cuts and exact boundary proof."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from functional_cones import Graph, boolean_ast, evaluate, conditional_negate, add_bits, recover_function


class ConeTests(unittest.TestCase):
    def test_liberty_implicit_and_and_negation(self):
        tree=boolean_ast('!((A+B) C)')
        for a in (0,1):
            for b in (0,1):
                for c in (0,1):
                    self.assertEqual(evaluate(tree,dict(A=a,B=b,C=c).__getitem__,1),
                                     1-((a|b)&c))

    def test_xor_precedence(self):
        tree=boolean_ast('A B ^ C + !D')
        values=dict(A=1,B=0,C=1,D=1)
        self.assertEqual(evaluate(tree,values.__getitem__,1),1)

    def test_twos_complement_and_pair_growth(self):
        for a in range(256):
            for sign in (0,1):
                bits=[(a>>i)&1 for i in range(10)]
                result=conditional_negate(bits,sign,1)
                self.assertEqual(sum(v<<i for i,v in enumerate(result)),(-a if sign else a)&1023)
        for a,b in ((255,255),(255,-255),(-255,-255),(1,-2)):
            lhs=[(a>>i)&1 for i in range(10)];rhs=[(b>>i)&1 for i in range(10)]
            result=add_bits(lhs,rhs,0)
            self.assertEqual(sum(v<<i for i,v in enumerate(result)),(a+b)&1023)

    def graph(self):
        library={'XOR':{'A':('in',None),'B':('in',None),'Y':('out',boolean_ast('A^B'))},
                 'AND':{'A':('in',None),'B':('in',None),'Y':('out',boolean_ast('A B'))}}
        return Graph('input a,b,c; output y; wire n; '
                     'XOR u_x (.A(a),.B(b),.Y(n)); AND u_a (.A(n),.B(c),.Y(y));',library)

    def test_cone_cut_excludes_upstream_cells(self):
        graph=self.graph()
        self.assertEqual(graph.cone(['y']),{'u_x','u_a'})
        self.assertEqual(graph.cone(['y'],['n']),{'u_a'})

    @unittest.skipUnless(importlib.util.find_spec('z3'),'z3-solver required for SAT proof')
    def test_exact_recovery_accepts_xor_and_rejects_or(self):
        graph=self.graph()
        nodes,proofs=recover_function(graph,lambda n,o:[n('a')^n('b')])
        self.assertEqual(nodes,['n']);self.assertEqual(len(proofs),1)
        nodes,proofs=recover_function(graph,lambda n,o:[n('a')|n('b')])
        self.assertEqual(nodes,[]);self.assertEqual(proofs,[])
        nodes,proofs=recover_function(graph,lambda n,o:[o^o])
        self.assertEqual(nodes,[]);self.assertEqual(proofs,[])


if __name__=='__main__':unittest.main()
