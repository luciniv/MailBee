import os
import aiohttp
from typing import Iterable, Tuple, Optional

imagechest_key = os.getenv("IMAGECHEST_API_KEY")
BASE_URL = "https://api.imgchest.com/v1"
POST_URL = "https://imgchest.com/p/"


async def create_post(
    images: Iterable[Tuple[bytes, str]],
    title: Optional[str] = None,
    nsfw: bool = False,
) -> dict:

    headers = {"Authorization": f"Bearer {imagechest_key}"}

    form = aiohttp.FormData()
    for data, filename in images:
        form.add_field(
            "images[]",
            data,
            filename=filename,
            content_type="application/octet-stream",
        )

    form.add_field("privacy", "hidden")
    form.add_field("nsfw", "true" if nsfw else "false")

    if title:
        form.add_field("title", title)

    async with aiohttp.ClientSession(
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=60),
    ) as session:
        async with session.post(
            f"{BASE_URL}/post",
            data=form,
        ) as resp:
            payload = await resp.json()
            if resp.status >= 400:
                raise RuntimeError(payload)

            return process_payload(payload)


def process_payload(payload: dict) -> dict:
    data = payload.get("data", {})
    if not data:
        raise RuntimeError("Invalid response from ImageChest API.")
    url = POST_URL + data.get("id", "")
    images = data.get("images", [])
    return url, images
