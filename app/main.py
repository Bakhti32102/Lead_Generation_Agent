"""
AI Lead Generation Agent -- Main Entry Point.

Usage:
    python -m app.main                  # Show config + run interactive menu
    python -m app.main run              # Run daily campaign
    python -m app.main run --country Pakistan --city Lahore --category "Dental Clinics" --count 10
    python -m app.main followups        # Process due follow-ups
    python -m app.main dashboard        # Show today's dashboard
    python -m app.main web              # Start web dashboard
    python -m app.main schedule         # Start scheduler
    python -m app.main config           # Show configuration status
    python -m app.main status           # Show full status
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def setup_logging(level: str = "INFO") -> None:
    """Configure logging for the application."""
    from app.config.settings import LOG_DIR

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_date_format = "%Y-%m-%d %H:%M:%S"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter(log_format, log_date_format))

    # File handler
    from datetime import date
    log_file = LOG_DIR / f"agent_{date.today().isoformat()}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, log_date_format))

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Lead Generation & Outreach Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # run command
    run_parser = subparsers.add_parser("run", help="Run daily campaign")
    run_parser.add_argument("--country", default="", help="Target country")
    run_parser.add_argument("--city", default="", help="Target city")
    run_parser.add_argument("--category", default="", help="Business category")
    run_parser.add_argument("--count", type=int, default=0, help="Number of leads")
    run_parser.add_argument("--no-maps", action="store_true", help="Skip Google Maps search")
    run_parser.add_argument("--no-google", action="store_true", help="Skip Google Search")
    run_parser.add_argument("--no-linkedin", action="store_true", help="Skip LinkedIn search")
    run_parser.add_argument("--no-requirements", action="store_true", help="Skip recent requirements")

    # followups command
    subparsers.add_parser("followups", help="Process due follow-ups")

    # dashboard command
    subparsers.add_parser("dashboard", help="Show today's dashboard")

    # web command
    web_parser = subparsers.add_parser("web", help="Start web dashboard")
    web_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    web_parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    web_parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    # schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Start scheduler")
    schedule_parser.add_argument("--interval", type=int, default=24, help="Hours between campaigns")

    # config command
    subparsers.add_parser("config", help="Show configuration status")

    # status command
    subparsers.add_parser("status", help="Show full status with config and dashboard")

    # menu command (default)
    subparsers.add_parser("menu", help="Interactive management menu")

    args = parser.parse_args()

    # Setup
    from app.config.settings import settings
    setup_logging(settings.log_level)
    logger = logging.getLogger("main")

    # Import database init
    from app.database.models import init_db
    init_db()

    # Show config status
    from app.dashboard.terminal import (
        print_config_status,
        print_today_dashboard,
        interactive_menu,
    )

    if args.command == "run":
        print_config_status()
        from app.scheduler.daily_campaign import DailyCampaign
        campaign = DailyCampaign()
        summary = campaign.run(
            country=args.country,
            city=args.city,
            category=args.category,
            target_count=args.count,
            search_google_maps=not args.no_maps,
            search_google=not args.no_google,
            search_linkedin=not args.no_linkedin,
            search_recent_requirements=not args.no_requirements,
        )
        logger.info(f"Campaign finished: {summary['status']}")

    elif args.command == "followups":
        from app.scheduler.followups import FollowUpScheduler
        scheduler = FollowUpScheduler()
        results = scheduler.run()
        logger.info(f"Follow-ups processed: {results}")

    elif args.command == "dashboard":
        print_config_status()
        print_today_dashboard()

    elif args.command == "web":
        from app.dashboard.web import run_web_dashboard
        run_web_dashboard(host=args.host, port=args.port, debug=args.debug)

    elif args.command == "schedule":
        from app.scheduler.scheduler import LeadGenerationScheduler
        scheduler = LeadGenerationScheduler()
        scheduler.start(interval_hours=args.interval)

    elif args.command == "config":
        print_config_status()

    elif args.command == "status":
        print_config_status()
        print_today_dashboard()

    elif args.command == "menu":
        print_config_status()
        interactive_menu()

    else:
        # Default: show config and enter interactive menu
        print_config_status()
        interactive_menu()


if __name__ == "__main__":
    main()
