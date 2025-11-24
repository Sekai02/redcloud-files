"""CLI entry point."""

from cli.repl import repl_loop


def main() -> None:
    """Entry point for CLI."""
    repl_loop()


if __name__ == "__main__":
    main()
