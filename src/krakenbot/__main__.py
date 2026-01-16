"""Package entry point for running KrakenBot as a module.

Allows running the bot via:
    python -m krakenbot

This module simply imports and runs the main() function from main.py.
"""

import asyncio

from krakenbot.main import main

if __name__ == "__main__":
    asyncio.run(main())
