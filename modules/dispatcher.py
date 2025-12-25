import importlib
import pathlib
import sys
import traceback
import subprocess
import logging
from typing import Any, Callable, Dict, List
import threading
import time
from typing import Optional, Set, Tuple
import shutil

# kolorowy output (opcjonalnie używa colorama jeśli dostępne)
try:
    import colorama

    colorama.init()
    RESET = colorama.Style.RESET_ALL
    RED = colorama.Fore.RED
    GREEN = colorama.Fore.GREEN
    YELLOW = colorama.Fore.YELLOW
    CYAN = colorama.Fore.CYAN
except Exception:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"


def color_text(text: str, color: str) -> str:
    try:
        return f"{color}{text}{RESET}"
    except Exception:
        return text


# setup file logger in user's profile
try:
    _log_dir = pathlib.Path.home() / ".polsoft" / "log"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / "pscCLI.log"
    _logger = logging.getLogger("pscli")
    # Only attach a file handler if the log file already exists; do not create new logs.
    if _log_file.exists():
        if not _logger.handlers:
            fh = logging.FileHandler(str(_log_file), encoding="utf-8", mode="a")
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            fh.setFormatter(fmt)
            _logger.addHandler(fh)
            _logger.setLevel(logging.INFO)
        # write session header
        try:
            with _log_file.open("a", encoding="utf-8") as _lf:
                _lf.write("[NEW SESSION]\n")
        except Exception:
            pass
    else:
        # do not create the file; keep a no-op logger
        _logger = logging.getLogger("pscli")
    # setup error report file (always available) and attach error-level handler
    try:
        _err_dir = pathlib.Path.home() / ".polsoft" / "error"
        _err_dir.mkdir(parents=True, exist_ok=True)
        _err_file = _err_dir / "pscCLIerror.txt"
        # attach an ERROR-level file handler to _logger (create file if missing)
        exists = any(
            isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '') == str(_err_file)
            for h in _logger.handlers
        )
        if not exists:
            fh_err = logging.FileHandler(str(_err_file), encoding="utf-8", mode="a")
            fh_err.setLevel(logging.ERROR)
            fmt_err = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            fh_err.setFormatter(fmt_err)
            _logger.addHandler(fh_err)
    except Exception:
        pass
    # ensure uncaught exceptions are written to error file as well
    try:
        def _handle_uncaught(exc_type, exc_value, exc_tb):
            try:
                _logger.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
            except Exception:
                try:
                    import traceback, sys
                    with (_err_file.open('a', encoding='utf-8') if ' _err_file' in locals() else open('pscCLIerror.txt','a',encoding='utf-8')) as fh:
                        fh.write('\n=== UNCAUGHT EXCEPTION %s ===\n' % __import__('datetime').datetime.now().isoformat())
                        traceback.print_exception(exc_type, exc_value, exc_tb, file=fh)
                except Exception:
                    pass
        sys.excepthook = _handle_uncaught
    except Exception:
        pass
except Exception:
    _logger = logging.getLogger("pscli")


class DispatcherError(Exception):
    pass


class ModuleLoadError(DispatcherError):
    pass


class CommandNotFoundError(DispatcherError):
    pass


class EntryPointError(DispatcherError):
    pass


