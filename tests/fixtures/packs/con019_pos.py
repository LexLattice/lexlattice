import asyncio

async def bad(urls):
    for u in urls:
        await asyncio.sleep(1)
