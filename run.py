import asyncio
import sys

if __name__ == "__main__":
    import uvicorn

    if sys.platform == "win32":
        # asyncio.set_event_loop_policy() runs too late when uvicorn imports the app
        # lazily inside asyncio.run(). Explicitly create ProactorEventLoop first so
        # Patchright can call asyncio.create_subprocess_exec().
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)

        config = uvicorn.Config(
            "backend.main:app",
            host="127.0.0.1",
            port=8080,
            reload=False,   # reload spawns worker processes that lose the loop
            loop="none",    # tell uvicorn not to touch the event loop we just created
        )
        server = uvicorn.Server(config)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
    else:
        uvicorn.run("backend.main:app", host="127.0.0.1", port=8080, reload=False)
