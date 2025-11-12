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

"""
HTML Creator - Update Page Tool

This module implements the update_page tool for updating existing pages in HTML reports/presentations.
It works with the html_creator configuration stored in global_storage.
"""

import logging
from datetime import datetime
from nexau.archs.main_sub.agent_state import AgentState
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result

# Configure logging
logger = logging.getLogger(__name__)


def update_page(
    index: int,
    action_description: str,
    html_content: str,
    agent_state: AgentState = None,
):
    """
    Update an existing page in the HTML presentation/report.

    This function updates an existing page at the specified index position within
    the html_creator configuration stored in global_storage.

    Args:
        index (int): The index position of the page to be updated
        action_description (str): Description of the action being performed on the page
        html_content (str): The HTML content to replace the existing page content
        agent_state (AgentState): Agent state for sharing data

    Returns:
        dict: Tool result with success/error status and data
    """
    try:
        # Validate required parameters
        if not agent_state:
            raise ValueError("agent_state is required")

        if not action_description.strip():
            raise ValueError("action_description is required")

        if not html_content.strip():
            raise ValueError("html content is required")

        if index < 0:
            raise ValueError("index must be non-negative")

        global_storage = agent_state.global_storage
        # Get html_creator configuration from global_storage
        agent_id = agent_state.agent_id
        agent_name = agent_state.agent_name
        resource_key = f"{agent_name}_{agent_id}_html_creator_data"
        with global_storage.lock_key(resource_key):
            html_creator_data = global_storage.get(resource_key)

            if not html_creator_data:
                raise ValueError(
                    "HTML creator not initialized. Please call initialize_design first."
                )

            slides = html_creator_data.get("slides", {})

            # Validate index bounds for update
            if index not in slides:
                raise ValueError(
                    "Index not found in slides, available slides: "
                    + ", ".join(slides.keys())
                )

            # Get the existing slide
            existing_slide = slides[index]
            existing_slide.update(
                {
                    "content": html_content,
                    "description": action_description,
                    "status": "updated",
                    "last_updated": datetime.now().isoformat(),
                }
            )
            html_creator_data["metadata"]["last_updated"] = datetime.now().isoformat()
            global_storage.set(resource_key, html_creator_data)

        # Prepare success response data
        data = {
            "status": "updated",
            "message": f"Successfully updated page at index {index}",
        }
        logger.info(f"Successfully updated page at index {index}: {action_description}")
        message = f"Successfully updated page at index {index}"
        return create_success_tool_result(data, message, "UpdatePage")

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(f"Update page failed: {error_msg}")
        return create_error_tool_result(
            error_msg, "Failed to update page", "UpdatePage"
        )

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Update page failed: {error_msg}")
        return create_error_tool_result(
            error_msg, "Failed to update page", "UpdatePage"
        )
