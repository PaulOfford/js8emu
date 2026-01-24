from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .config import load_config
from .server import JS8EmuServer


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="js8emu",
        description="JS8Emu: JS8Call service interface emulator for MbClient/MbServer development.",
    )
    p.add_argument("--config", default="config.ini", help="Path to config.ini (default: config.ini)")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Logging level (default: INFO)")
    p.add_argument("--verbose", action="store_true", help="Alias for --log-level DEBUG")
    p.add_argument("--dry-run", action="store_true", help="Validate config and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = _build_parser().parse_args(argv)

    level = "DEBUG" if args.verbose else args.log_level
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config(args.config)  # validates hard; raises on error
    if args.dry_run:
        logging.getLogger("js8emu").info("Config OK. Dry-run complete.")
        return 0

    server = JS8EmuServer(cfg)
    try:
        server.run_forever()
    except KeyboardInterrupt:
        logging.getLogger("js8emu").info("Interrupted; shutting down.")
    finally:
        server.close()

    return 0
