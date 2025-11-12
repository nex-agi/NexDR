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
from nexdr.agents.deep_research.serper_search import SerperSearch
from nexdr.agents.deep_research.update_search_resources import update_search_resources
from nexau.archs.main_sub.agent_context import GlobalStorage
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result


def web_search(
    query: str,
    search_type: str = "search",
    num_results: int = 10,
    global_storage: GlobalStorage = None,
):
    serper_search = SerperSearch()
    results = asyncio.run(
        serper_search.search(
            query,
            search_type,
            num_results,
        ),
    )
    if isinstance(results, list):
        results = update_search_resources(results, global_storage)
        data = {
            "web_search_result": results,
        }
        message = "Successfully searched web"
        tool_result = create_success_tool_result(data, message, "web_search")
        return tool_result
    elif isinstance(results, str):
        error = results
        message = "Failed to search web"
        tool_result = create_error_tool_result(error, message, "web_search")
        return tool_result
    else:
        error = "Unknown error when searching web"
        message = "Failed to search web"
        tool_result = create_error_tool_result(error, message, "web_search")
        return tool_result
