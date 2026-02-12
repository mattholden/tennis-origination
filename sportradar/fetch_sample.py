"""
Sample script: fetch competitions and seasons from Sportradar API.

Run from project root:
  uv run python -m sportradar.fetch_sample

Uses SPORTRADAR_API_KEY from .env. Writes sample JSON to sportradar/output/ if --write is passed.
"""

import argparse
import json
from pathlib import Path

from sportradar.client import SportradarClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Sportradar competitions and seasons")
    parser.add_argument("--write", action="store_true", help="Write JSON to sportradar/output/")
    args = parser.parse_args()

    client = SportradarClient()
    print("Fetching competitions...")
    competitions = client.get_competitions()
    print(f"  Got {len(competitions.get('competitions', []))} competitions, generated_at={competitions.get('generated_at')}")

    print("Fetching seasons...")
    seasons = client.get_seasons()
    print(f"  Got {len(seasons.get('seasons', []))} seasons, generated_at={seasons.get('generated_at')}")

    if args.write:
        out_dir = Path(__file__).resolve().parent / "output"
        out_dir.mkdir(exist_ok=True)
        for name, data in [("competitions", competitions), ("seasons", seasons)]:
            path = out_dir / f"sr_{name}.json"
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"  Wrote {path}")


if __name__ == "__main__":
    main()
