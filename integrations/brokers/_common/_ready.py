"""READY sentinel for the broker -> supervisor startup handshake.

The broker prints ``READY\\n`` to stdout as its very first line of output after
successfully connecting upstream. The supervisor reads stdout line-by-line and
transitions the integration from ``pending`` to ``active`` on this line.

Brokers must not write to stdout before calling this function; any pre-READY
noise would be mistaken for the ready signal or for upstream data.
"""


def print_ready() -> None:
    """Emit the READY sentinel with an immediate flush."""
    print("READY", flush=True)
