"""Read-only mapped-netlist cone analysis. Library functions remain local inputs.

The parser intentionally accepts only the structural syntax emitted by this DC
run. Random signatures find candidates; only SAT-proven bit equivalence may be
used to recover a removed arithmetic boundary.
"""
import csv
from functools import lru_cache
import random
import re


def boolean_ast(expression):
    tokens = re.findall(r'[A-Za-z_][A-Za-z_0-9]*|[01]|[!()+^]', expression)
    position = 0
    def atom():
        nonlocal position
        token = tokens[position]; position += 1
        if token == '!': return ('not', atom())
        if token == '(':
            value = union()
            assert tokens[position] == ')'
            position += 1
            return value
        return ('pin', token)
    def conjunction():
        value = atom()
        while position < len(tokens) and tokens[position] not in (')', '+', '^'):
            value = ('and', value, atom())
        return value
    def exclusive():
        nonlocal position
        value = conjunction()
        while position < len(tokens) and tokens[position] == '^':
            position += 1; value = ('xor', value, conjunction())
        return value
    def union():
        nonlocal position
        value = exclusive()
        while position < len(tokens) and tokens[position] == '+':
            position += 1; value = ('or', value, exclusive())
        return value
    result = union()
    assert position == len(tokens), expression
    return result


def evaluate(ast, get, one):
    op = ast[0]
    if op == 'pin': return one if ast[1] == '1' else (one ^ one if ast[1] == '0' else get(ast[1]))
    left = evaluate(ast[1], get, one)
    if op == 'not': return left ^ one
    right = evaluate(ast[2], get, one)
    return {'and': lambda: left & right, 'or': lambda: left | right,
            'xor': lambda: left ^ right}[op]()


def load_library(path):
    result = {}
    for row in csv.DictReader(path.open(), delimiter='\t'):
        entry = result.setdefault(row['reference'], {})
        value = (row['direction'], boolean_ast(row['function']) if row['function'] else None)
        if row['pin'] in entry: assert entry[row['pin']] == value
        entry[row['pin']] = value
    return result


class Graph:
    def __init__(self, body, library):
        self.cells = {}
        self.nodes = {}
        self.children = {}
        # Only one-bit leaf port connections; non-leaf concatenations stay opaque.
        for match in re.finditer(r'\b(\w+)\s+(\w+)\s*\((.*?)\);', body, re.S):
            ref, name, connections = match.groups()
            pins = dict((p, re.sub(r'\s+', '', n)) for p,n in re.findall(r'\.(\w+)\s*\((.*?)\)', connections, re.S))
            if ref not in library:
                self.children[name] = (ref, pins)
                continue
            self.cells[name] = (ref, pins)
            for pin, (direction, ast) in library[ref].items():
                if direction == 'out' and pin in pins and pins[pin]:
                    if ast is None: raise ValueError('No combinational function')
                    net = pins[pin]
                    if net in self.nodes: raise ValueError('Multiple drivers: ' + net)
                    self.nodes[net] = (name, ast, pins)
        self.boundary = set()
        self.inputs = {}
        for direction, width, names in re.findall(r'\b(input|output|wire)\s*(\[[^]]+\])?\s*([^;]+);', body):
            for name in names.split(','):
                name = name.strip()
                bounds = list(map(int, re.findall(r'\d+', width))) if width else []
                bits = [f'{name}[{i}]' for i in range(min(bounds), max(bounds)+1)] if bounds else [name]
                self.inputs[name] = bits
                if direction == 'input':self.boundary.update(bits)
        # Child output wires are boundaries for direct-parent cone ownership.
        for _, pins in self.cells.values():
            for net in pins.values():
                if net and net not in self.nodes: self.boundary.add(net)

    def simulator(self, symbolic=False):
        if symbolic:
            import z3
            one = z3.BitVecVal(1, 1)
            source = lambda n: z3.BitVec(n, 1)
        else:
            one = (1 << 1024) - 1
            rng = random.Random(44803)
            values = {n: rng.getrandbits(1024) for n in sorted(self.boundary)}
            source = lambda n: values[n]
        @lru_cache(None)
        def net(n):
            if n in ("1'b0", "1'b1"):return one if n[-1]=='1' else one ^ one
            if n not in self.nodes: return source(n)
            _, ast, pins = self.nodes[n]
            return evaluate(ast, lambda p: net(pins[p]), one)
        return net, one

    def cone(self, targets, stops=()):
        stops = set(stops); seen = set(); cells = set()
        def visit(net):
            if net in stops or net in seen or net not in self.nodes:return
            seen.add(net)
            name, ast, pins = self.nodes[net]
            cells.add(name)
            def inputs(node):
                if node[0] == 'pin':
                    if node[1] in pins:visit(pins[node[1]])
                else:
                    for child in node[1:]:inputs(child)
            inputs(ast)
        for target in targets: visit(target)
        return cells