class Dispatcher:
    """Prosty dispatcher ładujący moduły z katalogu `modules` i obsługujący aliasy.

    Moduł w `modules/<name>.py` powinien udostępniać jedną z funkcji wejściowych:
    `run(args)`, `main(args)` lub `cli(args)`.
    Można też zarejestrować bezpośrednio callable przez `register_module`.
    """

    def __init__(self, modules_pkg: str = "modules", root: str = None):
        # root: katalog główny projektu; jeśli None, ustawiamy na parent katalogu `modules/`
        if root:
            self.root = pathlib.Path(root).resolve()
        else:
            # modules/dispatcher.py -> parent (modules) -> parent (project root)
            self.root = pathlib.Path(__file__).resolve().parent.parent

        self.modules_pkg = modules_pkg
        # katalog z modułami jako Path (jeśli modules_pkg jest względne, szukamy względem root)
        modules_path = pathlib.Path(modules_pkg)
        if not modules_path.is_absolute():
            self.modules_dir = (self.root / modules_pkg).resolve()
        else:
            self.modules_dir = modules_path.resolve()

        self.aliases: Dict[str, str] = {}
        self._modules_cache: Dict[str, Any] = {}
        self._callables: Dict[str, Callable[..., Any]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        # mapowanie z nazwy z META -> filename (module key)
        self._meta_name_map: Dict[str, str] = {}
        # mapowanie module name -> path (uwzględnia .py/.cmd/.exe)
        self._module_files: Dict[str, str] = {}

        # przy inicjalizacji spróbuj wczytać domyślny plik aliases.json z root
        try:
            self.load_aliases(str(self.root / "aliases.json"))
        except Exception:
            # nie przerywamy działania jeśli plik nie istnieje lub jest niepoprawny
            pass

        # spróbuj załadować metadata dostępnych modułów
        try:
            self.refresh_metadata()
        except Exception:
            # nie blokujemy startu, metadata jest dodatkowa
            pass
        # user settings file under %USERPROFILE%/.polsoft/settings/psCLI.json
        try:
            home = pathlib.Path.home()
            self.user_settings_file = (home / ".polsoft" / "settings" / "psCLI.json").resolve()
        except Exception:
            self.user_settings_file = (self.root / "psCLI.user.json").resolve()

        # load user settings (aliases override previously loaded ones)
        try:
            self.load_user_settings()
        except Exception:
            pass

        # watcher
        self._watch_thread: Optional[threading.Thread] = None
        self._watch_stop: Optional[threading.Event] = None
        # katalog na pliki metadata (companion files)
        self.metadata_dir = (self.root / "metadata").resolve()
        try:
            _logger.info(f"Dispatcher initialized; root={self.root} modules_dir={self.modules_dir}")
        except Exception:
            pass

    def discover(self) -> List[str]:
        p = self.modules_dir
        if not p.exists():
            return []
        results: List[str] = []
        self._module_files = {}
        for f in p.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() in (".py", ".cmd", ".exe", ".bat", ".ps1", ".vbs", ".reg") and f.stem != "__init__":
                name = f.stem
                results.append(name)
                # store full path as string
                self._module_files[name] = str(f.resolve())
        return sorted(results)

    def _module_exists(self, name: str) -> bool:
        # check known file mapping first
        if name in self._module_files:
            return True
        path_py = self.modules_dir / f"{name}.py"
        return path_py.exists()

    def load(self, name: str) -> Any:
        # najpierw sprawdź czy zarejestrowano callable bezpośrednio
        if name in self._callables:
            return self._callables[name]

        if name in self._modules_cache:
            return self._modules_cache[name]

        try:
            # jeśli mamy przypisany plik i to nie jest .py, zwróć ścieżkę (uruchomienie zewnętrzne)
            file_path = self._module_files.get(name)
            if file_path:
                p = pathlib.Path(file_path)
                if p.suffix.lower() != ".py":
                    # zwracamy ścieżkę jako sygnal, że moduł jest zewnętrzny
                    self._modules_cache[name] = p
                    return p

            mod = importlib.import_module(f"{self.modules_pkg}.{name}")
            self._modules_cache[name] = mod
            return mod
        except Exception as e:
            try:
                _logger.exception(f"Cannot load module {name}: {e}")
            except Exception:
                pass
            raise ModuleLoadError(f"Cannot load module '{name}': {e}")

    def register_alias(self, alias: str, target: str) -> None:
        self.aliases[alias] = target
        try:
            self.save_user_settings()
        except Exception:
            pass

    def load_aliases(self, path: str) -> None:
        """Wczytuje aliasy z pliku JSON.

        Obsługiwane formaty:
        - Prosty mapping: { "e": "echo", "ls": "list" }
        - Zawinięty pod kluczem `aliases`: { "aliases": { ... } }
        """
        p = pathlib.Path(path)
        if not p.is_absolute():
            p = (self.root / p).resolve()
        if not p.exists():
            return

        import json

        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        if isinstance(data, dict):
            mapping = data.get("aliases", data)
            if isinstance(mapping, dict):
                for k, v in mapping.items():
                    self.aliases[str(k)] = str(v)
            else:
                raise ValueError("Invalid aliases format in JSON; expected object mapping")
        else:
            raise ValueError("Invalid aliases JSON; expected object at top level")

    def save_aliases(self, path: str = "aliases.json") -> None:
        """Zapisuje aktualne aliasy do pliku JSON (prosty mapping).

        Nadpisuje podany plik. Używaj ostrożnie — to zapis użytkownika.
        """
        import json

        p = pathlib.Path(path)
        if not p.is_absolute():
            p = (self.root / p).resolve()
        # ensure parent dir exists
        if not p.parent.exists():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        with p.open("w", encoding="utf-8") as fh:
            json.dump(self.aliases, fh, indent=2, ensure_ascii=False)

    def load_user_settings(self) -> None:
        """Load user-level settings from `%USERPROFILE%/.polsoft/settings/psCLI.json`.

        Aliases found here override previously loaded aliases.
        """
        p = pathlib.Path(getattr(self, "user_settings_file", str(self.root / "psCLI.user.json")))
        if not p.exists():
            return
        import json

        try:
            with p.open('r', encoding='utf-8') as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                aliases = data.get('aliases')
                if isinstance(aliases, dict):
                    # user settings override repository aliases
                    for k, v in aliases.items():
                        self.aliases[str(k)] = str(v)
        except Exception:
            return

    def save_user_settings(self) -> None:
        """Persist user-level settings to `%USERPROFILE%/.polsoft/settings/psCLI.json`.

        Currently persists only `aliases`.
        """
        p = pathlib.Path(getattr(self, "user_settings_file", str(self.root / "psCLI.user.json")))
        try:
            if not p.parent.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        import json

        payload = {"aliases": dict(self.aliases)}
        try:
            with p.open('w', encoding='utf-8') as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        except Exception:
            try:
                _logger.exception("Failed saving user settings")
            except Exception:
                pass
        else:
            try:
                _logger.info(f"Saved user settings to {p}")
            except Exception:
                pass

    def remove_alias(self, alias: str) -> bool:
        """Usuwa alias; zwraca True jeśli usunięto, False jeśli nie istniał."""
        if alias in self.aliases:
            del self.aliases[alias]
            try:
                self.save_user_settings()
            except Exception:
                pass
            return True
        return False

    def get_aliases(self) -> Dict[str, str]:
        return dict(self.aliases)

    def register_module(self, name: str, callable_obj: Callable[..., Any]) -> None:
        self._callables[name] = callable_obj

    def resolve(self, cmd: str) -> str:
        return self.aliases.get(cmd, cmd)

    def list_commands(self) -> Dict[str, List[str]]:
        return {
            "modules": sorted(self.discover()),
            "aliases": sorted(self.aliases.items()),
            "meta": self._metadata,
        }

    def refresh_metadata(self) -> None:
        """Wczytuje i cache'uje metadata dla wszystkich modułów znalezionych w katalogu."""
        modules = self.discover()
        new_meta: Dict[str, Dict[str, Any]] = {}
        meta_name_map: Dict[str, str] = {}
        _logger.info(f"Refreshing metadata for {len(modules)} modules")
        for m in modules:
            try:
                meta = self.get_metadata(m)
            except Exception:
                meta = {}
            new_meta[m] = meta
            meta_name = meta.get("name")
            if isinstance(meta_name, str) and meta_name and meta_name != m:
                # jeżeli META podaje nazwę komendy inną niż plik, zmapuj ją
                meta_name_map[meta_name] = m
            # automatyczne rejestrowanie aliasów zadeklarowanych w META
            aliases_map = meta.get("aliases") if isinstance(meta, dict) else None
            # aliases may be provided as mapping { alias: target } or as list [alias,...]
            if isinstance(aliases_map, dict):
                items = aliases_map.items()
            elif isinstance(aliases_map, list):
                # list of alias names -> map to META.name if provided else to filename
                items = ((a, meta_name if meta_name else m) for a in aliases_map)
            else:
                items = ()

            for a, t in items:
                try:
                    if not a:
                        continue
                    # nie nadpisuj istniejących aliasów użytkownika
                    if a in self.aliases:
                        continue
                    target = t
                    # jeśli target odnosi się do META.name, zamapuj na filename
                    if isinstance(target, str) and target == meta_name:
                        target = m
                    # fallback: if target is falsy, use module filename
                    if not target:
                        target = m
                    self.aliases[str(a)] = str(target)
                    try:
                        _logger.info(f"Registered alias from META: {a} -> {target}")
                    except Exception:
                        pass
                except Exception:
                    continue

        self._metadata = new_meta
        self._meta_name_map = meta_name_map
        # ensure companion metadata files exist for external modules (create stubs if missing)
        try:
            md_dir = pathlib.Path(self.metadata_dir)
            if not md_dir.exists():
                try:
                    md_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    md_dir = None
            if md_dir:
                import json
                for m, meta in new_meta.items():
                    try:
                        # prefer writing companion files for non-py module files
                        file_path = self._module_files.get(m)
                        if not file_path:
                            continue
                        p = pathlib.Path(file_path)
                        if p.suffix.lower() == ".py":
                            # optional: still write metadata for python modules if missing
                            continue
                        target = md_dir / f"{m}.meta.json"
                        if not target.exists():
                            if not isinstance(meta, dict) or not meta:
                                # generate a stub similar to get_metadata behavior
                                pretty = m.replace('_', ' ').replace('-', ' ').title()
                                stub = {
                                    'name': pretty,
                                    'description': f'External {p.suffix.lstrip(".")} script',
                                    'aliases': [m],
                                    'args': [],
                                    'category': 'external',
                                }
                                with target.open('w', encoding='utf-8') as fh:
                                    json.dump(stub, fh, indent=2, ensure_ascii=False)
                            else:
                                with target.open('w', encoding='utf-8') as fh:
                                    json.dump(meta, fh, indent=2, ensure_ascii=False)
                    except Exception:
                        continue
        except Exception:
            pass

    def _snapshot_modules(self) -> Dict[str, float]:
        """Return mapping of module name -> mtime for files in modules_dir."""
        snap: Dict[str, float] = {}
        p = self.modules_dir
        if not p.exists():
            return snap
        for f in p.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() in (".py", ".cmd", ".exe", ".bat", ".ps1", ".vbs", ".reg") and f.stem != "__init__":
                try:
                    snap[f.stem] = f.stat().st_mtime
                except Exception:
                    snap[f.stem] = 0.0
        return snap

    def start_watcher(self, callback: Optional[Callable[[Set[str], Set[str], Set[str]], None]] = None, interval: float = 1.0) -> None:
        """Start background thread monitoring modules_dir for changes.

        callback(added, removed, modified) will be called when changes detected.
        """
        if self._watch_thread and self._watch_thread.is_alive():
            return

        stop_evt = threading.Event()
        self._watch_stop = stop_evt

        def _watch_loop():
            prev = self._snapshot_modules()
            while not stop_evt.is_set():
                time.sleep(interval)
                curr = self._snapshot_modules()
                added = set(curr.keys()) - set(prev.keys())
                removed = set(prev.keys()) - set(curr.keys())
                modified = set(k for k in curr.keys() & prev.keys() if abs(curr[k] - prev[k]) > 1e-6)
                if added or removed or modified:
                    try:
                        # refresh metadata
                        self.refresh_metadata()
                    except Exception:
                        pass
                    try:
                        _logger.info(f"Watcher detected changes added={added} removed={removed} modified={modified}")
                    except Exception:
                        pass
                    if callback:
                        try:
                            callback(added, removed, modified)
                        except Exception:
                            pass
                    prev = curr

                    # dodatkowo spróbuj powiadomić system (Windows) o zmianie
                    try:
                        self._notify_change(added, removed, modified)
                    except Exception:
                        pass

        th = threading.Thread(target=_watch_loop, daemon=True)
        self._watch_thread = th
        th.start()

    def stop_watcher(self) -> None:
        if self._watch_stop:
            self._watch_stop.set()
        if self._watch_thread:
            try:
                self._watch_thread.join(0.5)
            except Exception:
                pass

    def _notify_change(self, added: Set[str], removed: Set[str], modified: Set[str]) -> None:
        """Postaraj się wyświetlić systemowe powiadomienie (Windows). Fallback: print.

        Najpierw spróbuj użyć win10toast jeśli zainstalowane; następnie PowerShell Popup.
        """
        title = "psCLI: modules changed"
        parts = []
        if added:
            parts.append("added: " + ",".join(sorted(added)))
        if removed:
            parts.append("removed: " + ",".join(sorted(removed)))
        if modified:
            parts.append("modified: " + ",".join(sorted(modified)))

        body = "; ".join(parts) if parts else "modules changed"

        try:
            _logger.info(f"Notify change: added={added} removed={removed} modified={modified}")
        except Exception:
            pass

        # try win10toast
        try:
            from win10toast import ToastNotifier

            toaster = ToastNotifier()
            toaster.show_toast(title, body, threaded=True, icon_path=None, duration=5)
            return
        except Exception:
            pass

        # fallback: use PowerShell Popup via COM (WScript.Shell) - shows a native dialog
        try:
            # construct safe powershell command
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(New-Object -ComObject WScript.Shell).Popup('{body}',3,'{title}',0x40)"
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass

        # final fallback: print
        print(f"[notify] {title}: {body}")

    def get_metadata(self, name: str) -> Dict[str, Any]:
        """Pobiera metadata modułu jako dict.

        Szuka kolejno:
        - funkcji `get_meta()` zwracającej mapping,
        - zmiennej `META` lub `__meta__` będącej mappingiem.
        Zwraca pusty dict jeśli brak metadata.
        """
        try:
            mod = self.load(name)
        except ModuleLoadError:
            return {}
        except Exception:
            return {}

        # jeśli load zwrócił Path (plik zewnętrzny), spróbuj wczytać companion .meta.json
        if isinstance(mod, pathlib.Path):
            p = mod
            # najpierw spróbuj projektowy katalog metadata/<name>.meta.json
            meta_path = pathlib.Path(self.metadata_dir) / f"{name}.meta.json"
            if not meta_path.exists():
                # fallback: obok pliku <module>.meta.json
                meta_path = p.with_suffix('.meta.json')

            if meta_path.exists():
                import json

                try:
                    with meta_path.open('r', encoding='utf-8') as fh:
                        data = json.load(fh)
                        if isinstance(data, dict):
                            return data
                except Exception:
                    return {}
            # jeśli brak companion JSON, spróbuj wyciągnąć JSON z nagłówka (.cmd)
            try:
                with p.open('r', encoding='utf-8', errors='ignore') as fh:
                    lines = []
                    start = False
                    for i, raw in enumerate(fh):
                        if i > 200:
                            break
                        line = raw.strip()
                        # obsługa komentarzy w .cmd: zaczynają się od '::' lub 'REM '
                        if line.startswith('::') or line.upper().startswith('REM '):
                            # usuń prefiks komentarza
                            content = line[2:].strip() if line.startswith('::') else line[3:].strip()
                            if content.upper().startswith('META-START'):
                                start = True
                                continue
                            if content.upper().startswith('META-END'):
                                break
                            if start:
                                lines.append(content)
                        else:
                            # jeżeli nie-komentarz i jeszcze nie zaczęliśmy, kontynuuj
                            if not start:
                                continue
                            else:
                                # jeśli zaczęliśmy i napotkaliśmy nie-komentarz, przerywamy
                                break

                    if lines:
                        import json

                        try:
                            json_text = '\n'.join(lines)
                            data = json.loads(json_text)
                            if isinstance(data, dict):
                                return data
                        except Exception:
                            return {}
            except Exception:
                return {}
            # If no companion JSON or embedded header found, generate a minimal stub
            try:
                # do not overwrite existing file if any race; create metadata dir if needed
                md_dir = pathlib.Path(self.metadata_dir)
                if not md_dir.exists():
                    try:
                        md_dir.mkdir(parents=True, exist_ok=True)
                    except Exception:
                        pass

                suffix = p.suffix.lower()
                # choose a sensible category based on extension
                ext_category = {
                    '.ps1': 'script',
                    '.bat': 'script',
                    '.cmd': 'script',
                    '.vbs': 'script',
                    '.reg': 'registry',
                    '.exe': 'binary'
                }.get(suffix, 'external')

                name = p.stem
                pretty = name.replace('_', ' ').replace('-', ' ').strip()
                pretty = pretty.title() if pretty else name

                stub = {
                    'name': pretty,
                    'description': f'External {suffix.lstrip(".")} script',
                    'aliases': [name],
                    'args': [],
                    'category': ext_category,
                }

                try:
                    target = md_dir / f"{name}.meta.json"
                    if not target.exists():
                        import json

                        with target.open('w', encoding='utf-8') as fh:
                            json.dump(stub, fh, indent=2, ensure_ascii=False)
                        try:
                            _logger.info(f"Wrote metadata stub: {target}")
                        except Exception:
                            pass
                    return stub
                except Exception:
                    try:
                        _logger.exception(f"Failed creating metadata stub for {name}")
                    except Exception:
                        pass
                    return stub
            except Exception:
                return {}

        # jeśli moduł został zarejestrowany jako callable, nie ma metadanych
        if not hasattr(mod, "__dict__"):
            return {}

        # get_meta function
        fn = getattr(mod, "get_meta", None)
        if callable(fn):
            try:
                data = fn()
                if isinstance(data, dict):
                    return data
            except Exception:
                return {}

        for key in ("META", "__meta__", "meta"):
            if hasattr(mod, key):
                val = getattr(mod, key)
                if isinstance(val, dict):
                    return val

        # Fallback: check metadata directory for <name>.meta.json (for Python modules without embedded metadata)
        try:
            meta_path = pathlib.Path(self.metadata_dir) / f"{name}.meta.json"
            if meta_path.exists():
                import json
                with meta_path.open('r', encoding='utf-8') as fh:
                    data = json.load(fh)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass

        return {}

    def print_module_help(self, name: str) -> None:
        """Formatowany help dla modułu korzystając z metadata."""
        meta = self.get_metadata(name)
        if not meta:
            # fallback: spróbuj załadować moduł i wypisać docstring
            try:
                mod = self.load(name)
                doc = getattr(mod, "__doc__", None)
                if doc:
                    print(doc.strip())
                else:
                    print(f"No help available for '{name}'")
            except Exception:
                print(f"Module '{name}' not found")
            return

        title = meta.get("name", name)
        desc = meta.get("description", "")
        args = meta.get("args", [])
        aliases = meta.get("aliases", [])

        print(f"{title}")
        if aliases:
            if isinstance(aliases, list):
                print(f"Aliases: {', '.join(aliases)}")
            elif isinstance(aliases, dict):
                print(f"Aliases: {', '.join(aliases.keys())}")

        if desc:
            print()
            print(color_text(desc, YELLOW))
            try:
                _logger.info(f"Displayed help for module {name}")
            except Exception:
                pass
        if args:
            print()
            print("Arguments:")
            for a in args:
                n = a.get("name")
                h = a.get("help", "")
                req = a.get("required", False)
                default = a.get("default", None)
                line = f"  {n}: {h}"
                if req:
                    line += " (required)"
                if default is not None and not req:
                    line += f" [default: {default}]"
                print(line)

    def dispatch(self, argv: List[str]) -> Any:
        # odśwież metadata przed dispatch, aby wykryć nowe/zmienione moduły
        try:
            self.refresh_metadata()
        except Exception:
            pass

        if not argv:
            raise DispatcherError("No command provided")

        cmd = argv[0]
        # Rozwiąz aliasów użytkownika
        cmd = self.resolve(cmd)

        # Obsługa plików .help oraz skrótu .h
        if cmd.lower().endswith(".help") or cmd.lower().endswith(".h"):
            help_dir = self.root / "help"
            # Zamiana skrótu .h na pełne rozszerzenie .help
            if cmd.lower().endswith(".h"):
                help_name = cmd[:-2] + ".help"
            else:
                help_name = cmd
            
            target_file = None
            if (help_dir / help_name).exists():
                target_file = help_dir / help_name
            elif help_dir.exists():
                for f in help_dir.iterdir():
                    if f.name.lower() == help_name.lower():
                        target_file = f
                        break
            
            if target_file:
                try:
                    with target_file.open("r", encoding="utf-8") as fh:
                        content = fh.read()
                    # Frontmatter (blok metadanych) jest pomijany przy wyświetlaniu
                    lines = content.splitlines()
                    if lines and lines[0].strip() == "---":
                        end_idx = -1
                        for i in range(1, len(lines)):
                            if lines[i].strip() == "---":
                                end_idx = i
                                break
                        if end_idx != -1:
                            content = "\n".join(lines[end_idx+1:])
                    print(content.strip())
                    return 0
                except Exception as e:
                    raise DispatcherError(f"Error reading help file '{target_file.name}': {e}")
            
            raise DispatcherError(f"Help file '{help_name}' not found")
        
        # Obsługa plików .ascii oraz skrótu .a
        if cmd.lower().endswith(".ascii") or cmd.lower().endswith(".a"):
            ascii_dir = self.root / "ascii"
            if cmd.lower().endswith(".a"):
                ascii_name = cmd[:-2] + ".ascii"
            else:
                ascii_name = cmd
            
            target_file = None
            if (ascii_dir / ascii_name).exists():
                target_file = ascii_dir / ascii_name
            elif ascii_dir.exists():
                for f in ascii_dir.iterdir():
                    if f.name.lower() == ascii_name.lower():
                        target_file = f
                        break
            
            if target_file:
                try:
                    with target_file.open("r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    print(content)
                    return 0
                except Exception as e:
                    raise DispatcherError(f"Error reading ascii file '{target_file.name}': {e}")
            
            raise DispatcherError(f"ASCII file '{ascii_name}' not found")

        # Jeśli komenda odpowiada nazwie z META (np. META['name'] != filename), zamapuj na filename
        if cmd in self._meta_name_map:
            cmd = self._meta_name_map[cmd]

        # callable zarejestrowany ręcznie
        if cmd in self._callables:
            try:
                return self._callables[cmd](argv[1:])
            except Exception as e:
                raise DispatcherError(f"Error while running callable '{cmd}': {e}")

        # moduł filesystemowy
        if self._module_exists(cmd) or cmd in self.discover():
            try:
                mod = self.load(cmd)
            except ModuleLoadError:
                raise
            except Exception as e:
                raise ModuleLoadError(f"Error loading module '{cmd}': {e}")
            # jeśli load zwrócił Path - to moduł zewnętrzny (.cmd/.exe)
            if isinstance(mod, pathlib.Path):
                path = mod
                args = argv[1:]
                suffix = path.suffix.lower()
                try:
                    # handle common Windows script types explicitly
                    if suffix == ".exe":
                        proc = subprocess.run([str(path)] + args)
                    elif suffix in (".cmd", ".bat"):
                        # run via shell to respect batch behavior
                        cmd_str = f'"{str(path)}"'
                        if args:
                            cmd_str += " " + " ".join(f'"{a}"' for a in args)
                        proc = subprocess.run(cmd_str, shell=True)
                    elif suffix == ".ps1":
                        # PowerShell script
                        cmd = [
                            "powershell",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(path),
                        ] + args
                        proc = subprocess.run(cmd)
                    elif suffix == ".vbs":
                        # VBScript via cscript
                        cmd = ["cscript", "//NoLogo", str(path)] + args
                        proc = subprocess.run(cmd)
                    elif suffix == ".reg":
                        # import registry file
                        cmd = ["reg", "import", str(path)]
                        proc = subprocess.run(cmd)
                    else:
                        # fallback: try shell execution
                        cmd_str = f'"{str(path)}"'
                        if args:
                            cmd_str += " " + " ".join(f'"{a}"' for a in args)
                        proc = subprocess.run(cmd_str, shell=True)

                    return proc.returncode
                except Exception as e:
                    raise DispatcherError(f"Error while executing external module '{path}': {e}")
            # jeśli moduł to callable (np. funkcja zarejestrowana przez register_module)
            if callable(mod):
                try:
                    return mod(argv[1:])
                except Exception as e:
                    raise DispatcherError(f"Error while running module '{cmd}': {e}")

            # szukamy wejściowej funkcji
            for entry in ("run", "main", "cli"):
                fn = getattr(mod, entry, None)
                if callable(fn):
                    try:
                        return fn(argv[1:])
                    except Exception as e:
                        raise DispatcherError(f"Error while running '{cmd}.{entry}': {e}")

            raise EntryPointError(f"Module '{cmd}' has no entrypoint (run/main/cli)")

        raise KeyError(f"Unknown command/module: {cmd}")


def print_help(dispatcher: Dispatcher) -> None:
    # odśwież metadata przed pokazaniem helpa
    try:
        dispatcher.refresh_metadata()
    except Exception:
        pass
    from collections import defaultdict
    from pathlib import Path

    grouped = defaultdict(list)
    # invert aliases -> collect aliases for each module target
    aliases_by_module = defaultdict(list)
    
    # Map lowercase module names to canonical names from discover()
    discovered = dispatcher.discover()
    module_map = {m.lower(): m for m in discovered}

    try:
        for a, t in (dispatcher.aliases or {}).items():
            # try to resolve target to canonical module name
            canonical = module_map.get(t.lower())
            if canonical:
                aliases_by_module[canonical].append(a)
            else:
                aliases_by_module[t].append(a)
    except Exception:
        pass
    for m in discovered:
        # Hide dispatcher and hidden modules
        if m == "dispatcher":
            continue

        meta = dispatcher._metadata.get(m, {}) or {}
        if meta.get("hidden"):
            continue

        title = meta.get("name", m)
        desc = meta.get("description", "")

        # determine if external
        is_external = False
        file_path = dispatcher._module_files.get(m)
        if file_path:
            try:
                if Path(file_path).suffix.lower() != ".py":
                    is_external = True
            except Exception:
                pass

        # choose category (prefer 'category', then 'group')
        category = meta.get("category") or meta.get("group")
        if not category:
            category = "Other" if not is_external else "External"
        
        # group field
        group_val = meta.get("group", "")

        # display name: keep title only (category is shown as section header)
        name_display = title

        # keep both plain and colored variants for proper column width calculation
        plain_name = name_display if (desc or is_external) else m
        colored_name = color_text(plain_name, CYAN)
        alias_list = sorted(aliases_by_module.get(m, []))
        grouped[category].append((plain_name, colored_name, desc, alias_list, group_val))

    print("Available modules:")
    # Build a global list of rows across categories to compute uniform column widths
    desc_max = 60
    all_rows = []  # tuples: (category, plain_name, colored_name, aliases_text, desc_text, group_text)
    for cat in grouped.keys():
        for plain_name, colored_name, desc, alias_list, group_val in grouped[cat]:
            aliases_text = ", ".join(alias_list) if alias_list else ""
            desc_text = desc or ""
            if len(desc_text) > desc_max:
                desc_text = desc_text[: desc_max - 3] + "..."
            all_rows.append((cat, plain_name, colored_name, aliases_text, desc_text, group_val))

    if not all_rows:
        return

    name_w = max(len(r[1]) for r in all_rows + [(None, "Module", "", "", "", "")])
    aliases_w = max(len(r[3]) for r in all_rows + [(None, "", "", "Aliases", "", "")])
    group_w = max(len(r[5]) for r in all_rows + [(None, "", "", "", "", "Group")])
    desc_w = max(len(r[4]) for r in all_rows + [(None, "", "", "", "Description", "")])

    # Now print per-category using the global widths so separators align vertically
    for cat in sorted(grouped.keys(), key=lambda s: s.lower()):
        rows = [r for r in all_rows if r[0] == cat]
        if not rows:
            continue
        print(f"  {cat}:")
        hdr_name = "Module".ljust(name_w)
        hdr_alias = "Aliases".ljust(aliases_w)
        hdr_group = "Group".ljust(group_w)
        hdr_desc = "Description".ljust(desc_w)
        print(f"    {hdr_name} | {hdr_alias} | {hdr_group} | {hdr_desc}")
        print(f"    {'-' * name_w} | {'-' * aliases_w} | {'-' * group_w} | {'-' * desc_w}")

        for _, plain_name, colored_name, aliases_text, desc_text, group_text in rows:
            # adjust colored name padding using difference between colored and plain lengths
            name_cell = colored_name.ljust(name_w + (len(colored_name) - len(plain_name)))

            # color aliases green (but avoid adding escape codes for empty aliases)
            if aliases_text:
                alias_colored = color_text(aliases_text, GREEN)
                alias_cell = alias_colored.ljust(aliases_w + (len(alias_colored) - len(aliases_text)))
            else:
                alias_cell = " " * aliases_w

            group_cell = group_text.ljust(group_w)

            # color description yellow
            if desc_text:
                desc_colored = color_text(desc_text, YELLOW)
                desc_cell = desc_colored.ljust(desc_w + (len(desc_colored) - len(desc_text)))
            else:
                desc_cell = " " * desc_w

            print(f"    {name_cell} | {alias_cell} | {group_cell} | {desc_cell}")
    if dispatcher.aliases:
        print("\nAliases:")
        for a, t in dispatcher.aliases.items():
            alias_col = color_text(a, GREEN)
            print(f"  {alias_col} -> {t}")
