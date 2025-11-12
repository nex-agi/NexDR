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

import re
import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from nexau.archs.main_sub.agent_context import GlobalStorage
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result


def word_tokenize(text: str) -> list[str]:
    # Convert English text to lowercase; leave Chinese characters unchanged.
    text = text.strip()
    # Separate Chinese, English, numbers, and punctuation (preserve Chinese characters and split gaps between languages).
    # Example: A mixed sentence is split into individual Chinese characters, English words, and numbers.
    tokens = []
    for seg in jieba.cut(text, cut_all=False):
        # Use regex to further split English and numerical segments.
        seg = seg.strip()
        sub_tokens = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]|[^\w\s]", seg)
        tokens.extend(sub_tokens)
    return tokens


def extract_snippet(text: str, query: str, max_snippet_length=100) -> str:
    pars = text.split("\n\n")
    if len(pars) == 0:
        return ""
    tokenized_corpus = [word_tokenize(text.lower()) for text in pars]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = word_tokenize(query.lower())
    scores = bm25.get_scores(tokenized_query)
    top1_index = np.argmax(scores)
    top1_par = pars[top1_index]
    words = word_tokenize(top1_par)
    if len(words) > max_snippet_length:
        topk_words = words[:max_snippet_length]
        top1_par = " ".join(topk_words) + "..."
    return top1_par


def doc_bm25_retrieval(
    doc_id: int, query: str, topk: int = 5, global_storage: GlobalStorage = None
):
    resources = global_storage.get("resources", {})
    doc_id2url = {item["id"]: item["link"] for item in resources.values()}
    if doc_id not in doc_id2url:
        error = f"Document {doc_id} not found"
        message = "Failed to retrieve document"
        tool_result = create_error_tool_result(error, message, "doc_bm25_retrieval")
        return tool_result
    url = doc_id2url[doc_id]
    chunks = resources[url].get("chunks", [])
    if len(chunks) == 0:
        error = f"Document {doc_id} has no available document chunks"
        message = "Failed to retrieve document"
        tool_result = create_error_tool_result(error, message, "doc_bm25_retrieval")
        return tool_result
    tokenized_corpus = [word_tokenize(text.lower()) for text in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    query = str(query).strip()
    query_tokens = word_tokenize(query.lower())
    scores = bm25.get_scores(query_tokens)
    topk_indices = np.argsort(scores)[::-1][:topk]
    topk_indices = sorted(topk_indices)
    topk_chunks = [chunks[i] for i in topk_indices]
    return_list = []
    for i, chunk in enumerate(topk_chunks):
        return_list.append(
            {
                "{doc_id}#C{chunk_id}": f"{doc_id}#C{topk_indices[i]}",
                "retrieval_score": scores[topk_indices[i]],
                "chunk_snippet": extract_snippet(
                    chunk,
                    query,
                    max_snippet_length=global_storage.get(
                        "doc_retrieval_max_snippet_length", 100
                    ),
                ),
            }
        )
    data = {
        "doc_id": doc_id,
        "query": query,
        "retrieval_results": return_list,
    }
    message = "Successfully retrieved document"
    tool_result = create_success_tool_result(data, message, "doc_bm25_retrieval")
    return tool_result
