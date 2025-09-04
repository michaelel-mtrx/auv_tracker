# /auv_tracker/core.py
from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, List, Optional, TypedDict
from queue import Queue, Empty

# ---- Types ----
class LatLon(TypedDict):
    lat: float
    lon: float

class Auv(TypedDict, total=False):
    timestamp: str
    lat: float
    lon: float
    alt: Optional[float]
    heading: Optional[float]

class Target(TypedDict, total=False):
    lat: float
    lon: float
    radius_m: float  # optional

class StateDict(TypedDict):
    auv: Optional[Auv]
    target: Optional[Target]
    path: List[LatLon]

# ---- State store ----
@dataclass
class State:
    auv: Optional[Auv]
    target: Optional[Target]
    path: List[LatLon]

class StateStore:
    def __init__(self) -> None:
        self._state = State(auv=None, target=None, path=[])
        self._lock = RLock()

    def get(self) -> StateDict:
        with self._lock:
            s = self._state
            return {
                "auv": None if s.auv is None else dict(s.auv),
                "target": None if s.target is None else dict(s.target),
                "path": [dict(p) for p in s.path],
            }

    def set_auv(self, auv: Auv) -> StateDict:
        with self._lock:
            self._state.auv = auv
            return self.get()

    def set_target(self, target: Optional[Target]) -> StateDict:
        with self._lock:
            self._state.target = target
            return self.get()

    def set_path(self, points: List[LatLon], mode: str = "replace") -> StateDict:
        with self._lock:
            if mode == "append":
                self._state.path.extend(points)
            else:
                self._state.path = list(points)
            return self.get()

# ---- SSE Broker ----
class Broker:
    """Fan-out broker that keeps at most one pending event per subscriber."""
    def __init__(self) -> None:
        self._subs: List[Queue[str]] = []
        self._lock = RLock()

    def subscribe(self, snapshot: str) -> Queue[str]:
        q: Queue[str] = Queue(maxsize=1)
        with self._lock:
            self._subs.append(q)
        self._put_latest(q, snapshot)
        return q

    def unsubscribe(self, q: Queue[str]) -> None:
        with self._lock:
            try:
                self._subs.remove(q)
            except ValueError:
                pass

    def publish_str(self, payload: str) -> None:
        with self._lock:
            for q in list(self._subs):
                self._put_latest(q, payload)

    @staticmethod
    def _put_latest(q: Queue[str], item: str) -> None:
        try:
            while True:
                q.get_nowait()
        except Empty:
            pass
        q.put_nowait(item)

def sse_wrap(obj: Dict[str, Any]) -> str:
    import json
    return f"data: {json.dumps(obj, separators=(',', ':'))}\n\n"

def validate_latlon(d: Dict[str, Any]) -> LatLon:
    try:
        lat = float(d["lat"])
        lon = float(d["lon"])
    except Exception as e:
        raise ValueError("lat/lon required and numeric") from e
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("lat/lon out of range")
    return {"lat": lat, "lon": lon}
