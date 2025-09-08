import asyncio

async def good(urls):
    await asyncio.gather(*(asyncio.sleep(1) for _ in urls))
