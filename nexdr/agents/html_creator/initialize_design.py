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
HTML Creator - Initialize Design Tool

This module implements the initialize_design tool for creating HTML reports/presentations.
It initializes the html_creator configuration in global_storage for future updates.
"""

import logging
from datetime import datetime
from nexau.archs.main_sub.agent_state import AgentState
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result

# Configure logging
logger = logging.getLogger(__name__)


def initialize_design(
    description: str,
    height: int,
    slide_name: str,
    slide_num: int,
    title: str,
    width: int,
    agent_state: AgentState = None,
):
    """
    Initialize HTML report/slide design with specified parameters.

    This function creates an initial html_creator configuration in global_storage
    that can be progressively updated by other tools.

    Args:
        description (str): The description or content for the slide/report
        height (int): The height dimension for the HTML output in pixels
        slide_name (str): The name identifier for the slide
        slide_num (int): The slide number in the presentation sequence
        title (str): The title of the slide/report
        width (int): The width dimension for the HTML output in pixels
        agent_state (AgentState): Agent state for sharing data

    Returns:
        dict: Tool result with success/error status and data
    """

    try:
        agent_id = agent_state.agent_id
        agent_name = agent_state.agent_name
        global_storage = agent_state.global_storage

        if not all([description, slide_name, title]):
            raise ValueError("description, slide_name, and title are required")

        if height <= 0 or width <= 0:
            raise ValueError("height and width must be positive integers")

        if slide_num < 0:
            raise ValueError("slide_num must be non-negative")

        # Initialize html_creator configuration in global_storage
        html_creator_data = {
            "slides": {},
            "metadata": {
                "description": description,
                "height": height,
                "slide_name": slide_name,
                "slide_num": slide_num,
                "title": title,
                "width": width,
                "last_updated": datetime.now().isoformat(),
                "version": "1.0",
            },
        }

        resource_key = f"{agent_name}_{agent_id}_html_creator_data"
        # Store the configuration in global_storage using thread-safe lock
        with global_storage.lock_key(resource_key):
            global_storage.set(resource_key, html_creator_data)

        # Prepare success response data
        data = {
            "status": "initialized",
            "message": f"HTML/PPT design initialized successfully for slide: {slide_name}",
        }

        logger.info(f"Successfully initialized HTML design: {slide_name}")

        message = f"Successfully initialized HTML design for slide '{slide_name}'"
        return create_success_tool_result(data, message, "InitializeDesign")

    except ValueError as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(f"Initialize design failed: {error_msg}")
        return create_error_tool_result(
            error_msg, "Failed to initialize HTML design", "InitializeDesign"
        )

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Initialize design failed: {error_msg}")
        return create_error_tool_result(
            error_msg, "Failed to initialize HTML design", "InitializeDesign"
        )
