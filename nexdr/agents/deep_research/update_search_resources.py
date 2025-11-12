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

from typing import Any
from nexau.archs.main_sub.agent_context import GlobalStorage


def update_search_resources(
    results: list[dict[str, Any]], global_storage: GlobalStorage
):
    """Update search resources with thread-safe operations using shared state."""
    with global_storage.lock_key("resources"):
        resources = global_storage.get("resources", {})
        for result in results:
            url = result.get("link", None)
            snippet = result.get("snippet", None)
            if not url:
                continue
            if url in resources.keys():
                # URL already exists, use existing ID
                result["id"] = resources[url]["id"]
                result_info = resources[url]
                if "snippet_id2content" not in result_info:
                    result_info["snippet_id2content"] = {}
                if "snippet_content2id" not in result_info:
                    result_info["snippet_content2id"] = {}
            else:
                # Generate new global ID for this URL atomically
                new_id = (
                    max(resources.values(), key=lambda x: x["id"])["id"] + 1
                    if resources
                    else 1
                )
                result["id"] = new_id
                result_info = result.copy()
                result_info["id"] = new_id
                result_info["snippet_id2content"] = {}
                result_info["snippet_content2id"] = {}

            # Handle snippet
            if snippet:
                if snippet in result_info["snippet_content2id"].keys():
                    snippet_id = result_info["snippet_content2id"][snippet]
                else:
                    snippet_id = (
                        max(
                            result_info["snippet_content2id"].values(),
                        )
                        + 1
                        if result_info["snippet_content2id"]
                        else 1
                    )
                    result_info["snippet_content2id"][snippet] = snippet_id
                    result_info["snippet_id2content"][snippet_id] = snippet
                result["snippet_id"] = snippet_id

            # Update resources with the result info
            resources[url] = result_info
        # Update resources in shared state atomically
        global_storage.set("resources", resources)

    return results
