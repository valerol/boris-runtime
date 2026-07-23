import argparse
import json
import sys

from core_surface.errors import CoreSurfaceError
from core_surface.loader import load_core_surface


def main():
    parser = argparse.ArgumentParser(
        description="Validate and inspect a versioned BOIS Core Surface package."
    )
    parser.add_argument("source", help="Path to a package directory or ZIP archive.")
    parser.add_argument(
        "--purpose",
        choices=("evaluation", "active"),
        default="evaluation",
        help="Requested lifecycle use. Candidate packages are evaluation-only.",
    )
    args = parser.parse_args()

    try:
        surface = load_core_surface(args.source, purpose=args.purpose)
    except CoreSurfaceError as exc:
        print(json.dumps({
            "status": "REJECTED",
            "error": exc.__class__.__name__,
            "detail": str(exc),
        }, indent=2), file=sys.stderr)
        return 2

    print(json.dumps({
        "status": "ACCEPTED",
        "surface": surface.summary(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
