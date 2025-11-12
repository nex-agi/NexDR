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
HTML Creator - Finish Tool

This module implements the finish tool for marking the completion of HTML report/presentation generation.
It works with the html_creator configuration stored in global_storage and finalizes the process.
"""

import logging
import os
import tempfile
from datetime import datetime
from nexau.archs.main_sub.agent_state import AgentState
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result
from nexdr.agents.html_creator.merge_slides import build_merged_presentation


logger = logging.getLogger(__name__)


def finish(agent_state: AgentState = None):
    """
    Mark the completion of HTML report/presentation generation.

    This function finalizes the html_creator process by updating the configuration
    status and preparing the final report summary.

    Args:
        agent_state (AgentState): Agent state for sharing data

    Returns:
        dict: Tool result with success/error status and data
    """

    try:
        # Validate required parameters
        if not agent_state:
            raise ValueError("agent_state is required")

        # Get html_creator configuration from global_storage
        agent_id = agent_state.agent_id
        agent_name = agent_state.agent_name
        resource_key = f"{agent_name}_{agent_id}_html_creator_data"
        global_storage = agent_state.global_storage
        with global_storage.lock_key(resource_key):
            html_creator_data = global_storage.get(resource_key)

            if not html_creator_data:
                raise ValueError("HTML creator not initialized. Nothing to finish.")

            slides = html_creator_data.get("slides", {})

            if not slides:
                raise ValueError(
                    "No slides found in the HTML presentation. Cannot finish empty presentation."
                )

            # Update all slides status to completed
            for slide in slides.values():
                if slide.get("status") not in ["completed", "finalized"]:
                    slide["status"] = "completed"

            # Build merged single-page HTML (iframe srcdoc pagination) directly from in-memory slides
            # Order slides by numeric key when possible, otherwise by key string
            ordered_keys = sorted(
                slides.keys(), key=lambda k: int(k) if str(k).isdigit() else str(k)
            )
            slide_html_list = []
            for key in ordered_keys:
                slide = slides.get(key) or {}
                content = slide.get("content", "")
                # Fallback: if full HTML not present, try a body or empty
                slide_html_list.append(content)

            # Get presentation title from metadata
            slide_name = html_creator_data.get("metadata", {}).get(
                "slide_name", "Presentation"
            )

            # Build merged presentation with fullscreen support
            merged_index_html = build_merged_presentation(
                slide_html_list, title=slide_name
            )

            # Attach merged HTML to html_creator_data
            if "metadata" not in html_creator_data:
                html_creator_data["metadata"] = {}

            html_creator_data["merged_index_html"] = merged_index_html

            # Update metadata to mark completion
            completion_time = datetime.now().isoformat()
            html_creator_data["metadata"].update(
                {
                    "last_updated": completion_time,
                    "completion_time": completion_time,
                    "status": "completed",
                    "finalized": True,
                }
            )
            filename = (
                html_creator_data["metadata"].get("slide_name", "presentation")
                + ".html"
            )
            # save merged index html to file
            workspace_root = global_storage.get("workspace", tempfile.gettempdir())
            os.makedirs(workspace_root, exist_ok=True)
            filepath = os.path.join(workspace_root, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(merged_index_html)
            html_creator_data["merged_index_html_filepath"] = filepath
            # Save updated configuration back to global_storage
            global_storage.set(resource_key, html_creator_data)

        # Prepare success response data
        data = {
            "total_slides": len(slides),
            "completion_time": completion_time,
            "status": "completed",
            "message": f"HTML presentation completed with {len(slides)} slides, file is saved at: {filepath}",
            "filepath": filepath,
        }
        logger.info(f"HTML presentation generation completed with {len(slides)} slides")
        message = f"HTML presentation generation completed successfully with {len(slides)} slides, file is saved at: {filepath}"
        return create_success_tool_result(data, message, "finish")

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(f"Finish failed: {error_msg}")
        return create_error_tool_result(
            error_msg, "Failed to finish HTML presentation", "finish"
        )

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Finish failed: {error_msg}")
        return create_error_tool_result(
            error_msg, "Failed to finish HTML presentation", "finish"
        )
