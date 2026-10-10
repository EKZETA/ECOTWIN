# PPO Training and Evaluation

## Method

- SUMO city grid, matched seeds `1000` through `1009` (10 episodes per controller).
- Each episode: 40 PPO decisions, one decision every 10 SUMO ticks.
- Compare deterministic PPO inference against the fixed first-green-phase controller.
- Acceptance rule: higher (less negative) mean composite reward, with no regression in
  mean wait, queue, or CO2 hotspot excess versus the fixed controller.
- Two PPO configurations, each independently initialized with PPO seed `42`, batch size
  `64`, 40 episode decisions, and 10 ticks per decision:
  - Learning rate `0.0003`, entropy coefficient `0.01`.
  - Learning rate `0.0001`, entropy coefficient `0.02`.
- Both candidates use gamma `0.99` and 10 optimization epochs. The original checkpoint
  was not overwritten. The `0.0003` run reproduced the original checkpoint policy weights;
  the `0.0001` run produced a distinct policy.

## Matched-seed results

Lower is better for wait, queue, hotspot excess, and final pollution. For reward, a
higher value (closer to zero) is better.

| Controller | Mean reward | Mean wait (s) | Mean queue (vehicles) | Mean hotspot excess (mg²) | Final pollution (mg) |
|---|---:|---:|---:|---:|---:|
| Fixed first-green baseline | -7.8383 | 8.0650 | 2.4000 | 36,484,949,794 | 1,637,312 |
| Existing PPO checkpoint | -7.7496 | 7.5538 | 2.2050 | 35,450,237,383 | 1,625,461 |
| Candidate, lr 0.0003 | -7.7496 | 7.5538 | 2.2050 | 35,450,237,383 | 1,625,461 |
| **Selected candidate, lr 0.0001** | **-7.6579** | **7.5338** | **2.2475** | **34,789,537,685** | **1,618,100** |

The selected candidate passes the stated average-metric acceptance rule: mean composite
reward improves by 2.30% versus baseline; mean wait by 6.59%; mean queue by 6.35%; and
mean hotspot excess by 4.65%. These are results for the bundled SUMO demand and the
specified seed set, not a guarantee for real-world traffic. The selected candidate was
better than baseline in 8/10 paired episodes for reward, 7/10 for wait, 8/10 for queue,
and 10/10 for hotspot excess; the acceptance rule is based on averages, not a claim that
it wins every individual episode.

The selected checkpoint was also loaded by the FastAPI backend in headless mode. A live
WebSocket smoke test received three frames, each with an active policy and telemetry plus
selected phases for all nine traffic lights. After changing the simulation loop to pace
frames against monotonic deadlines instead of sleeping after each completed frame, a
31-frame stream averaged 9.92 frames/second at the configured 10 fps (mean interval
100.8 ms; mean payload 7,416 bytes). Before that change, the same test averaged 8.19 fps.

## Artifacts

- [`ecotwin_ppo_baseline.json`](ecotwin_ppo_baseline.json): original checkpoint and
  matched baseline, 10 episodes.
- [`eval_lr3e4.json`](eval_lr3e4.json): first candidate, matched evaluation.
- [`eval_lr1e4.json`](eval_lr1e4.json): selected candidate, matched evaluation.
- [`train_lr3e4.json`](train_lr3e4.json): first candidate training history/configuration.
- [`train_lr1e4.json`](train_lr1e4.json): selected candidate training history/configuration.
- Selected local checkpoint: `models/ecotwin_ppo_tune_lr1e4`.

The selected model is the default backend checkpoint in this working copy. Model
directories are excluded from Git, so copy the selected checkpoint separately when
deploying on another machine.
