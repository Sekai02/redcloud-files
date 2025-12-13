"""CLI entry point."""

import sys
import os

from common.logging_config import setup_logging
from cli.repl import repl_loop


def main() -> None:
    """Entry point for CLI."""
    log_level = 'DEBUG' if '--debug' in sys.argv else os.getenv('LOG_LEVEL', 'INFO')
    
    logger = setup_logging('cli', log_level=log_level)
    
    if '--debug' in sys.argv:
        logger.info("Debug logging enabled")
        sys.argv.remove('--debug')
    
    logger.info("CLI starting...")
    try:
        repl_loop()
    except Exception as e:
        logger.error(f"CLI error: {e}", exc_info=True)
        raise
    finally:
        logger.info("CLI exiting")


if __name__ == "__main__":
    main()
