# coding=utf-8
# Copyright 2020 The TF-Agents Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Class implementation of Stationary Stochastic Python Bandit environment."""

from typing import Optional, Callable, Sequence, Text

import gin
import numpy as np

from tf_agents.bandits.environments import bandit_py_environment
from tf_agents.bandits.specs import utils as bandits_spec_utils
from tf_agents.specs import array_spec
from tf_agents.typing import types


@gin.configurable
class StationaryStochasticPyEnvironment(
    bandit_py_environment.BanditPyEnvironment):
  """Implements Stationary Stochastic Bandit environments."""

  def __init__(
      self,
      context_sampling_fn: Callable[[], np.ndarray],
      reward_fns: Sequence[Callable[[np.ndarray], Sequence[float]]],
      constraint_fns: Optional[
          Sequence[Callable[[np.ndarray], Sequence[float]]]] = None,
      batch_size: Optional[int] = 1,
      name: Optional[Text] = 'stationary_stochastic'):
    """Initializes a Stationary Stochastic Bandit environment.

    In each round, context is generated by context_sampling_fn, this context is
    passed through a reward_function for each arm.

    Example:
      def context_sampling_fn():
        return np.random.randint(0, 10, [1, 2])  # 2-dim ints between 0 and 10

      def reward_fn1(x):
        return x[0]
      def reward_fn2(x):
        return x[1]
      reward_fns = [reward_fn1, reward_fn2]  # Two arms

      env = StationaryStochasticPyEnvironment(context_sampling_fn,
                                              reward_fns)

    Args:
      context_sampling_fn: A function that outputs a random 2d array or list of
        ints or floats, where the first dimension is batch size.
      reward_fns: A function that generates a (perhaps non-scalar) reward when
        called with an observation.
      constraint_fns: A function that generates a (perhaps non-scalar)
        constraint metric when called with an observation.
      batch_size: The batch size. Must match the outer dimension of the output
        of context_sampling_fn.
      name: The name of this environment instance.
    """
    self._context_sampling_fn = context_sampling_fn
    self._reward_fns = reward_fns
    self._num_actions = len(reward_fns)
    self._constraint_fns = constraint_fns
    self._batch_size = batch_size

    action_spec = array_spec.BoundedArraySpec(
        shape=(),
        dtype=np.int32,
        minimum=0,
        maximum=self._num_actions - 1,
        name='action')

    example_observation = self._context_sampling_fn()
    observation_spec = array_spec.ArraySpec.from_array(example_observation[0])
    if example_observation.shape[0] != batch_size:
      raise ValueError(
          'The outer dimension of the observations should match the batch size.'
      )

    # Figure out the reward spec.
    # If we have constraints, the reward_spec will be a nested dict with keys:
    # 'reward' and 'constraint' (defined in tf_agents.bandits.specs.utils).
    example_reward = np.asarray(reward_fns[0](example_observation[0]))
    reward_spec = array_spec.ArraySpec(
        example_reward.shape, np.float32, name='reward')
    if self._constraint_fns is not None:
      example_constraint = np.asarray(constraint_fns[0](example_observation[0]))
      constraint_spec = array_spec.ArraySpec(
          example_constraint.shape, np.float32, name='constraint')
      reward_spec = {
          bandits_spec_utils.REWARD_SPEC_KEY: reward_spec,
          bandits_spec_utils.CONSTRAINTS_SPEC_KEY: constraint_spec
      }

    super(StationaryStochasticPyEnvironment, self).__init__(
        observation_spec, action_spec, reward_spec, name=name)

  def batched(self) -> bool:
    return True

  @property
  def batch_size(self) -> int:
    return self._batch_size

  def _observe(self) -> types.NestedArray:
    self._observation = self._context_sampling_fn()
    return self._observation

  def _apply_action(self, action: types.NestedArray) -> types.NestedArray:
    if len(action) != self.batch_size:
      raise ValueError('Number of actions must match batch size.')
    reward = np.stack(
        [self._reward_fns[a](o) for a, o in zip(action, self._observation)])
    if self._constraint_fns is not None:
      constraint = np.stack(
          [self._constraint_fns[a](o) for a, o in zip(action,
                                                      self._observation)])
      reward = {
          bandits_spec_utils.REWARD_SPEC_KEY: reward,
          bandits_spec_utils.CONSTRAINTS_SPEC_KEY: constraint
      }
    return reward
