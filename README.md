# ECOTWIN
Standard city traffic optimization algorithms are designed exclusively to minimize vehicle wait times. They completely ignore the environmental impact of their decisions, allowing hazardous
localized smog and CO2 to build up at major intersections.

An urban planner views a simulated city grid on the EcoTwin dashboard. The map displays a
heatmap of high carbon concentration "smog clouds". The active Reinforcement Learning agent dynamically
adjusts traffic light phases across the grid, not just to move cars, but to actively "flush" and disperse the
pollution pockets, balancing commute times with atmospheric health.

Key Modules:
• Simulation Environment (SUMO): Simulation of Urban MObility engine to run the mock city grid
and generate traffic/emissions data.
• Reinforcement Learning Agent (Ray RLlib / OpenAI Gym): A multi-objective RL agent trained
using Proximal Policy Optimization (PPO) to control traffic lights.
• Data API (FastAPI & WebSockets): Streams the live simulation state (vehicle positions, carbon
levels, light states) to the client.
• Cityscape Dashboard (React & Deck.gl / Leaflet): A map-based UI rendering the live traffic
simulation and carbon heatmaps.