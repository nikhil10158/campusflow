import argparse

from app import db
from app.seed import load


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the CampusFlow database with synthetic data")
    parser.add_argument("--regenerate", action="store_true", help="rebuild data/seed/baseline.json from the generator")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the database before loading")
    args = parser.parse_args()
    if args.regenerate:
        load.dump_rows(load.generate_rows())
        print(f"baseline written to {load.BASELINE_PATH}")
    load.seed_database(rebuild=args.reset)
    print(f"database ready at {db.get_engine().url}")


if __name__ == "__main__":
    main()
