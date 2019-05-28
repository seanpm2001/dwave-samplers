# Copyright 2018 D-Wave Systems Inc.
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

"""A dimod sampler_ that uses the MST2 multistart tabu search algorithm."""

from __future__ import division

import random
import warnings
import itertools
from functools import partial

import numpy
import dimod

from tabu import TabuSearch


class TabuSampler(dimod.Sampler):
    """A tabu-search sampler.

    Examples:
        This example solves a two-variable Ising model.

        >>> from tabu import TabuSampler
        >>> samples = TabuSampler().sample_ising({'a': -0.5, 'b': 1.0}, {'ab': -1})
        >>> list(samples.data()) # doctest: +SKIP
        [Sample(sample={'a': -1, 'b': -1}, energy=-1.5, num_occurrences=1)]
        >>> samples.first.energy
        -1.5

    """

    properties = None
    parameters = None

    def __init__(self):
        self.parameters = {'tenure': [],
                           'scale_factor': [],
                           'timeout': [],
                           'num_reads': [],
                           'init_solution': []}
        self.properties = {}

    def sample(self, bqm, initial_states=None, initial_states_generator='random',
               num_reads=1, tenure=None, timeout=20, scale_factor=1, **kwargs):
        """Run Tabu search on a given binary quadratic model.

        Args:
            bqm (:class:`~dimod.BinaryQuadraticModel`):
                The binary quadratic model (BQM) to be sampled.

            initial_states (:class:`~dimod.SampleSet`, optional, default=None):
                One or more samples that define the initial states, one per read.
                If the length of `initial_states` is shorter than `num_reads`,
                they will be expanded according to `initial_states_generator`.

            initial_states_generator (str, 'none'/'tile'/'random', optional):
                Defines a way `initial_states` of length differing from `num_reads`
                get used:

                * "none":
                    length must be greater or equal to `num_reads`, otherwise
                    `ValueError` is raised
                * "tile":
                    `initial_states` shorter than `num_reads` are repeated, up to
                    `num_reads` in length. Longer list of states is truncated.
                * "random":
                    similar to `tile`, but missing states are selected from a
                    uniform random state generator.

            num_reads (int, optional, default=1):
                Number of reads. Each run of the tabu algorithm generates a sample.

            tenure (int, optional):
                Tabu tenure, which is the length of the tabu list, or number of recently
                explored solutions kept in memory.
                Default is a quarter of the number of problem variables up to
                a maximum value of 20.

            timeout (int, optional):
                Total running time in milliseconds.

            scale_factor (number, optional):
                Scaling factor for linear and quadratic biases in the BQM. Internally, the BQM is
                converted to a QUBO matrix, and elements are stored as long ints
                using ``internal_q = long int (q * scale_factor)``.

            init_solution (:class:`~dimod.SampleSet`, optional):
                Deprecated. Alias for `initial_states`.

        Returns:
            :obj:`~dimod.SampleSet`: A `dimod` :obj:`.~dimod.SampleSet` object.

        Examples:
            This example samples a simple two-variable Ising model.

            >>> import dimod
            >>> bqm = dimod.BQM.from_ising({}, {'ab': 1})

            >>> import tabu
            >>> sampler = tabu.TabuSampler()

            >>> samples = sampler.sample(bqm)
            >>> samples.record[0].energy
            -1.0
        """

        if not isinstance(bqm, dimod.BinaryQuadraticModel):
            raise TypeError("'bqm' should be a 'dimod.BinaryQuadraticModel' instance")
        if not bqm:
            return dimod.SampleSet.from_samples([], energy=0, vartype=bqm.vartype)

        if tenure is None:
            tenure = max(min(20, len(bqm) // 4), 0)
        if not isinstance(tenure, int):
            raise TypeError("'tenure' should be an integer in range [0, num_vars - 1]")
        if not 0 <= tenure < len(bqm):
            raise ValueError("'tenure' should be an integer in range [0, num_vars - 1]")

        if not isinstance(num_reads, int):
            raise TypeError("'num_reads' should be a positive integer")
        if num_reads < 1:
            raise ValueError("'num_reads' should be a positive integer")

        if 'init_solution' in kwargs:
            warnings.warn(
                "'init_solution' is deprecated in favor of 'initial_states'.",
                DeprecationWarning)
            initial_states = kwargs.pop('init_solution')

        if initial_states is None:
            initial_states = dimod.SampleSet.from_samples([], vartype=bqm.vartype, energy=0)

        if not isinstance(initial_states, dimod.SampleSet):
            raise TypeError("'initial_states' is not 'dimod.SampleSet' instance")

        _generators = {
            'none': self._none_generator,
            'tile': self._tile_generator,
            'random': partial(self._random_generator, bqm=bqm.binary)
        }

        if len(initial_states) < num_reads and initial_states_generator == 'none':
            raise ValueError("insufficient 'initial_states' given")

        if len(initial_states) < 1 and initial_states_generator == 'tile':
            raise ValueError("cannot tile an empty sample set")

        if initial_states and initial_states.variables ^ bqm.variables:
            raise ValueError("mismatch between variables in 'initial_states' and 'bqm'")

        if initial_states_generator not in _generators:
            raise ValueError("unknown value for 'initial_states_generator'")

        binary_initial_states = initial_states.change_vartype(dimod.BINARY, inplace=False)
        init_sample_generator = _generators[initial_states_generator](binary_initial_states)

        qubo = self._bqm_to_tabu_qubo(bqm.binary)

        # run Tabu search
        samples = []
        energies = []
        for _ in range(num_reads):
            init_solution = self._bqm_sample_to_tabu_solution(next(init_sample_generator))
            r = TabuSearch(qubo, init_solution, tenure, scale_factor, timeout)
            sample = self._tabu_solution_to_bqm_sample(list(r.bestSolution()), bqm.binary)
            energy = bqm.binary.energy(sample)
            samples.append(sample)
            energies.append(energy)

        response = dimod.SampleSet.from_samples(
            samples, energy=energies, vartype=dimod.BINARY)
        response.change_vartype(bqm.vartype, inplace=True)
        return response

    @staticmethod
    def _none_generator(sampleset):
        for sample in sampleset:
            yield sample
        raise ValueError("sample set of initial states depleted")

    @staticmethod
    def _tile_generator(sampleset):
        for sample in itertools.cycle(sampleset):
            yield sample

    @staticmethod
    def _random_generator(sampleset, bqm):
        # yield from requires py3
        for sample in sampleset:
            yield sample
        while True:
            yield TabuSampler._random_sample(bqm)

    @staticmethod
    def _bqm_to_tabu_qubo(bqm):
        # Note: normally, conversion would be: `ud + ud.T - numpy.diag(numpy.diag(ud))`,
        # but the Tabu solver we're using requires slightly different qubo matrix.
        varorder = sorted(list(bqm.adj.keys()))
        ud = 0.5 * bqm.to_numpy_matrix(varorder)
        symm = ud + ud.T
        qubo = symm.tolist()
        return qubo

    @staticmethod
    def _bqm_sample_to_tabu_solution(sample):
        _, values = zip(*sorted(TabuSampler._sample_as_dict(sample).items()))
        return list(map(int, values))

    @staticmethod
    def _tabu_solution_to_bqm_sample(solution, bqm):
        varorder = sorted(list(bqm.adj.keys()))
        assert len(solution) == len(varorder)
        return dict(zip(varorder, solution))

    @staticmethod
    def _sample_as_dict(sample):
        """Convert list-like ``sample`` (list/dict/dimod.SampleView),
        ``list: var``, to ``map: idx -> var``.
        """
        if isinstance(sample, dict):
            return sample
        if isinstance(sample, (list, numpy.ndarray)):
            sample = enumerate(sample)
        return dict(sample)

    @staticmethod
    def _random_sample(bqm):
        values = list(bqm.vartype.value)
        return {i: random.choice(values) for i in bqm.variables}


if __name__ == "__main__":
    from pprint import pprint

    print("TabuSampler:")
    bqm = dimod.BinaryQuadraticModel(
        {'a': 0.0, 'b': -1.0, 'c': 0.5},
        {('a', 'b'): -1.0, ('b', 'c'): 1.5},
        offset=0.0, vartype=dimod.BINARY)
    response = TabuSampler().sample(bqm, num_reads=10)
    pprint(list(response.data()))

    print("ExactSolver:")
    response = dimod.ExactSolver().sample(bqm)
    pprint(list(response.data(sorted_by='energy')))
