from __future__ import annotations

import asyncio
import logging
from typing import Optional

import pyautogui
from PIL import Image

from .schemas import AgentAction, Tier1Result, Tier2Result
from .verification import VerificationManager

logger = logging.getLogger(__name__)


class ActionOrchestrator:
    def __init__(self, verification_manager: VerificationManager) -> None:
        self.verification_manager = verification_manager
        self.max_retries_no_change: int = 3

        # Keep pyautogui fast but not unsafe.
        pyautogui.PAUSE = 0.1

    async def execute_action(self, action: AgentAction) -> Tier2Result | None:
        """
        Execute a single action with tiered verification.

        Returns:
            Tier2Result if Tier 2 was invoked, otherwise None.
        """
        logger.debug(
            "Executing action %s at %s",
            action.action_type,
            action.coordinates,
        )

        # Capture pre-action screenshot.
        pre_img = await asyncio.to_thread(self._take_screenshot)

        tier1_result: Optional[Tier1Result] = None
        retries = 0

        while True:
            # Perform the UI action.
            await asyncio.to_thread(self._perform_action, action)

            # Capture post-action screenshot.
            post_img = await asyncio.to_thread(self._take_screenshot)

            # Critical actions always trigger Tier 2, but we still run Tier 1.
            tier1_result = self.verification_manager.tier1_verify(pre_img, post_img)

            if action.critical:
                logger.info("Action marked critical. Proceeding to Tier 2 verification.")
                break

            if tier1_result.status == "passed":
                # Fast path succeeded.
                return None

            if tier1_result.status == "no_change":
                retries += 1
                if retries >= self.max_retries_no_change:
                    logger.warning(
                        "No visual change after %d retries. Attempting UI reset (Esc / whitespace click).",
                        retries,
                    )
                    await asyncio.to_thread(self._attempt_ui_reset)
                    break
                else:
                    logger.info("Retrying action due to no visual change (retry %d).", retries)
                    pre_img = post_img
                    continue

            # unexpected_change: go to Tier 2 for inspection.
            logger.info(
                "Tier 1 reported unexpected change (distance=%d). Escalating to Tier 2.",
                tier1_result.hamming_distance,
            )
            break

        # Tier 2 verification path.
        logger.info("Falling back to Tier 2 verification.")

        x: Optional[int]
        y: Optional[int]
        if action.coordinates:
            x, y = action.coordinates
        else:
            x = y = None

        tier2_result = await self.verification_manager.tier2_verify(
            pre=pre_img,
            post=post_img,
            action_description=action.action_type,
            expected_outcome=action.expected_outcome,
            x=x,
            y=y,
        )

        if not tier2_result.success:
            logger.warning("Tier 2 reported failure: %s", tier2_result.reasoning)
            await asyncio.to_thread(self._handle_coordinate_drift, action)
        else:
            logger.info("Tier 2 verification succeeded: %s", tier2_result.reasoning)

        return tier2_result

    def _take_screenshot(self) -> Image.Image:
        screenshot = pyautogui.screenshot()
        return screenshot.convert("RGB")

    def _perform_action(self, action: AgentAction) -> None:
        if action.action_type == "click":
            if not action.coordinates:
                raise ValueError("click action requires coordinates")
            x, y = action.coordinates
            pyautogui.click(x, y)

        elif action.action_type == "type":
            if not action.payload:
                return
            pyautogui.typewrite(action.payload)

        elif action.action_type == "drag":
            if not action.coordinates or not action.payload:
                raise ValueError("drag action requires coordinates and payload as 'dx,dy'")
            x, y = action.coordinates

            try:
                dx_str, dy_str = action.payload.split(",", maxsplit=1)
                dx, dy = int(dx_str), int(dy_str)
            except Exception as exc:  # pragma: no cover - defensive
                raise ValueError("drag payload must be 'dx,dy'") from exc

            pyautogui.moveTo(x, y)
            pyautogui.dragRel(dx, dy, duration=0.2)

        elif action.action_type == "scroll":
            amount = int(action.payload) if action.payload else -500
            pyautogui.scroll(amount)

        elif action.action_type == "wait":
            delay = float(action.payload) if action.payload else 1.0
            pyautogui.sleep(delay)

        else:  # pragma: no cover - exhaustive guard
            raise ValueError(f"Unsupported action_type: {action.action_type}")

    def _attempt_ui_reset(self) -> None:
        # Visual stall recovery: send Esc and click a neutral screen area.
        try:
            pyautogui.press("esc")
        except Exception:
            logger.exception("Failed to send Esc key during UI reset.")

        try:
            width, height = pyautogui.size()
            pyautogui.click(width // 2, height // 2)
        except Exception:
            logger.exception("Failed to click whitespace during UI reset.")

    def _handle_coordinate_drift(self, action: AgentAction) -> None:
        """
        Placeholder for smarter coordinate recovery.

        In a full implementation, this would:
        - Render a grid overlay,
        - Use OpenCV template matching around the expected region,
        - Update `action.coordinates` with refined values.
        """
        logger.warning(
            "Coordinate drift detected for action %s. "
            "Coordinate re-calculation via grid overlay is not yet implemented.",
            action.action_type,
        )


