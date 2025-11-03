# run_local.py
import argparse
from publishers.wiley_library import process_wiley_library

def main():
    parser = argparse.ArgumentParser(description="Run Wiley OA PDF downloader locally")
    parser.add_argument("--keywords", nargs="+", default=["climate", "action"],
                        help="List of search keywords")
    parser.add_argument("--start-page", type=int, default=1, help="SRU start page")
    args = parser.parse_args()

    processed, total, next_page = process_wiley_library(
        keywords=args.keywords,
        start_page=args.start_page
    )
    print(f"✅ Done. Inserted/processed: {total}. Next page pointer: {next_page}")

if __name__ == "__main__":
    main()
