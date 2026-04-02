"""Allow running as: python -m tools.compaction_eval"""

from .app import create_app

if __name__ == "__main__":
    import os

    from aiohttp import web

    port = int(os.environ.get("PORT", 8081))
    web.run_app(create_app(), port=port)
