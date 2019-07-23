# Copyright 2019 D-Wave Systems Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A dimod sampler that uses the steepest gradient descent."""

from __future__ import division, absolute_import

from numbers import Integral
from random import randint

import dimod
import numpy as np

from greedy.descent import steepest_gradient_descent


__all__ = ["SteepestDescentSolver", "SteepestDescentSampler"]


class SteepestDescentSolver(dimod.Sampler):
    """Steepest gradient descent solver/sampler.

    Also aliased as :class:`.SteepestDescentSampler`.

    Examples:
        This example solves a simple Ising problem.

        >>> import greedy
        ...
        >>> sampler = greedy.SteepestDescentSampler()
        >>> samples = sample.sample_ising({}, {'ab': 1, 'bc': 1, 'ca': 1})
        ...
        >>> print(samples)
        ... # TODO

    """

    parameters = None
    properties = None

    def __init__(self):
        self.parameters = {
            'num_reads': [],
            'initial_states': [],
            'initial_states_generator': ['initial_states_generators'],
            'seed': []
        }
        self.properties = {
            'initial_states_generators': ('none', 'tile', 'random')
        }

    def sample(self, bqm, num_reads=None, initial_states=None,
               initial_states_generator="random", seed=None, **kwargs):
        """Sample from a binary quadratic model using an implemented sample method.

        Args:
            bqm (:class:`~dimod.BinaryQuadraticModel`):
                The binary quadratic model to be sampled.

            num_reads (int, optional, default=len(initial_states) or 1):
                Number of reads. Each read is generated by one run of the steepest
                descent algorithm. If `num_reads` is not explicitly given, it is
                selected to match the number of initial states given. If initial states
                are not provided, only one read is performed.

            initial_states (:class:`~dimod.SampleSet`, optional, default=None):
                One or more samples, each defining an initial state for all the
                problem variables. Initial states are given one per read, but
                if fewer than `num_reads` initial states are defined, additional
                values are generated as specified by `initial_states_generator`.

            initial_states_generator ({'none', 'tile', 'random'}, optional, default='random'):
                Defines the expansion of `initial_states` if fewer than
                `num_reads` are specified:

                * "none":
                    If the number of initial states specified is smaller than
                    `num_reads`, raises ValueError.

                * "tile":
                    Reuses the specified initial states if fewer than `num_reads`
                    or truncates if greater.

                * "random":
                    Expands the specified initial states with randomly generated
                    states if fewer than `num_reads` or truncates if greater.

            seed (int (32-bit unsigned integer), optional):
                Seed to use for the PRNG. Specifying a particular seed with a
                constant set of parameters produces identical results. If not
                provided, a random seed is chosen.

        Returns:
            :class:`dimod.SampleSet`: A `dimod` :class:`~dimod.SampleSet` object.

        Examples:
            This example samples a simple two-variable Ising model.

            >>> import dimod
            >>> bqm = dimod.BQM.from_ising({}, {'ab': 1})

            >>> import greedy
            >>> sampler = greedy.SteepestDescentSampler()

            >>> samples = sampler.sample(bqm)
            >>> samples.record[0].energy
            -1.0

        """

        num_variables = len(bqm)

        # convert bqm to an index-labelled one
        if all(v in bqm.linear for v in range(num_variables)):
            _bqm = bqm
            use_label_map = False
        else:
            try:
                inverse_mapping = dict(enumerate(sorted(bqm.linear)))
            except TypeError:
                # in python3 unlike types cannot be sorted
                inverse_mapping = dict(enumerate(bqm.linear))
            mapping = {v: i for i, v in inverse_mapping.items()}

            _bqm = bqm.relabel_variables(mapping, inplace=False)
            use_label_map = True

        # validate/initialize initial_states
        if initial_states is None:
            initial_states = dimod.SampleSet.from_samples(
                (np.empty((0, num_variables)), bqm.variables),
                energy=0, vartype=bqm.vartype)

        if not isinstance(initial_states, dimod.SampleSet):
            raise TypeError("'initial_states' is not 'dimod.SampleSet' instance")

        # validate num_reads and/or infer them from initial_states
        if num_reads is None:
            num_reads = len(initial_states) or 1
        if not isinstance(num_reads, Integral):
            raise TypeError("'num_reads' should be a positive integer")
        if num_reads < 1:
            raise ValueError("'num_reads' should be a positive integer")

        # validate/generate seed
        if not (seed is None or isinstance(seed, Integral)):
            raise TypeError("'seed' should be None or a positive integer")
        if isinstance(seed, Integral) and not 0 <= seed <= 2**32 - 1:
            raise ValueError("'seed' should be an integer between 0 and 2**32 - 1 inclusive")

        if seed is None:
            # pick a random seed
            seed = randint(0, 2**32 - 1)

        # get the Ising linear biases
        linear = _bqm.spin.linear
        linear_biases = [linear[v] for v in range(num_variables)]

        quadratic = _bqm.spin.quadratic
        coupler_starts, coupler_ends, coupler_weights = [], [], []
        if len(quadratic) > 0:
            couplers, coupler_weights = zip(*quadratic.items())
            couplers = map(lambda c: (c[0], c[1]), couplers)
            coupler_starts, coupler_ends = zip(*couplers)

        # initial states generators
        _generators = {
            'none': self._none_generator,
            'tile': self._tile_generator,
            'random': self._random_generator
        }

        if initial_states_generator not in _generators:
            raise ValueError("unknown value for 'initial_states_generator'")

        # unpack initial_states from sampleset to numpy array, label map and vartype
        initial_states_array = initial_states.record.sample
        init_label_map = dict(map(reversed, enumerate(initial_states.variables)))
        init_vartype = initial_states.vartype

        if set(init_label_map) ^ bqm.variables:
            raise ValueError("mismatch between variables in 'initial_states' and 'bqm'")

        # reorder initial states array according to label map
        identity = lambda i: i
        get_label = inverse_mapping.get if use_label_map else identity
        ordered_labels = [init_label_map[get_label(i)] for i in range(num_variables)]
        initial_states_array = initial_states_array[:, ordered_labels]

        numpy_initial_states = np.ascontiguousarray(initial_states_array, dtype=np.int8)

        # convert to ising, if provided in binary
        if init_vartype == dimod.BINARY:
            numpy_initial_states = 2 * numpy_initial_states - 1
        elif init_vartype != dimod.SPIN:
            raise TypeError("unsupported vartype")  # pragma: no cover

        # extrapolate and/or truncate initial states, if necessary
        extrapolate = _generators[initial_states_generator]
        numpy_initial_states = extrapolate(numpy_initial_states, num_reads, num_variables, seed)
        numpy_initial_states = self._truncate_filter(numpy_initial_states, num_reads)

        # run the steepest descent
        samples, energies = steepest_gradient_descent(
            num_reads,
            linear_biases, coupler_starts, coupler_ends, coupler_weights,
            numpy_initial_states)

        off = _bqm.spin.offset
        result = dimod.SampleSet.from_samples(
            samples,
            energy=energies+off,
            vartype=dimod.SPIN
        )

        result.change_vartype(_bqm.vartype, inplace=True)
        if use_label_map:
            result.relabel_variables(inverse_mapping, inplace=True)

        return result

    @staticmethod
    def _none_generator(initial_states, num_reads, *args, **kwargs):
        if len(initial_states) < num_reads:
            raise ValueError("insufficient number of initial states given")
        return initial_states

    @staticmethod
    def _tile_generator(initial_states, num_reads, *args, **kwargs):
        if len(initial_states) < 1:
            raise ValueError("cannot tile an empty sample set of initial states")

        if len(initial_states) >= num_reads:
            return initial_states

        reps, rem = divmod(num_reads, len(initial_states))

        initial_states = np.tile(initial_states, (reps, 1))
        initial_states = np.vstack((initial_states, initial_states[:rem]))

        return initial_states

    @staticmethod
    def _random_generator(initial_states, num_reads, num_variables, seed):
        rem = max(0, num_reads - len(initial_states))

        np_rand = np.random.RandomState(seed % 2**32)
        random_states = 2 * np_rand.randint(2, size=(rem, num_variables)).astype(np.int8) - 1

        # handle zero-length array of input states
        if len(initial_states):
            initial_states = np.vstack((initial_states, random_states))
        else:
            initial_states = random_states

        return initial_states

    @staticmethod
    def _truncate_filter(initial_states, num_reads):
        if len(initial_states) > num_reads:
            initial_states = initial_states[:num_reads]
        return initial_states


SteepestDescentSampler = SteepestDescentSolver
