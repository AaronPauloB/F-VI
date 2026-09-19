import os
import tempfile
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def make_test_db(tmp_path):
    return tmp_path / "test.db"


def fake_route_payload():
    return {
        "info": {"statuscode": 0, "messages": []},
        "route": {
            "summary": {"distance": 10.5, "time": 3600},
            "tollCost": 1.5,
            "hasTollRoad": True,
            "shape": {"shapePoints": [14.60, 120.98, 14.61, 121.00]},
            "legs": [{
                "maneuvers": [
                    {"narrative": "Head east.", "distance": 2.5, "time": 600, "streets": ["Example St"]},
                    {"narrative": "Turn right.", "distance": 8.0, "time": 3000, "streets": ["Demo Ave"]},
                ]
            }],
        },
    }


def test_validate_route_request():
    result = app.validate_route_request({
        "origin": "A",
        "destination": "B",
        "unit": "k",
        "route_type": "fastest",
        "avoids": ["Toll Road", "invalid"],
        "alternates": True,
    })
    assert result["avoids"] == ["Toll Road"]
    assert result["alternates"] is True


def test_route_api_returns_normalized_result(tmp_path):
    old_key = app.MAPQUEST_KEY
    old_db = app.DATABASE_PATH
    app.MAPQUEST_KEY = "test-key"
    app.DATABASE_PATH = make_test_db(tmp_path)
    app.init_db()

    try:
        with patch("app.request_mapquest", return_value=fake_route_payload()):
            client = app.app.test_client()
            response = client.post("/api/route", json={
                "origin": "A",
                "destination": "B",
                "unit": "k",
                "route_type": "fastest",
                "avoids": [],
                "alternates": False,
            })
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["routes"][0]["distance"] == 10.5
        assert data["routes"][0]["distance_unit"] == "km"
        assert len(data["routes"][0]["maneuvers"]) == 2
    finally:
        app.MAPQUEST_KEY = old_key
        app.DATABASE_PATH = old_db
