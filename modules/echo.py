# echo.py
"""
echo module written in pure Python.
Added:
- colored output (ANSI)
- error handling
"""

# ANSI colors
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def run(args=None):
    """
    Main function of the module.
    It is called automatically by the system.
    """
    try:
        if not args:
            print(f"{YELLOW}Usage: e echo <text>{RESET}")
            return

        text = " ".join(args)
        print(f"{GREEN}{text}{RESET}")

    except Exception as e:
        print(f"{RED}An error occurred: {e}{RESET}")


def echo(text: str) -> str:
    """
    Helper function — returns the text.
    """
    return text