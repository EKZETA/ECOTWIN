"""Safety-preserving traffic-signal phase transitions."""
from __future__ import annotations


def safe_transition_phase(
    current_phase: int,
    target_phase: int,
    phase_states: list[str],
) -> int | None:
    if not phase_states or not 0 <= current_phase < len(phase_states):
        raise ValueError(f"Invalid current traffic-light phase {current_phase}.")
    if not 0 <= target_phase < len(phase_states):
        raise ValueError(f"Invalid target traffic-light phase {target_phase}.")
    if current_phase == target_phase:
        return None

    current_state = phase_states[current_phase].lower()
    if "y" in current_state or not any(signal in current_state for signal in "gG"):
        return None

    transition_phase = (current_phase + 1) % len(phase_states)
    if "y" not in phase_states[transition_phase].lower():
        raise RuntimeError(
            f"Traffic-light phase {current_phase} has no yellow clearance phase "
            f"before phase {target_phase}."
        )
    return transition_phase
