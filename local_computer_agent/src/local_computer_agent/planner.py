from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class PlannedStep:
    command: str
    reason: str


class TaskPlanner:
    """
    Very small, extensible planner.

    Given a natural language developer goal, returns a sequence of
    high-level console commands (the same syntax you use in the
    interactive terminal: `browser search ...`, `code open`, `file ...`,
    `dev ...`, etc.).

    This is intentionally simple but structured so it can later
    be backed by an LLM without changing the rest of the system.
    """

    def plan(self, goal: str) -> List[PlannedStep]:
        text = goal.strip()
        lower = text.lower()
        steps: List[PlannedStep] = []

        if not text:
            return []

        # 1) Documentation / research steps.
        if any(k in lower for k in ["how to", "doc", "documentation", "api", "search"]):
            steps.append(
                PlannedStep(
                    command=f"browser search {text}",
                    reason="Look up documentation or prior art for the goal.",
                )
            )

        # 2) Open project in editor.
        if any(k in lower for k in ["code", "edit", "implement", "bug", "feature", "refactor"]):
            steps.append(
                PlannedStep(
                    command="code open",
                    reason="Open the project in VS Code for direct code edits.",
                )
            )

        # 3) Create or open a target file if mentioned.
        file_match = re.search(r"(?:file|module)\s+([A-Za-z0-9_\-/\.]+)", lower)
        if file_match:
            filename = file_match.group(1)
            steps.append(
                PlannedStep(
                    command=f"file new {filename}",
                    reason="Ensure the target file exists for editing.",
                )
            )

        # 4) Run tests if goal mentions correctness or failing tests.
        if any(k in lower for k in ["test", "failing", "bug", "error", "fix"]):
            steps.append(
                PlannedStep(
                    command="dev test",
                    reason="Run the test suite to see the current failure state.",
                )
            )

        # Fallback: if nothing matched, at least open code.
        if not steps:
            steps.append(
                PlannedStep(
                    command="code open",
                    reason="Open the project so the developer can inspect it.",
                )
            )

        return steps


