import logging
import sys

def setup_logging():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    # Set httpx logger to WARNING level
    logging.getLogger("httpx").setLevel(logging.WARNING)
