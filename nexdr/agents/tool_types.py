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

import json
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from enum import Enum
from typing import Any
from typing import Union


class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class GenericToolResult:
    """Generic result for tool operations."""

    status: ToolStatus = field(
        metadata={
            "description": "Overall execution status of the tool: success or error",
        },
    )
    message: str = field(
        metadata={"description": "Human-readable summary of the operation outcome"},
    )
    data: Any = field(
        default=None,
        metadata={
            "description": "Result payload for success, or error details for failures",
        },
    )
    tool_name: str = field(
        default="",
        metadata={
            "description": "Name/identifier of the tool that produced this result",
        },
    )
    params: dict[str, Any] | None = field(
        default=None,
        metadata={
            "description": "Original input parameters used to invoke the tool (optional)",
        },
    )
    timestamp: str = field(
        default="",
        metadata={"description": "ISO-8601 timestamp when the result was created"},
    )

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        result = {
            "status": self.status.value
            if isinstance(self.status, ToolStatus)
            else self.status,
            "message": self.message,
            "data": self.data,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
        }
        if self.params:
            result["params"] = self.params
        return result

    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# Union type for tool returns
ToolReturnType = Union[GenericToolResult, dict[str, Any]]


# Utility functions
def create_success_tool_result(
    data: Any = None,
    message: str = "Operation completed successfully",
    tool_name: str = "",
    params: dict[str, Any] | None = None,
) -> GenericToolResult:
    """Create a generic success result."""
    return GenericToolResult(
        status=ToolStatus.SUCCESS,
        data=data,
        message=message,
        tool_name=tool_name,
        params=params,
    ).to_dict()


def create_error_tool_result(
    error: str = "Operation failed",
    message: str = "Operation failed",
    tool_name: str = "",
    params: dict[str, Any] | None = None,
) -> GenericToolResult:
    """Create a generic error result."""
    return GenericToolResult(
        status=ToolStatus.ERROR,
        data=error,
        message=message,
        tool_name=tool_name,
        params=params,
    ).to_dict()


def is_success_tool_result(result: Any) -> bool:
    """Check if a result indicates success."""
    if isinstance(result, dict):
        status = result.get("status")
        return status == ToolStatus.SUCCESS or status == ToolStatus.SUCCESS.value
    elif hasattr(result, "status"):
        status_val = getattr(result, "status")
        return (
            status_val == ToolStatus.SUCCESS or status_val == ToolStatus.SUCCESS.value
        )
    return False


def is_error_tool_result(result: Any) -> bool:
    """Check if a result indicates an error."""
    if isinstance(result, dict):
        status = result.get("status")
        return status == ToolStatus.ERROR or status == ToolStatus.ERROR.value
    elif hasattr(result, "status"):
        status_val = getattr(result, "status")
        return status_val == ToolStatus.ERROR or status_val == ToolStatus.ERROR.value
    return False


def extract_tool_result_data(result: Any) -> Any:
    """Extract the actual result data from a result object."""
    if isinstance(result, dict):
        return result.get("data")
    elif hasattr(result, "data"):
        return result.data
    return result


def extract_tool_error_message(result: Any) -> str | None:
    """Extract error message from a result."""
    if isinstance(result, dict):
        return result.get("data")  # error info is now in data field
    elif hasattr(result, "data"):
        return result.data
    return None
