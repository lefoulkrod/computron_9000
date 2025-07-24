# flake8: noqa: T201
"""REPL for generate_completion using command-line input.

Allows toggling 'think' or 'no_think' mode.
"""

import asyncio
import logging
import pathlib
import sys

# Ensure project root is in sys.path for imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from config import load_config
from models import generate_completion, get_model_by_name

config = load_config()
logging.basicConfig(level=logging.DEBUG, format="%(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run REPL to call generate_completion with user input.

    Args:
        None

    Returns:
        None

    Raises:
        SystemExit: On invalid arguments or errors.
    """
    think: bool = False
    system_prompt: str | None = None
    model_name = config.settings.default_model

    GREEN = "\033[92m"
    END = "\033[0m"

    def green(text: str) -> str:
        return f"{GREEN}{text}{END}"

    print(green("Starting generate_completion REPL. Type /help for commands."))
    while True:
        try:
            user_input = input("\nEnter prompt (or /help): ").strip()
        except (EOFError, KeyboardInterrupt):
            print(green("Exiting REPL."))
            break
        if not user_input:
            continue
        if user_input.startswith("/"):
            cmd, *args_ = user_input[1:].split(maxsplit=1)
            arg = args_[0] if args_ else ""
            if cmd == "help":
                print(
                    green(
                        "Commands: /think, /nothink, /system <prompt>, /model <name>, /show, /exit"
                    )
                )
            elif cmd == "think":
                think = True
                print(green("Think mode enabled."))
            elif cmd == "nothink":
                think = False
                print(green("Think mode disabled."))
            elif cmd == "system":
                if arg:
                    system_prompt = arg
                    print(green("System prompt set."))
                else:
                    print(green(f"Current system prompt: {system_prompt}"))
            elif cmd == "model":
                if arg:
                    model_name = arg
                    print(green(f"Model set to: {model_name}"))
                else:
                    print(green(f"Current model: {model_name or 'default'}"))
            elif cmd == "show":
                print(
                    green(
                        f"think: {think}, system: {system_prompt}, model: {model_name or 'default'}"
                    )
                )
            elif cmd == "exit":
                print(green("Exiting REPL."))
                break
            else:
                print(green("Unknown command. Type /help for help."))
            continue
        # Generation
        model_obj = get_model_by_name(model_name)
        options = model_obj.options
        model = model_obj.model
        try:
            response, _ = await generate_completion(
                prompt=user_input,
                model=model,
                system=system_prompt,
                options=options,
                think=think,
            )
            print(green(f"Response: {response}"))
        except Exception as exc:
            print(green(f"Error generating completion: {exc}"))


if __name__ == "__main__":
    asyncio.run(main())
