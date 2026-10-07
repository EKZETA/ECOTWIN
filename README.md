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
python train.py --iters 50 --episode-steps 40
python evaluate.py --model-dir ..\models\ecotwin_ppo --episodes 3
```

To continue from an existing checkpoint without overwriting it, pass separate source and destination paths:

```powershell
python train.py --iters 50 --resume-from ..\models\ecotwin_ppo --save-dir ..\models\ecotwin_ppo_candidate --episode-steps 40
python evaluate.py --model-dir ..\models\ecotwin_ppo_candidate --episodes 5
```

The backend loads `models/ecotwin_ppo` by default. Its API and dashboard report when the
checkpoint is unavailable or could not be loaded; the simulation then remains uncontrolled by RL.
An active policy confirms live inference, not that it outperforms the fixed-phase baseline;
use the matched-seed evaluation before making a performance claim.