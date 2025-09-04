# run_simulation.py
from __future__ import annotations

import math
import random
import threading
import time
from datetime import datetime, timezone
from typing import Iterable

from auv_tracker import AuvTracker


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def step(lat: float, lon: float, heading_deg: float, distance_m: float) -> tuple[float, float]:
    """Move along heading by distance (m) on a local tangent plane."""
    north = math.cos(math.radians(heading_deg)) * distance_m
    east = math.sin(math.radians(heading_deg)) * distance_m
    dlat = north / 111_320.0
    # use latitude before update to convert east meters to degrees
    dlon = east / (111_320.0 * max(0.001, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def make_path_ahead(lat: float, lon: float, heading_deg: float, n: int = 6, spacing_m: float = 300.0) -> list[dict]:
    """Simple straight path n points ahead."""
    pts: list[dict] = []
    cur_lat, cur_lon = lat, lon
    for _ in range(n):
        cur_lat, cur_lon = step(cur_lat, cur_lon, heading_deg, spacing_m)
        pts.append({"lat": cur_lat, "lon": cur_lon})
    return pts


def random_target_near(lat: float, lon: float, max_radius_m: float = 1500.0) -> tuple[float, float, float]:
    """Uniform random target within circle (<= max_radius_m). Returns (lat, lon, radius_m)."""
    r = max_radius_m * math.sqrt(random.random())
    theta = random.uniform(0, 2 * math.pi)
    tlat, tlon = step(lat, lon, math.degrees(theta), r)
    radius_m = random.choice([150, 250, 300, 450, 600, 900])
    return tlat, tlon, float(radius_m)


def simulation_loop(
    tracker: AuvTracker,
    *,
    start_lat: float = 32.1000,
    start_lon: float = 34.7800,
    start_heading: float = 90.0,
    speed_mps: float = 3.0,
    dt: float = 1.0,
    path_every_n_ticks: int = 10,
    target_prob_per_tick: float = 0.005,
) -> None:
    """Infinite loop; Ctrl+C to stop."""
    lat, lon, heading = start_lat, start_lon, start_heading
    tick = 0

    # optional initial path/target
    tracker.set_path([{32.1020, 34.7800}, {32.1060, 34.7820}, {32.1080, 34.7800}, {32.1090, 34.7830}], mode="replace")
    tlat, tlon, r = random_target_near(lat, lon)
    tracker.set_target(lat=tlat, lon=tlon, radius_m=r)

    while True:
        tick += 1

        # small heading wander (kept in [0, 360))
        heading = (heading + random.uniform(-3.0, 3.0)) % 360.0

        # move the AUV
        lat, lon = step(lat, lon, heading, speed_mps * dt)
        tracker.set_auv(lat=lat, lon=lon, heading=heading, timestamp=now_iso())

        # refresh path periodically
        #if tick % path_every_n_ticks == 0:
        #    tracker.set_path(make_path_ahead(lat, lon, heading), mode="replace")

        # sometimes move target
        if random.random() < target_prob_per_tick:
            tlat, tlon, r = random_target_near(lat, lon)
            tracker.set_target(lat=tlat, lon=tlon, radius_m=r)

        time.sleep(dt)


def main() -> None:
    tracker = AuvTracker()

    # Run server in background so this script can keep updating state
    threading.Thread(target=lambda: tracker.run(debug=False), daemon=True).start()

    # Give the server a moment to start
    time.sleep(1.0)

    # Start the simulation (Ctrl+C to stop)
    try:
        simulation_loop(tracker)
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
