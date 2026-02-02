"""Command-line entrypoint for the carbon governor daemon."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
from collections.abc import Sequence
from pathlib import Path

from carbon_ops.governor.rapl import RaplTopologyConfig
from carbon_ops.governor.runtime import run_governor

LOGGER = logging.getLogger("carbon_ops.governor.daemon")


def _parse_octal(value: str) -> int:
    """Parse a base-8 integer string.

    Args:
        value: String representing an octal number.

    Returns:
        Parsed integer value.

    Raises:
        argparse.ArgumentTypeError: If ``value`` is not a valid octal string.
    """

    try:
        return int(value, 8)
    except ValueError as exc:  # pragma: no cover - argparse will surface error
        raise argparse.ArgumentTypeError(f"Invalid octal value: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the daemon CLI.

    Returns:
        Configured :class:`argparse.ArgumentParser` instance.
    """

    parser = argparse.ArgumentParser(description="Privileged carbon governor daemon")
    parser.add_argument(
        "--powercap-root",
        type=Path,
        default=Path("/sys/class/powercap"),
        help="Base path for RAPL counters (default: /sys/class/powercap)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Polling interval in seconds (default: 0.1)",
    )
    parser.add_argument(
        "--socket-path",
        type=Path,
        default=Path("/var/run/carbon-ops.sock"),
        help="Unix domain socket exposed to unprivileged clients.",
    )
    parser.add_argument(
        "--socket-group",
        default="carbon-users",
        help="POSIX group granted access to the Unix domain socket.",
    )
    parser.add_argument(
        "--socket-mode",
        type=_parse_octal,
        default=0o660,
        help="File mode (octal) applied to the socket (default: 660).",
    )
    parser.add_argument(
        "--disable-ipc",
        action="store_true",
        help="Run the polling loop without exposing the Unix domain socket.",
    )
    parser.add_argument(
        "--rapl-mode",
        choices=("sysfs", "msr"),
        default="sysfs",
        help="RAPL polling mode: sysfs (default) or msr for raw MSR reads.",
    )
    parser.add_argument(
        "--msr-cpus",
        type=str,
        default=None,
        help="Comma-separated CPU indices for MSR mode (default: all online CPUs).",
    )
    return parser


async def _run_async(args: argparse.Namespace) -> None:
    """Execute the governor runtime using parsed arguments.

    Args:
        args: Parsed command-line arguments.
    """

    msr_cpus = None
    if args.msr_cpus:
        try:
            msr_cpus = [int(token) for token in args.msr_cpus.split(",") if token]
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Invalid --msr-cpus value: {args.msr_cpus}"
            ) from exc

    config = RaplTopologyConfig(
        base_path=args.powercap_root,
        mode=args.rapl_mode,
        msr_cpus=msr_cpus,
    )
    socket_path: Path | None = None if args.disable_ipc else args.socket_path
    group_name: str | None = None if args.disable_ipc else args.socket_group

    await run_governor(
        config=config,
        poll_interval=args.poll_interval,
        socket_path=socket_path,
        group_name=group_name,
        socket_mode=args.socket_mode,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m carbon_ops.governor.daemon``.

    Args:
        argv: Optional argument list override.

    Returns:
        Exit status code (``0`` for success).
    """

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    stop_event = asyncio.Event()

    def _handle_signal(
        signum: int, _frame: object | None
    ) -> None:  # pragma: no cover - signal handling
        LOGGER.info("Received signal", extra={"signal": signum})
        stop_event.set()

    def _fallback_signal_handler(
        signum: int, frame: object | None
    ) -> None:  # pragma: no cover - signal handling
        _handle_signal(signum, frame)

    for sig in (
        signal.SIGTERM,
        signal.SIGINT,
    ):  # pragma: no cover - not triggered in tests
        try:
            loop.add_signal_handler(sig, _handle_signal, sig, None)
        except NotImplementedError:
            signal.signal(sig, _fallback_signal_handler)

    async def runner() -> None:
        main_task = asyncio.create_task(_run_async(args), name="carbon-governor-main")
        stop_task = asyncio.create_task(stop_event.wait(), name="carbon-governor-stop")

        done, pending = await asyncio.wait(
            {main_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )

        if stop_task in done and not main_task.done():
            main_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await main_task

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    try:
        loop.run_until_complete(runner())
    except KeyboardInterrupt:  # pragma: no cover - already handled by signal handler
        pass
    except Exception as exc:
        LOGGER.error("Governor terminated with error", exc_info=exc)
        return 1
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
