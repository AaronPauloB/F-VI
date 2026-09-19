import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MAPQUEST_KEY = os.getenv("MAPQUEST_API_KEY", "").strip()
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "route_history.db")
MAPQUEST_ROUTE_URL = "https://www.mapquestapi.com/directions/v2/route"
MAPQUEST_ALTERNATE_URL = "https://www.mapquestapi.com/directions/v2/alternateroutes"
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

VALID_UNITS = {"k": "Kilometers", "m": "Miles"}
VALID_ROUTE_TYPES = {
    "fastest": "Fastest",
    "shortest": "Shortest",
    "pedestrian": "Walking",
    "bicycle": "Bicycle",
}
VALID_AVOIDS = {
    "Limited Access": "Highways",
    "Toll Road": "Toll Roads",
    "Ferry": "Ferries",
    "Unpaved": "Unpaved Roads",
    "Bridge": "Bridges",
    "Tunnel": "Tunnels",
    "Country Border Crossing": "Country Border Crossings",
}


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS route_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                unit TEXT NOT NULL,
                route_type TEXT NOT NULL,
                distance REAL,
                distance_unit TEXT,
                duration TEXT,
                toll_cost REAL,
                route_name TEXT,
                created_at TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def api_error(message, status=400, details=None):
    payload = {"success": False, "error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status


def validate_route_request(data):
    origin = str(data.get("origin", "")).strip()
    destination = str(data.get("destination", "")).strip()
    unit = str(data.get("unit", "k")).lower().strip()
    route_type = str(data.get("route_type", "fastest")).lower().strip()
    avoids = data.get("avoids", [])
    alternates = bool(data.get("alternates", False))

    if not origin:
        raise ValueError("Starting location is required.")
    if not destination:
        raise ValueError("Destination is required.")
    if len(origin) > 250 or len(destination) > 250:
        raise ValueError("Locations must be 250 characters or fewer.")
    if unit not in VALID_UNITS:
        raise ValueError("Invalid distance unit.")
    if route_type not in VALID_ROUTE_TYPES:
        raise ValueError("Invalid route type.")
    if not isinstance(avoids, list):
        raise ValueError("Avoidance options must be a list.")

    clean_avoids = []
    for value in avoids:
        if value in VALID_AVOIDS:
            clean_avoids.append(value)

    # MapQuest alternate routes only work for a single origin/destination pair,
    # which is exactly what this application accepts.
    return {
        "origin": origin,
        "destination": destination,
        "unit": unit,
        "route_type": route_type,
        "avoids": clean_avoids,
        "alternates": alternates,
    }


def request_mapquest(url, params):
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError("MapQuest request timed out. Please try again.") from exc
    except requests.RequestException as exc:
        raise RuntimeError("Could not connect to MapQuest. Check your internet connection and try again.") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("MapQuest returned an unreadable response.") from exc


def check_mapquest_status(payload):
    status_code = payload.get("info", {}).get("statuscode")
    if status_code not in (None, 0):
        messages = payload.get("info", {}).get("messages", [])
        details = "; ".join(str(item) for item in messages) if messages else None
        mapping = {
            402: "MapQuest could not resolve one or both locations.",
            611: "One or both locations are missing.",
        }
        raise RuntimeError(mapping.get(status_code, f"MapQuest returned status code {status_code}."))


def build_params(route_request):
    params = {
        "key": MAPQUEST_KEY,
        "from": route_request["origin"],
        "to": route_request["destination"],
        "unit": route_request["unit"],
        "routeType": route_request["route_type"],
        "narrativeType": "text",
        "enhancedNarrative": "true",
        "tollCost": "true",
        "fullShape": "true",
        "shapeFormat": "raw",
        "outFormat": "json",
    }
    if route_request["avoids"]:
        params["avoids"] = ",".join(route_request["avoids"])
    return params


def clean_shape(route):
    points = route.get("shape", {}).get("shapePoints", []) or route.get("shapePoints", [])
    result = []
    for index in range(0, len(points) - 1, 2):
        try:
            lat = float(points[index])
            lng = float(points[index + 1])
        except (TypeError, ValueError):
            continue
        result.append([lat, lng])
    return result


def route_summary(route, origin, destination, unit, route_type, route_name=None):
    summary = route.get("summary", {})
    distance = float(summary.get("distance", 0) or 0)
    raw_time = int(summary.get("time", 0) or 0)
    hours, remainder = divmod(raw_time, 3600)
    minutes = remainder // 60
    duration = f"{hours} hr {minutes} min" if hours else f"{minutes} min"

    toll_value = route.get("tollCost")
    try:
        toll_value = float(toll_value) if toll_value is not None else None
    except (TypeError, ValueError):
        toll_value = None

    maneuvers = []
    legs = route.get("legs", []) or []
    for leg in legs:
        for index, maneuver in enumerate(leg.get("maneuvers", []) or [], start=1):
            maneuvers.append(
                {
                    "number": len(maneuvers) + 1,
                    "narrative": maneuver.get("narrative", "Continue on the route."),
                    "distance": float(maneuver.get("distance", 0) or 0),
                    "time": int(maneuver.get("time", 0) or 0),
                    "direction": maneuver.get("directionName") or maneuver.get("direction"),
                    "street": ", ".join(maneuver.get("streets", []) or []),
                }
            )

    return {
        "origin": origin,
        "destination": destination,
        "route_name": route_name,
        "route_type": route_type,
        "route_type_label": VALID_ROUTE_TYPES[route_type],
        "unit": unit,
        "unit_label": VALID_UNITS[unit],
        "distance": round(distance, 2),
        "distance_unit": "km" if unit == "k" else "mi",
        "duration": duration,
        "duration_seconds": raw_time,
        "toll_cost_usd": toll_value,
        "has_toll_road": bool(route.get("hasTollRoad", False)),
        "has_ferry": bool(route.get("hasFerry", False)),
        "maneuvers": maneuvers,
        "shape": clean_shape(route),
        "raw": route,
    }


def save_history(route):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO route_history
            (origin, destination, unit, route_type, distance, distance_unit, duration,
             toll_cost, route_name, created_at, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                route["origin"],
                route["destination"],
                route["unit"],
                route["route_type"],
                route["distance"],
                route["distance_unit"],
                route["duration"],
                route["toll_cost_usd"],
                route.get("route_name"),
                datetime.now(timezone.utc).isoformat(),
                json.dumps(route),
            ),
        )
        conn.commit()


