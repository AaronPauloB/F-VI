import urllib.parse
import requests
from colorama import init, Fore, Style
from tabulate import tabulate

# Initialize colorama
init(autoreset=True)

# MapQuest API
MAIN_API = "https://www.mapquestapi.com/directions/v2/route?"

# API Key
API_KEY = "EGVIJZBu6OlzjazQolRueK1VFVfoi30D"


def display_header():
    """Displays the application header."""
    print(Fore.CYAN + "=" * 60)
    print(Fore.CYAN + "           MAPQUEST ROUTE PLANNER")
    print(Fore.CYAN + "=" * 60)


def choose_unit():
    """Allows the user to select the distance unit."""

    while True:
        print("\nDistance Unit:")
        print("1. Kilometers (km)")
        print("2. Miles (mi)")

        choice = input("Choose an option [1/2]: ").strip()

        if choice == "1":
            return "km"

        elif choice == "2":
            return "mi"

        else:
            print(Fore.YELLOW + "Invalid choice. Please enter 1 or 2.")


def convert_distance(distance, unit):
    """
    Converts the distance returned by MapQuest.

    MapQuest returns distance in miles.
    """

    if unit == "km":
        return distance * 1.60934

    return distance


def display_route(orig, dest, route, unit):
    """Displays the route information in a formatted table."""

    unit_label = "km" if unit == "km" else "mi"

    # Total route information
    total_distance = convert_distance(route["distance"], unit)

    summary = [
        ["Starting Location", orig],
        ["Destination", dest],
        ["Travel Time", route["formattedTime"]],
        ["Total Distance", f"{total_distance:.2f} {unit_label}"]
    ]

    print("\n" + Fore.GREEN + "=" * 60)
    print(Fore.GREEN + "                    ROUTE SUMMARY")
    print(Fore.GREEN + "=" * 60)

    print(tabulate(summary, tablefmt="fancy_grid"))

    # Directions
    print("\n" + Fore.CYAN + "TURN-BY-TURN DIRECTIONS")
    print("=" * 60)

    directions = []

    for number, maneuver in enumerate(route["legs"][0]["maneuvers"], start=1):

        distance = convert_distance(maneuver["distance"], unit)

        directions.append([
            number,
            maneuver["narrative"],
            f"{distance:.2f} {unit_label}"
        ])

    print(
        tabulate(
            directions,
            headers=["#", "Instruction", "Distance"],
            tablefmt="grid"
        )
    )

    print(Fore.GREEN + "\nRoute successfully retrieved!\n")


def get_route(orig, dest, unit):
    """Requests route information from the MapQuest API."""

    params = {
        "key": API_KEY,
        "from": orig,
        "to": dest
    }

    url = MAIN_API + urllib.parse.urlencode(params)

    try:

        response = requests.get(url, timeout=10)

        # Raise an error for HTTP problems
        response.raise_for_status()

        json_data = response.json()

        json_status = json_data["info"]["statuscode"]

        if json_status == 0:

            print(Fore.GREEN + "\nAPI Status: 0 = Successful route call.")

            display_route(
                orig,
                dest,
                json_data["route"],
                unit
            )

        elif json_status == 402:

            print(Fore.RED + "\nInvalid input for one or both locations.")

        elif json_status == 611:

            print(Fore.RED + "\nMissing an entry for one or both locations.")

        else:

            print(
                Fore.RED +
                f"\nMapQuest returned status code: {json_status}"
            )

    except requests.exceptions.Timeout:

        print(
            Fore.RED +
            "\nError: The request timed out."
        )

    except requests.exceptions.ConnectionError:

        print(
            Fore.RED +
            "\nError: Unable to connect to the MapQuest API."
        )

    except requests.exceptions.RequestException as error:

        print(
            Fore.RED +
            f"\nRequest error: {error}"
        )

    except ValueError:

        print(
            Fore.RED +
            "\nError: Invalid response received from the API."
        )

    except KeyError:

        print(
            Fore.RED +
            "\nError: Unexpected data received from MapQuest."
        )


def main():
    """Main application loop."""

    display_header()

    print(
        Fore.WHITE +
        "Enter 'q' or 'quit' at any time to exit."
    )

    while True:

        print("\n" + "-" * 60)

        orig = input("Starting Location: ").strip()

        if orig.lower() in ["q", "quit"]:
            print(Fore.CYAN + "\nThank you for using MapQuest Route Planner!")
            break

        if not orig:
            print(Fore.YELLOW + "Starting location cannot be empty.")
            continue

        dest = input("Destination: ").strip()

        if dest.lower() in ["q", "quit"]:
            print(Fore.CYAN + "\nThank you for using MapQuest Route Planner!")
            break

        if not dest:
            print(Fore.YELLOW + "Destination cannot be empty.")
            continue

        unit = choose_unit()

        get_route(orig, dest, unit)


if __name__ == "__main__":
    main()