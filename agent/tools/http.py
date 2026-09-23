"""Cancel request-scoped provider tasks if the HTTP caller disconnects."""

import asyncio

from fastapi import HTTPException


async def execute_connected(orchestrator, body, request):
    stopped = asyncio.Event()

    async def disconnected():
        while not stopped.is_set():
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    work = asyncio.create_task(orchestrator.execute(body))
    monitor = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait({work, monitor}, return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            return work.result()
        raise HTTPException(499, "Client disconnected; tool execution cancelled.")
    finally:
        stopped.set()
        for task in (work, monitor):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, monitor, return_exceptions=True)
