"""Evaluate the trained RL Agent."""
import os
import argparse
from ray.rllib.algorithms.algorithm import Algorithm
from ray.tune.registry import register_env
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=str, default="./models/ecotwin_ppo_final")
    args = parser.parse_args()

    ray.init(ignore_reinit_error=True)
    register_env("ecotwin-v0", env_creator)

    model_path = os.path.abspath(args.model_dir)
    print(f"Loading trained model from {model_path} ...")
    algo = Algorithm.from_checkpoint(model_path)

    env = env_creator({})
    obs, info = env.reset()
    
    total_reward = 0.0
    done = False
    
    print("=" * 60)
    print("EcoTwin: Evaluating Trained PPO Agent")
    print("=" * 60)

    while not done:
        action = algo.compute_single_action(obs, explore=False)
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        total_reward += reward

    print("\n" + "=" * 60)
    print("Evaluation Completed Successfully")
    print("=" * 60)
    print(f"Final Episode Reward         : {total_reward:.2f}")
    print(f"Total Pollution (CO2)        : {info.get('pollution_total_mg', 0) / 1000.0:.2f} grams")
    print(f"Latest CO2 Hotspot Excess    : {info.get('co2_hotspot_excess_mg_squared', 0):.2f}")
    print("=" * 60)

    env.close()
    ray.shutdown()

if __name__ == "__main__":
    main()
