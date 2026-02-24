from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

from .action_orchestrator import ActionOrchestrator
from .command_router import CommandRouter
from .planner import TaskPlanner
from .schemas import AgentAction
from .verification import VerificationManager


def setup_logging(*, interactive: bool) -> None:
    """
    Configure logging.

    - Interactive mode: cleaner, minimal output.
    - One-shot CLI mode: more detailed logs.
    """
    if interactive:
        logging.basicConfig(
            level=logging.WARNING,
            format="[%(levelname)s] %(message)s",
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="local-computer-agent",
        description="Local-First Computer Use Agent (LCA) - runner",
    )
    parser.add_argument(
        "--action-json",
        type=str,
        default=None,
        help="JSON string representing one AgentAction.",
    )
    parser.add_argument(
        "--action-file",
        type=Path,
        default=None,
        help="Path to a JSON file containing one AgentAction.",
    )
    return parser.parse_args()


def _loads_json_tolerant(raw: str) -> object:
    """
    Accept either:
    - Proper JSON: {"k":"v"}
    - Common shell-escaped JSON pasted literally: {\"k\":\"v\"}
    """
    candidates: List[str] = [raw]

    # Common copy/paste artifacts.
    candidates.append(raw.strip())
    candidates.append(raw.strip().strip("'"))
    candidates.append(raw.strip().strip('"'))

    # Common shell-escaped JSON pasted literally.
    candidates.append(raw.replace('\\"', '"').replace("\\\\", "\\"))
    candidates.append(raw.replace('\\\\\"', '"').replace("\\\\", "\\"))

    last_err: Optional[Exception] = None
    for cand in candidates:
        if not cand:
            continue
        try:
            return json.loads(cand)
        except json.JSONDecodeError as err:
            last_err = err
            continue

        # If cand itself is a JSON string containing JSON, unwrap once.
        # Example: "\"{\\\"k\\\":\\\"v\\\"}\"" -> '{"k":"v"}'
        try:
            inner = json.loads(cand)
            if isinstance(inner, str):
                return json.loads(inner)
        except Exception:
            pass

    raise last_err or json.JSONDecodeError("Invalid JSON", raw, 0)


def load_action_from_args(args: argparse.Namespace) -> Optional[AgentAction]:
    if args.action_json and args.action_file:
        raise SystemExit("Provide only one of --action-json or --action-file.")

    if args.action_json:
        data = _loads_json_tolerant(args.action_json)
        return AgentAction.model_validate(data)

    if args.action_file:
        raw = args.action_file.read_text(encoding="utf-8")
        data = _loads_json_tolerant(raw)
        return AgentAction.model_validate(data)

    return None


async def run_interactive_loop(
    orchestrator: ActionOrchestrator,
    router: CommandRouter,
) -> None:
    """
    Simple terminal REPL so you can tell the agent what to do.
    """
    banner_line = "=" * 56
    print(banner_line)
    print(" Local-First Computer Agent (Interactive)")
    print(" Type 'help' for commands, 'exit' to quit.")
    print(banner_line)

    while True:
        # Run blocking input() in a thread so we don't block the event loop.
        line = await asyncio.to_thread(input, "LCA> ")
        cmd = line.strip()
        if not cmd:
            continue

        lower = cmd.lower()
        if lower in {"exit", "quit", "q"}:
            print("Exiting interactive LCA.")
            break
        if lower.startswith("plan "):
            goal = cmd[len("plan ") :].strip()
            if not goal:
                print("Usage: plan YOUR GOAL (e.g. plan fix failing tests in module auth.py)")
                continue
            planner = TaskPlanner()
            steps = planner.plan(goal)
            if not steps:
                print("[PLAN] No steps generated.")
                continue
            print("[PLAN] Steps:")
            for idx, step in enumerate(steps, start=1):
                print(f"  {idx}. {step.command}  # {step.reason}")
            # Execute steps automatically.
            for idx, step in enumerate(steps, start=1):
                print(f"[PLAN] Executing step {idx}: {step.command}")
                # Try high-level handler first.
                handled = await router.handle(step.command)
                if handled:
                    continue
                # Otherwise, treat as low-level UI command.
                try:
                    action = _parse_command_to_action(step.command)
                except ValueError as exc:
                    print(f"[PLAN] Could not execute step {idx}: {exc}")
                    continue
                print(f"[ACTION] {action.action_type} {action.coordinates or ''}")
                await orchestrator.execute_action(action)
                print("[DONE]")
            continue

        if lower in {"help", "h"}:
            print("Commands:")
            print("  click X Y [critical]      - click at (X, Y)")
            print("  type TEXT                 - type TEXT at current focus")
            print("  wait SECONDS              - wait for SECONDS (float)")
            print("  scroll AMOUNT             - scroll by AMOUNT (int, negative = up)")
            print("  plan GOAL                 - auto-plan and run steps for GOAL")
            print("  browser open              - open default browser")
            print("  browser search QUERY      - search QUERY in browser")
            print("  code open [PATH]          - open VS Code / project or file")
            print("  file new|write|append P T - create or edit files")
            print("  dev test|format|doctor|cmd ...   - run dev workflows / environment doctor")
            print("  exit / quit               - stop the agent")
            continue

        try:
            # High-level commands first.
            handled = await router.handle(cmd)
            if handled:
                continue

            # Fallback to low-level UI actions.
            action = _parse_command_to_action(cmd)
        except ValueError as exc:
            print(f"Could not understand command: {exc}")
            continue
        print(f"[ACTION] {action.action_type} {action.coordinates or ''}")
        await orchestrator.execute_action(action)
        print("[DONE]")


