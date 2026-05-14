"""Entry point: start asyncio loop, bootstrap service, expose DBus interface."""

from __future__ import annotations

import asyncio
import signal
import sys

from backend.dbus.dbus_server import OBJECT_PATH, SERVICE_NAME, serve
from backend.service.vpn_service import VpnService


async def main() -> int:
    svc = VpnService()
    await svc.bootstrap()

    bus = await serve(svc)
    print(
        f"[info] Noctalia VPN backend ready on session bus: {SERVICE_NAME} {OBJECT_PATH}",
        flush=True,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _shutdown(*_: object) -> None:
        if not stop_event.is_set():
            print("[info] shutdown signal received", flush=True)
            stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    disconnect_task = asyncio.create_task(bus.wait_for_disconnect())
    stop_task = asyncio.create_task(stop_event.wait())
    done, _ = await asyncio.wait(
        {disconnect_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for t in (disconnect_task, stop_task):
        if not t.done():
            t.cancel()
    # surface any disconnect exception
    if disconnect_task in done and not disconnect_task.cancelled():
        exc = disconnect_task.exception()
        if exc:
            print(f"[error] bus disconnected: {exc}", flush=True)

    print("[info] shutting down VPN service", flush=True)
    try:
        await svc.shutdown()
    except Exception as exc:
        print(f"[error] shutdown error: {exc}", flush=True)
    try:
        bus.disconnect()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
