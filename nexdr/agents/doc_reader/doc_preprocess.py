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
import os
import tempfile
from datetime import datetime

import tiktoken

from nexdr.agents.tool_types import create_error_tool_result
from nexdr.agents.tool_types import create_success_tool_result
from nexdr.agents.doc_reader.chunker import split_text_into_chunks
from nexau.archs.main_sub.agent_context import GlobalStorage
from nexdr.agents.doc_reader.jina_parser import FileParser


logger = logging.getLogger(__name__)


def is_url(url_or_local_file: str) -> bool:
    return url_or_local_file.startswith("http")


def count_tokens(text: str) -> int:
    encoding = tiktoken.encoding_for_model("gpt-4o")
    return len(encoding.encode(text, disallowed_special=()))


def add_line_id_for_doc_content(
    doc_id: str, doc_chunks: list[str]
) -> tuple[list[str], dict[int, str]]:
    lines_id_2_content = {}
    start_line_id = 1
    new_doc_chunks = []
    for i, chunk in enumerate(doc_chunks):
        lines = chunk.split("\n\n")
        lines = [line.strip() for line in lines if line.strip()]
        lines_id_2_content.update(
            {start_line_id + j: line for j, line in enumerate(lines)},
        )
        new_doc_chunks.append(
            "\n\n".join(
                [
                    f"【{doc_id}†L{start_line_id + j}】: {line}"
                    for j, line in enumerate(lines)
                ],
            ),
        )
        start_line_id += len(lines)
    return new_doc_chunks, lines_id_2_content


def extract_headings(chunk: str) -> list[str]:
    headings = []
    for line in chunk.split("\n\n"):
        if line.startswith("#"):
            headings.append(line[:100] + "..." if len(line) > 100 else line)
    return headings


def extract_chunks_table_of_contents(doc_id: str, chunks: list[str]) -> dict[str, str]:
    table_of_contents = {}
    for i, chunk in enumerate(chunks):
        headings = extract_headings(chunk)
        table_of_contents[f"{doc_id}#C{i}"] = headings
    return table_of_contents


def doc_preprocess(input: str, global_storage: GlobalStorage):
    workspace = global_storage.get("workspace", None)
    resources = global_storage.get("resources", {})
    if input.startswith("http") or os.path.exists(input):
        url_or_local_file = input
    elif workspace and os.path.exists(os.path.join(workspace, input)):
        url_or_local_file = os.path.join(workspace, input)
    elif input.isdigit():
        input = int(input)
        id2url = {item["id"]: item["link"] for item in resources.values()}
        if input not in id2url:
            error = f"Invalid document id: {input}"
            message = "Failed to preprocess document, invalid document id"
            tool_result = create_error_tool_result(
                error,
                message,
                "doc_preprocess",
            )
            return tool_result
        url_or_local_file = id2url[input]
    else:
        error = f"Invalid input: {input}"
        message = "Failed to preprocess document, invalid input, input should be a web URL, local file path or document id"
        tool_result = create_error_tool_result(
            error,
            message,
            "doc_preprocess",
        )
        return tool_result
    success, doc_result = doc_preprocess_function(
        url_or_local_file,
        global_storage,
    )
    if success:
        data = doc_result
        message = "Successfully preprocessed document"
        tool_result = create_success_tool_result(
            data,
            message,
            "doc_preprocess",
        )
        return tool_result
    else:
        error = doc_result
        message = "Failed to preprocess document"
        tool_result = create_error_tool_result(
            error,
            message,
            "doc_preprocess",
        )
        return tool_result


def doc_preprocess_function(
    url_or_local_file: str, global_storage: GlobalStorage
) -> tuple[bool, dict]:
    """
    Preprocess the document and record it in the shared context.
    """
    # Use atomic context manager for safe resource access and update
    with global_storage.lock_key("resources"):
        resources = global_storage.get("resources", {})
        if url_or_local_file in resources:
            doc_id = resources[url_or_local_file]["id"]
            if "content_for_llm" in resources[url_or_local_file]:
                return_dict = resources[url_or_local_file]["content_for_llm"]
                success = return_dict["status"] == "success"
                return success, return_dict
        else:
            max_id = (
                max(resources.values(), key=lambda x: x["id"])["id"] if resources else 0
            )
            doc_id = max_id + 1
            resources[url_or_local_file] = {
                "id": doc_id,
                "link": url_or_local_file,
            }
        # Update resources in shared state atomically
        global_storage.set("resources", resources)

    file_parser = FileParser()
    success, doc_content, return_suffix = asyncio.run(
        file_parser.parse(url_or_local_file),
    )
    token_count = count_tokens(doc_content)
    agentic_doc_read_token_limit = global_storage.get(
        "agentic_doc_read_token_limit",
        21000,
    )
    return_dict = {
        "doc_id": doc_id,
        "link": url_or_local_file,
        "status": "success" if success else "failed",
        "token_count": token_count,
    }
    chunk_size = global_storage.get("doc_chunk_size", 2100)
    logger.info(
        f"read token limit: {agentic_doc_read_token_limit}, chunk size: {chunk_size}",
    )
    chunks = split_text_into_chunks(doc_content, chunk_size)
    chunk_table_of_contents = extract_chunks_table_of_contents(doc_id, chunks)
    chunks, doc_lines_id_2_content = add_line_id_for_doc_content(
        doc_id,
        chunks,
    )
    document_content_with_line_id = "\n\n".join(chunks)
    chunk_count = len(chunks)
    if token_count > agentic_doc_read_token_limit:
        return_dict["system_remainder"] = (
            f"The document 【{doc_id}】({url_or_local_file}) is too long, split it into {chunk_count} chunks, each chunk is less than {chunk_size} tokens."
        )
        # add table of contents, first 3 chunks' content to return_dict
        return_dict["section_headings_in_each_chunk"] = chunk_table_of_contents
        return_dict["chunk_0_content"] = chunks[0]
        return_dict["chunk_1_content"] = chunks[1]
        return_dict["chunk_2_content"] = chunks[2]
    else:
        chunks = [document_content_with_line_id]
        return_dict["document_content"] = document_content_with_line_id
        return_dict["system_remainder"] = (
            f"The document 【{doc_id}】({url_or_local_file}) is short, return the entire content."
        )
    if success:
        temp_dir = global_storage.get("temp_dir", tempfile.mkdtemp())
        filepath = os.path.join(temp_dir, f"{doc_id}{return_suffix}")
        with open(filepath, "w") as f:
            f.write(doc_content)
        return_dict["system_remainder"] += (
            f"The document 【{doc_id}】({url_or_local_file}) is saved to {filepath}"
        )
    document_info_dict = {
        "id": doc_id,
        "link": url_or_local_file,
        "status": "success" if success else "failed",
        "content": document_content_with_line_id,
        "token_count": token_count,
        "chunks": chunks,
        "chunk_count": chunk_count,
        "line_id_2_content": doc_lines_id_2_content,
        "timestamp": datetime.now().isoformat(),
        "content_for_llm": return_dict,
    }

    with global_storage.lock_key("resources"):
        # Store the document information in the dictionary using the document path as the key
        resources = global_storage.get("resources", {})
        if url_or_local_file not in resources:
            resources[url_or_local_file] = {}
        resources[url_or_local_file].update(document_info_dict)
        # Update resources in shared state atomically
        global_storage.set("resources", resources)
    return success, return_dict
