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
import logging
import mimetypes
import os
from pathlib import Path
from typing import Tuple
from urllib import request as urllib_request


logger = logging.getLogger(__name__)

JINA_READER_ENDPOINT = "https://r.jina.ai/"
DEFAULT_SUFFIX = ".txt"
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".py",
    ".json",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
}


class FileParser:
    """
    Use Jina's universal reader to fetch textual content from URLs or read local files.
    Returns a tuple of (success, content, suffix).
    """

    def __init__(self, timeout: float = 45.0) -> None:
        self.timeout = timeout
        self.api_key = os.getenv("JINA_API_KEY")

    async def parse(self, url_or_local_file: str) -> Tuple[bool, str, str]:
        if self._looks_like_url(url_or_local_file):
            return await self._parse_remote(url_or_local_file)
        return await self._parse_local(url_or_local_file)

    async def _parse_remote(self, url: str) -> Tuple[bool, str, str]:
        if not self.api_key:
            error_msg = (
                "JINA_API_KEY environment variable is required but not set. "
                "Please set it with your Jina API key."
            )
            logger.error(error_msg)
            return False, error_msg, DEFAULT_SUFFIX

        jina_url = self._build_jina_reader_url(url)
        logger.info("Fetching document via Jina reader: %s", jina_url)

        try:
            raw_bytes = await asyncio.to_thread(
                self._fetch_bytes, jina_url, self.timeout, self.api_key
            )
        except Exception as exc:
            logger.exception("Failed to fetch remote document: %s", url)
            return False, f"Failed to fetch {url}: {exc}", DEFAULT_SUFFIX

        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_bytes.decode("utf-8", errors="ignore")

        if not content.strip():
            logger.warning("Empty content returned from Jina reader for %s", url)
            return False, "Empty content returned from Jina reader", DEFAULT_SUFFIX

        return True, content, DEFAULT_SUFFIX

    async def _parse_local(self, path_str: str) -> Tuple[bool, str, str]:
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            error_msg = f"Local file not found: {path}"
            logger.error(error_msg)
            return False, error_msg, DEFAULT_SUFFIX

        suffix = path.suffix.lower()
        read_as_text = suffix in TEXT_EXTENSIONS or self._is_probably_text(path)

        try:
            if read_as_text:
                content = await asyncio.to_thread(
                    path.read_text, encoding="utf-8", errors="ignore"
                )
            else:
                content = await asyncio.to_thread(
                    path.read_bytes,
                )
                try:
                    content = content.decode("utf-8")
                except UnicodeDecodeError:
                    content = content.decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.exception("Failed to read local file: %s", path)
            return False, f"Failed to read {path}: {exc}", suffix or DEFAULT_SUFFIX

        if not content.strip():
            logger.warning("Local file %s yielded empty content", path)
            return False, "Local file is empty", suffix or DEFAULT_SUFFIX

        return True, content, suffix or DEFAULT_SUFFIX

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        return value.startswith("http://") or value.startswith("https://")

    @staticmethod
    def _fetch_bytes(url: str, timeout: float, api_key: str) -> bytes:
        headers = {
            "User-Agent": "NexDR/1.0",
            "Authorization": f"Bearer {api_key}",
        }
        request = urllib_request.Request(url, headers=headers)
        with urllib_request.urlopen(request, timeout=timeout) as response:
            return response.read()

    @staticmethod
    def _build_jina_reader_url(url: str) -> str:
        if url.startswith(JINA_READER_ENDPOINT):
            return url
        return f"{JINA_READER_ENDPOINT}{url}"

    @staticmethod
    def _is_probably_text(path: Path) -> bool:
        mime_type, _ = mimetypes.guess_type(path.name)
        return mime_type is not None and mime_type.startswith("text")


if __name__ == "__main__":
    parser = FileParser()
    success, content, suffix = asyncio.run(parser.parse("https://chat2svg.github.io/"))
    print(success, content, suffix)
