"""Compare a trained RL policy with fixed first-green-phase control."""
import argparse
import os
from pathlib import Path

import ray
from ray.rllib.algorithms.algorithm import Algorithm
from ray.tune.registry import register_env

if __package__:
    from .ecotwin_env import EcoTwinEnv
    from .rl_controller import deterministic_action
    from .reward import RewardConfig
else:
    from ecotwin_env import EcoTwinEnv
    from rl_controller import deterministic_action
    from reward import RewardConfig


def env_creator(env_config):
    return EcoTwinEnv(
        cfg_path=env_config.get("cfg_path"),
        net_path=env_config.get("net_path"),
        decision_interval_steps=env_config.get("decision_interval_steps", 10),
        episode_steps=env_config.get("episode_steps", 40),
        pollution_rows=env_config.get("pollution_rows", 10),
        pollution_columns=env_config.get("pollution_columns", 10),
        pollution_threshold_mg=env_config.get("pollution_threshold_mg", 500.0),
        reward_config=RewardConfig(),
    )


def evaluate_policy(env, policy, episodes: int, seed: int):
    results = []
    for episode in range(episodes):
        observation, _ = env.reset(seed=seed + episode)
        total_reward = 0.0
        total_wait = 0.0
        total_queue = 0
        total_hotspot_excess = 0.0
        reward_components = {}
        done = False
        while not done:
            action = policy(observation, env)
            observation, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            total_reward += reward
            total_wait += info["wait_seconds"]
            total_queue += info["queue_vehicles"]
            total_hotspot_excess += info["co2_hotspot_excess_mg_squared"]
            for name, value in info["reward_parts"].items():
                reward_components[name] = reward_components.get(name, 0.0) + value

        results.append({
            "reward": total_reward,
            "mean_wait_seconds": total_wait / info["episode_step"],
            "mean_queue_vehicles": total_queue / info["episode_step"],
            "mean_hotspot_excess": total_hotspot_excess / info["episode_step"],
            "final_pollution_mg": info["pollution_total_mg"],
            "steps": info["episode_step"],
            "reward_components": reward_components,
        })
    return results


def summarize(label: str, results) -> None:
    episodes = len(results)
    average_component = lambda name: sum(
        result["reward_components"].get(name, 0.0) / result["steps"]
        for result in results
    ) / episodes
    print(
        f"{label}: reward={sum(r['reward'] for r in results) / episodes:.2f}, "
        f"wait={sum(r['mean_wait_seconds'] for r in results) / episodes:.2f}s, "
        f"queue={sum(r['mean_queue_vehicles'] for r in results) / episodes:.2f}, "
        f"hotspot={sum(r['mean_hotspot_excess'] for r in results) / episodes:.2f}, "
        f"final pollution={sum(r['final_pollution_mg'] for r in results) / episodes:.2f}mg, "
        f"reward parts/step=(wait {average_component('wait_penalty'):.4f}, "
        f"CO2 {average_component('co2_hotspot_penalty'):.4f}, "
        f"queue {average_component('queue_penalty'):.4f}, "
        f"switch {average_component('phase_switch_penalty'):.4f})"
    )


def main():
    parser = argparse.ArgumentParser(description="Evaluate PPO against fixed-phase control.")
    default_model_path = Path(__file__).resolve().parents[1] / "models" / "ecotwin_ppo"
    parser.add_argument("--model-dir", type=str, default=str(default_model_path))
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--episode-steps", type=int, default=40)
    parser.add_argument("--decision-interval-steps", type=int, default=10)
    args = parser.parse_args()
    if args.episodes <= 0:
        parser.error("--episodes must be greater than zero")

    model_path = os.path.abspath(args.model_dir)
    if not os.path.exists(model_path):
        parser.error(f"Model checkpoint does not exist: {model_path}")

    algo = None
    env = env_creator({
        "episode_steps": args.episode_steps,
        "decision_interval_steps": args.decision_interval_steps,
    })
    try:
        ray.init(ignore_reinit_error=True, include_dashboard=False)
        register_env("ecotwin-v0", env_creator)
        algo = Algorithm.from_checkpoint(model_path)

        ppo_results = evaluate_policy(
            env,
            lambda observation, _env: deterministic_action(algo, observation),
            args.episodes,
            args.seed,
        )
        baseline_results = evaluate_policy(
            env,
            lambda _observation, current_env: current_env.action_space.nvec * 0,
            args.episodes,
            args.seed,
        )
        print(f"Evaluation on {args.episodes} matched episode(s), seeds {args.seed}–{args.seed + args.episodes - 1}")
        summarize("PPO", ppo_results)
        summarize("Fixed first-green baseline", baseline_results)
    finally:
        env.close()
        if algo is not None:
            algo.stop()
        ray.shutdown()


if __name__ == "__main__":
    main()
