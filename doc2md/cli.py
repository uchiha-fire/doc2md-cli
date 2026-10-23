"""
CLI interface and interactive wizard for doc2md.
Zephyrus Labs (https://zephyrus-labs.tech/)
Lead Developer: Shubham Sharma
"""
import argparse
import json
import os
import sys
from typing import List, Optional

from doc2md import __version__
from doc2md.core import convert_to_markdown, DocumentResult

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    banner = f"""{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════════╗
║               doc2md-cli  v{__version__}                           ║
║     Universal Document to LLM-Optimized Markdown             ║
║     Zephyrus Labs (https://zephyrus-labs.tech/)              ║
╚══════════════════════════════════════════════════════════════╝{RESET}"""
    print(banner)


def display_conversion_summary(result: DocumentResult, out_dest: Optional[str] = None):
    print(f"\n{BOLD}Document Conversion Summary:{RESET}")
    print("-" * 65)
    print(f"  {BOLD}Source Format:{RESET}     {result.format.upper()}")
    print(f"  {BOLD}Pages / Slides:{RESET}    {result.total_pages}")
    print(f"  {BOLD}Total Words:{RESET}       {result.word_count:,}")
    print(f"  {BOLD}Estimated Tokens:{RESET}  {CYAN}~{result.estimated_tokens:,} tokens{RESET}")
    if result.chunks:
        print(f"  {BOLD}LLM Chunks:{RESET}        {len(result.chunks)} chunks")
    if out_dest:
        print(f"  {BOLD}Saved To:{RESET}          {GREEN}{out_dest}{RESET}")
    print("-" * 65 + "\n")


def run_interactive_wizard() -> int:
    print_banner()
    print(f"\n{BOLD}Welcome to the doc2md Interactive Converter Wizard!{RESET}\n")

    while True:
        file_path = input(f"{BOLD}Enter path to document (PDF, DOCX, PPTX, TXT):{RESET} ").strip()
        if not file_path or not os.path.exists(file_path):
            print(f"{RED}File not found: '{file_path}'. Please try again.{RESET}")
            continue
        break

    print(f"\n{BOLD}Select Output Mode:{RESET}")
    print("  [1] Print Markdown to terminal (stdout)")
    print("  [2] Save Markdown to file [Default]")
    print("  [3] Output JSON payload with token stats")

    mode_choice = input(f"{BOLD}Choose [1/2/3] (default: 2):{RESET} ").strip() or "2"

    out_file = None
    if mode_choice == "2":
        base, _ = os.path.splitext(file_path)
        default_out = f"{base}.md"
        out_file = input(f"{BOLD}Enter output markdown path (default: {default_out}):{RESET} ").strip() or default_out

    extract_tables_str = input(f"{BOLD}Format tables into Markdown pipe tables? [Y/n]:{RESET} ").strip().lower()
    extract_tables = extract_tables_str != "n"

    strip_headers_str = input(f"{BOLD}Strip repetitive header/footer boilerplate? [Y/n]:{RESET} ").strip().lower()
    strip_boilerplate = strip_headers_str != "n"

    chunk_size_str = input(f"{BOLD}Split into LLM chunk size in chars (optional, press Enter to skip):{RESET} ").strip()
    chunk_size = int(chunk_size_str) if chunk_size_str.isdigit() else None

    try:
        print(f"\n{CYAN}Converting document to token-optimized Markdown...{RESET}")
        res = convert_to_markdown(
            file_path,
            extract_tables=extract_tables,
            strip_boilerplate=strip_boilerplate,
            chunk_size=chunk_size,
        )

        if mode_choice == "1":
            print("\n" + "=" * 65)
            print(res.markdown_text)
            print("=" * 65)
            display_conversion_summary(res)
        elif mode_choice == "3":
            print(json.dumps(res.to_dict(), indent=2))
        else:
            os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(res.markdown_text)
            display_conversion_summary(res, out_dest=out_file)
            print(f"{GREEN}✓ Successfully converted and saved!{RESET}\n")

        return 0
    except Exception as e:
        print(f"{RED}Error converting document: {e}{RESET}")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or "--interactive" in argv or "-i" in argv:
        return run_interactive_wizard()

    parser = argparse.ArgumentParser(
        prog="doc2md",
        description="Universal Document to LLM-Optimized Markdown Converter by Zephyrus Labs",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Path to input document (.pdf, .docx, .pptx, .txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Destination markdown file path (defaults to stdout if omitted)",
    )
    parser.add_argument(
        "-t",
        "--no-tables",
        action="store_true",
        help="Disable pipe table formatting",
    )
    parser.add_argument(
        "-c",
        "--chunk-size",
        type=int,
        default=None,
        help="Split output into token-friendly character chunks",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output JSON payload with metadata, page count, and tokens",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress banner and summary messages",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Launch interactive configuration wizard",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"doc2md-cli {__version__} by Zephyrus Labs",
    )

    args = parser.parse_args(argv)

    if not args.input:
        return run_interactive_wizard()

    if not os.path.exists(args.input):
        print(f"{RED}Error: File '{args.input}' not found.{RESET}", file=sys.stderr)
        return 1

    try:
        res = convert_to_markdown(
            args.input,
            extract_tables=not args.no_tables,
            chunk_size=args.chunk_size,
        )

        if args.json:
            print(json.dumps(res.to_dict(), indent=2))
            return 0

        if args.output:
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(res.markdown_text)
            if not args.quiet:
                display_conversion_summary(res, out_dest=args.output)
        else:
            print(res.markdown_text)

        return 0
    except Exception as e:
        print(f"{RED}Error converting file: {e}{RESET}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
