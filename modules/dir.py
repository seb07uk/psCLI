try:
    from modules.dispatcher import color_text, GREEN, YELLOW, CYAN
except Exception:
    import sys, pathlib
    root_dir = pathlib.Path(__file__).resolve().parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    try:
        from modules.dispatcher import color_text, GREEN, YELLOW, CYAN
    except Exception:
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        CYAN = "\033[36m"
        def color_text(text: str, color: str) -> str:
            return text

try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
except Exception:
    console = None

import os
import pathlib
import fnmatch
from datetime import datetime
import ctypes

META = {
    "name": "dir",
    "description": "Windows-like directory listing with colored names",
    "aliases": [],
    "args": [
        {"name": "[path]", "help": "Path to list (default: current)", "required": False},
        {"name": "[pattern]", "help": "Wildcard filter (e.g. *.py)", "required": False},
        {"name": "[/drives]", "help": "List available drives", "required": False},
        {"name": "[/cd path]", "help": "Change working directory before listing", "required": False},
        {"name": "[/s]", "help": "Recursive listing", "required": False},
        {"name": "[/b]", "help": "Bare format (names only)", "required": False},
        {"name": "[/ah]", "help": "Show hidden items only", "required": False},
    ],
    "group": "core",
    "category": "utility",
}

def _color_for(entry: pathlib.Path) -> str:
    if entry.is_dir():
        return CYAN
    ext = entry.suffix.lower()
    if ext in (".exe", ".bat", ".cmd", ".ps1"):
        return GREEN
    if ext in (".zip", ".7z", ".rar", ".tar", ".gz"):
        return YELLOW
    return None

def _list_drives():
    # Get drive strings buffer
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.kernel32.GetLogicalDriveStringsW(ctypes.sizeof(buf), buf)
    drives = [d for d in buf[:].split("\x00") if d]
    # Classify
    type_map = {
        0: "Unknown",
        1: "NoRootDir",
        2: "Removable",
        3: "Fixed",
        4: "Remote",
        5: "CDROM",
        6: "RAMDisk",
    }
    result = []
    for d in drives:
        t = ctypes.windll.kernel32.GetDriveTypeW(d)
        result.append((d, type_map.get(t, "Unknown")))
    return result

