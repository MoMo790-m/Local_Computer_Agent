from __future__ import annotations

import asyncio
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class FixSuggestion:
    description: str
    command: list[str]


class DiagnosticsEngine:
    """
    Heuristic diagnostics engine for development environment issues.

    - Runs a command (e.g. `uv run pytest`)
    - Parses stdout/stderr for common errors (missing deps, conflicts, config files)
    - Applies a sequence of automatic fixes
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    async def run_with_repairs(self, argv: Iterable[str], max_rounds: int = 3) -> int:
        """
        Run a command, diagnose failures, and try to auto-fix issues.
        """
        round_no = 0
        last_code: Optional[int] = None

        while round_no < max_rounds:
            round_no += 1
            print(f"[DOCTOR] Round {round_no}: running {' '.join(shlex.quote(a) for a in argv)}")
            code, out, err = await self._run_capture(argv)
            last_code = code

            if code == 0:
                print("[DOCTOR] Command succeeded. No further action needed.")
                return code

            combined = (out or "") + "\n" + (err or "")
            suggestions = self._suggest_fixes(combined)
            if not suggestions:
                print("[DOCTOR] No automatic fix found for this error.")
                return code

            for fix in suggestions:
                print(f"[DOCTOR] Applying fix: {fix.description}")
                await self._run_and_show(fix.command)

        print("[DOCTOR] Reached max repair rounds without success.")
        return last_code if last_code is not None else 1

    async def _run_capture(self, argv: Iterable[str]) -> tuple[int, str, str]:
        def _run() -> tuple[int, str, str]:
            proc = subprocess.Popen(
                list(argv),
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            out, err = proc.communicate()
            return proc.returncode, out, err

        return await asyncio.to_thread(_run)

    async def _run_and_show(self, argv: Iterable[str]) -> int:
        cmd_display = " ".join(shlex.quote(a) for a in argv)
        print(f"[DOCTOR] Running: {cmd_display}")

        def _run() -> int:
            proc = subprocess.Popen(
                list(argv),
                cwd=self.project_root,
            )
            return proc.wait()

        code = await asyncio.to_thread(_run)
        print(f"[DOCTOR] Exit code: {code}")
        return code

    def _suggest_fixes(self, output: str) -> List[FixSuggestion]:
        suggestions: List[FixSuggestion] = []
        lower = output.lower()

        # 1) Missing Python package.
        m = re.search(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", output)
        if m:
            name = m.group(1)
            suggestions.append(
                FixSuggestion(
                    description=f"Install missing dependency '{name}' via uv.",
                    command=["uv", "add", name],
                )
            )

        # 2) Version conflict hints.
        if "versionconflict" in lower or "version conflict" in lower:
            suggestions.append(
                FixSuggestion(
                    description="Resolve version conflicts by refreshing the lockfile.",
                    command=["uv", "lock", "--upgrade"],
                )
            )

        # 3) Common runtime / config errors referencing a missing file.
        file_match = re.search(
            r"FileNotFoundError: \[Errno 2\] No such file or directory: ['\"]([^'\"]+)['\"]",
            output,
        )
        if file_match:
            missing = file_match.group(1)
            path = (self.project_root / missing).resolve()
            if self.project_root in path.parents or path == self.project_root / missing:
                suggestions.append(
                    FixSuggestion(
                        description=f"Create missing file '{missing}'.",
                        command=["python", "-c", f"from pathlib import Path; Path({missing!r}).parent.mkdir(parents=True, exist_ok=True); Path({missing!r}).touch()"],
                    )
                )

        return suggestions


