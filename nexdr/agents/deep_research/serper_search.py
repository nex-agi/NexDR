# Copyright (c) Nex-AGI. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import base64
import io
import os
from typing import Any

import httpx
from PIL import Image


IMAGE_CAPTIONER_SYSTEM_PROMPT = """
You are a helpful assistant that captions images.  
Your task:  
1. Generate a natural, detailed caption describing the image content in exactly 100 words.  
2. Evaluate and report whether the image contains any visible watermark (Yes/No + short explanation).  
3. Assess the image clarity (e.g., Clear, Slightly Blurry, Blurry) with a brief justification.  

Your response must follow this structure:  
- Caption (100 words)  
- Watermark Analysis  
- Clarity Analysis
"""


async def download_image_and_get_size(image_url: str) -> tuple[str, tuple[int, int]]:
    """Download image from URL and return base64 data and original size"""
    async with httpx.AsyncClient() as client:
        response = await client.get(image_url)
        response.raise_for_status()

        # Open image to get dimensions
        image = Image.open(io.BytesIO(response.content))
        original_size = image.size  # (width, height)

        # Convert to base64
        base64_data = base64.b64encode(response.content).decode("utf-8")

        return base64_data, original_size


def process_base64_image(base64_data: str) -> tuple[str, tuple[int, int]]:
    """Process base64 image data and return cleaned base64 and original size"""
    # Remove data URL prefix if present
    if base64_data.startswith("data:"):
        # Extract base64 part after comma
        base64_data = base64_data.split(",", 1)[1]

    # Decode to get image
    image_bytes = base64.b64decode(base64_data)
    image = Image.open(io.BytesIO(image_bytes))
    original_size = image.size  # (width, height)

    return base64_data, original_size


async def async_image_captioner_with_base64(
    base64_data: str, mime_type: str = "image/jpeg"
) -> str:
    """Async image captioner that accepts base64 data"""
    api_key = os.getenv("MULTI_MODAL_LLM_API_KEY")
    base_url = os.getenv("MULTI_MODAL_LLM_BASE_URL")
    model = os.getenv("MULTI_MODAL_LLM_MODEL")

    # Use AsyncOpenAI for async operations
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    # Create data URL for the API
    data_url = f"data:{mime_type};base64,{base64_data}"

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": IMAGE_CAPTIONER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Please caption this image:"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )
    return response.choices[0].message.content


