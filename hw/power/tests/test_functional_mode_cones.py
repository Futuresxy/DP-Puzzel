"""Check that format-specific area ownership excludes shared and masked paths."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from functional_cones import Graph, boolean_ast
from functional_mode_cones import mode_cone

LIB={
    'AND': {'A':('in',None),'B':('in',None),'Z':('out',boolean_ast('A B'))},
    'OR': {'A':('in',None),'B':('in',None),'Z':('out',boolean_ast('A+B'))},
    'INV': {'A':('in',None),'Z':('out',boolean_ast('!A'))},
}

class ModeConeTest(unittest.TestCase):
    def test_mux_keeps_only_selected_data_dependencies(self):
        graph=Graph('''input [3:0] in_datatype; input a,b; output y;
        INV invert(.A(in_datatype[0]),.Z(nmode));
        AND left(.A(a),.B(in_datatype[0]),.Z(l));
        AND right(.A(b),.B(nmode),.Z(r));
        OR output_gate(.A(l),.B(r),.Z(y));''',LIB)
        self.assertEqual(mode_cone(graph,['y'],1),{'left','output_gate'})
        self.assertEqual(mode_cone(graph,['y'],0),{'right','output_gate'})
        self.assertEqual(mode_cone(graph,['y'],1)-mode_cone(graph,['y'],0),{'left'})

    def test_controlling_constant_masks_unknown_data_cone(self):
        graph=Graph('''input a,b; output y;
        AND payload(.A(a),.B(b),.Z(p));
        OR force_one(.A(p),.B(1'b1),.Z(y));''',LIB)
        self.assertEqual(mode_cone(graph,['y'],10),set())

    def test_shared_data_path_is_not_format_exclusive(self):
        graph=Graph('input a; output y; INV common(.A(a),.Z(y));',LIB)
        self.assertEqual(mode_cone(graph,['y'],10),mode_cone(graph,['y'],7))

if __name__=='__main__':unittest.main()
