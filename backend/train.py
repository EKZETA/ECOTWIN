"""Train the RL Agent (PPO) using Ray RLlib."""
import os
import argparse
from pathlib import Path
from ray.rllib.algorithms.algorithm import Algorithm
from ray.rllib.algorithms.ppo import PPOConfig
from ray.tune.registry import register_env
import ray

if __package__:
    from .ecotwin_env import EcoTwinEnv
    from .reward import RewardConfig
else:
    from ecotwin_env import EcoTwinEnv
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
    args = parser.parse_args()
    if min(args.iters, args.batch_size, args.episode_steps, args.decision_interval_steps) <= 0:
        parser.error("iterations, batch size, episode steps, and decision interval must be positive")
    if args.resume_from:
        resume_path = Path(args.resume_from).resolve()
        if not resume_path.is_dir() or not (resume_path / "rllib_checkpoint.json").is_file():
            parser.error(f"RLlib checkpoint does not exist: {resume_path}")

    algo = None
    ray.init(ignore_reinit_error=True, include_dashboard=False)
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
                gamma=0.99,
                lr=3e-4,
                train_batch_size=args.batch_size,
                minibatch_size=64,
                num_epochs=10,
                vf_loss_coeff=0.5,
                entropy_coeff=0.01
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

        for i in range(args.iters):
            result = algo.train()
            env_metrics = result.get("env_runners", {})
            reward_mean = result.get(
                "episode_reward_mean",
                env_metrics.get("episode_return_mean", env_metrics.get("episode_reward_mean")),
            )
            len_mean = result.get("episode_len_mean", env_metrics.get("episode_len_mean"))
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
    finally:
        if algo is not None:
            algo.stop()
        ray.shutdown()

if __name__ == "__main__":
    main()
