"""Ray initialization settings shared by training, evaluation, and inference."""
from __future__ import annotations

import os


def initialize_ray():
    import ray

    memory_mb = int(os.environ.get("RAY_OBJECT_STORE_MEMORY_MB", "80"))
    if memory_mb < 80:
        raise ValueError("RAY_OBJECT_STORE_MEMORY_MB must be at least 80 MiB.")
    return ray.init(
        ignore_reinit_error=True,
        include_dashboard=False,
        object_store_memory=memory_mb * 1024 * 1024,
    )
