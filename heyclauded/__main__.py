import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from dbus_fast import BusType, RequestNameReply
from dbus_fast.aio import MessageBus

from . import BUS_NAME, OBJECT_PATH, __version__
from .config import load
from .daemon import Daemon, HeyClaudeInterface

log = logging.getLogger("heyclauded")


async def run(config_path: Path | None) -> int:
    cfg = load(config_path)
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    daemon = Daemon(cfg)
    bus.export(OBJECT_PATH, HeyClaudeInterface(daemon))
    reply = await bus.request_name(BUS_NAME)
    if reply != RequestNameReply.PRIMARY_OWNER:
        log.error("%s is already owned — daemon already running?", BUS_NAME)
        return 1
    log.info("heyclauded %s up on %s", __version__, BUS_NAME)

    if cfg.preload_stt:
        asyncio.ensure_future(daemon.stt.preload())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, daemon.stopped.set)

    await daemon.stopped.wait()
    log.info("shutting down")
    await daemon.cancel()
    bus.disconnect()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="heyclauded")
    ap.add_argument("--config", type=Path, default=None,
                    help="config file (default: ~/.config/hey-claude/config.toml)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    sys.exit(asyncio.run(run(args.config)))


if __name__ == "__main__":
    main()
