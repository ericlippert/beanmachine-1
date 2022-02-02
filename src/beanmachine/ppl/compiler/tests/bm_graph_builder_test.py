# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Tests for bm_graph_builder.py"""
import unittest
from typing import Any

import torch
from beanmachine.ppl.compiler.bm_graph_builder import BMGraphBuilder
from beanmachine.ppl.compiler.bmg_nodes import (
    AdditionNode,
    ConstantTensorNode,
    DivisionNode,
    EqualNode,
    GreaterThanEqualNode,
    GreaterThanNode,
    LessThanEqualNode,
    LessThanNode,
    MatrixMultiplicationNode,
    MultiplicationNode,
    NotEqualNode,
    RealNode,
    SampleNode,
)
from beanmachine.ppl.compiler.gen_bmg_cpp import to_bmg_cpp
from beanmachine.ppl.compiler.gen_bmg_graph import to_bmg_graph
from beanmachine.ppl.compiler.gen_bmg_python import to_bmg_python
from beanmachine.ppl.compiler.gen_dot import to_dot
from beanmachine.ppl.compiler.runtime import BMGRuntime
from torch import Tensor, tensor


def tidy(s: str) -> str:
    return "\n".join(c.strip() for c in s.strip().split("\n")).strip()


def tensor_equality(x: Tensor, y: Tensor) -> bool:
    # Tensor equality is weird.  Suppose x and y are both
    # tensor([1.0, 2.0]). Then x.eq(y) is tensor([True, True]),
    # and x.eq(y).all() is tensor(True).
    return bool(x.eq(y).all())


