"""Benchmark SubprocVecEnv throughput."""
import sys, os, time, traceback
import numpy as np
_real_out = sys.__stdout__

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.utils import set_random_seed
from rl.ddm_env import DDMEnv

def make_env(seed):
    def _init():
        set_random_seed(seed)
        return DDMEnv(opponent='claude', seed=seed)
    return _init

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    _real_out.write(f"Starting {n}-worker SubprocVecEnv benchmark...\n"); _real_out.flush()

    try:
        vec = SubprocVecEnv([make_env(i) for i in range(n)])
        vec.reset()
        _real_out.write("Reset ok, benchmarking...\n"); _real_out.flush()

        t0 = time.time()
        N = 3000
        for i in range(N):
            # Correct: batch of n actions, each of shape action_space.shape
            actions = np.array([vec.action_space.sample() for _ in range(n)])
            vec.step(actions)
            if i == 99:
                elapsed_so_far = time.time() - t0
                _real_out.write(f"100 steps done ({100*n/elapsed_so_far:.0f} sps so far)...\n")
                _real_out.flush()
        elapsed = time.time() - t0
        sps = (N * n) / elapsed
        _real_out.write(f"{n}-worker: {sps:.1f} steps/s over {N*n} steps ({elapsed:.1f}s)\n")
        _real_out.flush()
        vec.close()
    except Exception as e:
        _real_out.write(f"ERROR: {e}\n")
        _real_out.write(traceback.format_exc())
        _real_out.flush()