def get_route(route_request):
    params = build_params(route_request)
    payload = request_mapquest(MAPQUEST_ROUTE_URL, params)
    check_mapquest_status(payload)
    route = payload.get("route")
    if not route:
        raise RuntimeError("MapQuest returned no route data.")
    return route_summary(
        route,
        route_request["origin"],
        route_request["destination"],
        route_request["unit"],
        route_request["route_type"],
        route_name="Primary Route",
    )


def get_alternate_routes(route_request):
    params = build_params(route_request)
    params.update({"maxRoutes": 3, "timeOverage": 35})
    payload = request_mapquest(MAPQUEST_ALTERNATE_URL, params)
    status = payload.get("info", {}).get("statuscode")
    if status not in (None, 0):
        messages = payload.get("info", {}).get("messages", [])
        details = "; ".join(str(item) for item in messages) if messages else None
        raise RuntimeError(details or f"MapQuest alternate-routes service returned status code {status}.")

    raw_routes = payload.get("alternateRoutes") or []
    if not raw_routes and payload.get("route"):
        raw_routes = [payload["route"]]

    routes = []
    for index, route in enumerate(raw_routes, start=1):
        name = route.get("name") or f"Route {index}"
        routes.append(
            route_summary(
                route,
                route_request["origin"],
                route_request["destination"],
                route_request["unit"],
                route_request["route_type"],
                route_name=name,
            )
        )
    return routes


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {
            "success": True,
            "configured": bool(MAPQUEST_KEY),
            "service": "MapQuest Route Planner",
        }
    )


@app.post("/api/route")
def route_api():
    if not MAPQUEST_KEY:
        return api_error("MapQuest API key is not configured. Add MAPQUEST_API_KEY to your .env file.", 500)

    try:
        route_request = validate_route_request(request.get_json(silent=True) or {})
        primary = get_route(route_request)
        routes = [primary]
        if route_request["alternates"]:
            routes = get_alternate_routes(route_request)
            if not routes:
                routes = [primary]

        for route in routes:
            save_history(route)

        return jsonify(
            {
                "success": True,
                "routes": routes,
                "query": route_request,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except ValueError as exc:
        return api_error(str(exc), 400)
    except RuntimeError as exc:
        return api_error(str(exc), 502)
    except Exception as exc:
        app.logger.exception("Unexpected route error")
        return api_error("An unexpected server error occurred.", 500, str(exc) if app.debug else None)


@app.get("/api/history")
def history_api():
    limit = min(max(int(request.args.get("limit", 10)), 1), 50)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, origin, destination, unit, route_type, distance,
                   distance_unit, duration, toll_cost, route_name, created_at
            FROM route_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return jsonify({"success": True, "history": [dict(row) for row in rows]})


@app.delete("/api/history")
def clear_history_api():
    with get_db() as conn:
        conn.execute("DELETE FROM route_history")
        conn.commit()
    return jsonify({"success": True, "message": "Route history cleared."})


@app.get("/download/<path:filename>")
def download_file(filename):
    # Reserved for future exported report files.
    return send_from_directory(BASE_DIR, filename, as_attachment=True)


init_db()

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=debug)
