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

from nexau.archs.main_sub.agent_context import GlobalStorage
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result


def doc_reader(doc_id: int, chunk_id: int, global_storage: GlobalStorage):
    resources = global_storage.get("resources", {})
    doc_id2url = {item["id"]: item["link"] for item in resources.values()}
    if doc_id not in doc_id2url:
        error = f"Document {doc_id} not found"
        message = "Failed to read document"
        tool_result = create_error_tool_result(error, message, "doc_reader")
        return tool_result
    url = doc_id2url[doc_id]
    chunks = resources[url].get("chunks", [])
    if len(chunks) == 0:
        error = f"Document {doc_id} has no available document chunks"
        message = "Failed to read document"
        tool_result = create_error_tool_result(error, message, "doc_reader")
        return tool_result

    if chunk_id >= len(chunks):
        error = f"Chunk {chunk_id} not found in document {doc_id}, the document has {len(chunks)} chunks."
        message = "Failed to read document"
        tool_result = create_error_tool_result(error, message, "doc_reader")
        return tool_result
    data = {
        "doc_id": doc_id,
        "chunk_id": f"{doc_id}#C{chunk_id}",
        "chunk_content": chunks[chunk_id],
    }
    message = "Successfully read document"
    tool_result = create_success_tool_result(data, message, "doc_reader")
    return tool_result
