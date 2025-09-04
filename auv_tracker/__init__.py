# /auv_tracker/__init__.py
from __future__ import annotations
from typing import Any, Dict, Iterable, Optional
from .core import StateStore, Broker, sse_wrap, Auv, Target, LatLon
from .server import create_app

class AuvTracker:
    """Importable facade providing both a Python API and a Flask app."""
    def __init__(self) -> None:
        self.store = StateStore()
        self.broker = Broker()
        self.app = create_app(self.store, self.broker)

    # ----- Python methods (no HTTP) -----
    def get_state(self) -> Dict[str, Any]:
        return self.store.get()

    def set_auv(self, *, lat: float, lon: float, alt: float | None = None,
                heading: float | None = None, timestamp: str = "") -> None:
        auv: Auv = {"lat": float(lat), "lon": float(lon), "alt": alt, "heading": heading, "timestamp": timestamp}
        state = self.store.set_auv(auv)
        self.broker.publish_str(sse_wrap(state))

    def set_target(self, *, lat: float, lon: float, radius_m: float | None = None) -> None:
        target: Target = {"lat": float(lat), "lon": float(lon)}
        if radius_m is not None:
            if radius_m < 0:
                raise ValueError("radius_m must be >= 0")
            target["radius_m"] = float(radius_m)
        state = self.store.set_target(target)
        self.broker.publish_str(sse_wrap(state))

    def clear_target(self) -> None:
        state = self.store.set_target(None)
        self.broker.publish_str(sse_wrap(state))

    def set_path(self, points: Iterable[tuple[float, float]] | Iterable[Dict[str, float]],
                 mode: str = "replace") -> None:
        if mode not in {"replace", "append"}:
            raise ValueError("mode must be 'replace' or 'append'")
        latlons: list[LatLon] = []
        for p in points:
            if isinstance(p, dict):
                latlons.append({"lat": float(p["lat"]), "lon": float(p["lon"])})
            else:
                lat, lon = p  # tuple-like
                latlons.append({"lat": float(lat), "lon": float(lon)})
        state = self.store.set_path(latlons, mode=mode)
        self.broker.publish_str(sse_wrap(state))

    # ----- Server -----
    def run(self, host: str = "0.0.0.0", port: int = 8000, debug: bool = True) -> None:
        self.app.run(host=host, port=port, debug=debug)
