import sys
import os
import traceback

try:
    from colorama import Fore, Style, init as _colorama_init
    _colorama_init()
except Exception:
    # Minimal ANSI fallback if colorama isn't available
    class _C:
        RESET = "\u001b[0m"
        RED = "\u001b[31m"
        GREEN = "\u001b[32m"
        YELLOW = "\u001b[33m"
        CYAN = "\u001b[36m"

    class Fore:
        RED = _C.RED
        GREEN = _C.GREEN
        YELLOW = _C.YELLOW
        CYAN = _C.CYAN

    class Style:
        RESET_ALL = _C.RESET


META = {
    "name": "List",
    "description": "List files and modules with colored output",
    "aliases": ["list", "ls"],
    "args": ["[path]"],
    "category": "utility",
}


def _print(s, color=None, file=sys.stdout):
    try:
        if color:
            file.write(f"{color}{s}{Style.RESET_ALL}\n")
        else:
            file.write(s + "\n")
    except Exception:
        # last-resort plain print if write fails
        try:
            print(s, file=file)
        except Exception:
            pass


def run(args):
    """List files in a path (default: current directory).

    Usage: list [path]
    """
    try:
        target = args[0] if args else os.getcwd()
        if not os.path.exists(target):
            _print(f"Path not found: {target}", Fore.RED, sys.stderr)
            return 2

        if os.path.isfile(target):
            # print file info
            size = os.path.getsize(target)
            _print(f"File: {target}", Fore.CYAN)
            _print(f"Size: {size} bytes", Fore.YELLOW)
            return 0

        # directory: list entries
        entries = sorted(os.listdir(target))
        _print(f"Listing: {os.path.abspath(target)}", Fore.GREEN)
        if not entries:
            _print("(empty)", Fore.YELLOW)
            return 0

        for name in entries:
            full = os.path.join(target, name)
            try:
                if os.path.isdir(full):
                    _print(f"[DIR]  {name}", Fore.CYAN)
                elif os.access(full, os.X_OK):
                    _print(f"[EXE]  {name}", Fore.GREEN)
                else:
                    _print(f"[FILE] {name}", None)
            except Exception:
                _print(f"[ERR]  {name}", Fore.RED)

        return 0

    except Exception as e:
        # log traceback to stderr but keep user-friendly message
        _print("An unexpected error occurred while listing.", Fore.RED, sys.stderr)
        tb = traceback.format_exc()
        try:
            sys.stderr.write(tb + "\n")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    rc = run(sys.argv[1:])
    try:
        sys.exit(rc)
    except Exception:
        pass
