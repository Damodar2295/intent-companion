"""Run with: python -m scripts.validate_seeds [--directory data]."""

import argparse
import json
from pathlib import Path

from agent.canonical.seeds import validate_seed_directory
from config.settings import ROOT


def main():
    parser = argparse.ArgumentParser(
        description="Validate canonical seed models and references without changing storage"
    )
    parser.add_argument("--directory", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    print(json.dumps(validate_seed_directory(args.directory), indent=2))


if __name__ == "__main__":
    main()
