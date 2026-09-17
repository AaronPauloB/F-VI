from flask import Flask, render_template, request
import requests

app = Flask(__name__)

MAIN_API = "https://www.mapquestapi.com/directions/v2/route"
API_KEY = "EGVIJZBu6OlzjazQolRueK1VFVfoi30D"


@app.route("/", methods=["GET", "POST"])
def index():

    # Default values
    orig = ""
    dest = ""
    unit = "km"

    route_info = None
    directions = []
    error = None

    if request.method == "POST":

        orig = request.form.get("origin", "").strip()
        dest = request.form.get("destination", "").strip()
        unit = request.form.get("unit", "km")

        # Check for empty input
        if not orig or not dest:
            error = "Please enter both a starting location and destination."

        else:

            params = {
                "key": API_KEY,
                "from": orig,
                "to": dest
            }

            try:

                response = requests.get(
                    MAIN_API,
                    params=params,
                    timeout=10
                )

                response.raise_for_status()

                data = response.json()

                status = data["info"]["statuscode"]

                # Successful request
                if status == 0:

                    route = data["route"]

                    # Convert total distance
                    if unit == "km":
                        total_distance = route["distance"] * 1.60934
                        unit_label = "km"
                    else:
                        total_distance = route["distance"]
                        unit_label = "mi"

                    # Store route information
                    route_info = {
                        "time": route["formattedTime"],
                        "distance": round(total_distance, 2),
                        "unit": unit_label
                    }

                    # Process directions
                    for maneuver in route["legs"][0]["maneuvers"]:

                        if unit == "km":
                            distance = maneuver["distance"] * 1.60934
                        else:
                            distance = maneuver["distance"]

                        directions.append({
                            "instruction": maneuver["narrative"],
                            "distance": round(distance, 2),
                            "unit": unit_label
                        })

                elif status == 402:

                    error = "Invalid input for one or both locations."

                elif status == 611:

                    error = "One or both locations are missing."

                else:

                    error = f"MapQuest returned status code {status}."

            except requests.exceptions.Timeout:

                error = "The request timed out."

            except requests.exceptions.ConnectionError:

                error = "Unable to connect to the MapQuest API."

            except requests.exceptions.RequestException as e:

                error = f"Request error: {e}"

            except (ValueError, KeyError):

                error = "Invalid response received from MapQuest."

    return render_template(
        "index.html",
        orig=orig,
        dest=dest,
        unit=unit,
        route_info=route_info,
        directions=directions,
        error=error
    )


if __name__ == "__main__":
    app.run(debug=True)