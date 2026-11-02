"""Command-line entry point.

    python cli.py search         # keyword search + quick apply
    python cli.py filter         # jobs from FILTER_URL in .env + quick apply
    python cli.py recommended    # recommended-jobs page + chatbot drawer
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def main():
    parser = argparse.ArgumentParser(description="Naukri auto-apply agent")
    parser.add_argument("mode", choices=["search", "filter", "recommended"])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    # Imported lazily so each mode only requires the .env settings it uses
    if args.mode == "search":
        from naukri_agent import search
        search.run()
    elif args.mode == "filter":
        from naukri_agent import search
        search.run_filter()
    else:
        from naukri_agent import recommended
        recommended.main()


if __name__ == "__main__":
    main()
