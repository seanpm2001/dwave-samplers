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

import dimod
import greedy


class SteepestDescentSimple(object):
    params = [1, 1000, 1000000]
    param_names = ['num_reads']

    def setup(self, num_reads):
        self.sampler = greedy.SteepestDescentSampler()
        self.h = {0: 2, 1: 2}
        self.J = {(0, 1): -1}

    def time_single_flip(self, num_reads):
        self.sampler.sample_ising(self.h, self.J, num_reads=num_reads, seed=0)


class SteepestDescentComplete(object):
    params = ([100, 1000, 2000], [1, 10])
    param_names = ['graph_size', 'num_reads']
    timeout = 300

    def setup(self, graph_size, num_reads):
        self.sampler = greedy.SteepestDescentSampler()
        self.bqm = dimod.generators.random.ran_r(r=1, graph=graph_size, seed=0)

    def time_ran1(self, graph_size, num_reads):
        self.sampler.sample(self.bqm, num_reads=num_reads, seed=0)
