import os
import sys

sumo_home = os.environ.get("SUMO_HOME", r"C:\Program Files (x86)\Eclipse\Sumo")
os.environ["SUMO_HOME"] = sumo_home
tools = os.path.join(sumo_home, "tools")
if tools not in sys.path:
    sys.path.append(tools)

import traci

def run_test(steps=200):
    # Absolute path so it works whether you run from project root or inside simulation/
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_file = os.path.join(base_dir, "configs", "simulation.sumocfg")

    # Command to run SUMO in headless mode
    sumo_cmd = [
        "sumo",
        "-c", cfg_file,
        "--no-step-log", "true",
        "--duration-log.disable", "true",
        "--quit-on-end", "true"
    ]

    print("=" * 60)
    print("EcoTwin: Starting TraCI Telemetry & Emission Test")
    print("=" * 60)

    traci.start(sumo_cmd)

    tls_ids = traci.trafficlight.getIDList()
    print(f"Connected! Controlling {len(tls_ids)} Traffic Lights: {list(tls_ids)}\n")

    total_co2_mg = 0.0
    peak_active_vehicles = 0
    total_wait_seconds = 0.0

    print("Advancing simulation steps and extracting telemetry...")

    for step in range(1, steps + 1):
        traci.simulationStep()

        vehicle_ids = traci.vehicle.getIDList()
        n_vehicles = len(vehicle_ids)
        if n_vehicles > peak_active_vehicles:
            peak_active_vehicles = n_vehicles

        step_co2 = 0.0
        for vid in vehicle_ids:
            co2_rate = traci.vehicle.getCO2Emission(vid)
            wait = traci.vehicle.getWaitingTime(vid)

            step_co2 += (co2_rate * 0.5)
            total_wait_seconds += (wait * 0.5)

        total_co2_mg += step_co2

        # Print a snapshot every 40 steps (every 20s of sim time)
        if step % 40 == 0:
            sim_time = traci.simulation.getTime()
            sample_tls = tls_ids[0]
            tls_state = traci.trafficlight.getRedYellowGreenState(sample_tls)
            print(f"  [Step {step:03d} | Time: {sim_time:5.1f}s] Active Cars: {n_vehicles:2d} | Total CO2: {total_co2_mg / 1000.0:6.1f} g | TLS {sample_tls}: {tls_state[:6]}")

    # Outside the loop: close connection and print totals
    traci.close()

    print("\n" + "=" * 60)
    print("Telemetry Test Completed Successfully")
    print("=" * 60)
    print(f"Simulation Steps Run     : {steps} ({steps * 0.5:.1f} simulated seconds)")
    print(f"Peak Concurrent Vehicles : {peak_active_vehicles}")
    print(f"Total CO2 Emitted        : {total_co2_mg / 1000.0:.2f} grams ({total_co2_mg / 1e6:.4f} kg)")
    print(f"Total Cumulative Wait    : {total_wait_seconds:.1f} vehicle-seconds")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
