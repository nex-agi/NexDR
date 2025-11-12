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

import base64
import logging
import os
from io import BytesIO
from typing import Annotated

import requests
from langfuse.openai import openai
from PIL import Image
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result

logger = logging.getLogger(__name__)


IMAGE_CAPTIONER_SYSTEM_PROMPT = """
You are an expert image analyst and captioner. Your task is to analyze the provided image and answer the user's query while providing a detailed description of the image content.

## Input
- An image
- A specific query about the image

## Output Requirements
1. Answer the user's query directly and concisely
2. Provide a detailed description of the image content
3. Structure your response in a clear, organized manner
4. Output in the same language as the query
"""


def read_image(image_url: str) -> str | None:
    def is_valid_image_data(data: bytes) -> bool:
        """Check if the data is a valid image using PIL"""
        try:
            # Try to open the image with PIL
            with Image.open(BytesIO(data)) as img:
                # Verify the image by accessing its size (this forces PIL to decode the image)
                img.verify()
            return True
        except Exception as e:
            logger.debug(f"PIL validation failed: {str(e)}")
            return False

    if os.path.exists(image_url):  # if is local file
        try:
            with open(image_url, "rb") as image_file:
                image_data = image_file.read()
                if not is_valid_image_data(image_data):
                    logger.warning(f"File {image_url} is not a valid image")
                    return None
                base64_image = base64.b64encode(image_data).decode("utf-8")
                return base64_image
        except Exception as e:
            logger.warning(f"Error reading local file {image_url}: {str(e)}")
            return None

    try_time = 3
    for _ in range(try_time):
        try:
            response = requests.get(image_url, timeout=5)
            response.raise_for_status()  # Raise an exception for bad status codes

            if not is_valid_image_data(response.content):
                logger.warning(
                    f"URL {image_url} does not contain valid image data",
                )
                return None

            base64_image = base64.b64encode(response.content).decode("utf-8")
            return base64_image
        except Exception as e:
            logger.warning(f"Error in read_image: {str(e)}")
    return None


def image_caption_tool(
    input: Annotated[str, "The url of the image."],
    query: Annotated[str, "The query to the image."],
) -> str:
    """
    This tool is used to get the visual information of the image.
    """
    base_url = os.getenv("MULTI_MODAL_LLM_BASE_URL")
    api_key = os.getenv("MULTI_MODAL_LLM_API_KEY")
    model = os.getenv("MULTI_MODAL_LLM_MODEL")
    if not base_url or not api_key or not model:
        raise ValueError(
            "MULTI_MODAL_LLM_BASE_URL, MULTI_MODAL_LLM_API_KEY, and MULTI_MODAL_LLM_MODEL must be set in the environment variables to use the image caption tool."
        )
    llm = openai.OpenAI(api_key=api_key, base_url=base_url)
    image_base64 = read_image(image_url=input)
    if not image_base64:
        return f"Error: Failed to read the image {input}."
    messages = [
        {
            "role": "system",
            "content": IMAGE_CAPTIONER_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Generate the caption of the image and answer the query. The query is: {query}.",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}",
                    },
                },
            ],
        },
    ]
    try:
        response = llm.chat.completions.create(model=model, messages=messages)
        assistant_response = response.choices[0].message.content
        data = {
            "input": input,
            "query": query,
            "image_caption_result": assistant_response,
        }
        message = "Successfully generated the caption of the image"
        tool_result = create_success_tool_result(data, message, "image_caption_tool")
        return tool_result
    except Exception as e:
        logger.warning(f"Error in image_caption_tool: {str(e)}")
        error = f"Error processing image {input}, error: {str(e)}"
        message = "Failed to generate the caption of the image"
        tool_result = create_error_tool_result(error, message, "image_caption_tool")
        return tool_result
