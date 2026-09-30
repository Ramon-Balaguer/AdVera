"""advera-agent [--tray | --configure | --probe] [--backend-url URL] [--allow-remote-recording]

Without flags the agent runs headless in the console with the saved configuration.
`--backend-url` overrides the saved backend for this run only; nothing is written.
"""

import argparse
import asyncio
import json
import logging
import sys

from advera_agent import config
from advera_agent.capture import probe
from advera_agent.remote import RemoteAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="advera-agent", description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--tray", action="store_true", help="run as a Windows tray process")
    group.add_argument("--configure", action="store_true", help="open the configuration wizard")
    group.add_argument("--probe", action="store_true", help="print track capabilities and exit")
    parser.add_argument("--backend-url", help="backend for this run, e.g. http://localhost:18000")
    parser.add_argument(
        "--allow-remote-recording",
        action="store_true",
        help="in console mode, start recordings requested by the backend without asking",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.probe:
        print(json.dumps(probe(), indent=2, ensure_ascii=False))
        return 0
    if args.configure:
        from advera_agent.wizard import run_wizard

        run_wizard()
        return 0

    cfg = config.load()
    if args.backend_url:
        try:
            cfg.backend_url = config.normalize_url(args.backend_url)
        except config.ConfigError as error:
            print(f"Invalid --backend-url: {error.code}", file=sys.stderr)
            return 2
    if args.allow_remote_recording:
        cfg.consent = "always"
    if not cfg.configured:
        print(
            "The agent is not configured: run `python -m advera_agent --configure` "
            "or pass --backend-url",
            file=sys.stderr,
        )
        return 1
    try:
        health = config.check_health(cfg.backend_url)
    except config.ConfigError as error:
        # Keep running: the agent reconnects when the backend comes up, but say why now.
        health = error.code
    logging.getLogger("advera.agent").info("backend %s health: %s", cfg.backend_url, health)

    if args.tray:
        from advera_agent.tray import TrayApp

        TrayApp(cfg).run()
        return 0
    try:
        asyncio.run(RemoteAgent(cfg).run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
