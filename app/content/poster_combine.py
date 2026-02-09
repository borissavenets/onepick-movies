"""Combine two movie posters into a single side-by-side image."""

import asyncio
import os
import tempfile
from io import BytesIO

import httpx
from PIL import Image

from app.logging import get_logger

logger = get_logger(__name__)

TARGET_HEIGHT = 1024
DIVIDER_WIDTH = 4
JPEG_QUALITY = 85


async def _fetch_image(url: str) -> Image.Image:
    """Fetch an image from URL or load from local file."""
    if os.path.isfile(url):
        return Image.open(url).convert("RGB")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGB")


def _resize_to_height(img: Image.Image, height: int) -> Image.Image:
    """Resize image to target height, preserving aspect ratio."""
    if img.height == height:
        return img
    ratio = height / img.height
    new_width = round(img.width * ratio)
    return img.resize((new_width, height), Image.LANCZOS)


async def combine_posters(url_a: str, url_b: str) -> str | None:
    """Download two posters and combine them side-by-side.

    Supports both URLs and local file paths (same as safe_send_photo).
    Returns path to a temporary JPEG file, or None on any error.
    """
    try:
        img_a, img_b = await asyncio.gather(
            _fetch_image(url_a),
            _fetch_image(url_b),
        )

        img_a = _resize_to_height(img_a, TARGET_HEIGHT)
        img_b = _resize_to_height(img_b, TARGET_HEIGHT)

        total_width = img_a.width + DIVIDER_WIDTH + img_b.width
        canvas = Image.new("RGB", (total_width, TARGET_HEIGHT), color=(0, 0, 0))
        canvas.paste(img_a, (0, 0))
        canvas.paste(img_b, (img_a.width + DIVIDER_WIDTH, 0))

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        canvas.save(tmp, format="JPEG", quality=JPEG_QUALITY)
        tmp.close()

        logger.info(f"Combined poster saved: {tmp.name}")
        return tmp.name

    except Exception:
        logger.warning("Failed to combine posters, falling back", exc_info=True)
        return None