def add_bits(left, right, zero):
    result=[]; carry=zero
    for a,b in zip(left,right):
        result.append(a ^ b ^ carry)
        carry=(a & b) | ((a ^ b) & carry)
    return result


def conditional_negate(bits, sign, one):
    zero=one ^ one
    return add_bits([b ^ sign for b in bits], [sign]+[zero]*(len(bits)-1), zero)


def pair_functions(net, one, index):
    zero=one ^ one
    def is_type(value):
        equal=one
        for bit in range(4):equal &= net(f'in_datatype[{bit}]') ^ (zero if value & (1<<bit) else one)
        return equal
    enable=net('in_valid') & (is_type(7)|is_type(8)|is_type(9))
    operands=[]; raw=[]
    for offset in (0,1):
        element=2*index+offset
        mag=[net(f'in_products[{22*element+bit}]') for bit in range(8)]+[zero,zero]
        value=conditional_negate(mag,net(f'in_negative[{element}]'),one)
        raw.append(value)
        operands.append([b & enable for b in value])
    pair_sum=add_bits(*operands,zero)
    pair_abs=conditional_negate(pair_sum,pair_sum[-1],one)
    raw_sum=add_bits(*raw,zero)
    return dict(pair_a=operands[0],pair_b=operands[1],pair_sum=pair_sum,pair_abs=pair_abs,
                raw_a=raw[0],raw_b=raw[1],raw_sum=raw_sum,
                raw_abs=conditional_negate(raw_sum,raw_sum[-1],one))


def recover_pair(graph):
    """Find exact net (or its inverted polarity) for every surviving pair bit."""
    import z3
    net, one = graph.simulator()
    lookup={}
    for name in graph.nodes:
        value=net(name)
        lookup.setdefault(value,[]).append((name,False))
        lookup.setdefault(value^one,[]).append((name,True))
    symbolic, symbolic_one=graph.simulator(True)
    recovered={}; proofs=[]
    for index in range(4):
        targets=pair_functions(net,one,index)
        symbolic_targets=pair_functions(symbolic,symbolic_one,index)
        for field, bits in targets.items():
            found=[]
            for bit,value in enumerate(bits):
                if value in (0,one):continue  # Shared tie cells are not arithmetic boundaries.
                candidates=lookup.get(value,[])
                for name,inverted in candidates:
                    solver=z3.Solver();solver.set(timeout=10000)
                    expr=symbolic(name) ^ (symbolic_one if inverted else symbolic_one^symbolic_one)
                    solver.add(expr != symbolic_targets[field][bit])
                    if solver.check()==z3.unsat:
                        found.append(name);proofs.append((index,field,bit,name,inverted));break
            recovered[f'{index}_{field}']=sorted(set(found))
    return recovered,proofs


def recover_function(graph, target_builder):
    """Recover internal boundaries by signature filtering and exact SAT proof."""
    import z3
    net, one=graph.simulator(); sym, sym_one=graph.simulator(True)
    candidates={}
    for name in graph.nodes:
        value=net(name)
        candidates.setdefault(value,[]).append((name,False))
        candidates.setdefault(value^one,[]).append((name,True))
    targets=target_builder(net,one); symbolic=target_builder(sym,sym_one)
    found=[];proofs=[]
    for bit,value in enumerate(targets):
        if value in (0,one):continue
        for name,inverted in candidates.get(value,[]):
            solver=z3.Solver();solver.set(timeout=10000)
            expr=sym(name) ^ (sym_one if inverted else sym_one^sym_one)
            solver.add(expr != symbolic[bit])
            if solver.check()==z3.unsat:
                found.append(name);proofs.append((bit,name,inverted));break
    return sorted(set(found)),proofs


def signal_bits(graph, expression):
    """Expand DC structural concatenations, part selects and declared vectors."""
    result=[]
    for token in re.findall(r"1'b[01]|[A-Za-z_][A-Za-z_0-9]*(?:\[\d+(?::\d+)?\])?",expression):
        m=re.fullmatch(r'(\w+)\[(\d+):(\d+)\]',token)
        if m:
            base,high,low=m.groups();result.extend(f'{base}[{i}]' for i in range(int(low),int(high)+1))
        elif '[' not in token and token in graph.inputs:result.extend(graph.inputs[token])
        else:result.append(token)
    return result
