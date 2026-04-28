"""CLI: ``python -m scrapers`` — use ``sync`` for a full refresh, or run one step."""

import argparse
import sys
from types import SimpleNamespace

from . import catalog, infer_terms, program_requirements, sections, session_dates


def _run_sync(args: argparse.Namespace) -> None:
    print("=== Catalog (all subjects) ===\n")
    catalog.run(
        SimpleNamespace(
            all_subjects=True,
            subject=None,
            backup_db=args.backup_db,
            db=args.db,
        )
    )

    print("\n=== Infer terms from degree maps ===\n")
    infer_terms.run(
        SimpleNamespace(
            db=args.db,
            falcon_url=infer_terms.DEFAULT_FALCON_URL,
            quiet=args.quiet,
        )
    )

    print("\n=== Sections ===\n")
    sections.run(
        SimpleNamespace(
            db=args.db,
            quiet=args.quiet,
        )
    )

    print("\n=== Session dates ===\n")
    session_dates.run(
        SimpleNamespace(
            db=args.db,
            calendar_url=session_dates.ACADEMIC_CALENDAR_URL,
            quiet=args.quiet,
        )
    )

    print("\nAll sync steps finished.")


def _print_root_help(exit_code: int = 0) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scrapers",
        description="UTPB course scrapers. Run `sync` from the project root for a full database refresh.",
    )
    parser.print_help()
    print(
        "\nCommands:\n"
        "  sync           Full pipeline: catalog --all-subjects, infer-terms, sections, session-dates\n"
        "  catalog        SmartCatalog -> courses table\n"
        "  program-requirements  SmartCatalog Programs of Study -> reviewable requirement tables\n"
        "  infer-terms    Degree map PDFs -> term_infered on courses\n"
        "  sections       Registrar schedules -> sections table\n"
        "  session-dates  Academic calendar -> session_calendar\n"
        "\n"
        "Each script-specific command accepts the same flags as before "
        "(see `python -m scrapers catalog -h`, etc.).\n"
        "Legacy entry points still work: scraper.py, infer_term_from_degree_maps.py, "
        "scrape_sections.py, scrape_session_dates.py.\n"
    )
    raise SystemExit(exit_code)


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        _print_root_help(0 if argv else 2)

    cmd, *rest = argv

    if cmd == "sync":
        p = argparse.ArgumentParser(prog="python -m scrapers sync", description="Run all scrapers in order.")
        p.add_argument("--db", default="data/courses.db", help="SQLite database path")
        p.add_argument("--quiet", action="store_true", help="Less log output for infer-terms, sections, session-dates")
        p.add_argument(
            "--backup-db",
            action="store_true",
            help="Before catalog writes, copy the whole DB file to data/archive/",
        )
        _run_sync(p.parse_args(rest))
        return

    if cmd == "catalog":
        catalog.main(rest)
        return
    if cmd == "program-requirements":
        program_requirements.main(rest)
        return
    if cmd == "infer-terms":
        infer_terms.main(rest)
        return
    if cmd == "sections":
        sections.main(rest)
        return
    if cmd == "session-dates":
        session_dates.main(rest)
        return

    print(f"Unknown command: {cmd}\n", file=sys.stderr)
    print("Try: python -m scrapers sync   or   python -m scrapers catalog -h", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