class SerperSearch:
    def __init__(self, timeout: float = 30.0, max_retries: int = 3):
        self.api_key = os.getenv("SERPER_API_KEY")
        if not self.api_key:
            raise ValueError("Serper API key is required")
        self.base_url = "https://google.serper.dev/"
        self.timeout = timeout
        self.max_retries = max_retries
        self.result_key_for_type: dict = {
            "news": "news",
            "places": "places",
            "images": "images",
            "search": "organic",
        }

    async def search(
        self,
        query: str,
        search_type: str = "search",
        num_results: int = 10,
    ) -> list[dict[str, Any]] | str:
        if search_type not in self.result_key_for_type.keys():
            return f"Invalid search type: {search_type}. Serper search type should be one of {self.result_key_for_type.keys()}"

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": num_results}

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=self.timeout,
                        read=self.timeout,
                        write=self.timeout,
                        pool=self.timeout,
                    ),
                ) as client:
                    response = await client.post(
                        self.base_url + search_type,
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()

                    data = response.json()
                    results = data.get(
                        self.result_key_for_type[search_type],
                        [],
                    )
                    results = results[:num_results]

                    # Process image results to add captions and size info
                    if search_type == "images":
                        # Prepare tasks for parallel processing
                        processing_tasks = []
                        valid_image_indices = []

                        for i, result in enumerate(results):
                            if "imageUrl" in result:
                                if result["imageUrl"].startswith("data:"):
                                    # Process base64 image data
                                    try:
                                        base64_data, original_size = (
                                            process_base64_image(result["imageUrl"])
                                        )
                                        result["originalSize"] = {
                                            "width": original_size[0],
                                            "height": original_size[1],
                                        }

                                        # Add caption generation task for base64 data
                                        processing_tasks.append(
                                            async_image_captioner_with_base64(
                                                base64_data
                                            )
                                        )
                                        valid_image_indices.append(i)
                                        # Remove the original imageUrl to save space
                                        del result["imageUrl"]
                                    except Exception as e:
                                        result["error"] = (
                                            f"Failed to process base64 image: {str(e)}"
                                        )
                                        del result["imageUrl"]
                                else:
                                    # Download image and get size info
                                    async def process_url_image(url, idx):
                                        try:
                                            (
                                                base64_data,
                                                original_size,
                                            ) = await download_image_and_get_size(url)
                                            results[idx]["originalSize"] = {
                                                "width": original_size[0],
                                                "height": original_size[1],
                                            }
                                            return (
                                                await async_image_captioner_with_base64(
                                                    base64_data
                                                )
                                            )
                                        except Exception as e:
                                            results[idx]["error"] = (
                                                f"Failed to download/process image: {str(e)}"
                                            )
                                            return f"Failed to process image: {str(e)}"

                                    processing_tasks.append(
                                        process_url_image(result["imageUrl"], i)
                                    )
                                    valid_image_indices.append(i)

                        # Execute all processing tasks in parallel
                        if processing_tasks:
                            try:
                                captions = await asyncio.gather(
                                    *processing_tasks, return_exceptions=True
                                )

                                # Assign captions back to results
                                for idx, caption in zip(valid_image_indices, captions):
                                    if isinstance(caption, Exception):
                                        results[idx]["caption"] = (
                                            f"Failed to generate caption: {str(caption)}"
                                        )
                                    else:
                                        results[idx]["caption"] = caption
                            except Exception as e:
                                # Fallback: if parallel processing fails entirely
                                for idx in valid_image_indices:
                                    results[idx]["caption"] = (
                                        f"Parallel processing failed: {str(e)}"
                                    )
                    else:
                        # For non-image searches, handle base64 images as before
                        for result in results:
                            if "imageUrl" in result and result["imageUrl"].startswith(
                                "data:",
                            ):
                                # delete base64 image url
                                del result["imageUrl"]
                    for result in results:
                        result.pop("thumbnailUrl", None)
                        result.pop("thumbnailWidth", None)
                        result.pop("thumbnailHeight", None)
                        result.pop("imageWidth", None)
                        result.pop("imageHeight", None)
                        result.pop("googleUrl", None)
                        result.pop("googleUrl", None)
                    return results

            except httpx.ConnectTimeout as e:
                if attempt == self.max_retries - 1:
                    return f"Connection timeout after {self.max_retries} attempts: {str(e)}"
                await asyncio.sleep(2**attempt)  # Exponential backoff
                continue

            except httpx.TimeoutException as e:
                if attempt == self.max_retries - 1:
                    return (
                        f"Request timeout after {self.max_retries} attempts: {str(e)}"
                    )
                await asyncio.sleep(2**attempt)
                continue

            except httpx.HTTPStatusError as e:
                if attempt == self.max_retries - 1:
                    return f"HTTP error {e.response.status_code}: {str(e)}"
                await asyncio.sleep(2**attempt)
                continue

            except Exception as e:
                if attempt == self.max_retries - 1:
                    return f"Unexpected error: {str(e)}"
                await asyncio.sleep(2**attempt)
                continue

        return f"Failed to complete search after {self.max_retries} attempts"


def search_images(query: str) -> list[dict[str, Any]]:
    searcher = SerperSearch()
    return asyncio.run(searcher.search(query, "images", 5))


if __name__ == "__main__":
    import time
    import json

    searcher = SerperSearch()

    async def main():
        # Test regular search
        print("Testing regular search:")
        results = await searcher.search(
            "Tencent game self-developed capabilities", "search", 5
        )
        print(f"Found {len(results)} results")

        # Test image search with parallel caption generation
        print("\nTesting image search with parallel captions:")
        start_time = time.time()
        image_results = await searcher.search("cute cats", "images", 5)
        end_time = time.time()

        print(f"Found {len(image_results)} image results")
        print(f"Parallel caption generation took: {end_time - start_time:.2f} seconds")

        # Print captions and size info if available
        for i, result in enumerate(image_results):
            print(f"Image {i + 1}:")
            if "originalSize" in result:
                print(
                    f"  Size: {result['originalSize']['width']}x{result['originalSize']['height']}"
                )
            if "imageUrl" in result:
                print(f"  URL: {result['imageUrl']}")
            if "caption" in result:
                print(f"  Caption: {result['caption']}")
            if "error" in result:
                print(f"  Error: {result['error']}")
            print()
        with open("image_results.json", "w") as f:
            json.dump(image_results, f, indent=4, ensure_ascii=False)

    asyncio.run(main())
