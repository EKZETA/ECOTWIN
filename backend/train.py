"""Train the RL Agent (PPO) using Ray RLlib."""
import os
import argparse
import json
from pathlib import Path
from ray.rllib.algorithms.algorithm import Algorithm
from ray.rllib.algorithms.ppo import PPOConfig
from ray.tune.registry import register_env
import ray

if __package__:
    from .ecotwin_env import EcoTwinEnv
    from .ray_runtime import initialize_ray
    from .reward import RewardConfig
else:
    from ecotwin_env import EcoTwinEnv
    from ray_runtime import initialize_ray
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
        reward_config=RewardConfig()
    )


def main():
    parser = argparse.ArgumentParser(description="Train PPO Agent for EcoTwin")
    parser.add_argument("--iters", type=int, default=50, help="Number of training iterations")
    default_model_path = Path(__file__).resolve().parents[1] / "models" / "ecotwin_ppo"
    parser.add_argument("--save-dir", type=str, default=str(default_model_path), help="Directory to save the trained model")
    parser.add_argument("--resume-from", type=str, help="Resume training from an existing RLlib checkpoint")
    parser.add_argument("--seed", type=int, default=42, help="Random seed used for training")
    parser.add_argument("--batch-size", type=int, default=64, help="Environment steps per PPO training batch")
    parser.add_argument("--episode-steps", type=int, default=20, help="RL decisions per simulation episode")
    parser.add_argument("--decision-interval-steps", type=int, default=10, help="SUMO ticks between RL decisions")
    parser.add_argument("--learning-rate", type=float, default=3e-4, help="PPO optimizer learning rate")
    parser.add_argument("--entropy-coeff", type=float, default=0.01, help="PPO entropy regularization coefficient")
    parser.add_argument("--gamma", type=float, default=0.99, help="PPO discount factor")
    parser.add_argument("--num-epochs", type=int, default=10, help="PPO optimization epochs per training batch")
    parser.add_argument("--metrics-output", type=str, help="Optional path to save per-iteration metrics as JSON")
    args = parser.parse_args()
    if min(args.iters, args.batch_size, args.episode_steps, args.decision_interval_steps) <= 0:
        parser.error("iterations, batch size, episode steps, and decision interval must be positive")
    if args.learning_rate <= 0 or args.entropy_coeff < 0 or not 0 < args.gamma <= 1 or args.num_epochs <= 0:
        parser.error("learning rate and epochs must be positive; entropy must be nonnegative; gamma must be in (0, 1]")
    if args.resume_from:
        resume_path = Path(args.resume_from).resolve()
        if not resume_path.is_dir() or not (resume_path / "rllib_checkpoint.json").is_file():
            parser.error(f"RLlib checkpoint does not exist: {resume_path}")

    algo = None
    initialize_ray()
    try:
        register_env("ecotwin-v0", env_creator)

        config = (
            PPOConfig()
            .environment("ecotwin-v0", env_config={
                "decision_interval_steps": args.decision_interval_steps,
                "episode_steps": args.episode_steps,
            })
            .env_runners(num_env_runners=1, rollout_fragment_length=16, sample_timeout_s=180)
            .training(
                gamma=args.gamma,
                lr=args.learning_rate,
                train_batch_size=args.batch_size,
                minibatch_size=min(64, args.batch_size),
                num_epochs=args.num_epochs,
                vf_loss_coeff=0.5,
                entropy_coeff=args.entropy_coeff
            )
            .debugging(seed=args.seed)
        )
        algo = (
            Algorithm.from_checkpoint(str(resume_path))
            if args.resume_from
            else config.build_algo()
        )

        print("=" * 60)
        print("EcoTwin: Starting RLlib PPO Training")
        print("=" * 60)

        iteration_metrics = []
        for i in range(args.iters):
            result = algo.train()
            env_metrics = result.get("env_runners", {})
            reward_mean = result.get(
                "episode_reward_mean",
                env_metrics.get("episode_return_mean", env_metrics.get("episode_reward_mean")),
            )
            len_mean = result.get("episode_len_mean", env_metrics.get("episode_len_mean"))
            iteration_metrics.append({
                "iteration": i + 1,
                "episode_reward_mean": float(reward_mean) if reward_mean is not None else None,
                "episode_length_mean": float(len_mean) if len_mean is not None else None,
            })
            print(
                f"Iteration: {i + 1:3d} | "
                f"Reward mean: {reward_mean if reward_mean is not None else 'pending':>8} | "
                f"Len mean: {len_mean if len_mean is not None else 'pending':>6}",
                flush=True,
            )

        save_path = os.path.abspath(args.save_dir)
        os.makedirs(save_path, exist_ok=True)
        checkpoint = algo.save(save_path)
        checkpoint_path = getattr(checkpoint, "path", save_path)
        print(f"Training complete. Checkpoint saved to {checkpoint_path}")
        if args.metrics_output:
            metrics_path = Path(args.metrics_output).resolve()
            metrics_path.parent.mkdir(parents=True, exist_ok=True)
            metrics_path.write_text(json.dumps({
                "checkpoint": str(checkpoint_path),
                "iterations": args.iters,
                "seed": args.seed,
                "episode_steps": args.episode_steps,
                "decision_interval_steps": args.decision_interval_steps,
                "train_batch_size": args.batch_size,
                "learning_rate": args.learning_rate,
                "entropy_coeff": args.entropy_coeff,
                "gamma": args.gamma,
                "num_epochs": args.num_epochs,
                "history": iteration_metrics,
            }, indent=2) + "\n", encoding="utf-8")
            print(f"Training metrics saved to {metrics_path}")
    finally:
        if algo is not None:
            algo.stop()
        ray.shutdown()

if __name__ == "__main__":
    main()
