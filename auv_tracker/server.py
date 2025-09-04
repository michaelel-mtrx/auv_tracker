# /auv_tracker/server.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from flask import Flask, Response, jsonify, request, send_from_directory
from queue import Empty, Queue
from pathlib import Path
from .core import (
    StateStore, Broker, sse_wrap, validate_latlon,
    Auv, Target, LatLon
)

def create_app(store: StateStore, broker: Broker) -> Flask:
    static_dir = Path(__file__).with_name("static")
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="/static")

    @app.get("/")
    def index() -> Any:
        resp = send_from_directory(str(static_dir), "index.html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    @app.get("/api/state")
    def api_state() -> Any:
        return jsonify(store.get())

    @app.post("/api/auv")
    def api_auv() -> Any:
        data: Dict[str, Any] = request.get_json(silent=True) or {}
        try:
            latlon = validate_latlon(data)
            auv: Auv = {
                **latlon,
                "alt": float(data["alt"]) if data.get("alt") is not None else None,
                "heading": float(data["heading"]) if data.get("heading") is not None else None,
                "timestamp": str(data.get("timestamp") or ""),
            }
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        state = store.set_auv(auv)
        broker.publish_str(sse_wrap(state))
        return "", 204

    @app.post("/api/target")
    def api_target() -> Any:
        data: Dict[str, Any] = request.get_json(silent=True) or {}
        if data in ({}, None) or data.get("clear"):
            state = store.set_target(None)
            broker.publish_str(sse_wrap(state))
            return "", 204

        try:
            latlon = validate_latlon(data)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        r = data.get("radius_m")
        if r is not None:
            try:
                r = float(r)
                if r < 0:
                    return jsonify({"error": "radius_m must be >= 0"}), 400
            except Exception:
                return jsonify({"error": "radius_m must be numeric"}), 400

        target: Target = {**latlon}
        if r is not None:
            target["radius_m"] = r

        state = store.set_target(target)
        broker.publish_str(sse_wrap(state))
        return "", 204

    @app.post("/api/path")
    def api_path() -> Any:
        data: Dict[str, Any] = request.get_json(silent=True) or {}
        mode = str(data.get("mode", "replace")).strip().lower()
        if mode not in {"replace", "append"}:
            return jsonify({"error": "mode must be 'replace' or 'append'"}), 400

        points_raw = data.get("points")
        if not isinstance(points_raw, list):
            return jsonify({"error": "points must be a list of {lat,lon}"}), 400

        points: List[LatLon] = []
        try:
            for item in points_raw:
                points.append(validate_latlon(item))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        state = store.set_path(points, mode=mode)
        broker.publish_str(sse_wrap(state))
        return "", 204

    @app.get("/stream")
    def stream() -> Response:
        def event_stream(q: Queue[str]):
            try:
                while True:
                    try:
                        chunk = q.get(timeout=15.0)
                        yield chunk
                    except Empty:
                        yield ": keep-alive\n\n"
            finally:
                broker.unsubscribe(q)

        snapshot = sse_wrap(store.get())
        q = broker.subscribe(snapshot)
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return Response(event_stream(q), headers=headers)

    return app