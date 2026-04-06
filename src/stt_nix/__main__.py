import asyncio
import logging

from .daemon import Daemon


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    daemon = Daemon()
    asyncio.run(daemon.run())


if __name__ == "__main__":
    main()
