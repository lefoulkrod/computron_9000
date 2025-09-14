import asyncio
import signal

import pytest

from utils.shutdown import (
    register_shutdown,
    _registered_callbacks as registered_callbacks,
    _run_shutdown_handlers as run_shutdown_handlers,
    _shutdown_has_run as shutdown_has_run,
    _trigger_shutdown as trigger_shutdown,
    _unregister_shutdown as unregister_shutdown,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_and_run_async_handler():
    order = []

    async def a():
        await asyncio.sleep(0)
        order.append("a")

    register_shutdown(a, name="a", priority=1)
    assert "a" in registered_callbacks()

    await run_shutdown_handlers()
    assert order == ["a"]
    assert shutdown_has_run() is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_priority_and_multiple_handlers():
    ran = []

    async def hi():
        ran.append("hi")

    def lo():
        ran.append("lo")

    register_shutdown(lo, name="lo", priority=0)
    register_shutdown(hi, name="hi", priority=10)

    await run_shutdown_handlers()
    # hi has higher priority, runs first
    assert ran == ["hi", "lo"]


@pytest.mark.unit
def test_trigger_shutdown_blocks():
    # This should not raise even if called multiple times
    trigger_shutdown(block=True, timeout=1)
    trigger_shutdown(block=True, timeout=1)


@pytest.mark.unit
def test_unregister():
    def f():
        pass

    name = register_shutdown(f, name="f")
    assert name in registered_callbacks()
    assert unregister_shutdown(name) is True
    assert name not in registered_callbacks()
