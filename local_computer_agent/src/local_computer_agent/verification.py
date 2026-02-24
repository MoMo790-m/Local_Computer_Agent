from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

import imagehash
from PIL import Image

from .schemas import Tier1Result, Tier2Result

logger = logging.getLogger(__name__)


@dataclass
class VerificationConfig:
    phash_threshold: int = 5
    crop_radius: int = 150


class VerificationManager:
    """
    Two-layer verification:

    - Tier 1: Perceptual hashing (pHash), fast path.
    - Tier 2: LLM / VLM reasoning, slow fallback.
    """

    def __init__(self, *, config: Optional[VerificationConfig] = None) -> None:
        self.config = config or VerificationConfig()

    def compute_phash(self, img: Image.Image) -> imagehash.ImageHash:
        return imagehash.phash(img)

    def tier1_verify(self, pre: Image.Image, post: Image.Image) -> Tier1Result:
        pre_hash = self.compute_phash(pre)
        post_hash = self.compute_phash(post)
        distance = pre_hash - post_hash

        if distance == 0:
            status: str = "no_change"
        elif distance > self.config.phash_threshold:
            status = "passed"
        else:
            status = "unexpected_change"

        result = Tier1Result(
            changed=distance > 0,
            hamming_distance=int(distance),
            status=status,  # type: ignore[arg-type]
        )

        if result.status == "passed":
            logger.info("Tier1 OK (distance=%d).", distance)
        elif result.status == "no_change":
            logger.warning("Tier1: no visual change detected.")
        else:
            logger.warning("Tier1: change below threshold (distance=%d).", distance)

        return result

    def _crop_around_point(
        self,
        img: Image.Image,
        x: Optional[int],
        y: Optional[int],
    ) -> Image.Image:
        if x is None or y is None:
            return img

        w, h = img.size
        r = self.config.crop_radius
        left = max(0, x - r)
        top = max(0, y - r)
        right = min(w, x + r)
        bottom = min(h, y + r)
        return img.crop((left, top, right, bottom))

    async def tier2_verify(
        self,
        *,
        pre: Image.Image,
        post: Image.Image,
        action_description: str,
        expected_outcome: str,
        x: Optional[int],
        y: Optional[int],
    ) -> Tier2Result:
        """
        Placeholder VLM-based visual verification hook.

        This method is intentionally lightweight and can be wired to either
        Ollama or OpenAI. For now, it only returns a dummy success value.
        """
        pre_crop = self._crop_around_point(pre, x, y)
        post_crop = self._crop_around_point(post, x, y)

        # Serialize crops to bytes that can be sent to a VLM later.
        def to_bytes(image: Image.Image) -> bytes:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue()

        _pre_bytes = to_bytes(pre_crop)
        _post_bytes = to_bytes(post_crop)

        # TODO: Integrate Ollama/OpenAI VLM here.
        # For now, we optimistically assume success when Tier 2 is reached.
        logger.info("Falling back to Tier 2 visual reasoning for action: %s", action_description)

        return Tier2Result(
            success=True,
            reasoning=(
                "Tier 2 verification placeholder assumed success. "
                "Wire this method to a real VLM for production use."
            ),
        )


