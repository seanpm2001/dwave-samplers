import itertools
import unittest

import dimod
import numpy as np

import savanna


class TestLogPartitionBQM(unittest.TestCase):
    def test_three_path_bqm(self):
        bqm = dimod.BinaryQuadraticModel.empty(dimod.SPIN)

        bqm.add_interaction(0, 1, .69)
        bqm.add_interaction(1, 2, +1.0)
        bqm.add_interaction(2, 0, .5)
        bqm.add_offset(0)

        pos = {0: (0, 0), 1: (1, 0), 2: (0, 1)}

        logZ = savanna.log_partition_bqm(bqm, pos)

        en = list(-bqm.energy(dict(zip(range(len(bqm)), config)))
                  for config in itertools.product((-1, 1), repeat=len(bqm)))

        self.assertAlmostEqual(np.log(np.sum(np.exp(en))), logZ)

    def test_four_path_bqm(self):
        bqm = dimod.BinaryQuadraticModel.empty(dimod.SPIN)

        bqm.add_interaction(0, 1, +1.0)
        bqm.add_interaction(1, 2, +1.0)
        bqm.add_interaction(2, 3, +1.0)
        bqm.add_interaction(0, 3, +1.0)
        bqm.add_offset(1.8)

        pos = {0: (+1, +1),
               1: (-1, +1),
               2: (-1, -1),
               3: (+1, -1)}

        logZ = savanna.log_partition_bqm(bqm, pos)

        en = list(-bqm.energy(dict(zip(range(len(bqm)), config)))
                  for config in itertools.product((-1, 1), repeat=len(bqm)))

        self.assertAlmostEqual(np.log(np.sum(np.exp(en))), logZ)

    def test_FrustTriangleL39(self):
        from tests.data import bqm_L39, pos_L39

        logZ = savanna.log_partition_bqm(bqm_L39, pos_L39)

    def test_square_with_chord(self):
        bqm = dimod.BinaryQuadraticModel.from_ising({0: -0.0, 1: -0.0, 2: -0.0, 3: -0.0},
                                                    {(1, 2): 2, (0, 1): 1, (1, 3): 1, (2, 3): 1, (0, 2): 1})
        pos = {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)}

        logZ = savanna.log_partition_bqm(bqm, pos)

        en = []
        for config in itertools.product((-1, 1), repeat=len(bqm)):
            sample = dict(zip(range(len(bqm)), config))
            en.append(bqm.energy(sample))

        self.assertAlmostEqual(np.log(np.sum(np.exp(-1*np.asarray(en)))), logZ)

    def test_square_with_chord_2(self):
        bqm = dimod.BinaryQuadraticModel({0: -0.0, 1: -0.0, 2: -0.0, 3: -0.0},
                                         {(1, 2): 200, (0, 1): 100, (1, 3): 100, (2, 3): 100, (0, 2): 100},
                                         -0.0, dimod.SPIN)

        pos = {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)}

        logZ = savanna.log_partition_bqm(bqm, pos)

        en = []
        for config in itertools.product((-1, 1), repeat=len(bqm)):
            sample = dict(zip(range(len(bqm)), config))
            en.append(bqm.energy(sample))

        self.assertAlmostEqual(np.log(np.sum(np.exp(-1*np.asarray(en)))), logZ)

    def test_orderings(self):
        bqm = dimod.BinaryQuadraticModel({0: -0.0, 1: -0.0, 2: -0.0, 3: -0.0},
                                         {(1, 2): 200, (0, 1): 100, (1, 3): 100, (2, 3): 100, (0, 2): 100},
                                         -0.0, dimod.SPIN)

        pos = {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1)}

        en = []
        for config in itertools.product((-1, 1), repeat=len(bqm)):
            sample = dict(zip(range(len(bqm)), config))
            en.append(bqm.energy(sample))
        true_logZ = np.log(np.sum(np.exp(-1*np.asarray(en))))

        for order in itertools.permutations(bqm, 4):
            new_bqm = dimod.BinaryQuadraticModel.empty(dimod.SPIN)
            for v in order:
                new_bqm.add_variable(v, bqm.linear[v])
            for u, v in bqm.quadratic:
                new_bqm.add_interaction(u, v, bqm.quadratic[(u, v)])

            assert bqm == new_bqm

            new_pos = {v: pos[v] for v in order}

            # print(savanna.log_partition_bqm(bqm, new_pos), true_logZ)
            self.assertAlmostEqual(savanna.log_partition_bqm(new_bqm, new_pos), true_logZ)