class BMGraphBuilderTest(unittest.TestCase):
    def assertEqual(self, x: Any, y: Any) -> bool:
        if isinstance(x, Tensor) and isinstance(y, Tensor):
            return tensor_equality(x, y)
        return super().assertEqual(x, y)

    def test_graph_builder_1(self) -> None:

        # Just a trivial model to test whether we can take a properly-typed
        # accumulated graph and turn it into BMG, DOT, or a program that
        # produces a BMG.
        #
        # @random_variable def flip(): return Bernoulli(0.5)
        # @functional      def mult(): return (-flip() + 2) * 2
        bmg = BMGraphBuilder()
        half = bmg.add_probability(0.5)
        two = bmg.add_real(2)
        flip = bmg.add_bernoulli(half)
        samp = bmg.add_sample(flip)
        real = bmg.add_to_real(samp)
        neg = bmg.add_negate(real)
        add = bmg.add_addition(two, neg)
        mult = bmg.add_multiplication(two, add)
        bmg.add_observation(samp, True)
        bmg.add_query(mult)

        observed = to_dot(bmg, label_edges=False)
        expected = """
digraph "graph" {
  N0[label=0.5];
  N1[label=Bernoulli];
  N2[label=Sample];
  N3[label="Observation True"];
  N4[label=2];
  N5[label=ToReal];
  N6[label="-"];
  N7[label="+"];
  N8[label="*"];
  N9[label=Query];
  N0 -> N1;
  N1 -> N2;
  N2 -> N3;
  N2 -> N5;
  N4 -> N7;
  N4 -> N8;
  N5 -> N6;
  N6 -> N7;
  N7 -> N8;
  N8 -> N9;
}"""
        self.maxDiff = None
        self.assertEqual(expected.strip(), observed.strip())

        g = to_bmg_graph(bmg).graph
        observed = g.to_string()
        expected = """
Node 0 type 1 parents [ ] children [ 1 ] probability 0.5
Node 1 type 2 parents [ 0 ] children [ 2 ] unknown
Node 2 type 3 parents [ 1 ] children [ 4 ] boolean 1
Node 3 type 1 parents [ ] children [ 6 7 ] real 2
Node 4 type 3 parents [ 2 ] children [ 5 ] real 0
Node 5 type 3 parents [ 4 ] children [ 6 ] real 0
Node 6 type 3 parents [ 3 5 ] children [ 7 ] real 0
Node 7 type 3 parents [ 3 6 ] children [ ] real 0"""
        self.assertEqual(tidy(expected), tidy(observed))

        observed = to_bmg_python(bmg).code

        expected = """
from beanmachine import graph
from torch import tensor
g = graph.Graph()
n0 = g.add_constant_probability(0.5)
n1 = g.add_distribution(
  graph.DistributionType.BERNOULLI,
  graph.AtomicType.BOOLEAN,
  [n0],
)
n2 = g.add_operator(graph.OperatorType.SAMPLE, [n1])
g.observe(n2, True)
n3 = g.add_constant_real(2.0)
n4 = g.add_operator(graph.OperatorType.TO_REAL, [n2])
n5 = g.add_operator(graph.OperatorType.NEGATE, [n4])
n6 = g.add_operator(graph.OperatorType.ADD, [n3, n5])
n7 = g.add_operator(graph.OperatorType.MULTIPLY, [n3, n6])
q0 = g.query(n7)
"""
        self.assertEqual(expected.strip(), observed.strip())

        observed = to_bmg_cpp(bmg).code

        expected = """
graph::Graph g;
uint n0 = g.add_constant_probability(0.5);
uint n1 = g.add_distribution(
  graph::DistributionType::BERNOULLI,
  graph::AtomicType::BOOLEAN,
  std::vector<uint>({n0}));
uint n2 = g.add_operator(
  graph::OperatorType::SAMPLE, std::vector<uint>({n1}));
g.observe([n2], true);
uint n3 = g.add_constant(2.0);
uint n4 = g.add_operator(
  graph::OperatorType::TO_REAL, std::vector<uint>({n2}));
uint n5 = g.add_operator(
  graph::OperatorType::NEGATE, std::vector<uint>({n4}));
uint n6 = g.add_operator(
  graph::OperatorType::ADD, std::vector<uint>({n3, n5}));
uint n7 = g.add_operator(
  graph::OperatorType::MULTIPLY, std::vector<uint>({n3, n6}));
uint q0 = g.query(n7);
"""
        self.assertEqual(expected.strip(), observed.strip())

    def test_graph_builder_2(self) -> None:
        bmg = BMGraphBuilder()

        one = bmg.add_pos_real(1)
        two = bmg.add_pos_real(2)
        # These should all be folded:
        four = bmg.add_power(two, two)
        fourth = bmg.add_division(one, four)
        flip = bmg.add_bernoulli(fourth)
        samp = bmg.add_sample(flip)
        inv = bmg.add_complement(samp)  #  NOT operation
        real = bmg.add_to_positive_real(inv)
        div = bmg.add_division(real, two)
        p = bmg.add_power(div, two)
        lg = bmg.add_log(p)
        bmg.add_query(lg)
        # Note that the orphan nodes "1" and "4" are not stripped out
        # by default. If you want them gone, the "after_transform" flag does
        # a type check and also removes everything that is not an ancestor
        # of a query or observation.
        observed = to_dot(bmg, label_edges=False)
        expected = """
digraph "graph" {
  N00[label=1];
  N01[label=4];
  N02[label=0.25];
  N03[label=Bernoulli];
  N04[label=Sample];
  N05[label=complement];
  N06[label=ToPosReal];
  N07[label=2];
  N08[label="/"];
  N09[label="**"];
  N10[label=Log];
  N11[label=Query];
  N02 -> N03;
  N03 -> N04;
  N04 -> N05;
  N05 -> N06;
  N06 -> N08;
  N07 -> N08;
  N07 -> N09;
  N08 -> N09;
  N09 -> N10;
  N10 -> N11;
}
"""
        self.maxDiff = None
        self.assertEqual(expected.strip(), observed.strip())

        g = to_bmg_graph(bmg).graph
        observed = g.to_string()
        # Here however the orphaned nodes are never added to the graph.
        expected = """
Node 0 type 1 parents [ ] children [ 1 ] probability 0.25
Node 1 type 2 parents [ 0 ] children [ 2 ] unknown
Node 2 type 3 parents [ 1 ] children [ 3 ] boolean 0
Node 3 type 3 parents [ 2 ] children [ 4 ] boolean 0
Node 4 type 3 parents [ 3 ] children [ 6 ] positive real 1e-10
Node 5 type 1 parents [ ] children [ 6 ] positive real 0.5
Node 6 type 3 parents [ 4 5 ] children [ 8 ] positive real 1e-10
Node 7 type 1 parents [ ] children [ 8 ] positive real 2
Node 8 type 3 parents [ 6 7 ] children [ 9 ] positive real 1e-10
Node 9 type 3 parents [ 8 ] children [ ] real 0"""
        self.assertEqual(tidy(expected), tidy(observed))

    # The "add" methods do exactly that: add a node to the graph if it is not
    # already there.
    #
    # The "handle" methods try to keep everything in unwrapped values if possible;
    # they are trying to keep values out of the graph when possible. More specifically:
    # The arithmetic "handle" functions will detect when they are given normal
    # values and not produce graph nodes; they just do the math and produce the
    # normal Python value. The "handle" functions for constructing distributions
    # however are only ever called in non-test scenarios when a graph node
    # *must* be added to the graph, so they always do so.
    #
    # The next few tests verify that the handle functions are working as designed.

    def test_addition(self) -> None:
        """Test addition"""

        # This test verifies that various mechanisms for producing an addition node
        # in the graph -- or avoiding producing such a node -- are working as designed.

        bmg = BMGRuntime()

        t1 = tensor(1.0)
        t2 = tensor(2.0)
        t3 = tensor(3.0)

        # Graph nodes
        gr1 = bmg._bmg.add_real(1.0)
        self.assertTrue(isinstance(gr1, RealNode))
        gt1 = bmg._bmg.add_constant_tensor(t1)
        self.assertTrue(isinstance(gt1, ConstantTensorNode))

        # torch defines a "static" add method that takes two values.
        # Calling torch.add(x, y) should be logically the same as x + y

        ta = torch.add
        self.assertEqual(bmg.handle_dot_get(torch, "add"), ta)

        # torch defines an "instance" add method that takes a value.
        # Calling Tensor.add(x, y) or x.add(y) should be logically the same as x + y.

        # In Tensor.add(x, y), x is required to be a tensor, not a double. We do
        # not enforce this rule; handle_function(ta2, [x, y]) where x is a
        # double-valued graph node would not fail.
        #
        # That's fine; ensuring that every Bean Machine program that would crash
        # also crashes during compilation is not a design requirement, particularly
        # when we are generating a BMG model with the desired semantics.

        ta1 = t1.add
        self.assertEqual(bmg.handle_dot_get(t1, "add"), ta1)

        gta1 = bmg.handle_dot_get(gt1, "add")

        ta2 = torch.Tensor.add
        self.assertEqual(bmg.handle_dot_get(torch.Tensor, "add"), ta2)

        # Make a sample node; this cannot be simplified away.
        h = bmg._bmg.add_constant_tensor(tensor(0.5))
        b = bmg._bmg.add_bernoulli(h)
        s = bmg._bmg.add_sample(b)
        self.assertTrue(isinstance(s, SampleNode))

        sa = bmg.handle_dot_get(s, "add")

        # Adding two values produces a value
        self.assertEqual(bmg.handle_addition(1.0, 2.0), 3.0)
        self.assertEqual(bmg.handle_addition(1.0, t2), t3)
        self.assertEqual(bmg.handle_addition(t1, 2.0), t3)
        self.assertEqual(bmg.handle_addition(t1, t2), t3)
        self.assertEqual(bmg.handle_function(ta, [1.0], {"other": 2.0}), t3)
        self.assertEqual(bmg.handle_function(ta, [1.0, t2]), t3)
        self.assertEqual(bmg.handle_function(ta, [t1, 2.0]), t3)
        self.assertEqual(bmg.handle_function(ta, [t1, t2]), t3)
        self.assertEqual(bmg.handle_function(ta1, [2.0]), t3)
        self.assertEqual(bmg.handle_function(ta1, [], {"other": 2.0}), t3)
        self.assertEqual(bmg.handle_function(ta1, [t2]), t3)
        self.assertEqual(bmg.handle_function(ta2, [t1, 2.0]), t3)
        self.assertEqual(bmg.handle_function(ta2, [t1, t2]), t3)
        self.assertEqual(bmg.handle_function(ta2, [t1], {"other": t2}), t3)

        # Adding a graph constant and a value produces a value.
        # Note that this does not typically happen during accumulation of
        # a model, but we support it anyways.
        self.assertEqual(bmg.handle_addition(gr1, 2.0), 3.0)
        self.assertEqual(bmg.handle_addition(gr1, t2), t3)
        self.assertEqual(bmg.handle_addition(gt1, 2.0), t3)
        self.assertEqual(bmg.handle_addition(gt1, t2), t3)
        self.assertEqual(bmg.handle_addition(2.0, gr1), 3.0)
        self.assertEqual(bmg.handle_addition(2.0, gt1), t3)
        self.assertEqual(bmg.handle_addition(t2, gr1), t3)
        self.assertEqual(bmg.handle_addition(t2, gt1), t3)
        self.assertEqual(bmg.handle_function(ta, [gr1, 2.0]), t3)
        self.assertEqual(bmg.handle_function(ta, [gr1, t2]), t3)
        self.assertEqual(bmg.handle_function(ta, [gt1, 2.0]), t3)
        self.assertEqual(bmg.handle_function(ta, [gt1, t2]), t3)
        self.assertEqual(bmg.handle_function(gta1, [2.0]), t3)
        self.assertEqual(bmg.handle_function(gta1, [t2]), t3)
        self.assertEqual(bmg.handle_function(ta2, [gt1, 2.0]), t3)
        self.assertEqual(bmg.handle_function(ta2, [gt1, t2]), t3)
        self.assertEqual(bmg.handle_function(ta, [2.0, gr1]), t3)
        self.assertEqual(bmg.handle_function(ta, [2.0, gt1]), t3)
        self.assertEqual(bmg.handle_function(ta, [t2, gr1]), t3)
        self.assertEqual(bmg.handle_function(ta, [t2, gt1]), t3)
        self.assertEqual(bmg.handle_function(ta1, [gr1]), t2)
        self.assertEqual(bmg.handle_function(ta1, [gt1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t2, gr1]), t3)
        self.assertEqual(bmg.handle_function(ta2, [t2, gt1]), t3)

        # Adding two graph constants produces a value
        self.assertEqual(bmg.handle_addition(gr1, gr1), 2.0)
        self.assertEqual(bmg.handle_addition(gr1, gt1), t2)
        self.assertEqual(bmg.handle_addition(gt1, gr1), t2)
        self.assertEqual(bmg.handle_addition(gt1, gt1), t2)
        self.assertEqual(bmg.handle_function(ta, [gr1, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gr1, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1, gt1]), t2)
        self.assertEqual(bmg.handle_function(gta1, [gr1]), t2)
        self.assertEqual(bmg.handle_function(gta1, [gt1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt1, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt1, gt1]), t2)

        # Sample plus value produces node
        n = AdditionNode
        self.assertTrue(isinstance(bmg.handle_addition(s, 2.0), n))
        self.assertTrue(isinstance(bmg.handle_addition(s, t2), n))
        self.assertTrue(isinstance(bmg.handle_addition(2.0, s), n))
        self.assertTrue(isinstance(bmg.handle_addition(t2, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, 2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [2.0, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [t2, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta1, [s]), n))
        self.assertTrue(isinstance(bmg.handle_function(gta1, [s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, 2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [t2, s]), n))

        # Sample plus graph node produces node
        self.assertTrue(isinstance(bmg.handle_addition(s, gr1), n))
        self.assertTrue(isinstance(bmg.handle_addition(s, gt1), n))
        self.assertTrue(isinstance(bmg.handle_addition(gr1, s), n))
        self.assertTrue(isinstance(bmg.handle_addition(gt1, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, gr1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gr1, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gt1, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [gr1]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(gta1, [s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, gr1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [gt1, s]), n))

    def test_division(self) -> None:
        """Test division"""

        # This test verifies that various mechanisms for producing a division node
        # in the graph -- or avoiding producing such a node -- are working as designed.

        bmg = BMGRuntime()

        t1 = tensor(1.0)
        t2 = tensor(2.0)

        # Graph nodes
        gr1 = bmg._bmg.add_real(1.0)
        self.assertTrue(isinstance(gr1, RealNode))
        gr2 = bmg._bmg.add_real(2.0)
        self.assertTrue(isinstance(gr2, RealNode))
        gt1 = bmg._bmg.add_constant_tensor(t1)
        self.assertTrue(isinstance(gt1, ConstantTensorNode))
        gt2 = bmg._bmg.add_constant_tensor(t2)
        self.assertTrue(isinstance(gt2, ConstantTensorNode))

        # torch defines a "static" div method that takes two values.
        # Calling torch.div(x, y) should be logically the same as x + y

        ta = torch.div
        self.assertEqual(bmg.handle_dot_get(torch, "div"), ta)

        # torch defines an "instance" div method that takes a value.
        # Calling Tensor.div(x, y) or x.div(y) should be logically the same as x + y.

        ta1 = t2.div
        self.assertEqual(bmg.handle_dot_get(t2, "div"), ta1)

        gta1 = bmg.handle_dot_get(gt2, "div")

        ta2 = torch.Tensor.div
        self.assertEqual(bmg.handle_dot_get(torch.Tensor, "div"), ta2)

        # Make a sample node; this cannot be simplified away.
        h = bmg._bmg.add_constant_tensor(tensor(0.5))
        b = bmg._bmg.add_bernoulli(h)
        s = bmg._bmg.add_sample(b)
        self.assertTrue(isinstance(s, SampleNode))

        sa = bmg.handle_dot_get(s, "div")

        # Dividing two values produces a value
        self.assertEqual(bmg.handle_division(2.0, 1.0), 2.0)
        self.assertEqual(bmg.handle_division(2.0, t1), t2)
        self.assertEqual(bmg.handle_division(t2, 1.0), t2)
        self.assertEqual(bmg.handle_division(t2, t1), t2)
        self.assertEqual(bmg.handle_function(ta, [2.0], {"other": 1.0}), t2)
        self.assertEqual(bmg.handle_function(ta, [2.0, t1]), t2)
        self.assertEqual(bmg.handle_function(ta, [t2, 1.0]), t2)
        self.assertEqual(bmg.handle_function(ta, [t2, t1]), t2)
        self.assertEqual(bmg.handle_function(ta1, [1.0]), t2)
        self.assertEqual(bmg.handle_function(ta1, [], {"other": 1.0}), t2)
        self.assertEqual(bmg.handle_function(ta1, [t1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t2, 1.0]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t2], {"other": 1.0}), t2)
        self.assertEqual(bmg.handle_function(ta2, [t2, t1]), t2)

        # Dividing a graph constant and a value produces a value
        self.assertEqual(bmg.handle_division(gr2, 2.0), 1.0)
        self.assertEqual(bmg.handle_division(gr2, t2), t1)
        self.assertEqual(bmg.handle_division(gt2, 2.0), t1)
        self.assertEqual(bmg.handle_division(gt2, t2), t1)
        self.assertEqual(bmg.handle_division(2.0, gr2), 1.0)
        self.assertEqual(bmg.handle_division(2.0, gt2), t1)
        self.assertEqual(bmg.handle_division(t2, gr2), t1)
        self.assertEqual(bmg.handle_division(t2, gt2), t1)
        self.assertEqual(bmg.handle_function(ta, [gr2, 2.0]), t1)
        self.assertEqual(bmg.handle_function(ta, [gr2, t2]), t1)
        self.assertEqual(bmg.handle_function(ta, [gt2, 2.0]), t1)
        self.assertEqual(bmg.handle_function(ta, [gt2, t2]), t1)
        self.assertEqual(bmg.handle_function(gta1, [2.0]), t1)
        self.assertEqual(bmg.handle_function(gta1, [t2]), t1)
        self.assertEqual(bmg.handle_function(ta2, [gt2, 2.0]), t1)
        self.assertEqual(bmg.handle_function(ta2, [gt2, t2]), t1)
        self.assertEqual(bmg.handle_function(ta, [2.0, gr2]), t1)
        self.assertEqual(bmg.handle_function(ta, [2.0], {"other": gr2}), t1)
        self.assertEqual(bmg.handle_function(ta, [2.0, gt2]), t1)
        self.assertEqual(bmg.handle_function(ta, [t2, gr2]), t1)
        self.assertEqual(bmg.handle_function(ta, [t2, gt2]), t1)
        self.assertEqual(bmg.handle_function(ta1, [gr2]), t1)
        self.assertEqual(bmg.handle_function(ta1, [gt2]), t1)
        self.assertEqual(bmg.handle_function(ta2, [t2, gr2]), t1)
        self.assertEqual(bmg.handle_function(ta2, [t2, gt2]), t1)

        # Dividing two graph constants produces a value
        self.assertEqual(bmg.handle_division(gr2, gr1), 2.0)
        self.assertEqual(bmg.handle_division(gr2, gt1), t2)
        self.assertEqual(bmg.handle_division(gt2, gr1), t2)
        self.assertEqual(bmg.handle_division(gt2, gt1), t2)
        self.assertEqual(bmg.handle_function(ta, [gr2, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gr2, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt2, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt2, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt2], {"other": gt1}), t2)
        self.assertEqual(bmg.handle_function(gta1, [gr1]), t2)
        self.assertEqual(bmg.handle_function(gta1, [gt1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt2, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt2, gt1]), t2)

        # Sample divided by value produces node
        n = DivisionNode
        self.assertTrue(isinstance(bmg.handle_division(s, 2.0), n))
        self.assertTrue(isinstance(bmg.handle_division(s, t2), n))
        self.assertTrue(isinstance(bmg.handle_division(2.0, s), n))
        self.assertTrue(isinstance(bmg.handle_division(t2, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, 2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [2.0, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [t2, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(gta1, [s]), n))
        self.assertTrue(isinstance(bmg.handle_function(gta1, [], {"other": s}), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, 2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [t2, s]), n))

        # Sample divided by graph node produces node
        self.assertTrue(isinstance(bmg.handle_division(s, gr1), n))
        self.assertTrue(isinstance(bmg.handle_division(s, gt1), n))
        self.assertTrue(isinstance(bmg.handle_division(gr1, s), n))
        self.assertTrue(isinstance(bmg.handle_division(gt1, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, gr1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gr1, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gt1, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [gr1]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, gr1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [gt1, s]), n))

    def test_multiplication(self) -> None:
        """Test multiplication"""

        # This test verifies that various mechanisms for producing a multiplication node
        # in the graph -- or avoiding producing such a node -- are working as designed.

        bmg = BMGRuntime()

        t1 = tensor(1.0)
        t2 = tensor(2.0)

        # Graph nodes
        gr1 = bmg._bmg.add_real(1.0)
        self.assertTrue(isinstance(gr1, RealNode))
        gr2 = bmg._bmg.add_real(2.0)
        gt1 = bmg._bmg.add_constant_tensor(t1)
        self.assertTrue(isinstance(gt1, ConstantTensorNode))
        gt2 = bmg._bmg.add_constant_tensor(t2)

        # torch defines a "static" mul method that takes two values.
        # Calling torch.mul(x, y) should be logically the same as x * y

        ta = torch.mul
        self.assertEqual(bmg.handle_dot_get(torch, "mul"), ta)

        # torch defines an "instance" mul method that takes a value.
        # Calling Tensor.mul(x, y) or x.mul(y) should be logically the same as x * y.
        ta1 = t1.mul
        self.assertEqual(bmg.handle_dot_get(t1, "mul"), ta1)

        gta1 = bmg.handle_dot_get(gt1, "mul")
        gta2 = bmg.handle_dot_get(gt2, "mul")

        ta2 = torch.Tensor.mul
        self.assertEqual(bmg.handle_dot_get(torch.Tensor, "mul"), ta2)

        # Make a sample node; this cannot be simplified away.
        h = bmg._bmg.add_constant_tensor(tensor(0.5))
        b = bmg._bmg.add_bernoulli(h)
        s = bmg._bmg.add_sample(b)
        self.assertTrue(isinstance(s, SampleNode))

        sa = bmg.handle_dot_get(s, "mul")

        # Multiplying two values produces a value
        self.assertEqual(bmg.handle_multiplication(1.0, 2.0), 2.0)
        self.assertEqual(bmg.handle_multiplication(1.0, t2), t2)
        self.assertEqual(bmg.handle_multiplication(t1, 2.0), t2)
        self.assertEqual(bmg.handle_multiplication(t1, t2), t2)
        self.assertEqual(bmg.handle_function(ta, [1.0], {"other": 2.0}), t2)
        self.assertEqual(bmg.handle_function(ta, [1.0, t2]), t2)
        self.assertEqual(bmg.handle_function(ta, [t1, 2.0]), t2)
        self.assertEqual(bmg.handle_function(ta, [t1, t2]), t2)
        self.assertEqual(bmg.handle_function(ta1, [2.0]), t2)
        self.assertEqual(bmg.handle_function(ta1, [], {"other": 2.0}), t2)
        self.assertEqual(bmg.handle_function(ta1, [t2]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t1, 2.0]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t1], {"other": 2.0}), t2)
        self.assertEqual(bmg.handle_function(ta2, [t1, t2]), t2)

        # Multiplying a graph constant and a value produces a value
        self.assertEqual(bmg.handle_multiplication(gr1, 2.0), 2.0)
        self.assertEqual(bmg.handle_multiplication(gr1, t2), t2)
        self.assertEqual(bmg.handle_multiplication(gt1, 2.0), t2)
        self.assertEqual(bmg.handle_multiplication(gt1, t2), t2)
        self.assertEqual(bmg.handle_multiplication(2.0, gr1), 2.0)
        self.assertEqual(bmg.handle_multiplication(2.0, gt1), t2)
        self.assertEqual(bmg.handle_multiplication(t2, gr1), t2)
        self.assertEqual(bmg.handle_multiplication(t2, gt1), t2)
        self.assertEqual(bmg.handle_function(ta, [gr1, 2.0]), t2)
        self.assertEqual(bmg.handle_function(ta, [gr1, t2]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1, 2.0]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1, t2]), t2)
        self.assertEqual(bmg.handle_function(gta1, [2.0]), t2)
        self.assertEqual(bmg.handle_function(gta1, [t2]), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt1, 2.0]), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt1, t2]), t2)
        self.assertEqual(bmg.handle_function(ta, [2.0, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta, [2.0, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta, [t2, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta, [t2, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta1, [gr1]), t1)
        self.assertEqual(bmg.handle_function(ta1, [gt1]), t1)
        self.assertEqual(bmg.handle_function(ta1, [], {"other": gt1}), t1)
        self.assertEqual(bmg.handle_function(ta2, [t2, gr1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t2, gt1]), t2)

        # Multiplying two graph constants produces a value
        self.assertEqual(bmg.handle_multiplication(gr1, gr1), 1.0)
        self.assertEqual(bmg.handle_multiplication(gr1, gt1), t1)
        self.assertEqual(bmg.handle_multiplication(gt1, gr1), t1)
        self.assertEqual(bmg.handle_multiplication(gt1, gt1), t1)
        self.assertEqual(bmg.handle_function(ta, [gr1, gr1]), t1)
        self.assertEqual(bmg.handle_function(ta, [gr1, gt1]), t1)
        self.assertEqual(bmg.handle_function(ta, [gt1, gr1]), t1)
        self.assertEqual(bmg.handle_function(ta, [gt1, gt1]), t1)
        self.assertEqual(bmg.handle_function(gta1, [gr1]), t1)
        self.assertEqual(bmg.handle_function(gta1, [gt1]), t1)
        self.assertEqual(bmg.handle_function(ta2, [gt1, gr1]), t1)
        self.assertEqual(bmg.handle_function(ta2, [gt1, gt1]), t1)

        # Sample times value produces node
        n = MultiplicationNode
        self.assertTrue(isinstance(bmg.handle_multiplication(s, 2.0), n))
        self.assertTrue(isinstance(bmg.handle_multiplication(s, t2), n))
        self.assertTrue(isinstance(bmg.handle_multiplication(2.0, s), n))
        self.assertTrue(isinstance(bmg.handle_multiplication(t2, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, 2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [2.0, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [t2, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(gta2, [s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, 2.0]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, t2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [t2, s]), n))

        # Sample times graph node produces node
        self.assertTrue(isinstance(bmg.handle_multiplication(s, gr2), n))
        self.assertTrue(isinstance(bmg.handle_multiplication(s, gt2), n))
        self.assertTrue(isinstance(bmg.handle_multiplication(gr2, s), n))
        self.assertTrue(isinstance(bmg.handle_multiplication(gt2, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, gr2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, gt2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gr2, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gt2, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [gr2]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [gt2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, gr2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, gt2]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [gt2, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [gt2], {"other": s}), n))

    def test_matrix_multiplication(self) -> None:
        """Test matrix_multiplication"""

        # This test verifies that various mechanisms for producing a matrix
        # multiplication node in the graph -- or avoiding producing such a
        # node -- are working as designed.

        bmg = BMGRuntime()

        t1 = tensor([[3.0, 4.0], [5.0, 6.0]])
        t2 = tensor([[29.0, 36.0], [45.0, 56.0]])

        # Graph nodes
        gt1 = bmg._bmg.add_constant_tensor(t1)
        self.assertTrue(isinstance(gt1, ConstantTensorNode))
        gt2 = bmg._bmg.add_constant_tensor(t2)
        self.assertTrue(isinstance(gt2, ConstantTensorNode))

        # torch defines a "static" mm method that takes two values.

        ta = torch.mm
        self.assertEqual(bmg.handle_dot_get(torch, "mm"), ta)

        # torch defines an "instance" mm method that takes a value.

        ta1 = t1.mm
        self.assertEqual(bmg.handle_dot_get(t1, "mm"), ta1)

        gta1 = bmg.handle_dot_get(gt1, "mm")

        ta2 = torch.Tensor.mm
        self.assertEqual(bmg.handle_dot_get(torch.Tensor, "mm"), ta2)

        # Make a sample node; this cannot be simplified away.
        h = bmg._bmg.add_constant_tensor(tensor([[0.5, 0.5], [0.5, 0.5]]))
        b = bmg._bmg.add_bernoulli(h)
        s = bmg._bmg.add_sample(b)
        self.assertTrue(isinstance(s, SampleNode))

        sa = bmg.handle_dot_get(s, "mm")

        # Multiplying two values produces a value
        self.assertEqual(bmg.handle_matrix_multiplication(t1, t1), t2)
        self.assertEqual(bmg.handle_function(ta, [t1, t1]), t2)
        self.assertEqual(bmg.handle_function(ta, [t1], {"mat2": t1}), t2)
        self.assertEqual(bmg.handle_function(ta1, [t1]), t2)
        self.assertEqual(bmg.handle_function(ta1, [], {"mat2": t1}), t2)
        self.assertEqual(bmg.handle_function(ta2, [t1, t1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t1], {"mat2": t1}), t2)

        # Multiplying a graph constant and a value produces a value
        self.assertEqual(bmg.handle_matrix_multiplication(gt1, t1), t2)
        self.assertEqual(bmg.handle_matrix_multiplication(t1, gt1), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1, t1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1], {"mat2": t1}), t2)
        self.assertEqual(bmg.handle_function(gta1, [t1]), t2)
        self.assertEqual(bmg.handle_function(gta1, [], {"mat2": t1}), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt1, t1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [gt1], {"mat2": t1}), t2)
        self.assertEqual(bmg.handle_function(ta, [t1, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta, [t1], {"mat2": gt1}), t2)
        self.assertEqual(bmg.handle_function(ta1, [gt1]), t2)
        self.assertEqual(bmg.handle_function(ta1, [], {"mat2": gt1}), t2)
        self.assertEqual(bmg.handle_function(ta2, [t1, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta2, [t1], {"mat2": gt1}), t2)

        # Multiplying two graph constants produces a value
        self.assertEqual(bmg.handle_matrix_multiplication(gt1, gt1), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1, gt1]), t2)
        self.assertEqual(bmg.handle_function(ta, [gt1], {"mat2": gt1}), t2)
        self.assertEqual(bmg.handle_function(gta1, [gt1]), t1)
        self.assertEqual(bmg.handle_function(gta1, [], {"mat2": gt1}), t1)
        self.assertEqual(bmg.handle_function(ta2, [gt1, gt1]), t1)
        self.assertEqual(bmg.handle_function(ta2, [gt1], {"mat2": gt1}), t1)

        # Sample times value produces node
        n = MatrixMultiplicationNode
        self.assertTrue(isinstance(bmg.handle_matrix_multiplication(s, t1), n))
        self.assertTrue(isinstance(bmg.handle_matrix_multiplication(t1, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, t1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s], {"mat2": t1}), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [t1, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [t1], {"mat2": s}), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [t1]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [], {"mat2": t1}), n))
        self.assertTrue(isinstance(bmg.handle_function(gta1, [s]), n))
        self.assertTrue(isinstance(bmg.handle_function(gta1, [], {"mat2": s}), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, t1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s], {"mat2": t1}), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [t2, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [t2], {"mat2": s}), n))

        # Sample times graph node produces node
        self.assertTrue(isinstance(bmg.handle_matrix_multiplication(s, gt1), n))
        self.assertTrue(isinstance(bmg.handle_matrix_multiplication(gt1, s), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s, gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [s], {"mat2": gt1}), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gt1, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta, [gt1], {"mat2": s}), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(sa, [], {"mat2": gt1}), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s, gt1]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [s], {"mat2": gt1}), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [gt1, s]), n))
        self.assertTrue(isinstance(bmg.handle_function(ta2, [gt1], {"mat2": s}), n))

    def test_comparison(self) -> None:
        """Test comparison"""
        bmg = BMGRuntime()

        t1 = tensor(1.0)
        t2 = tensor(2.0)
        f = tensor(False)
        t = tensor(True)
        g1 = bmg._bmg.add_real(1.0)
        g2 = bmg._bmg.add_real(2.0)
        h = bmg._bmg.add_real(0.5)
        hc = bmg._bmg.add_halfcauchy(h)
        s = bmg._bmg.add_sample(hc)

        self.assertEqual(bmg.handle_equal(t2, t1), f)
        self.assertEqual(bmg.handle_equal(t1, t1), t)
        self.assertEqual(bmg.handle_equal(t1, t2), f)
        self.assertEqual(bmg.handle_equal(g2, t1), f)
        self.assertEqual(bmg.handle_equal(g1, t1), t)
        self.assertEqual(bmg.handle_equal(g1, t2), f)
        self.assertEqual(bmg.handle_equal(t2, g1), f)
        self.assertEqual(bmg.handle_equal(t1, g1), t)
        self.assertEqual(bmg.handle_equal(t1, g2), f)
        self.assertEqual(bmg.handle_equal(g2, g1), f)
        self.assertEqual(bmg.handle_equal(g1, g1), t)
        self.assertEqual(bmg.handle_equal(g1, g2), f)
        self.assertTrue(isinstance(bmg.handle_equal(s, t1), EqualNode))
        self.assertTrue(isinstance(bmg.handle_equal(t1, s), EqualNode))

        self.assertEqual(bmg.handle_not_equal(t2, t1), t)
        self.assertEqual(bmg.handle_not_equal(t1, t1), f)
        self.assertEqual(bmg.handle_not_equal(t1, t2), t)
        self.assertEqual(bmg.handle_not_equal(g2, t1), t)
        self.assertEqual(bmg.handle_not_equal(g1, t1), f)
        self.assertEqual(bmg.handle_not_equal(g1, t2), t)
        self.assertEqual(bmg.handle_not_equal(t2, g1), t)
        self.assertEqual(bmg.handle_not_equal(t1, g1), f)
        self.assertEqual(bmg.handle_not_equal(t1, g2), t)
        self.assertEqual(bmg.handle_not_equal(g2, g1), t)
        self.assertEqual(bmg.handle_not_equal(g1, g1), f)
        self.assertEqual(bmg.handle_not_equal(g1, g2), t)
        self.assertTrue(isinstance(bmg.handle_not_equal(s, t1), NotEqualNode))
        self.assertTrue(isinstance(bmg.handle_not_equal(t1, s), NotEqualNode))

        self.assertEqual(bmg.handle_greater_than(t2, t1), t)
        self.assertEqual(bmg.handle_greater_than(t1, t1), f)
        self.assertEqual(bmg.handle_greater_than(t1, t2), f)
        self.assertEqual(bmg.handle_greater_than(g2, t1), t)
        self.assertEqual(bmg.handle_greater_than(g1, t1), f)
        self.assertEqual(bmg.handle_greater_than(g1, t2), f)
        self.assertEqual(bmg.handle_greater_than(t2, g1), t)
        self.assertEqual(bmg.handle_greater_than(t1, g1), f)
        self.assertEqual(bmg.handle_greater_than(t1, g2), f)
        self.assertEqual(bmg.handle_greater_than(g2, g1), t)
        self.assertEqual(bmg.handle_greater_than(g1, g1), f)
        self.assertEqual(bmg.handle_greater_than(g1, g2), f)
        self.assertTrue(isinstance(bmg.handle_greater_than(s, t1), GreaterThanNode))
        self.assertTrue(isinstance(bmg.handle_greater_than(t1, s), GreaterThanNode))

        self.assertEqual(bmg.handle_greater_than_equal(t2, t1), t)
        self.assertEqual(bmg.handle_greater_than_equal(t1, t1), t)
        self.assertEqual(bmg.handle_greater_than_equal(t1, t2), f)
        self.assertEqual(bmg.handle_greater_than_equal(g2, t1), t)
        self.assertEqual(bmg.handle_greater_than_equal(g1, t1), t)
        self.assertEqual(bmg.handle_greater_than_equal(g1, t2), f)
        self.assertEqual(bmg.handle_greater_than_equal(t2, g1), t)
        self.assertEqual(bmg.handle_greater_than_equal(t1, g1), t)
        self.assertEqual(bmg.handle_greater_than_equal(t1, g2), f)
        self.assertEqual(bmg.handle_greater_than_equal(g2, g1), t)
        self.assertEqual(bmg.handle_greater_than_equal(g1, g1), t)
        self.assertEqual(bmg.handle_greater_than_equal(g1, g2), f)
        self.assertTrue(
            isinstance(bmg.handle_greater_than_equal(s, t1), GreaterThanEqualNode)
        )
        self.assertTrue(
            isinstance(bmg.handle_greater_than_equal(t1, s), GreaterThanEqualNode)
        )

        self.assertEqual(bmg.handle_less_than(t2, t1), f)
        self.assertEqual(bmg.handle_less_than(t1, t1), f)
        self.assertEqual(bmg.handle_less_than(t1, t2), t)
        self.assertEqual(bmg.handle_less_than(g2, t1), f)
        self.assertEqual(bmg.handle_less_than(g1, t1), f)
        self.assertEqual(bmg.handle_less_than(g1, t2), t)
        self.assertEqual(bmg.handle_less_than(t2, g1), f)
        self.assertEqual(bmg.handle_less_than(t1, g1), f)
        self.assertEqual(bmg.handle_less_than(t1, g2), t)
        self.assertEqual(bmg.handle_less_than(g2, g1), f)
        self.assertEqual(bmg.handle_less_than(g1, g1), f)
        self.assertEqual(bmg.handle_less_than(g1, g2), t)
        self.assertTrue(isinstance(bmg.handle_less_than(s, t1), LessThanNode))
        self.assertTrue(isinstance(bmg.handle_less_than(t1, s), LessThanNode))

        self.assertEqual(bmg.handle_less_than_equal(t2, t1), f)
        self.assertEqual(bmg.handle_less_than_equal(t1, t1), t)
        self.assertEqual(bmg.handle_less_than_equal(t1, t2), t)
        self.assertEqual(bmg.handle_less_than_equal(g2, t1), f)
        self.assertEqual(bmg.handle_less_than_equal(g1, t1), t)
        self.assertEqual(bmg.handle_less_than_equal(g1, t2), t)
        self.assertEqual(bmg.handle_less_than_equal(t2, g1), f)
        self.assertEqual(bmg.handle_less_than_equal(t1, g1), t)
        self.assertEqual(bmg.handle_less_than_equal(t1, g2), t)
        self.assertEqual(bmg.handle_less_than_equal(g2, g1), f)
        self.assertEqual(bmg.handle_less_than_equal(g1, g1), t)
        self.assertEqual(bmg.handle_less_than_equal(g1, g2), t)
        self.assertTrue(
            isinstance(bmg.handle_less_than_equal(s, t1), LessThanEqualNode)
        )
        self.assertTrue(
            isinstance(bmg.handle_less_than_equal(t1, s), LessThanEqualNode)
        )

    def test_to_positive_real(self) -> None:
        """Test to_positive_real"""
        bmg = BMGraphBuilder()
        two = bmg.add_pos_real(2.0)
        # to_positive_real on a positive real constant is an identity
        self.assertEqual(bmg.add_to_positive_real(two), two)
        beta22 = bmg.add_beta(two, two)
        to_pr = bmg.add_to_positive_real(beta22)
        # to_positive_real nodes are deduplicated
        self.assertEqual(bmg.add_to_positive_real(beta22), to_pr)

    def test_to_probability(self) -> None:
        """Test to_probability"""
        bmg = BMGraphBuilder()
        h = bmg.add_probability(0.5)
        # to_probability on a prob constant is an identity
        self.assertEqual(bmg.add_to_probability(h), h)
        # We have (hc / (0.5 + hc)) which is always between
        # 0 and 1, but the quotient of two positive reals
        # is a positive real. Force it to be a probability.
        hc = bmg.add_halfcauchy(h)
        s = bmg.add_addition(hc, h)
        q = bmg.add_division(hc, s)
        to_p = bmg.add_to_probability(q)
        # to_probability nodes are deduplicated
        self.assertEqual(bmg.add_to_probability(q), to_p)

    def test_if_then_else(self) -> None:
        self.maxDiff = None
        bmg = BMGraphBuilder()
        p = bmg.add_constant(0.5)
        z = bmg.add_constant(0.0)
        o = bmg.add_constant(1.0)
        b = bmg.add_bernoulli(p)
        s = bmg.add_sample(b)
        bmg.add_if_then_else(s, o, z)
        observed = to_dot(bmg)
        expected = """
digraph "graph" {
  N0[label=0.5];
  N1[label=Bernoulli];
  N2[label=Sample];
  N3[label=1.0];
  N4[label=0.0];
  N5[label=if];
  N0 -> N1[label=probability];
  N1 -> N2[label=operand];
  N2 -> N5[label=condition];
  N3 -> N5[label=consequence];
  N4 -> N5[label=alternative];
}"""
        self.assertEqual(expected.strip(), observed.strip())

    def test_allowed_functions(self) -> None:
        bmg = BMGRuntime()
        p = bmg._bmg.add_constant(0.5)
        b = bmg._bmg.add_bernoulli(p)
        s = bmg._bmg.add_sample(b)
        d = bmg.handle_function(dict, [[(1, s)]])
        self.assertEqual(d, {1: s})

    def test_add_tensor(self) -> None:
        bmg = BMGraphBuilder()
        p = bmg.add_constant(0.5)
        b = bmg.add_bernoulli(p)
        s = bmg.add_sample(b)

        # Tensors are deduplicated
        t1 = bmg.add_tensor(torch.Size([3]), s, s, p)
        t2 = bmg.add_tensor(torch.Size([3]), *[s, s, p])
        self.assertTrue(t1 is t2)

        observed = to_dot(bmg)
        expected = """
digraph "graph" {
  N0[label=0.5];
  N1[label=Bernoulli];
  N2[label=Sample];
  N3[label=Tensor];
  N0 -> N1[label=probability];
  N0 -> N3[label=2];
  N1 -> N2[label=operand];
  N2 -> N3[label=0];
  N2 -> N3[label=1];
}
"""
        self.assertEqual(observed.strip(), expected.strip())

    def test_remove_leaf_from_builder(self) -> None:
        bmg = BMGraphBuilder()
        p = bmg.add_constant(0.5)
        b = bmg.add_bernoulli(p)
        s = bmg.add_sample(b)
        o = bmg.add_observation(s, True)

        observed = to_dot(bmg)
        expected = """
digraph "graph" {
  N0[label=0.5];
  N1[label=Bernoulli];
  N2[label=Sample];
  N3[label="Observation True"];
  N0 -> N1[label=probability];
  N1 -> N2[label=operand];
  N2 -> N3[label=operand];
}
"""
        self.assertEqual(observed.strip(), expected.strip())

        with self.assertRaises(ValueError):
            # Not a leaf
            bmg.remove_leaf(s)

        bmg.remove_leaf(o)
        observed = to_dot(bmg)
        expected = """
digraph "graph" {
  N0[label=0.5];
  N1[label=Bernoulli];
  N2[label=Sample];
  N0 -> N1[label=probability];
  N1 -> N2[label=operand];
}
"""
        self.assertEqual(observed.strip(), expected.strip())

        # Is a leaf now.
        bmg.remove_leaf(s)
        observed = to_dot(bmg)
        expected = """
digraph "graph" {
  N0[label=0.5];
  N1[label=Bernoulli];
  N0 -> N1[label=probability];
}
"""
        self.assertEqual(observed.strip(), expected.strip())
