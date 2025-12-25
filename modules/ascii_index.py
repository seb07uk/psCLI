try:
    from modules.dispatcher import color_text, CYAN, YELLOW
except Exception:
    import sys
    import pathlib
    root_dir = pathlib.Path(__file__).resolve().parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    try:
        from modules.dispatcher import color_text, CYAN, YELLOW
    except Exception:
        CYAN = "\033[36m"
        YELLOW = "\033[33m"
        def color_text(text: str, color: str) -> str:
            return text

import pathlib

META = {
    "name": "ascii.index",
    "description": "Lists all .ascii files in the ascii directory",
    "aliases": ["ascii.list", "ai"],
    "group": "ASCII",
    "category": "System",
}

def run(args):
    root_dir = pathlib.Path(__file__).resolve().parent.parent
    ascii_dir = root_dir / "ascii"

    if not ascii_dir.exists() or not ascii_dir.is_dir():
        print(color_text("ASCII directory not found.", YELLOW))
        return 1

    files = sorted([f for f in ascii_dir.iterdir() if f.is_file() and f.suffix.lower() == ".ascii"])
    if not files:
        print(color_text("No .ascii files found.", YELLOW))
        return 0

    print(f"Found {len(files)} .ascii files:")
    print("-" * 40)

    for f in files:
        name = f.name
        preview = ""
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                # find first non-empty line for preview
                for line in fh:
                    s = line.strip()
                    if s:
                        preview = s
                        break
            if preview and len(preview) > 50:
                preview = preview[:47] + "..."
        except Exception:
            preview = ""

        name_colored = color_text(name, CYAN)
        if preview:
            print(f"{name_colored} - {preview}")
        else:
            print(f"{name_colored}")

    return 0

if __name__ == "__main__":
    run([])
