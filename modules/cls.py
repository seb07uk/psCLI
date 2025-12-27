import sys

META = {
    "name": "clear",
    "description": "Clears the terminal screen",
    "aliases": ["cls", "clear"],
    "group": "core",
    "category": "utility",
}

def run(args):
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    return 0
