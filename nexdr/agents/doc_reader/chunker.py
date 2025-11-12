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

import tiktoken


class MarkdownChunker:
    def __init__(self, chunk_size: int = 500, overlap_size: int = 0, tokenizer=None):
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        if tokenizer is None:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4o")
        else:
            self.tokenizer = tokenizer

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, disallowed_special=()))

    def tokenize(self, text: str) -> list[int]:
        return self.tokenizer.encode(text, disallowed_special=())

    def detokenize(self, token_ids: list[int]) -> str:
        return self.tokenizer.decode(token_ids)

    def _split_long_paragraph(self, paragraph: str) -> list[str]:
        """Split a long paragraph into smaller chunks at spaces or newlines."""
        if self.count_tokens(paragraph) <= self.chunk_size:
            return [paragraph]

        # Try to split at newlines first
        if "\n" in paragraph:
            lines = paragraph.split("\n")
            chunks = []
            current_chunk: list[str] = []
            current_tokens = 0

            for line in lines:
                line_tokens = self.count_tokens(line)

                # If adding this line would exceed chunk size
                if current_tokens + line_tokens > self.chunk_size and current_chunk:
                    chunk_text = "\n".join(current_chunk)
                    chunks.append(chunk_text)
                    current_chunk = [line]
                    current_tokens = line_tokens
                else:
                    current_chunk.append(line)
                    current_tokens += line_tokens

            # Add the last chunk
            if current_chunk:
                chunk_text = "\n".join(current_chunk)
                chunks.append(chunk_text)

            return chunks

        # If no newlines, try to split at spaces
        if " " in paragraph:
            words = paragraph.split(" ")
            chunks = []
            current_chunk = []
            current_tokens = 0

            for word in words:
                word_tokens = self.count_tokens(word + " ")  # Include space

                # If adding this word would exceed chunk size
                if current_tokens + word_tokens > self.chunk_size and current_chunk:
                    chunk_text = " ".join(current_chunk)
                    chunks.append(chunk_text)
                    current_chunk = [word]
                    current_tokens = word_tokens
                else:
                    current_chunk.append(word)
                    current_tokens += word_tokens

            # Add the last chunk
            if current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append(chunk_text)

            return chunks

        # If no spaces or newlines, split by character count
        # Use chunk_size as character size for simplicity and speed
        chunks = []
        for i in range(0, len(paragraph), self.chunk_size):
            chunk = paragraph[i : i + self.chunk_size]
            if chunk:  # Only add non-empty chunks
                chunks.append(chunk)

        return chunks

    def split_text(self, markdown_text: str) -> list[str]:
        # Split text into paragraphs
        paragraphs = [p.strip() for p in markdown_text.split("\n\n") if p.strip()]

        chunks: list[dict[str, object]] = []
        current_chunk: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            # If paragraph is too long, split it first
            if para_tokens > self.chunk_size:
                # If we have a current chunk, save it first
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append(
                        {"content": chunk_text, "token_count": current_tokens},
                    )
                    current_chunk = []
                    current_tokens = 0

                # Split the long paragraph
                para_chunks = self._split_long_paragraph(para)
                for para_chunk in para_chunks:
                    para_chunk_tokens = self.count_tokens(para_chunk)
                    chunks.append(
                        {"content": para_chunk, "token_count": para_chunk_tokens},
                    )
                continue

            # If adding this paragraph would exceed chunk size
            if current_tokens + para_tokens > self.chunk_size and current_chunk:
                # Create a chunk from current paragraphs
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(
                    {"content": chunk_text, "token_count": current_tokens},
                )

                # Handle overlap
                if self.overlap_size > 0:
                    # Keep complete paragraphs for overlap
                    overlap_paras: list[str] = []
                    overlap_tokens = 0
                    for p in reversed(current_chunk):
                        p_tokens = self.count_tokens(p)
                        if overlap_tokens + p_tokens <= self.overlap_size:
                            overlap_paras.insert(0, p)
                            overlap_tokens += p_tokens
                        else:
                            break
                    current_chunk = overlap_paras
                    current_tokens = overlap_tokens
                else:
                    current_chunk = []
                    current_tokens = 0

            # Add paragraph to current chunk
            current_chunk.append(para)
            current_tokens += para_tokens

        # Add the last chunk if there's anything left
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(
                {"content": chunk_text, "token_count": current_tokens},
            )
        chunks_content = [str(chunk["content"]).strip() for chunk in chunks]
        return chunks_content


def split_text_into_chunks(
    text: str, chunk_size: int = 500, overlap_size: int = 0
) -> list[str]:
    chunker = MarkdownChunker(chunk_size=chunk_size, overlap_size=overlap_size)
    return chunker.split_text(text)