def _parse_command_to_action(cmd: str) -> AgentAction:
    """
    Parse a simple text command into an AgentAction.
    """
    parts = cmd.split()
    if not parts:
        raise ValueError("empty command")

    verb = parts[0].lower()

    if verb == "click":
        if len(parts) < 3:
            raise ValueError("usage: click X Y [critical]")
        try:
            x = int(parts[1])
            y = int(parts[2])
        except ValueError as exc:
            raise ValueError("X and Y must be integers") from exc

        critical = any(p.lower() == "critical" for p in parts[3:])
        expected = "Click performed at screen coordinates."
        return AgentAction(
            action_type="click",
            coordinates=(x, y),
            payload=None,
            expected_outcome=expected,
            critical=critical,
        )

    if verb == "type":
        if len(parts) < 2:
            raise ValueError("usage: type TEXT")
        text = cmd[len(parts[0]) :].strip()
        return AgentAction(
            action_type="type",
            coordinates=None,
            payload=text,
            expected_outcome="Text is typed into the focused element.",
            critical=False,
        )

    if verb == "wait":
        if len(parts) < 2:
            raise ValueError("usage: wait SECONDS")
        try:
            seconds = float(parts[1])
        except ValueError as exc:
            raise ValueError("SECONDS must be a number") from exc
        return AgentAction(
            action_type="wait",
            coordinates=None,
            payload=str(seconds),
            expected_outcome="A wait delay completes.",
            critical=False,
        )

    if verb == "scroll":
        if len(parts) < 2:
            raise ValueError("usage: scroll AMOUNT")
        try:
            amount = int(parts[1])
        except ValueError as exc:
            raise ValueError("AMOUNT must be an integer") from exc
        return AgentAction(
            action_type="scroll",
            coordinates=None,
            payload=str(amount),
            expected_outcome="The view is scrolled.",
            critical=False,
        )

    raise ValueError(f"unknown command verb: {verb}")


async def async_main() -> None:
    args = parse_args()
    user_action = load_action_from_args(args)

    interactive = user_action is None
    setup_logging(interactive=interactive)

    logger = logging.getLogger(__name__)
    logger.info("Starting Local-First Computer Agent (LCA) loop.")
    verification_manager = VerificationManager()
    orchestrator = ActionOrchestrator(verification_manager)
    router = CommandRouter(project_root=Path.cwd())

    if user_action is not None:
        # One-shot mode using CLI-provided action.
        await orchestrator.execute_action(user_action)
    else:
        # No JSON/file given -> interactive REPL.
        await run_interactive_loop(orchestrator, router)

    logger.info("Agent loop finished.")


def main() -> None:
    asyncio.run(async_main())


