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

from nexau.archs.main_sub.agent_state import AgentState
from nexau.archs.main_sub.agent_context import GlobalStorage
from nexau.archs.config.config_loader import load_agent_config
import os


def get_deep_research_trace(global_storage: GlobalStorage = None):
    if not global_storage:
        raise ValueError("global_storage is required")

    all_keys = global_storage.keys()
    all_deep_research_messages = []
    for key in all_keys:
        if key.startswith("deep_research_agent") and key.endswith("messages"):
            deep_research_trace = global_storage.get(key)
            all_deep_research_messages.extend(
                deep_research_trace[1:]
            )  # index-0 is the system message
    return all_deep_research_messages


def html_creator_tool(html_requirements: str, agent_state: AgentState = None):
    """
    HTML Creator Tool
    """
    if not agent_state:
        raise ValueError("agent_state is required")

    global_storage = agent_state.global_storage
    html_agent_yaml = global_storage.get("html_creator_yaml_path")
    if not html_agent_yaml or not os.path.exists(html_agent_yaml):
        raise ValueError(f"html_agent_yaml file {html_agent_yaml} is not found")

    deep_research_trace_history = get_deep_research_trace(global_storage)
    html_agent = load_agent_config(html_agent_yaml, global_storage=global_storage)
    response = html_agent.run(html_requirements, history=deep_research_trace_history)
    return response
