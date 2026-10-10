# ECOTWIN
Standard city traffic optimization algorithms are designed exclusively to minimize vehicle wait times. They completely ignore the environmental impact of their decisions, allowing hazardous
localized smog and CO2 to build up at major intersections.

An urban planner views a simulated city grid on the EcoTwin dashboard. The map displays a
heatmap of high carbon concentration. The active Reinforcement Learning agent dynamically
adjusts traffic light phases across the grid, not just to move cars, but to actively "flush" and disperse the
pollution pockets, balancing commute times with atmospheric health.

Key Modules:
• Simulation Environment (SUMO): Simulation of Urban MObility engine to run the mock city grid
and generate traffic/emissions data.
• Reinforcement Learning Agent (Ray RLlib / OpenAI Gym): A multi-objective PPO agent trained
to control traffic lights and reduce waiting, queues, CO₂ hotspots, and unnecessary phase changes.
  Signal changes pass through the SUMO program's yellow-clearance phase.
• Data API (FastAPI & WebSockets): Streams the live simulation state (vehicle positions, carbon
levels, light states) to the client.
• Cityscape Dashboard (React & Deck.gl / Leaflet): A map-based UI rendering the live traffic
simulation and carbon heatmaps.

Train and evaluate the agent from the `backend` directory before starting the live dashboard:

```powershell
python train.py --iters 50 --episode-steps 40 --decision-interval-steps 10 --metrics-output ..\reports\train-default.json
python evaluate.py --model-dir ..\models\ecotwin_ppo --episodes 5 --output ..\reports\ecotwin_ppo.json
```

To resume an existing checkpoint without overwriting it, pass separate source and
destination paths:

```powershell
python train.py --iters 50 --resume-from ..\models\ecotwin_ppo --save-dir ..\models\ecotwin_ppo_candidate --metrics-output ..\reports\train-candidate.json
python evaluate.py --model-dir ..\models\ecotwin_ppo_candidate --episodes 5 --output ..\reports\ecotwin_ppo_candidate.json
```

PPO hyperparameters (`--learning-rate`, `--entropy-coeff`, `--gamma`, and
`--num-epochs`) can be varied between fresh, isolated training runs. Resuming loads the
checkpoint's serialized PPO configuration; keep each run's checkpoint and metrics in
separate paths, then evaluate candidates on the same seeds.

The backend loads `models/ecotwin_ppo_tune_lr1e4` by default, the best of two isolated
50-iteration candidates evaluated on ten matched SUMO seeds. The original
`models/ecotwin_ppo` checkpoint remains untouched. See
[`reports/ppo_training_evaluation.md`](reports/ppo_training_evaluation.md) and the
per-run JSON artifacts for training history and matched-seed results.

Models are local artifacts and are ignored by Git. Preserve or separately distribute the
selected checkpoint when setting up another machine. The API and dashboard report when
the configured checkpoint is unavailable or could not be loaded; the simulation then
remains uncontrolled by RL.

Ray uses an explicit 80 MiB object store by default to support machines where automatic
memory detection reports less than Ray's minimum. Set `RAY_OBJECT_STORE_MEMORY_MB` in
`.env` to a larger value if available system memory allows it. Evaluation reports contain
per-episode PPO and fixed-baseline metrics on the same seeds.