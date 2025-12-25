META = {
    "name": "echo",
    "description": "Prints the passed arguments to stdout.",
    "aliases": {"say": "echo"},
    "args": [
        {"name": "text...", "help": "Text to output (can be multiple arguments).", "required": True}
    ],
    "group": "core",
    "category": "utility",
}


def run(args):
    """Prosty moduł przykładowy: wypisuje przekazane argumenty."""
    if not args:
        print("echo: (no args)")
        return 0
    print(" ".join(args))
    return 0
