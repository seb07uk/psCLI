#!/usr/bin/env python3
from modules.dispatcher import Dispatcher, print_help, color_text, RED, YELLOW
import sys
import traceback


def main():
	d = Dispatcher()
	# Przykładowy alias domyślny (nadpisywalny przez aliases.json)
	d.register_alias("e", "echo")
	# dodatkowo spróbuj wczytać aliases.json z katalogu roboczego
	d.load_aliases("aliases.json")
	# refresh metadata/aliases from modules
	try:
		d.refresh_metadata()
	except Exception:
		pass

	# watch mode: `watch` starts interactive REPL and background watcher
	if len(sys.argv) >= 2 and sys.argv[1] in ("watch", "--watch"):
		import shlex

		def on_change(added, removed, modified):
			from modules.dispatcher import color_text, YELLOW

			parts = []
			if added:
				parts.append("added:" + ",".join(sorted(added)))
			if removed:
				parts.append("removed:" + ",".join(sorted(removed)))
			if modified:
				parts.append("modified:" + ",".join(sorted(modified)))
			if parts:
				print(color_text("[watch] ", YELLOW) + " ".join(parts))

		d.start_watcher(callback=on_change)

		try:
			while True:
				try:
					line = input("ps> ")
				except EOFError:
					break
				line = line.strip()
				if not line:
					continue
				if line in ("exit", "quit"):
					break
				args = shlex.split(line)
				# reuse main handling for some commands
				if args[0] == "aliases":
					cmd = args[1] if len(args) >= 2 else "list"
					if cmd == "list":
						for a, t in d.get_aliases().items():
							print(f"{a} -> {t}")
						continue
					if cmd == "add":
						if len(args) < 4:
							print("Usage: aliases add <alias> <target>")
							continue
						d.register_alias(args[2], args[3])
						d.save_aliases(str(d.root / "aliases.json"))
						print(f"Added alias {args[2]} -> {args[3]}")
						continue
					if cmd == "remove":
						if len(args) < 3:
							print("Usage: aliases remove <alias>")
							continue
						removed = d.remove_alias(args[2])
						d.save_aliases(str(d.root / "aliases.json"))
						print(f"Removed alias {args[2]}")
						continue

				if args[0] in ("help", "--help", "-h"):
					if len(args) >= 2:
						d.print_module_help(args[1])
					else:
						print_help(d)
					continue

				try:
					res = d.dispatch(args)
					if isinstance(res, int) and res != 0:
						print(f"Exit code: {res}")
				except Exception as exc:
					from modules.dispatcher import color_text, RED, YELLOW

					print(color_text("Error: ", RED) + color_text(str(exc), YELLOW))
            
		finally:
			d.stop_watcher()
		return

	# If no args provided, show help first then enter interactive REPL
	if len(sys.argv) <= 1:
		# show global help on startup
		print_help(d)
		import shlex

		try:
			while True:
				try:
					line = input("ps> ")
				except EOFError:
					break
				line = line.strip()
				if not line:
					continue
				if line in ("exit", "quit"):
					break

				args = shlex.split(line)

				# alias management inside REPL
				if args[0] == "aliases":
					cmd = args[1] if len(args) >= 2 else "list"
					if cmd == "list":
						for a, t in d.get_aliases().items():
							print(f"{a} -> {t}")
						continue
					if cmd == "add":
						if len(args) < 4:
							print("Usage: aliases add <alias> <target>")
							continue
						d.register_alias(args[2], args[3])
						d.save_aliases(str(d.root / "aliases.json"))
						print(f"Added alias {args[2]} -> {args[3]}")
						continue
					if cmd == "remove":
						if len(args) < 3:
							print("Usage: aliases remove <alias>")
							continue
						removed = d.remove_alias(args[2])
						d.save_aliases(str(d.root / "aliases.json"))
						print(f"Removed alias {args[2]}")
						continue

				if args[0] in ("help", "--help", "-h"):
					if len(args) >= 2:
						d.print_module_help(args[1])
					else:
						print_help(d)
					continue

				try:
					res = d.dispatch(args)
					if isinstance(res, int) and res != 0:
						print(f"Exit code: {res}")
				except Exception as exc:
					from modules.dispatcher import color_text, RED, YELLOW

					print(color_text("Error: ", RED) + color_text(str(exc), YELLOW))
		except KeyboardInterrupt:
			print()

		return

	# CLI do zarządzania aliasami: aliases list|add|remove
	if sys.argv[1] == "aliases":
		cmd = sys.argv[2] if len(sys.argv) >= 3 else "list"
		if cmd == "list":
			for a, t in d.get_aliases().items():
				print(f"{a} -> {t}")
			return
		if cmd == "add":
			if len(sys.argv) < 5:
				print("Usage: aliases add <alias> <target> [path]")
				return
			alias = sys.argv[3]
			target = sys.argv[4]
			d.register_alias(alias, target)
			path = sys.argv[5] if len(sys.argv) >= 6 else "aliases.json"
			try:
				d.save_aliases(path)
				print(f"Added alias {alias} -> {target} (saved to {path})")
			except Exception as e:
				print(f"Added alias {alias} -> {target} (failed to save: {e})")
			return
		if cmd == "remove":
			if len(sys.argv) < 4:
				print("Usage: aliases remove <alias> [path]")
				return
			alias = sys.argv[3]
			removed = d.remove_alias(alias)
			path = sys.argv[4] if len(sys.argv) >= 5 else "aliases.json"
			try:
				d.save_aliases(path)
			except Exception:
				pass
			if removed:
				print(f"Removed alias {alias} (saved to {path})")
			else:
				print(f"Alias {alias} not found")
			return

	if sys.argv[1] in ("help", "--help", "-h"):
		if len(sys.argv) >= 3:
			d.print_module_help(sys.argv[2])
		else:
			print_help(d)
		return

	# Obsługa `<module> --help`
	if len(sys.argv) >= 3 and sys.argv[2] in ("--help", "-h"):
		d.print_module_help(sys.argv[1])
		return

	try:
		res = d.dispatch(sys.argv[1:])
		if isinstance(res, int):
			sys.exit(res)
	except Exception as exc:
		# kolorowany komunikat o błędzie
		msg = str(exc)
		print(color_text("Error: ", RED) + color_text(msg, YELLOW))
		# w trybie developerskim możemy wypisać trace
		if "DEBUG" in sys.environ if hasattr(sys, "environ") else False:
			traceback.print_exc()
		sys.exit(2)


if __name__ == "__main__":
	main()

