# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import unittest

import torch
from beanmachine.ppl.compiler.bm_graph_builder import BMGraphBuilder
from beanmachine.ppl.compiler.gen_bmg_graph import to_bmg_graph
from beanmachine.ppl.compiler.gen_dot import to_dot
from beanmachine.ppl.model.rv_identifier import RVIdentifier
from torch import Size


def _rv_id() -> RVIdentifier:
    return RVIdentifier(lambda a, b: a, (1, 1))


class FixMatrixOpTest(unittest.TestCase):
    def test_fix_matrix_addition(self) -> None:
        self.maxDiff = None
        bmg = BMGraphBuilder()
        zeros = bmg.add_real_matrix(torch.zeros(2))
        ones = bmg.add_pos_real_matrix(torch.ones(2))
        tensor_elements = []
        for index in range(0, 2):
            index_node = bmg.add_natural(index)
            index_mu = bmg.add_vector_index(zeros, index_node)
            index_sigma = bmg.add_vector_index(ones, index_node)
            normal = bmg.add_normal(index_mu, index_sigma)
            sample = bmg.add_sample(normal)
            tensor_elements.append(sample)
        matrix = bmg.add_tensor(Size([2]), *tensor_elements)
        exp = bmg.add_matrix_exp(matrix)
        mult = bmg.add_elementwise_multiplication(matrix, matrix)
        add = bmg.add_matrix_addition(exp, mult)
        bmg.add_query(add, _rv_id())
        observed = to_dot(bmg, after_transform=False)
        expectation = """
digraph "graph" {
  N00[label="[0.0,0.0]"];
  N01[label=0];
  N02[label=index];
  N03[label="[1.0,1.0]"];
  N04[label=index];
  N05[label=Normal];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=index];
  N10[label=Normal];
  N11[label=Sample];
  N12[label=Tensor];
  N13[label=MatrixExp];
  N14[label=ElementwiseMult];
  N15[label=MatrixAdd];
  N16[label=Query];
  N00 -> N02[label=left];
  N00 -> N08[label=left];
  N01 -> N02[label=right];
  N01 -> N04[label=right];
  N02 -> N05[label=mu];
  N03 -> N04[label=left];
  N03 -> N09[label=left];
  N04 -> N05[label=sigma];
  N05 -> N06[label=operand];
  N06 -> N12[label=left];
  N07 -> N08[label=right];
  N07 -> N09[label=right];
  N08 -> N10[label=mu];
  N09 -> N10[label=sigma];
  N10 -> N11[label=operand];
  N11 -> N12[label=right];
  N12 -> N13[label=operand];
  N12 -> N14[label=left];
  N12 -> N14[label=right];
  N13 -> N15[label=left];
  N14 -> N15[label=right];
  N15 -> N16[label=operator];
}
                """
        self.assertEqual(expectation.strip(), observed.strip())
        observed = to_dot(bmg, after_transform=True)
        expectation = """
digraph "graph" {
  N00[label="[0.0,0.0]"];
  N01[label=0];
  N02[label=index];
  N03[label="[1.0,1.0]"];
  N04[label=index];
  N05[label=Normal];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=index];
  N10[label=Normal];
  N11[label=Sample];
  N12[label=2];
  N13[label=ToMatrix];
  N14[label=MatrixExp];
  N15[label=ToRealMatrix];
  N16[label=ElementwiseMult];
  N17[label=MatrixAdd];
  N18[label=Query];
  N00 -> N02[label=left];
  N00 -> N08[label=left];
  N01 -> N02[label=right];
  N01 -> N04[label=right];
  N02 -> N05[label=mu];
  N03 -> N04[label=left];
  N03 -> N09[label=left];
  N04 -> N05[label=sigma];
  N05 -> N06[label=operand];
  N06 -> N13[label=0];
  N07 -> N08[label=right];
  N07 -> N09[label=right];
  N07 -> N13[label=columns];
  N08 -> N10[label=mu];
  N09 -> N10[label=sigma];
  N10 -> N11[label=operand];
  N11 -> N13[label=1];
  N12 -> N13[label=rows];
  N13 -> N14[label=operand];
  N13 -> N16[label=left];
  N13 -> N16[label=right];
  N14 -> N15[label=operand];
  N15 -> N17[label=left];
  N16 -> N17[label=right];
  N17 -> N18[label=operator];
}
        """
        self.assertEqual(expectation.strip(), observed.strip())

        generated_graph = to_bmg_graph(bmg)
        observed = generated_graph.graph.to_dot()
        expectation = """
digraph "graph" {
  N0[label="matrix"];
  N1[label="0"];
  N2[label="Index"];
  N3[label="matrix"];
  N4[label="Index"];
  N5[label="Normal"];
  N6[label="~"];
  N7[label="1"];
  N8[label="Index"];
  N9[label="Index"];
  N10[label="Normal"];
  N11[label="~"];
  N12[label="2"];
  N13[label="ToMatrix"];
  N14[label="MatrixExp"];
  N15[label="ToReal"];
  N16[label="ElementwiseMultiply"];
  N17[label="MatrixAdd"];
  N0 -> N2;
  N0 -> N8;
  N1 -> N2;
  N1 -> N4;
  N2 -> N5;
  N3 -> N4;
  N3 -> N9;
  N4 -> N5;
  N5 -> N6;
  N6 -> N13;
  N7 -> N8;
  N7 -> N9;
  N7 -> N13;
  N8 -> N10;
  N9 -> N10;
  N10 -> N11;
  N11 -> N13;
  N12 -> N13;
  N13 -> N14;
  N13 -> N16;
  N13 -> N16;
  N14 -> N15;
  N15 -> N17;
  N16 -> N17;
  Q0[label="Query"];
  N17 -> Q0;
}
        """
        self.assertEqual(expectation.strip(), observed.strip())

    def test_fix_elementwise_multiply(self) -> None:
        self.maxDiff = None
        bmg = BMGraphBuilder()
        zeros = bmg.add_real_matrix(torch.zeros(2))
        ones = bmg.add_pos_real_matrix(torch.ones(2))
        tensor_elements = []
        for index in range(0, 2):
            index_node = bmg.add_natural(index)
            index_mu = bmg.add_vector_index(zeros, index_node)
            index_sigma = bmg.add_vector_index(ones, index_node)
            normal = bmg.add_normal(index_mu, index_sigma)
            sample = bmg.add_sample(normal)
            tensor_elements.append(sample)
        matrix = bmg.add_tensor(Size([2]), *tensor_elements)
        exp = bmg.add_matrix_exp(matrix)
        add = bmg.add_matrix_addition(matrix, matrix)
        mult = bmg.add_elementwise_multiplication(exp, add)
        sum = bmg.add_matrix_sum(mult)
        bmg.add_query(sum, _rv_id())
        observed = to_dot(bmg, after_transform=False)
        expectation = """
digraph "graph" {
  N00[label="[0.0,0.0]"];
  N01[label=0];
  N02[label=index];
  N03[label="[1.0,1.0]"];
  N04[label=index];
  N05[label=Normal];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=index];
  N10[label=Normal];
  N11[label=Sample];
  N12[label=Tensor];
  N13[label=MatrixExp];
  N14[label=MatrixAdd];
  N15[label=ElementwiseMult];
  N16[label=MatrixSum];
  N17[label=Query];
  N00 -> N02[label=left];
  N00 -> N08[label=left];
  N01 -> N02[label=right];
  N01 -> N04[label=right];
  N02 -> N05[label=mu];
  N03 -> N04[label=left];
  N03 -> N09[label=left];
  N04 -> N05[label=sigma];
  N05 -> N06[label=operand];
  N06 -> N12[label=left];
  N07 -> N08[label=right];
  N07 -> N09[label=right];
  N08 -> N10[label=mu];
  N09 -> N10[label=sigma];
  N10 -> N11[label=operand];
  N11 -> N12[label=right];
  N12 -> N13[label=operand];
  N12 -> N14[label=left];
  N12 -> N14[label=right];
  N13 -> N15[label=left];
  N14 -> N15[label=right];
  N15 -> N16[label=operand];
  N16 -> N17[label=operator];
}
                """
        self.assertEqual(expectation.strip(), observed.strip())
        observed = to_dot(bmg, after_transform=True)
        expectation = """
digraph "graph" {
  N00[label="[0.0,0.0]"];
  N01[label=0];
  N02[label=index];
  N03[label="[1.0,1.0]"];
  N04[label=index];
  N05[label=Normal];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=index];
  N10[label=Normal];
  N11[label=Sample];
  N12[label=2];
  N13[label=ToMatrix];
  N14[label=MatrixExp];
  N15[label=ToRealMatrix];
  N16[label=MatrixAdd];
  N17[label=ElementwiseMult];
  N18[label=MatrixSum];
  N19[label=Query];
  N00 -> N02[label=left];
  N00 -> N08[label=left];
  N01 -> N02[label=right];
  N01 -> N04[label=right];
  N02 -> N05[label=mu];
  N03 -> N04[label=left];
  N03 -> N09[label=left];
  N04 -> N05[label=sigma];
  N05 -> N06[label=operand];
  N06 -> N13[label=0];
  N07 -> N08[label=right];
  N07 -> N09[label=right];
  N07 -> N13[label=columns];
  N08 -> N10[label=mu];
  N09 -> N10[label=sigma];
  N10 -> N11[label=operand];
  N11 -> N13[label=1];
  N12 -> N13[label=rows];
  N13 -> N14[label=operand];
  N13 -> N16[label=left];
  N13 -> N16[label=right];
  N14 -> N15[label=operand];
  N15 -> N17[label=left];
  N16 -> N17[label=right];
  N17 -> N18[label=operand];
  N18 -> N19[label=operator];
}
        """
        self.assertEqual(expectation.strip(), observed.strip())

        generated_graph = to_bmg_graph(bmg)
        observed = generated_graph.graph.to_dot()
        expectation = """
digraph "graph" {
  N0[label="matrix"];
  N1[label="0"];
  N2[label="Index"];
  N3[label="matrix"];
  N4[label="Index"];
  N5[label="Normal"];
  N6[label="~"];
  N7[label="1"];
  N8[label="Index"];
  N9[label="Index"];
  N10[label="Normal"];
  N11[label="~"];
  N12[label="2"];
  N13[label="ToMatrix"];
  N14[label="MatrixExp"];
  N15[label="ToReal"];
  N16[label="MatrixAdd"];
  N17[label="ElementwiseMultiply"];
  N18[label="MatrixSum"];
  N0 -> N2;
  N0 -> N8;
  N1 -> N2;
  N1 -> N4;
  N2 -> N5;
  N3 -> N4;
  N3 -> N9;
  N4 -> N5;
  N5 -> N6;
  N6 -> N13;
  N7 -> N8;
  N7 -> N9;
  N7 -> N13;
  N8 -> N10;
  N9 -> N10;
  N10 -> N11;
  N11 -> N13;
  N12 -> N13;
  N13 -> N14;
  N13 -> N16;
  N13 -> N16;
  N14 -> N15;
  N15 -> N17;
  N16 -> N17;
  N17 -> N18;
  Q0[label="Query"];
  N18 -> Q0;
}
        """
        self.assertEqual(expectation.strip(), observed.strip())

    def test_fix_matrix_sum(self) -> None:
        self.maxDiff = None
        bmg = BMGraphBuilder()
        probs = bmg.add_real_matrix(torch.tensor([[0.75, 0.25], [0.125, 0.875]]))
        tensor_elements = []
        for row in range(0, 2):
            row_node = bmg.add_natural(row)
            row_prob = bmg.add_column_index(probs, row_node)
            for column in range(0, 2):
                col_index = bmg.add_natural(column)
                prob = bmg.add_vector_index(row_prob, col_index)
                bernoulli = bmg.add_bernoulli(prob)
                sample = bmg.add_sample(bernoulli)
                tensor_elements.append(sample)
        matrix = bmg.add_tensor(Size([2, 2]), *tensor_elements)
        sum = bmg.add_matrix_sum(matrix)
        bmg.add_query(sum, _rv_id())
        observed_beanstalk = to_dot(bmg, after_transform=True)
        expected = """
digraph "graph" {
  N00[label="[[0.75,0.25],\\\\n[0.125,0.875]]"];
  N01[label=0];
  N02[label=ColumnIndex];
  N03[label=index];
  N04[label=ToProb];
  N05[label=Bernoulli];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=ToProb];
  N10[label=Bernoulli];
  N11[label=Sample];
  N12[label=ColumnIndex];
  N13[label=index];
  N14[label=ToProb];
  N15[label=Bernoulli];
  N16[label=Sample];
  N17[label=index];
  N18[label=ToProb];
  N19[label=Bernoulli];
  N20[label=Sample];
  N21[label=2];
  N22[label=ToMatrix];
  N23[label=ToRealMatrix];
  N24[label=MatrixSum];
  N25[label=Query];
  N00 -> N02[label=left];
  N00 -> N12[label=left];
  N01 -> N02[label=right];
  N01 -> N03[label=right];
  N01 -> N13[label=right];
  N02 -> N03[label=left];
  N02 -> N08[label=left];
  N03 -> N04[label=operand];
  N04 -> N05[label=probability];
  N05 -> N06[label=operand];
  N06 -> N22[label=0];
  N07 -> N08[label=right];
  N07 -> N12[label=right];
  N07 -> N17[label=right];
  N08 -> N09[label=operand];
  N09 -> N10[label=probability];
  N10 -> N11[label=operand];
  N11 -> N22[label=1];
  N12 -> N13[label=left];
  N12 -> N17[label=left];
  N13 -> N14[label=operand];
  N14 -> N15[label=probability];
  N15 -> N16[label=operand];
  N16 -> N22[label=2];
  N17 -> N18[label=operand];
  N18 -> N19[label=probability];
  N19 -> N20[label=operand];
  N20 -> N22[label=3];
  N21 -> N22[label=columns];
  N21 -> N22[label=rows];
  N22 -> N23[label=operand];
  N23 -> N24[label=operand];
  N24 -> N25[label=operator];
}
        """

        self.assertEqual(observed_beanstalk.strip(), expected.strip())

        generated_graph = to_bmg_graph(bmg)
        observed_bmg = generated_graph.graph.to_dot()
        expectation = """
digraph "graph" {
  N0[label="matrix"];
  N1[label="0"];
  N2[label="ColumnIndex"];
  N3[label="Index"];
  N4[label="ToProb"];
  N5[label="Bernoulli"];
  N6[label="~"];
  N7[label="1"];
  N8[label="Index"];
  N9[label="ToProb"];
  N10[label="Bernoulli"];
  N11[label="~"];
  N12[label="ColumnIndex"];
  N13[label="Index"];
  N14[label="ToProb"];
  N15[label="Bernoulli"];
  N16[label="~"];
  N17[label="Index"];
  N18[label="ToProb"];
  N19[label="Bernoulli"];
  N20[label="~"];
  N21[label="2"];
  N22[label="ToMatrix"];
  N23[label="ToReal"];
  N24[label="MatrixSum"];
  N0 -> N2;
  N0 -> N12;
  N1 -> N2;
  N1 -> N3;
  N1 -> N13;
  N2 -> N3;
  N2 -> N8;
  N3 -> N4;
  N4 -> N5;
  N5 -> N6;
  N6 -> N22;
  N7 -> N8;
  N7 -> N12;
  N7 -> N17;
  N8 -> N9;
  N9 -> N10;
  N10 -> N11;
  N11 -> N22;
  N12 -> N13;
  N12 -> N17;
  N13 -> N14;
  N14 -> N15;
  N15 -> N16;
  N16 -> N22;
  N17 -> N18;
  N18 -> N19;
  N19 -> N20;
  N20 -> N22;
  N21 -> N22;
  N21 -> N22;
  N22 -> N23;
  N23 -> N24;
  Q0[label="Query"];
  N24 -> Q0;
}
"""
        self.assertEqual(expectation.strip(), observed_bmg.strip())

    def test_fix_matrix_exp_log_phi(self) -> None:
        self.maxDiff = None
        bmg = BMGraphBuilder()
        probs = bmg.add_real_matrix(torch.tensor([[0.75, 0.25], [0.125, 0.875]]))
        tensor_elements = []
        for row in range(0, 2):
            row_node = bmg.add_natural(row)
            row_prob = bmg.add_column_index(probs, row_node)
            for column in range(0, 2):
                col_index = bmg.add_natural(column)
                prob = bmg.add_vector_index(row_prob, col_index)
                bernoulli = bmg.add_bernoulli(prob)
                sample = bmg.add_sample(bernoulli)
                tensor_elements.append(sample)
        matrix = bmg.add_tensor(Size([2, 2]), *tensor_elements)
        me = bmg.add_matrix_exp(matrix)
        ml = bmg.add_matrix_log(matrix)
        mp = bmg.add_matrix_phi(matrix)
        bmg.add_query(me, _rv_id())
        bmg.add_query(ml, _rv_id())
        bmg.add_query(mp, _rv_id())
        observed_beanstalk = to_dot(bmg, after_transform=True)
        expectation = """
digraph "graph" {
  N00[label="[[0.75,0.25],\\\\n[0.125,0.875]]"];
  N01[label=0];
  N02[label=ColumnIndex];
  N03[label=index];
  N04[label=ToProb];
  N05[label=Bernoulli];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=ToProb];
  N10[label=Bernoulli];
  N11[label=Sample];
  N12[label=ColumnIndex];
  N13[label=index];
  N14[label=ToProb];
  N15[label=Bernoulli];
  N16[label=Sample];
  N17[label=index];
  N18[label=ToProb];
  N19[label=Bernoulli];
  N20[label=Sample];
  N21[label=2];
  N22[label=ToMatrix];
  N23[label=ToRealMatrix];
  N24[label=MatrixExp];
  N25[label=Query];
  N26[label=ToPosRealMatrix];
  N27[label=MatrixLog];
  N28[label=Query];
  N29[label=MatrixPhi];
  N30[label=Query];
  N00 -> N02[label=left];
  N00 -> N12[label=left];
  N01 -> N02[label=right];
  N01 -> N03[label=right];
  N01 -> N13[label=right];
  N02 -> N03[label=left];
  N02 -> N08[label=left];
  N03 -> N04[label=operand];
  N04 -> N05[label=probability];
  N05 -> N06[label=operand];
  N06 -> N22[label=0];
  N07 -> N08[label=right];
  N07 -> N12[label=right];
  N07 -> N17[label=right];
  N08 -> N09[label=operand];
  N09 -> N10[label=probability];
  N10 -> N11[label=operand];
  N11 -> N22[label=1];
  N12 -> N13[label=left];
  N12 -> N17[label=left];
  N13 -> N14[label=operand];
  N14 -> N15[label=probability];
  N15 -> N16[label=operand];
  N16 -> N22[label=2];
  N17 -> N18[label=operand];
  N18 -> N19[label=probability];
  N19 -> N20[label=operand];
  N20 -> N22[label=3];
  N21 -> N22[label=columns];
  N21 -> N22[label=rows];
  N22 -> N23[label=operand];
  N22 -> N26[label=operand];
  N23 -> N24[label=operand];
  N23 -> N29[label=operand];
  N24 -> N25[label=operator];
  N26 -> N27[label=operand];
  N27 -> N28[label=operator];
  N29 -> N30[label=operator];
}
        """
        self.assertEqual(expectation.strip(), observed_beanstalk.strip())

        generated_graph = to_bmg_graph(bmg)
        observed_bmg = generated_graph.graph.to_dot()
        expectation = """
digraph "graph" {
  N0[label="matrix"];
  N1[label="0"];
  N2[label="ColumnIndex"];
  N3[label="Index"];
  N4[label="ToProb"];
  N5[label="Bernoulli"];
  N6[label="~"];
  N7[label="1"];
  N8[label="Index"];
  N9[label="ToProb"];
  N10[label="Bernoulli"];
  N11[label="~"];
  N12[label="ColumnIndex"];
  N13[label="Index"];
  N14[label="ToProb"];
  N15[label="Bernoulli"];
  N16[label="~"];
  N17[label="Index"];
  N18[label="ToProb"];
  N19[label="Bernoulli"];
  N20[label="~"];
  N21[label="2"];
  N22[label="ToMatrix"];
  N23[label="ToReal"];
  N24[label="MatrixExp"];
  N25[label="ToPosReal"];
  N26[label="MatrixLog"];
  N27[label="MatrixPhi"];
  N0 -> N2;
  N0 -> N12;
  N1 -> N2;
  N1 -> N3;
  N1 -> N13;
  N2 -> N3;
  N2 -> N8;
  N3 -> N4;
  N4 -> N5;
  N5 -> N6;
  N6 -> N22;
  N7 -> N8;
  N7 -> N12;
  N7 -> N17;
  N8 -> N9;
  N9 -> N10;
  N10 -> N11;
  N11 -> N22;
  N12 -> N13;
  N12 -> N17;
  N13 -> N14;
  N14 -> N15;
  N15 -> N16;
  N16 -> N22;
  N17 -> N18;
  N18 -> N19;
  N19 -> N20;
  N20 -> N22;
  N21 -> N22;
  N21 -> N22;
  N22 -> N23;
  N22 -> N25;
  N23 -> N24;
  N23 -> N27;
  N25 -> N26;
  Q0[label="Query"];
  N24 -> Q0;
  Q1[label="Query"];
  N26 -> Q1;
  Q2[label="Query"];
  N27 -> Q2;
}
"""
        self.assertEqual(expectation.strip(), observed_bmg.strip())

    def test_fix_matrix_complement(self) -> None:
        self.maxDiff = None
        bmg = BMGraphBuilder()
        probs = bmg.add_real_matrix(torch.tensor([[0.75, 0.25], [0.125, 0.875]]))
        tensor_elements = []
        # create non constant bool matrix
        for row in range(0, 2):
            row_node = bmg.add_natural(row)
            row_prob = bmg.add_column_index(probs, row_node)
            for column in range(0, 2):
                col_index = bmg.add_natural(column)
                prob = bmg.add_vector_index(row_prob, col_index)
                bernoulli = bmg.add_bernoulli(prob)
                sample = bmg.add_sample(bernoulli)
                tensor_elements.append(sample)
        matrix = bmg.add_tensor(Size([2, 2]), *tensor_elements)

        # create constant matrices
        const_prob_matrix = bmg.add_probability_matrix(
            torch.tensor([[0.25, 0.75], [0.5, 0.5]])
        )
        const_bool_matrix = bmg.add_probability_matrix(
            torch.tensor([[True, False], [False, False]])
        )
        const_prob_simplex = bmg.add_simplex(torch.tensor([0.5, 0.5]))

        mc_non_constant_boolean = bmg.add_matrix_complement(matrix)
        mc_const_prob = bmg.add_matrix_complement(const_prob_matrix)
        mc_const_bool = bmg.add_matrix_complement(const_bool_matrix)
        mc_const_simplex = bmg.add_matrix_complement(const_prob_simplex)

        bmg.add_query(mc_non_constant_boolean, _rv_id())
        bmg.add_query(mc_const_prob, _rv_id())
        bmg.add_query(mc_const_bool, _rv_id())
        bmg.add_query(mc_const_simplex, _rv_id())
        observed_beanstalk = to_dot(bmg, after_transform=True)
        expectation = """
digraph "graph" {
  N00[label="[[0.75,0.25],\\\\n[0.125,0.875]]"];
  N01[label=0];
  N02[label=ColumnIndex];
  N03[label=index];
  N04[label=ToProb];
  N05[label=Bernoulli];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=ToProb];
  N10[label=Bernoulli];
  N11[label=Sample];
  N12[label=ColumnIndex];
  N13[label=index];
  N14[label=ToProb];
  N15[label=Bernoulli];
  N16[label=Sample];
  N17[label=index];
  N18[label=ToProb];
  N19[label=Bernoulli];
  N20[label=Sample];
  N21[label=2];
  N22[label=ToMatrix];
  N23[label=MatrixComplement];
  N24[label=Query];
  N25[label="[[0.25,0.75],\\\\n[0.5,0.5]]"];
  N26[label=MatrixComplement];
  N27[label=Query];
  N28[label="[[True,False],\\\\n[False,False]]"];
  N29[label=MatrixComplement];
  N30[label=Query];
  N31[label="[0.5,0.5]"];
  N32[label=MatrixComplement];
  N33[label=Query];
  N00 -> N02[label=left];
  N00 -> N12[label=left];
  N01 -> N02[label=right];
  N01 -> N03[label=right];
  N01 -> N13[label=right];
  N02 -> N03[label=left];
  N02 -> N08[label=left];
  N03 -> N04[label=operand];
  N04 -> N05[label=probability];
  N05 -> N06[label=operand];
  N06 -> N22[label=0];
  N07 -> N08[label=right];
  N07 -> N12[label=right];
  N07 -> N17[label=right];
  N08 -> N09[label=operand];
  N09 -> N10[label=probability];
  N10 -> N11[label=operand];
  N11 -> N22[label=1];
  N12 -> N13[label=left];
  N12 -> N17[label=left];
  N13 -> N14[label=operand];
  N14 -> N15[label=probability];
  N15 -> N16[label=operand];
  N16 -> N22[label=2];
  N17 -> N18[label=operand];
  N18 -> N19[label=probability];
  N19 -> N20[label=operand];
  N20 -> N22[label=3];
  N21 -> N22[label=columns];
  N21 -> N22[label=rows];
  N22 -> N23[label=operand];
  N23 -> N24[label=operator];
  N25 -> N26[label=operand];
  N26 -> N27[label=operator];
  N28 -> N29[label=operand];
  N29 -> N30[label=operator];
  N31 -> N32[label=operand];
  N32 -> N33[label=operator];
}
        """
        self.assertEqual(expectation.strip(), observed_beanstalk.strip())

        generated_graph = to_bmg_graph(bmg)
        observed_bmg = generated_graph.graph.to_dot()
        expectation = """
digraph "graph" {
  N0[label="matrix"];
  N1[label="0"];
  N2[label="ColumnIndex"];
  N3[label="Index"];
  N4[label="ToProb"];
  N5[label="Bernoulli"];
  N6[label="~"];
  N7[label="1"];
  N8[label="Index"];
  N9[label="ToProb"];
  N10[label="Bernoulli"];
  N11[label="~"];
  N12[label="ColumnIndex"];
  N13[label="Index"];
  N14[label="ToProb"];
  N15[label="Bernoulli"];
  N16[label="~"];
  N17[label="Index"];
  N18[label="ToProb"];
  N19[label="Bernoulli"];
  N20[label="~"];
  N21[label="2"];
  N22[label="ToMatrix"];
  N23[label="MatrixComplement"];
  N24[label="matrix"];
  N25[label="MatrixComplement"];
  N26[label="matrix"];
  N27[label="MatrixComplement"];
  N28[label="simplex"];
  N29[label="MatrixComplement"];
  N0 -> N2;
  N0 -> N12;
  N1 -> N2;
  N1 -> N3;
  N1 -> N13;
  N2 -> N3;
  N2 -> N8;
  N3 -> N4;
  N4 -> N5;
  N5 -> N6;
  N6 -> N22;
  N7 -> N8;
  N7 -> N12;
  N7 -> N17;
  N8 -> N9;
  N9 -> N10;
  N10 -> N11;
  N11 -> N22;
  N12 -> N13;
  N12 -> N17;
  N13 -> N14;
  N14 -> N15;
  N15 -> N16;
  N16 -> N22;
  N17 -> N18;
  N18 -> N19;
  N19 -> N20;
  N20 -> N22;
  N21 -> N22;
  N21 -> N22;
  N22 -> N23;
  N24 -> N25;
  N26 -> N27;
  N28 -> N29;
  Q0[label="Query"];
  N23 -> Q0;
  Q1[label="Query"];
  N25 -> Q1;
  Q2[label="Query"];
  N27 -> Q2;
  Q3[label="Query"];
  N29 -> Q3;
}
"""
        self.assertEqual(expectation.strip(), observed_bmg.strip())

    def test_fix_matrix_log1mexp(self) -> None:
        self.maxDiff = None
        bmg = BMGraphBuilder()
        probs = bmg.add_real_matrix(torch.tensor([[0.75, 0.25], [0.125, 0.875]]))
        tensor_elements = []
        # create non constant real matrix
        for row in range(0, 2):
            row_node = bmg.add_natural(row)
            row_prob = bmg.add_column_index(probs, row_node)
            for column in range(0, 2):
                col_index = bmg.add_natural(column)
                prob = bmg.add_vector_index(row_prob, col_index)
                bern = bmg.add_bernoulli(prob)
                sample = bmg.add_sample(bern)
                neg_two = bmg.add_neg_real(-2.0)
                neg_samples = bmg.add_multiplication(neg_two, sample)
                tensor_elements.append(neg_samples)
        matrix = bmg.add_tensor(Size([2, 2]), *tensor_elements)

        # create constant matrix
        const_neg_real_matrix = bmg.add_neg_real_matrix(
            torch.tensor([[-0.25, -0.75], [-0.5, -0.5]]),
        )

        mlog1mexp_non_constant_real = bmg.add_matrix_log1mexp(matrix)
        mlog1mexp_const_neg_real = bmg.add_matrix_log1mexp(const_neg_real_matrix)

        bmg.add_query(mlog1mexp_non_constant_real, _rv_id())
        bmg.add_query(mlog1mexp_const_neg_real, _rv_id())
        observed_beanstalk = to_dot(bmg, after_transform=True)
        expectation = """
digraph "graph" {
  N00[label="[[0.75,0.25],\\\\n[0.125,0.875]]"];
  N01[label=0];
  N02[label=ColumnIndex];
  N03[label=index];
  N04[label=ToProb];
  N05[label=Bernoulli];
  N06[label=Sample];
  N07[label=1];
  N08[label=index];
  N09[label=ToProb];
  N10[label=Bernoulli];
  N11[label=Sample];
  N12[label=ColumnIndex];
  N13[label=index];
  N14[label=ToProb];
  N15[label=Bernoulli];
  N16[label=Sample];
  N17[label=index];
  N18[label=ToProb];
  N19[label=Bernoulli];
  N20[label=Sample];
  N21[label=2];
  N22[label=-2.0];
  N23[label=0.0];
  N24[label=if];
  N25[label=if];
  N26[label=if];
  N27[label=if];
  N28[label=ToMatrix];
  N29[label=MatrixLog1mexp];
  N30[label=Query];
  N31[label="[[-0.25,-0.75],\\\\n[-0.5,-0.5]]"];
  N32[label=MatrixLog1mexp];
  N33[label=Query];
  N00 -> N02[label=left];
  N00 -> N12[label=left];
  N01 -> N02[label=right];
  N01 -> N03[label=right];
  N01 -> N13[label=right];
  N02 -> N03[label=left];
  N02 -> N08[label=left];
  N03 -> N04[label=operand];
  N04 -> N05[label=probability];
  N05 -> N06[label=operand];
  N06 -> N24[label=condition];
  N07 -> N08[label=right];
  N07 -> N12[label=right];
  N07 -> N17[label=right];
  N08 -> N09[label=operand];
  N09 -> N10[label=probability];
  N10 -> N11[label=operand];
  N11 -> N25[label=condition];
  N12 -> N13[label=left];
  N12 -> N17[label=left];
  N13 -> N14[label=operand];
  N14 -> N15[label=probability];
  N15 -> N16[label=operand];
  N16 -> N26[label=condition];
  N17 -> N18[label=operand];
  N18 -> N19[label=probability];
  N19 -> N20[label=operand];
  N20 -> N27[label=condition];
  N21 -> N28[label=columns];
  N21 -> N28[label=rows];
  N22 -> N24[label=consequence];
  N22 -> N25[label=consequence];
  N22 -> N26[label=consequence];
  N22 -> N27[label=consequence];
  N23 -> N24[label=alternative];
  N23 -> N25[label=alternative];
  N23 -> N26[label=alternative];
  N23 -> N27[label=alternative];
  N24 -> N28[label=0];
  N25 -> N28[label=1];
  N26 -> N28[label=2];
  N27 -> N28[label=3];
  N28 -> N29[label=operand];
  N29 -> N30[label=operator];
  N31 -> N32[label=operand];
  N32 -> N33[label=operator];
}
        """
        self.assertEqual(expectation.strip(), observed_beanstalk.strip())

        generated_graph = to_bmg_graph(bmg)
        observed_bmg = generated_graph.graph.to_dot()
        expectation = """
digraph "graph" {
  N0[label="matrix"];
  N1[label="0"];
  N2[label="ColumnIndex"];
  N3[label="Index"];
  N4[label="ToProb"];
  N5[label="Bernoulli"];
  N6[label="~"];
  N7[label="1"];
  N8[label="Index"];
  N9[label="ToProb"];
  N10[label="Bernoulli"];
  N11[label="~"];
  N12[label="ColumnIndex"];
  N13[label="Index"];
  N14[label="ToProb"];
  N15[label="Bernoulli"];
  N16[label="~"];
  N17[label="Index"];
  N18[label="ToProb"];
  N19[label="Bernoulli"];
  N20[label="~"];
  N21[label="2"];
  N22[label="-2"];
  N23[label="-1e-10"];
  N24[label="IfThenElse"];
  N25[label="IfThenElse"];
  N26[label="IfThenElse"];
  N27[label="IfThenElse"];
  N28[label="ToMatrix"];
  N29[label="MatrixLog1mexp"];
  N30[label="matrix"];
  N31[label="MatrixLog1mexp"];
  N0 -> N2;
  N0 -> N12;
  N1 -> N2;
  N1 -> N3;
  N1 -> N13;
  N2 -> N3;
  N2 -> N8;
  N3 -> N4;
  N4 -> N5;
  N5 -> N6;
  N6 -> N24;
  N7 -> N8;
  N7 -> N12;
  N7 -> N17;
  N8 -> N9;
  N9 -> N10;
  N10 -> N11;
  N11 -> N25;
  N12 -> N13;
  N12 -> N17;
  N13 -> N14;
  N14 -> N15;
  N15 -> N16;
  N16 -> N26;
  N17 -> N18;
  N18 -> N19;
  N19 -> N20;
  N20 -> N27;
  N21 -> N28;
  N21 -> N28;
  N22 -> N24;
  N22 -> N25;
  N22 -> N26;
  N22 -> N27;
  N23 -> N24;
  N23 -> N25;
  N23 -> N26;
  N23 -> N27;
  N24 -> N28;
  N25 -> N28;
  N26 -> N28;
  N27 -> N28;
  N28 -> N29;
  N30 -> N31;
  Q0[label="Query"];
  N29 -> Q0;
  Q1[label="Query"];
  N31 -> Q1;
}
"""
        self.assertEqual(expectation.strip(), observed_bmg.strip())
