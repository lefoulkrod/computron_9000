"""REPL for running bash commands in the virtual computer container."""

import asyncio
import logging

from pydantic import ValidationError

from tools.virtual_computer.run_bash_cmd import RunBashCmdError, run_bash_cmd

logger = logging.getLogger(__name__)


def main() -> None:
    """Run a REPL to execute bash commands in the virtual computer container.

    Prompts the user for a bash command, executes it, and prints the result.
    """
    print("Virtual Computer Bash REPL. Type 'exit' or 'quit' to leave.")
    while True:
        try:
            cmd = input("bash> ").strip()
            if cmd.lower() in {"exit", "quit"}:
                print("Exiting REPL.")
                break
            if not cmd:
                continue
            result = asyncio.run(run_bash_cmd(cmd))
            print("--- Result ---")
            print(f"Exit code: {result.exit_code}")
            print(f"Stdout:\n{result.stdout}")
            print(f"Stderr:\n{result.stderr}")
        except RunBashCmdError as exc:
            print(f"Command failed: {exc}")
        except ValidationError as exc:
            print(f"Validation error: {exc}")
        except (KeyboardInterrupt, EOFError):
            print("Exiting REPL.")
            break
        except Exception as exc:
            print(f"Unexpected error: {exc}")


if __name__ == "__main__":
    main()