def run(args):
    # flags: /drives, /cd PATH, /s, /b, /ah
    show_drives = any(a.lower() in ("/drives", "--drives") for a in args)
    if show_drives:
        drives = _list_drives()
        print("\n Available drives:\n")
        for root, kind in sorted(drives):
            disp = color_text(root, CYAN if kind in ("Fixed", "Removable", "CDROM") else YELLOW)
            print(f"  {disp}  ({kind})")
        return 0

    # handle change directory flag
    base = None
    pattern = None
    recursive = any(a.lower() in ("/s", "--s") for a in args)
    bare = any(a.lower() in ("/b", "--b") for a in args)
    only_hidden = any(a.lower() in ("/ah", "--ah") for a in args)
    i = 0
    while i < len(args):
        a = args[i]
        if a.lower() in ("/cd", "--cd"):
            if i + 1 < len(args):
                target = args[i + 1]
                # normalize drive-only into root
                if len(target) == 2 and target[1] == ":":
                    target = target + "\\"
                try:
                    os.chdir(target)
                except Exception as e:
                    print(f"Cannot change directory to '{target}': {e}")
                    return 1
                i += 2
                continue
        elif not (a.startswith("/") or a.startswith("--")) and base is None:
            # path argument
            p = a
            if len(p) == 2 and p[1] == ":":
                p = p + "\\"
            base = pathlib.Path(p).resolve()
        elif a.startswith("*") and pattern is None:
            pattern = a
        i += 1

    if base is None:
        base = pathlib.Path.cwd()
    if pattern is None and args and args[0] and args[0].startswith("*"):
        pattern = args[0]

    if not base.exists():
        print(f"File Not Found: {base}")
        return 1

    print(f"\n Directory of {str(base)}\n")

    def is_hidden(p: pathlib.Path) -> bool:
        try:
            attr = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            return bool(attr & 0x2)
        except Exception:
            return False

    def list_entries(path: pathlib.Path):
        lst = []
        for e in path.iterdir():
            if pattern and not fnmatch.fnmatch(e.name, pattern):
                continue
            if only_hidden and not is_hidden(e):
                continue
            lst.append(e)
        lst.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
        return lst

    entries = list_entries(base)

    if bare:
        def print_bare(path: pathlib.Path):
            for e in list_entries(path):
                print(str(e))
                if recursive and e.is_dir():
                    print_bare(e)
        print_bare(base)
    elif console:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Date")
        table.add_column("Type", width=6)
        table.add_column("Size", justify="right")
        table.add_column("Name")
        file_count = 0
        file_bytes = 0
        dir_count = 0
        for e in entries:
            try:
                stat = e.stat()
            except Exception:
                continue
            dt = datetime.fromtimestamp(stat.st_mtime).strftime("%m/%d/%Y  %I:%M %p")
            if e.is_dir():
                dir_count += 1
                kind = "<DIR>"
                size_part = ""
            else:
                file_count += 1
                file_bytes += stat.st_size
                kind = ""
                size_part = f"{stat.st_size}"
            color = CYAN if e.is_dir() else (GREEN if e.suffix.lower() in (".exe", ".bat", ".cmd", ".ps1") else (YELLOW if e.suffix.lower() in (".zip", ".7z", ".rar", ".tar", ".gz") else None))
            name_disp = color_text(e.name, color) if color else e.name
            table.add_row(dt, kind, size_part, name_disp)
            if recursive and e.is_dir():
                for root, dirs, files in os.walk(str(e)):
                    for fname in files:
                        fpath = pathlib.Path(root) / fname
                        try:
                            stat = fpath.stat()
                        except Exception:
                            continue
                        dt = datetime.fromtimestamp(stat.st_mtime).strftime("%m/%d/%Y  %I:%M %p")
                        file_count += 1
                        file_bytes += stat.st_size
                        table.add_row(dt, "", f"{stat.st_size}", str(fpath))
        console.print(table)
        free_bytes = 0
        try:
            free_val = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(str(base), None, None, ctypes.byref(free_val))
            free_bytes = free_val.value
        except Exception:
            free_bytes = 0
        print(f"             {file_count:>10} File(s)    {file_bytes:>14} bytes")
        print(f"             {dir_count:>10} Dir(s)     {free_bytes:>14} bytes free")
    else:
        file_count = 0
        file_bytes = 0
        dir_count = 0
        for e in entries:
            try:
                stat = e.stat()
            except Exception:
                continue
            dt = datetime.fromtimestamp(stat.st_mtime)
            ts = dt.strftime("%m/%d/%Y  %I:%M %p")
            if e.is_dir():
                dir_count += 1
                kind = "<DIR>"
                size_part = " " * 14
            else:
                file_count += 1
                file_bytes += stat.st_size
                kind = "     "
                size_part = f"{stat.st_size:>14}"
            color = CYAN if e.is_dir() else (GREEN if e.suffix.lower() in (".exe", ".bat", ".cmd", ".ps1") else (YELLOW if e.suffix.lower() in (".zip", ".7z", ".rar", ".tar", ".gz") else None))
            name = e.name
            name_disp = color_text(name, color) if color else name
            print(f"{ts}  {kind:5} {size_part} {name_disp}")
        free_bytes = 0
        try:
            free_val = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(str(base), None, None, ctypes.byref(free_val))
            free_bytes = free_val.value
        except Exception:
            free_bytes = 0
        print(f"             {file_count:>10} File(s)    {file_bytes:>14} bytes")
        print(f"             {dir_count:>10} Dir(s)     {free_bytes:>14} bytes free")

    return 0

if __name__ == "__main__":
    run([])
