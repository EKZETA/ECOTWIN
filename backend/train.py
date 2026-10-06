"""Train the RL Agent (PPO) using Ray RLlib."""
import os
import argparse
from ray.rllib.algorithms.ppo import PPOConfig
from ray.tune.registry import register_env
from ray import tune
import ray

from ecotwin_env import EcoTwinEnv
from reward import RewardConfig

def env_creator(env_config):
    return EcoTwinEnv(
        cfg_path=env_config.get("cfg_path"),
        net_path=env_config.get("net_path"),
        decision_interval_steps=env_config.get("decision_interval_steps", 20),
        episode_steps=env_config.get("episode_steps", 180),
        pollution_rows=env_config.get("pollution_rows", 10),
        pollution_columns=env_config.get("pollution_columns", 10),
        pollution_threshold_mg=env_config.get("pollution_threshold_mg", 500.0),
        reward_config=RewardConfig()
    )


def main():
    parser = argparse.ArgumentParser(description="Train PPO Agent for EcoTwin")
    parser.add_argument("--iters", type=int, default=50, help="Number of training iterations")
    parser.add_argument("--save-dir", type=str, default="./models/ecotwin_ppo", help="Directory to save the trained model")
    args = parser.parse_args()

    ray.init(ignore_reinit_error=True)

    # Register the environment
    register_env("ecotwin-v0", env_creator)

    # Setup PPO Configuration
    config = (
        PPOConfig()
        .environment("ecotwin-v0", env_config={})
        .env_runners(num_env_runners=1) # 1 worker since SUMO can be heavy to run multiple in parallel on some machines
        .training(
            gamma=0.99,
            lr=1e-4,
            train_batch_size=1024,
            minibatch_size=64,
            vf_loss_coeff=0.5,
            entropy_coeff=0.01
        )
    )

    # Build the algorithm
    algo = config.build()

    print("=" * 60)
    print("EcoTwin: Starting RLlib PPO Training")
    print("=" * 60)

    for i in range(args.iters):
        result = algo.train()
        # Extract metrics defensively since Ray dict structures vary by version
        reward_mean = result.get('episode_reward_mean', result.get('env_runners', {}).get('episode_reward_mean', 0.0))
        len_mean = result.get('episode_len_mean', result.get('env_runners', {}).get('episode_len_mean', 0.0))
        
        print(f"Iteration: {i+1:3d} | "
              f"Reward mean: {reward_mean:6.2f} | "
              f"Len mean: {len_mean:6.2f}")

    save_path = os.path.abspath(args.save_dir)
    print(f"Training complete. Saving checkpoint to {save_path}")
    os.makedirs(save_path, exist_ok=True)
    algo.save(save_path)

    print("=" * 60)
    print("EcoTwin: Training finished and model saved.")
    print("=" * 60)

    ray.shutdown()


if __name__ == "__main__":
    main()
