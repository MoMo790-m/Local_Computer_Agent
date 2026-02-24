from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import webbrowser
from pathlib import Path
from typing import Iterable

from .diagnostics import DiagnosticsEngine

logger = logging.getLogger(__name__)


class CommandRouter:
    """
    High-level command router for real-world desktop automation.

    This stays separate from low-level UI actions so the system
    remains modular and easy to extend with new capabilities.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._diagnostics = DiagnosticsEngine(self.project_root)

    async def handle(self, raw: str) -> bool:
        """
        Try to handle a high-level command.

        Returns True if the command was handled, False if it should
        fall back to low-level action parsing.
        """
        parts = raw.strip().split()
        if not parts:
            return False

        head = parts[0].lower()
        tail = parts[1:]

        if head in {"browser", "web"}:
            await self._handle_browser(tail)
            return True

        if head in {"code", "vscode"}:
            await self._handle_vscode(tail)
            return True

        if head in {"file", "fs"}:
            await self._handle_filesystem(tail)
            return True

        if head in {"dev", "run"}:
            await self._handle_dev(tail)
            return True

        return False

    async def _handle_browser(self, args: list[str]) -> None:
        """
        browser open
        browser search <query...>
        """
        if not args:
            print("[BROWSER] usage: browser open | browser search QUERY")
            return

        sub = args[0].lower()
        rest = " ".join(args[1:]).strip()

        if sub == "open":
            url = "https://www.google.com"
            await asyncio.to_thread(webbrowser.open, url)
            print(f"[BROWSER] Opened {url}")
            return

        if sub == "search":
            if not rest:
                print("[BROWSER] usage: browser search QUERY")
                return
            query = rest.replace(" ", "+")
            url = f"https://www.google.com/search?q={query}"
            await asyncio.to_thread(webbrowser.open, url)
            print(f"[BROWSER] Searching in browser: {rest}")
            return

        print("[BROWSER] unknown subcommand. Use: open | search QUERY")

    async def _handle_vscode(self, args: list[str]) -> None:
        """
        code open
        code open path/to/file.py
        """
        target: Path | None = None
        if args and args[0].lower() == "open":
            if len(args) == 1:
                target = self.project_root
            else:
                target = (self.project_root / Path(args[1])).resolve()

        if target is None:
            print("[CODE] usage: code open [PATH]")
            return

        def launch() -> None:
            try:
                subprocess.Popen(["code", str(target)])
            except OSError:
                # Fall back to OS default opener.
                if target.is_dir():
                    os.startfile(str(target))  # type: ignore[attr-defined]
                else:
                    os.startfile(str(target))  # type: ignore[attr-defined]

        await asyncio.to_thread(launch)
        print(f"[CODE] Opening in VS Code / default: {target}")

    async def _handle_filesystem(self, args: list[str]) -> None:
        """
        file new path
        file write path TEXT...
        file append path TEXT...
        """
        if not args:
            print("[FILE] usage: file new|write|append PATH [TEXT]")
            return

        sub = args[0].lower()
        if len(args) < 2:
            print("[FILE] missing PATH")
            return

        path = (self.project_root / Path(args[1])).resolve()
        text = " ".join(args[2:]) if len(args) > 2 else ""

        def ensure_parent(p: Path) -> None:
            p.parent.mkdir(parents=True, exist_ok=True)

        if sub == "new":
            await asyncio.to_thread(ensure_parent, path)
            await asyncio.to_thread(path.write_text, "", "utf-8")
            print(f"[FILE] Created empty file: {path}")
            return

        if sub in {"write", "set"}:
            await asyncio.to_thread(ensure_parent, path)
            await asyncio.to_thread(path.write_text, text, "utf-8")
            print(f"[FILE] Wrote {len(text)} chars to: {path}")
            return

        if sub == "append":
            await asyncio.to_thread(ensure_parent, path)
            def append_line(p: Path, content: str) -> None:
                with p.open("a", encoding="utf-8") as f:
                    f.write(content + os.linesep)

            await asyncio.to_thread(append_line, path, text)
            print(f"[FILE] Appended {len(text)} chars to: {path}")
            return

        print("[FILE] unknown subcommand. Use: new|write|append")

    async def _handle_dev(self, args: list[str]) -> None:
        """
        dev test            -> run tests
        dev format          -> run formatter (placeholder)
        dev doctor          -> auto-diagnose env issues via tests
        dev cmd ARGS...     -> run arbitrary shell command
        """
        if not args:
            print("[DEV] usage: dev test|format|cmd COMMAND...")
            return

        sub = args[0].lower()
        rest = args[1:]

        if sub == "test":
            await self._run_shell(["uv", "run", "pytest"])
            return

        if sub == "format":
            # Placeholder; adapt to your formatter of choice.
            await self._run_shell(["uv", "run", "python", "-m", "black", "src"])
            return

        if sub == "doctor":
            # Use pytest as a proxy for environment health.
            await self._diagnostics.run_with_repairs(["uv", "run", "pytest"])
            return

        if sub == "cmd":
            if not rest:
                print("[DEV] usage: dev cmd COMMAND...")
                return
            await self._run_shell(list(rest))
            return

        print("[DEV] unknown subcommand. Use: test|format|doctor|cmd COMMAND...")

    async def _run_shell(self, argv: Iterable[str]) -> None:
        cmd_display = " ".join(shlex.quote(a) for a in argv)
        print(f"[DEV] Running: {cmd_display}")

        def run() -> int:
            proc = subprocess.Popen(
                list(argv),
                cwd=self.project_root,
            )
            return proc.wait()

        code = await asyncio.to_thread(run)
        print(f"[DEV] Exit code: {code}")


