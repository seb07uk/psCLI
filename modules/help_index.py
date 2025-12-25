try:
    from modules.dispatcher import color_text, CYAN, GREEN, YELLOW
except Exception:
    import sys
    import pathlib
    root_dir = pathlib.Path(__file__).resolve().parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    try:
        from modules.dispatcher import color_text, CYAN, GREEN, YELLOW
    except Exception:
        RESET = "\033[0m"
        CYAN = "\033[36m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        def color_text(text: str, color: str) -> str:
            return text
import pathlib

META = {
    "name": "help.index",
    "description": "Lists all available .help files in the help directory",
    "aliases": ["help.list", "hl"],
    "group": "Help",
    "category": "System"
}

def run(args):
    """Skanuje katalog help i wyświetla listę plików .help."""
    # Katalog help znajduje się dwa poziomy wyżej niż ten plik (modules/help_index.py -> modules -> root -> help)
    root_dir = pathlib.Path(__file__).resolve().parent.parent
    help_dir = root_dir / "help"

    if not help_dir.exists() or not help_dir.is_dir():
        print(color_text("Help directory not found.", YELLOW))
        return 1

    help_files = sorted([f for f in help_dir.iterdir() if f.is_file() and f.name.lower().endswith(".help")])

    if not help_files:
        print(color_text("No help files found.", YELLOW))
        return 0

    print(f"Found {len(help_files)} help files:")
    print("-" * 40)
    
    for f in help_files:
        name = f.name
        # Spróbuj odczytać metadata lub pierwszą linię jako opis
        desc = ""
        try:
            with f.open("r", encoding="utf-8") as fh:
                content = fh.read()
                lines = content.splitlines()
                
                # Check for frontmatter
                if lines and lines[0].strip() == "---":
                    meta = {}
                    for i in range(1, len(lines)):
                        line = lines[i].strip()
                        if line == "---":
                            break
                        if ":" in line:
                            key, val = line.split(":", 1)
                            meta[key.strip().lower()] = val.strip()
                    
                    if "description" in meta:
                        desc = meta["description"]
                    elif "desc" in meta:
                        desc = meta["desc"]
                
                # Fallback to first line if no description in metadata
                if not desc:
                    # If we had frontmatter, skip it to find content
                    start_idx = 0
                    if lines and lines[0].strip() == "---":
                         for i in range(1, len(lines)):
                             if lines[i].strip() == "---":
                                 start_idx = i + 1
                                 break
                    
                    # Find first non-empty line
                    for i in range(start_idx, len(lines)):
                        line = lines[i].strip()
                        if line:
                            desc = line
                            break

                if desc:
                    # Jeśli linia jest długa, przytnij ją
                    if len(desc) > 50:
                        desc = desc[:47] + "..."
        except Exception:
            pass
            
        name_colored = color_text(name, CYAN)
        if desc:
            print(f"{name_colored} - {desc}")
        else:
            print(f"{name_colored}")

    return 0
