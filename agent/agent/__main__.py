"""advera-agent [--tray | --configure | --probe]

Without flags the agent runs headless in the console with the saved configuration.
"""

import argparse
import asyncio
import json
import logging
import sys

from agent import config
from agent.capture import probe
from agent.remote import RemoteAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="advera-agent", description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tray", action="store_true", help="run as a Windows tray process")
    group.add_argument("--configure", action="store_true", help="open the configuration wizard")
    group.add_argument("--probe", action="store_true", help="print track capabilities and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.probe:
        print(json.dumps(probe(), indent=2, ensure_ascii=False))
        return 0
    if args.configure:
        from agent.wizard import run_wizard

        run_wizard()
        return 0
    if args.tray:
        from agent.tray import TrayApp

        TrayApp().run()
        return 0

    cfg = config.load()
    if not cfg.configured:
        print("The agent is not configured: run `python -m agent --configure`", file=sys.stderr)
        return 1
    try:
        asyncio.run(RemoteAgent(cfg).run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
