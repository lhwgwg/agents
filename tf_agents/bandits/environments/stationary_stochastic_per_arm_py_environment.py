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

"""Stationary Stochastic Python Bandit environment with per-arm features."""

from typing import Optional, Callable, Sequence, Text

import gin
import numpy as np

from tf_agents.bandits.environments import bandit_py_environment
from tf_agents.bandits.specs import utils as bandit_spec_utils
from tf_agents.specs import array_spec
from tf_agents.typing import types

GLOBAL_KEY = bandit_spec_utils.GLOBAL_FEATURE_KEY
PER_ARM_KEY = bandit_spec_utils.PER_ARM_FEATURE_KEY
NUM_ACTIONS_KEY = bandit_spec_utils.NUM_ACTIONS_FEATURE_KEY


@gin.configurable
class StationaryStochasticPerArmPyEnvironment(
    bandit_py_environment.BanditPyEnvironment):
  """Stationary Stochastic Bandit environment with per-arm features."""

  def __init__(self,
               global_context_sampling_fn: Callable[[], types.Array],
               arm_context_sampling_fn: Callable[[], types.Array],
               max_num_actions: int,
               reward_fn: Callable[[types.Array], Sequence[float]],
               num_actions_fn: Optional[Callable[[], int]] = None,
               batch_size: Optional[int] = 1,
               name: Optional[Text] = 'stationary_stochastic_per_arm'):
    """Initializes the environment.

    In each round, global context is generated by global_context_sampling_fn,
    per-arm contexts are generated by arm_context_sampling_fn. The reward_fn
    function takes the concatenation of a global and a per-arm feature, and
    outputs a possibly random reward.
    In case `num_action_fn` is specified, the number of actions will be dynamic
    and a `num_actions` feature key indicates the number of actions in any given
    sample.

    Example:
      def global_context_sampling_fn():
        return np.random.randint(0, 10, [2])  # 2-dimensional global features.

      def arm_context_sampling_fn():
        return np.random.randint(-3, 4, [3])  # 3-dimensional arm features.

      def reward_fn(x):
        return sum(x)

      def num_actions_fn():
        return np.random.randint(2, 6)

      env = StationaryStochasticPerArmPyEnvironment(global_context_sampling_fn,
                                                    arm_context_sampling_fn,
                                                    5,
                                                    reward_fn,
                                                    num_actions_fn)

    Args:
      global_context_sampling_fn: A function that outputs a random 1d array or
        list of ints or floats. This output is the global context. Its shape and
        type must be consistent across calls.
      arm_context_sampling_fn: A function that outputs a random 1 array or list
        of ints or floats (same type as the output of
        `global_context_sampling_fn`). This output is the per-arm context. Its
        shape must be consistent across calls.
      max_num_actions: (int) the maximum number of actions in every sample. If
        `num_actions_fn` is not set, this many actions are available in every
        time step.
      reward_fn: A function that generates a reward when called with an
        observation.
      num_actions_fn: If set, it should be a function that outputs a single
        integer specifying the number of actions for a given time step. The
        value output by this function will be capped between 1 and
        `max_num_actions`. The number of actions will be encoded in the
        observation by the feature key `num_actions`.
      batch_size: The batch size.
      name: The name of this environment instance.
    """
    self._global_context_sampling_fn = global_context_sampling_fn
    self._arm_context_sampling_fn = arm_context_sampling_fn
    self._max_num_actions = max_num_actions
    self._reward_fn = reward_fn
    self._batch_size = batch_size
    self._num_actions_fn = num_actions_fn

    observation_spec = {
        GLOBAL_KEY:
            array_spec.ArraySpec.from_array(global_context_sampling_fn()),
        PER_ARM_KEY:
            array_spec.add_outer_dims_nest(
                array_spec.ArraySpec.from_array(arm_context_sampling_fn()),
                (max_num_actions,))
    }
    if self._num_actions_fn is not None:
      num_actions_spec = array_spec.BoundedArraySpec(
          shape=(),
          dtype=np.dtype(type(self._num_actions_fn())),
          minimum=1,
          maximum=max_num_actions)
      observation_spec.update({NUM_ACTIONS_KEY: num_actions_spec})

    action_spec = array_spec.BoundedArraySpec(
        shape=(),
        dtype=np.int32,
        minimum=0,
        maximum=max_num_actions - 1,
        name='action')

    super(StationaryStochasticPerArmPyEnvironment,
          self).__init__(observation_spec, action_spec, name=name)

  def batched(self) -> bool:
    return True

  @property
  def batch_size(self) -> int:
    return self._batch_size

  def _observe(self) -> types.NestedArray:
    global_obs = np.stack(
        [self._global_context_sampling_fn() for _ in range(self._batch_size)])
    arm_obs = np.reshape([
        self._arm_context_sampling_fn()
        for _ in range(self._batch_size * self._max_num_actions)
    ], (self._batch_size, self._max_num_actions, -1))
    self._observation = {GLOBAL_KEY: global_obs, PER_ARM_KEY: arm_obs}

    if self._num_actions_fn:
      num_actions = [self._num_actions_fn() for _ in range(self._batch_size)]
      num_actions = np.maximum(num_actions, 1)
      num_actions = np.minimum(num_actions, self._max_num_actions)
      self._observation.update({NUM_ACTIONS_KEY: num_actions})
    return self._observation

  def _apply_action(self, action: np.ndarray) -> types.Array:
    if action.shape[0] != self.batch_size:
      raise ValueError('Number of actions must match batch size.')
    global_obs = self._observation[GLOBAL_KEY]
    batch_size_range = range(self.batch_size)
    arm_obs = self._observation[PER_ARM_KEY][batch_size_range, action, :]
    reward = np.stack([
        self._reward_fn(np.concatenate((global_obs[b, :], arm_obs[b, :])))
        for b in batch_size_range
    ])
    return reward
