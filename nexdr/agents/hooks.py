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

import logging
import os
import re
import json
import uuid
from nexau.archs.main_sub.execution.hooks import (
    Middleware,
    HookResult,
    AfterModelHookInput,
    AfterToolHookInput,
    BeforeModelHookInput,
)
from nexau.archs.main_sub.execution.hooks import ModelCallParams, ModelCallFn
from nexau.archs.main_sub.execution.model_response import ModelResponse
from nexau.archs.config.config_loader import load_agent_config
from nexau.archs.main_sub.utils.token_counter import TokenCounter


logger = logging.getLogger(__name__)


class LoggingMiddleware(Middleware):
    """Middleware that logs after-model and/or after-tool phases."""

    def __init__(
        self,
        *,
        model_logger: str | None = None,
        tool_logger: str | None = None,
        message_preview_chars: int = 120,
        tool_preview_chars: int = 500,
        log_model_calls: bool = False,
    ) -> None:
        self.model_logger = logging.getLogger(model_logger) if model_logger else None
        self.tool_logger = logging.getLogger(tool_logger) if tool_logger else None
        self.message_preview_chars = message_preview_chars
        self.tool_preview_chars = tool_preview_chars
        self.log_model_calls = log_model_calls

    def after_model(self, hook_input: AfterModelHookInput) -> HookResult:  # type: ignore[override]
        # save all messages to global storage
        agent_id = hook_input.agent_state.agent_id
        agent_name = hook_input.agent_state.agent_name
        global_storage = hook_input.agent_state.global_storage
        messages = hook_input.messages
        message_key = f"{agent_name}_{agent_id}_messages"
        with global_storage.lock_key(message_key):
            global_storage.set(message_key, messages)

        logger = self.model_logger
        if not logger:
            return HookResult.no_changes()

        parsed = hook_input.parsed_response
        logger.info("🎣 ===== AFTER MODEL HOOK TRIGGERED =====")
        logger.info(
            "Agent: %s (%s)",
            hook_input.agent_state.agent_name,
            hook_input.agent_state.agent_id,
        )
        logger.info("Response length: %s characters", len(hook_input.original_response))

        if parsed is None:
            logger.info("No parsed response available")
        else:
            logger.info("Summary: %s", parsed.get_call_summary())
            logger.info("Tool calls: %s", len(parsed.tool_calls))
            logger.info("Sub-agent calls: %s", len(parsed.sub_agent_calls))
            logger.info("Batch agent calls: %s", len(parsed.batch_agent_calls))
            logger.info("Parallel tools: %s", parsed.is_parallel_tools)
            logger.info("Parallel sub-agents: %s", parsed.is_parallel_sub_agents)

        logger.info("Message history: %s items", len(hook_input.messages))
        for idx, msg in enumerate(hook_input.messages[-3:]):
            preview = str(msg.get("content", ""))[: self.message_preview_chars]
            logger.info(
                "Recent message %s: %s -> %s", idx + 1, msg.get("role"), preview
            )

        logger.info("🎣 ===== END AFTER MODEL HOOK =====")
        return HookResult.no_changes()

    def after_tool(self, hook_input: AfterToolHookInput) -> HookResult:  # type: ignore[override]
        logger = self.tool_logger
        if not logger:
            return HookResult.no_changes()

        logger.info("🔧 ===== AFTER TOOL HOOK TRIGGERED =====")
        logger.info(
            "Agent: %s (%s)",
            hook_input.agent_state.agent_name,
            hook_input.agent_state.agent_id,
        )
        logger.info("Tool: %s", hook_input.tool_name)
        logger.info("Input: %s", hook_input.tool_input)

        output_preview = str(hook_input.tool_output)
        if len(output_preview) > self.tool_preview_chars:
            truncated = output_preview[: self.tool_preview_chars]
            logger.info("🔧 Tool output (truncated): %s...", truncated)
        else:
            logger.info("🔧 Tool output: %s", output_preview)
        logger.info("🔧 ===== END AFTER TOOL HOOK =====")
        return HookResult.no_changes()

    def wrap_model_call(
        self, params: ModelCallParams, call_next: ModelCallFn
    ) -> ModelResponse | None:  # type: ignore[override]
        if not self.log_model_calls and not self.model_logger:
            return call_next(params)

        self._log_model_call(f"LLM call invoked with {len(params.messages)} messages")
        try:
            response = call_next(params)
            if response is None:
                self._log_model_call("LLM call returned no response")
            else:
                preview = (response.render_text() or response.content or "").strip()
                if preview:
                    preview = preview[: self.message_preview_chars]
                    self._log_model_call(f"LLM response preview: {preview}")
            return response
        except Exception as exc:  # pragma: no cover - logging path
            self._log_model_call(f"LLM call wrapper error: {exc}", error=True)
            raise

    def _log_model_call(self, message: str, error: bool = False) -> None:
        logger = self.model_logger
        if logger:
            log_fn = logger.error if error else logger.info
            log_fn(message)
        else:
            print(message)


class ContinueResearchMiddleware(Middleware):
    """Middleware that logs after-model and/or after-tool phases."""

    def __init__(
        self, continue_judge_agent_config_path: str, max_continue_times: int = 5
    ) -> None:
        self.continue_judge_agent_config_path = continue_judge_agent_config_path
        assert os.path.exists(self.continue_judge_agent_config_path), (
            f"Continue judge agent config file {self.continue_judge_agent_config_path} does not exist"
        )
        self.max_continue_times = max_continue_times
        self.continue_times = 0

    def after_model(self, hook_input: AfterModelHookInput) -> HookResult:  # type: ignore[override]
        # Check if the parsed response is None or has no tool calls
        if self.judge_agent_will_finish(hook_input):
            # If research will finish, first judge if the agent need continue
            is_complete, judge_reason = self.agent_need_continue(hook_input)
            if is_complete:
                # Research is complete, let it finish
                return HookResult.no_changes()
            else:
                # Research is incomplete, force continue with feedback
                logger.info(
                    f"Continue judge determined research incomplete: {judge_reason}"
                )
                # Append user message with the reason to messages
                modified_messages = hook_input.messages.copy()
                feedback_message = {
                    "role": "user",
                    "content": f"<system_reminder>\nYour research is not yet complete. Please continue with more investigation.\n\nReason: {judge_reason}\n</system_reminder>",
                }
                modified_messages.append(feedback_message)
                # delete handoff_to_report_writer tool call
                hook_input.parsed_response.tool_calls = [
                    tool_call
                    for tool_call in hook_input.parsed_response.tool_calls
                    if tool_call.tool_name != "handoff_to_report_writer"
                ]
                return HookResult.with_modifications(
                    messages=modified_messages, force_continue=True
                )
        else:
            # If research will not finish, return no changes
            return HookResult.no_changes()

    def judge_agent_will_finish(self, hook_input: AfterModelHookInput) -> bool:
        if hook_input.parsed_response is None:
            return True
        elif hook_input.parsed_response.has_calls():
            all_tool_calls = hook_input.parsed_response.tool_calls
            for tool_call in all_tool_calls:
                if tool_call.tool_name == "handoff_to_report_writer":
                    return True
            return False
        else:
            return True

    def agent_need_continue(self, hook_input: AfterModelHookInput) -> tuple[bool, str]:
        if self.continue_times >= self.max_continue_times:
            return False, "Max continue times reached"

        self.continue_times += 1
        agent = load_agent_config(
            self.continue_judge_agent_config_path,
            global_storage=hook_input.agent_state.global_storage,
        )
        system_reminder = "Please judge if the research agent has completed all required research tasks comprehensively."
        input_history = hook_input.messages[1:]  # index-0 is the system message
        input_message = ""
        for message in input_history:
            role = message["role"]
            content = message.get("content", "")
            if content:
                input_message += f"<{role}>\n{content}\n</{role}>\n\n"

        user_message = f"<system_reminder>\n{system_reminder}\n</system_reminder>\n\n<research_history>\n{input_message}\n</research_history>"
        response_content = agent.run(user_message)

        # Extract judge_result (case-insensitive, flexible matching)
        judge_result_match = re.search(
            r"<judge_result[^>]*>\s*(true|false|yes|no|1|0)\s*</judge_result>",
            response_content,
            re.IGNORECASE | re.DOTALL,
        )
        if not judge_result_match:
            logger.warning(
                f"Continue judge agent response missing <judge_result> tag. Response: {response_content}"
            )
            return False, "Continue judge agent returned invalid format"

        # More flexible result interpretation
        result_value = judge_result_match.group(1).lower().strip()
        judge_result = result_value in ["true", "yes", "1"]

        # Extract judge_reason if result is False (more flexible matching)
        judge_reason = ""
        if not judge_result:
            judge_reason_match = re.search(
                r"<judge_reason[^>]*>\s*(.*?)\s*</judge_reason>",
                response_content,
                re.IGNORECASE | re.DOTALL,
            )
            if judge_reason_match:
                judge_reason = judge_reason_match.group(1).strip()
            else:
                judge_reason = "The research is incomplete. Please continue with more in-depth investigation."

        return judge_result, judge_reason


class TodoValidationMiddleware(Middleware):
    """Middleware that validates TodoWrite tool calls using an LLM judge."""

    def __init__(
        self,
        todo_validator_agent_config_path: str,
        max_validation_times: int = 10,
        validate_every_n_calls: int = 1,
        skip_first_n_calls: int = 0,
    ) -> None:
        """
        Initialize TodoValidationMiddleware.

        Args:
            todo_validator_agent_config_path: Path to the validator agent config
            max_validation_times: Maximum number of validations to perform
            validate_every_n_calls: Validate every N TodoWrite calls (1 = validate all)
            skip_first_n_calls: Skip validation for the first N TodoWrite calls
        """
        self.todo_validator_agent_config_path = todo_validator_agent_config_path
        assert os.path.exists(self.todo_validator_agent_config_path), (
            f"Todo validator agent config file {self.todo_validator_agent_config_path} does not exist"
        )

        self.max_validation_times = max_validation_times
        self.validate_every_n_calls = validate_every_n_calls
        self.skip_first_n_calls = skip_first_n_calls

        # State tracking
        self.validation_count = 0
        self.todo_write_call_count = 0

    def after_model(self, hook_input: AfterModelHookInput) -> HookResult:  # type: ignore[override]
        """Validate TodoWrite calls after model response."""

        # Check if there are any tool calls
        if not hook_input.parsed_response or not hook_input.parsed_response.tool_calls:
            return HookResult.no_changes()

        # Find all TodoWrite calls
        todo_write_calls = [
            call
            for call in hook_input.parsed_response.tool_calls
            if call.tool_name == "TodoWrite"
        ]

        if not todo_write_calls:
            logger.info("🎯 No TodoWrite calls found, skipping validation")
            return HookResult.no_changes()

        # Check if we should validate based on frequency
        if (
            self.todo_write_call_count - self.skip_first_n_calls
        ) % self.validate_every_n_calls != 0:
            logger.info(
                f"🎯 Skipping validation (validate every {self.validate_every_n_calls} calls)"
            )
            return HookResult.no_changes()

        # Increment call count
        self.todo_write_call_count += 1

        logger.info(
            f"🎯 Found {len(todo_write_calls)} TodoWrite call(s) (total calls: {self.todo_write_call_count})"
        )

        # Check if we should skip this validation
        if self.todo_write_call_count <= self.skip_first_n_calls:
            logger.info(
                f"🎯 Skipping validation (within first {self.skip_first_n_calls} calls)"
            )
            return HookResult.no_changes()

        # Check if we've reached max validation times
        if self.validation_count >= self.max_validation_times:
            logger.info(
                f"🎯 Max validation times ({self.max_validation_times}) reached, skipping validation"
            )
            return HookResult.no_changes()

        # Perform validation
        self.validation_count += 1
        logger.info(
            f"🎯 Performing validation {self.validation_count}/{self.max_validation_times}"
        )

        try:
            is_valid, feedback = self.validate_todo_write(
                todo_calls=todo_write_calls, messages=hook_input.messages
            )

            if is_valid:
                logger.info("🎯 TodoWrite validation passed")
                return HookResult.no_changes()

            # Validation failed, add feedback and force continue
            logger.warning(f"🎯 TodoWrite validation failed: {feedback}")

            # Remove invalid TodoWrite calls
            hook_input.parsed_response.tool_calls = [
                call
                for call in hook_input.parsed_response.tool_calls
                if call.tool_name != "TodoWrite"
            ]

            # Add feedback message
            modified_messages = hook_input.messages.copy()
            modified_messages.append({"role": "user", "content": feedback})

            logger.info("🎯 TodoWrite validation completed with modifications")
            return HookResult.with_modifications(
                parsed_response=hook_input.parsed_response,
                messages=modified_messages,
                force_continue=True,
            )

        except Exception as e:
            logger.error(f"🎯 Validation failed with exception: {e}")
            # On error, allow the TodoWrite to proceed
            return HookResult.no_changes()

    def validate_todo_write(self, todo_calls: list, messages: list) -> tuple[bool, str]:
        """
        Validate TodoWrite calls using the validator agent.

        Args:
            todo_calls: List of TodoWrite tool calls
            messages: Current conversation messages

        Returns:
            (is_valid, feedback): Whether valid and feedback message if invalid
        """
        # Load validator agent
        agent = load_agent_config(
            self.todo_validator_agent_config_path,
            global_storage=None,  # Validator doesn't need shared state
        )

        # Prepare context from messages
        conversation_context = []
        for msg in messages[1:]:  # Skip system message
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Truncate very long content
            if len(content) > 8000:
                content = content[:4000] + "\n...[truncated]...\n" + content[-4000:]

            if content:
                conversation_context.append(
                    f"<{role.upper()}>\n{content}\n</{role.upper()}>"
                )

        conversation_str = "\n\n".join(conversation_context)

        # Prepare TodoWrite parameters
        import json

        todo_params_list = []
        for call in todo_calls:
            try:
                params_str = json.dumps(call.parameters, ensure_ascii=False, indent=2)
                todo_params_list.append(params_str)
            except Exception:
                todo_params_list.append(str(call.parameters))

        todo_params_str = "\n\n---\n\n".join(todo_params_list)

        # Build validation request
        validation_request = f"""<system_reminder>
Please evaluate if the TodoWrite tool call(s) below are reasonable and appropriate.
</system_reminder>

<conversation_history>
{conversation_str}
</conversation_history>

<todo_write_calls>
{todo_params_str}
</todo_write_calls>

Please evaluate and provide your judgment."""

        # Call validator agent
        logger.info("🎯 Calling validator agent...")
        response_content = agent.run(validation_request)
        logger.info(f"🎯 Validator response: {response_content[:200]}...")

        # Parse response using XML tags
        is_valid, feedback = self.parse_validator_response(response_content)

        return is_valid, feedback

    def parse_validator_response(self, response: str) -> tuple[bool, str]:
        """
        Parse validator agent response with XML tags.

        Expected format:
        <validation_result>true/false</validation_result>
        <validation_reason>reason text</validation_reason>
        <validation_suggestion>suggestion text</validation_suggestion>

        Args:
            response: Validator agent response

        Returns:
            (is_valid, feedback): Whether valid and feedback message if invalid
        """
        # Extract validation_result (case-insensitive)
        result_match = re.search(
            r"<validation_result[^>]*>\s*(true|false|yes|no|1|0)\s*</validation_result>",
            response,
            re.IGNORECASE | re.DOTALL,
        )

        if not result_match:
            logger.warning(
                f"Validator response missing <validation_result> tag. Response: {response}"
            )
            # Default to valid on parse error to avoid blocking
            return True, ""

        # Parse result value
        result_value = result_match.group(1).lower().strip()
        is_valid = result_value in ["true", "yes", "1"]

        if is_valid:
            return True, ""

        # Extract reason and suggestion
        reason_match = re.search(
            r"<validation_reason[^>]*>\s*(.*?)\s*</validation_reason>",
            response,
            re.IGNORECASE | re.DOTALL,
        )

        suggestion_match = re.search(
            r"<validation_suggestion[^>]*>\s*(.*?)\s*</validation_suggestion>",
            response,
            re.IGNORECASE | re.DOTALL,
        )

        reason = reason_match.group(1).strip() if reason_match else ""
        suggestion = suggestion_match.group(1).strip() if suggestion_match else ""

        # Build feedback message
        feedback_parts = ["⚠️ **TodoWrite Validation Failed**"]

        if reason:
            feedback_parts.append(f"\n**Reason**: {reason}")

        if suggestion:
            feedback_parts.append(f"\n**Suggestion**: {suggestion}")

        feedback_parts.append(
            "\n\nPlease adjust your research plan based on the feedback."
        )

        feedback = "".join(feedback_parts)

        return False, feedback


class TodoAndContinueMiddleware(Middleware):
    """
    Combined middleware that first validates TodoWrite calls,
    then judges if research should continue (only if no TodoWrite calls exist).

    Logic:
    1. First check for TodoWrite calls and validate them if present
    2. If TodoWrite calls exist (even if invalid), skip continue judgment
    3. Only perform continue judgment if no TodoWrite calls were made
    """

    def __init__(
        self,
        todo_validator_agent_config_path: str,
        continue_judge_agent_config_path: str,
        max_validation_times: int = 10,
        validate_every_n_calls: int = 1,
        skip_first_n_calls: int = 0,
        max_continue_times: int = 5,
        max_context_tokens: int = 100000,
        keep_last_n_user_messages: int = 3,
        compressed_preview_chars: int = 200,
        min_compress_tokens: int = 500,
        token_counter_strategy: str = "tiktoken",
        token_counter_model: str = "gpt-4o",
    ) -> None:
        """
        Initialize TodoAndContinueMiddleware.

        Args:
            todo_validator_agent_config_path: Path to the todo validator agent config
            continue_judge_agent_config_path: Path to the continue judge agent config
            max_validation_times: Maximum number of todo validations to perform
            validate_every_n_calls: Validate every N TodoWrite calls (1 = validate all)
            skip_first_n_calls: Skip validation for the first N TodoWrite calls
            max_continue_times: Maximum number of continue judgments
            max_context_tokens: Maximum context size (in tokens) before triggering compression
            keep_last_n_user_messages: Number of most recent user messages to keep uncompressed
            compressed_preview_chars: Number of characters to keep in compressed message preview
            min_compress_tokens: Minimum token count for a message to be eligible for compression
            token_counter_strategy: Token counting strategy ("tiktoken" or "fallback")
            token_counter_model: Model name for token counter (e.g., "gpt-4o")
        """
        # Todo validation config
        self.todo_validator_agent_config_path = todo_validator_agent_config_path
        assert os.path.exists(self.todo_validator_agent_config_path), (
            f"Todo validator agent config file {self.todo_validator_agent_config_path} does not exist"
        )

        self.max_validation_times = max_validation_times
        self.validate_every_n_calls = validate_every_n_calls
        self.skip_first_n_calls = skip_first_n_calls

        # Continue judge config
        self.continue_judge_agent_config_path = continue_judge_agent_config_path
        assert os.path.exists(self.continue_judge_agent_config_path), (
            f"Continue judge agent config file {self.continue_judge_agent_config_path} does not exist"
        )

        self.max_continue_times = max_continue_times

        # Context compression config
        self.max_context_tokens = max_context_tokens
        self.keep_last_n_user_messages = keep_last_n_user_messages
        self.compressed_preview_chars = compressed_preview_chars
        self.min_compress_tokens = min_compress_tokens

        # Initialize token counter
        self.token_counter = TokenCounter(
            strategy=token_counter_strategy, model=token_counter_model
        )
        logger.info(
            f"🔢 Initialized TokenCounter with strategy={token_counter_strategy}, model={token_counter_model}"
        )

        # State tracking
        self.validation_count = 0
        self.todo_write_call_count = 0
        self.continue_times = 0

    def before_model(self, hook_input: BeforeModelHookInput) -> HookResult:  # type: ignore[override]
        """
        Check context size and compress old user messages if necessary.
        """
        messages = hook_input.messages

        # Calculate total context size using TokenCounter
        total_tokens = self.token_counter.count_tokens(messages)

        logger.info(
            f"📊 Current context size: {total_tokens} tokens (max: {self.max_context_tokens})"
        )

        if total_tokens <= self.max_context_tokens:
            # No compression needed
            return HookResult.no_changes()

        logger.info(
            f"⚠️ Context size ({total_tokens} tokens) exceeds max ({self.max_context_tokens}), starting compression"
        )

        # Compress old user messages
        compressed_messages = self._compress_old_user_messages(
            messages=messages, agent_state=hook_input.agent_state
        )

        # Calculate new size using TokenCounter
        new_tokens = self.token_counter.count_tokens(compressed_messages)
        logger.info(
            f"✅ Compression complete. New context size: {new_tokens} tokens (saved: {total_tokens - new_tokens} tokens)"
        )

        return HookResult.with_modifications(messages=compressed_messages)

    def after_model(self, hook_input: AfterModelHookInput) -> HookResult:  # type: ignore[override]
        """
        Combined logic: first validate TodoWrite, then judge continue if no TodoWrite.
        """

        # Step 1: Check for TodoWrite calls
        has_todo_write = self._has_todo_write_calls(hook_input)

        if has_todo_write:
            # If there are TodoWrite calls, validate them
            logger.info(
                "🔄 Found TodoWrite calls, validating and skipping continue judgment"
            )
            return self._handle_todo_validation(hook_input)

        # Step 2: No TodoWrite calls, check if we should run continue judgment
        logger.info("🔄 No TodoWrite calls found, checking if continue judgment needed")
        return self._handle_continue_judgment(hook_input)

    def _has_todo_write_calls(self, hook_input: AfterModelHookInput) -> bool:
        """Check if there are any TodoWrite calls."""
        if not hook_input.parsed_response or not hook_input.parsed_response.tool_calls:
            return False

        for call in hook_input.parsed_response.tool_calls:
            if call.tool_name == "TodoWrite":
                return True

        return False

    def _handle_todo_validation(self, hook_input: AfterModelHookInput) -> HookResult:
        """Handle TodoWrite validation logic."""

        # Find all TodoWrite calls
        todo_write_calls = [
            call
            for call in hook_input.parsed_response.tool_calls
            if call.tool_name == "TodoWrite"
        ]

        # Check if we should validate based on frequency
        if (
            self.todo_write_call_count - self.skip_first_n_calls
        ) % self.validate_every_n_calls != 0:
            logger.info(
                f"🎯 Skipping validation (validate every {self.validate_every_n_calls} calls)"
            )
            return HookResult.no_changes()

        # Increment call count
        self.todo_write_call_count += 1

        logger.info(
            f"🎯 Found {len(todo_write_calls)} TodoWrite call(s) (total calls: {self.todo_write_call_count})"
        )

        # Check if we should skip this validation
        if self.todo_write_call_count <= self.skip_first_n_calls:
            logger.info(
                f"🎯 Skipping validation (within first {self.skip_first_n_calls} calls)"
            )
            return HookResult.no_changes()

        # Check if we've reached max validation times
        if self.validation_count >= self.max_validation_times:
            logger.info(
                f"🎯 Max validation times ({self.max_validation_times}) reached, skipping validation"
            )
            return HookResult.no_changes()

        # Perform validation
        self.validation_count += 1
        logger.info(
            f"🎯 Performing validation {self.validation_count}/{self.max_validation_times}"
        )

        try:
            is_valid, feedback = self._validate_todo_write(
                todo_calls=todo_write_calls, messages=hook_input.messages
            )

            if is_valid:
                logger.info("🎯 TodoWrite validation passed")
                return HookResult.no_changes()

            # Validation failed, add feedback and force continue
            logger.warning(f"🎯 TodoWrite validation failed: {feedback}")

            # Remove invalid TodoWrite calls
            hook_input.parsed_response.tool_calls = [
                call
                for call in hook_input.parsed_response.tool_calls
                if call.tool_name != "TodoWrite"
            ]

            # Add feedback message
            modified_messages = hook_input.messages.copy()
            modified_messages.append({"role": "user", "content": feedback})

            logger.info("🎯 TodoWrite validation completed with modifications")
            return HookResult.with_modifications(
                parsed_response=hook_input.parsed_response,
                messages=modified_messages,
                force_continue=True,
            )

        except Exception as e:
            logger.error(f"🎯 Validation failed with exception: {e}")
            # On error, allow the TodoWrite to proceed
            return HookResult.no_changes()

    def _handle_continue_judgment(self, hook_input: AfterModelHookInput) -> HookResult:
        """Handle continue judgment logic (only runs when no TodoWrite calls)."""

        # Check if the agent will finish
        if self._judge_agent_will_finish(hook_input):
            # If research will finish, first judge if the agent needs to continue
            is_complete, judge_reason = self._agent_need_continue(hook_input)
            if is_complete:
                # Research is complete, let it finish
                return HookResult.no_changes()
            else:
                # Research is incomplete, force continue with feedback
                logger.info(
                    f"Continue judge determined research incomplete: {judge_reason}"
                )
                # Append user message with the reason to messages
                modified_messages = hook_input.messages.copy()
                feedback_message = {
                    "role": "user",
                    "content": f"<system_reminder>\nYour research is not yet complete. Please continue with more investigation.\n\nReason: {judge_reason}\n</system_reminder>",
                }
                modified_messages.append(feedback_message)
                # delete handoff_to_report_writer tool call
                hook_input.parsed_response.tool_calls = [
                    tool_call
                    for tool_call in hook_input.parsed_response.tool_calls
                    if tool_call.tool_name != "handoff_to_report_writer"
                ]
                return HookResult.with_modifications(
                    messages=modified_messages, force_continue=True
                )
        else:
            # If research will not finish, return no changes
            return HookResult.no_changes()

    def _judge_agent_will_finish(self, hook_input: AfterModelHookInput) -> bool:
        """Check if the agent intends to finish (has handoff_to_report_writer call)."""
        if hook_input.parsed_response is None:
            return True
        elif hook_input.parsed_response.has_calls():
            all_tool_calls = hook_input.parsed_response.tool_calls
            for tool_call in all_tool_calls:
                if tool_call.tool_name == "handoff_to_report_writer":
                    return True
            return False
        else:
            return True

    def _agent_need_continue(self, hook_input: AfterModelHookInput) -> tuple[bool, str]:
        """Judge if the agent needs to continue researching."""
        if self.continue_times >= self.max_continue_times:
            return True, "Max continue times reached"

        self.continue_times += 1
        agent = load_agent_config(
            self.continue_judge_agent_config_path,
            global_storage=hook_input.agent_state.global_storage,
        )
        system_reminder = "Please judge if the research agent has completed all required research tasks comprehensively."
        input_history = hook_input.messages[1:]  # index-0 is the system message
        input_message = ""
        for message in input_history:
            role = message["role"]
            content = message.get("content", "")
            if len(content) > 8000:
                content = content[:4000] + "\n...[truncated]...\n" + content[-4000:]
            if content:
                input_message += f"<{role}>\n{content}\n</{role}>\n\n"

        user_message = f"<system_reminder>\n{system_reminder}\n</system_reminder>\n\n<research_history>\n{input_message}\n</research_history>"
        response_content = agent.run(user_message)

        # Extract judge_result (case-insensitive, flexible matching)
        judge_result_match = re.search(
            r"<judge_result[^>]*>\s*(true|false|yes|no|1|0)\s*</judge_result>",
            response_content,
            re.IGNORECASE | re.DOTALL,
        )
        if not judge_result_match:
            logger.warning(
                f"Continue judge agent response missing <judge_result> tag. Response: {response_content}"
            )
            return True, "Continue judge agent returned invalid format"

        # More flexible result interpretation
        result_value = judge_result_match.group(1).lower().strip()
        judge_result = result_value in ["true", "yes", "1"]

        # Extract judge_reason if result is False (more flexible matching)
        judge_reason = ""
        if not judge_result:
            judge_reason_match = re.search(
                r"<judge_reason[^>]*>\s*(.*?)\s*</judge_reason>",
                response_content,
                re.IGNORECASE | re.DOTALL,
            )
            if judge_reason_match:
                judge_reason = judge_reason_match.group(1).strip()
            else:
                judge_reason = "The research is incomplete. Please continue with more in-depth investigation."

        return judge_result, judge_reason

    def _validate_todo_write(
        self, todo_calls: list, messages: list
    ) -> tuple[bool, str]:
        """
        Validate TodoWrite calls using the validator agent.

        Args:
            todo_calls: List of TodoWrite tool calls
            messages: Current conversation messages

        Returns:
            (is_valid, feedback): Whether valid and feedback message if invalid
        """
        # Load validator agent
        agent = load_agent_config(
            self.todo_validator_agent_config_path,
            global_storage=None,  # Validator doesn't need shared state
        )

        # Prepare context from messages
        conversation_context = []
        for msg in messages[1:]:  # Skip system message
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Truncate very long content
            if len(content) > 8000:
                content = content[:4000] + "\n...[truncated]...\n" + content[-4000:]

            if content:
                conversation_context.append(
                    f"<{role.upper()}>\n{content}\n</{role.upper()}>"
                )

        conversation_str = "\n\n".join(conversation_context)

        # Prepare TodoWrite parameters
        import json

        todo_params_list = []
        for call in todo_calls:
            try:
                params_str = json.dumps(call.parameters, ensure_ascii=False, indent=2)
                todo_params_list.append(params_str)
            except Exception:
                todo_params_list.append(str(call.parameters))

        todo_params_str = "\n\n---\n\n".join(todo_params_list)

        # Build validation request
        validation_request = f"""<system_reminder>
Please evaluate if the TodoWrite tool call(s) below are reasonable and appropriate.
</system_reminder>

<conversation_history>
{conversation_str}
</conversation_history>

<todo_write_calls>
{todo_params_str}
</todo_write_calls>

Please evaluate and provide your judgment."""

        # Call validator agent
        logger.info("🎯 Calling validator agent...")
        response_content = agent.run(validation_request)
        logger.info(f"🎯 Validator response: {response_content[:200]}...")

        # Parse response using XML tags
        is_valid, feedback = self._parse_validator_response(response_content)

        return is_valid, feedback

    def _parse_validator_response(self, response: str) -> tuple[bool, str]:
        """
        Parse validator agent response with XML tags.

        Expected format:
        <validation_result>true/false</validation_result>
        <validation_reason>reason text</validation_reason>
        <validation_suggestion>suggestion text</validation_suggestion>

        Args:
            response: Validator agent response

        Returns:
            (is_valid, feedback): Whether valid and feedback message if invalid
        """
        # Extract validation_result (case-insensitive)
        result_match = re.search(
            r"<validation_result[^>]*>\s*(true|false|yes|no|1|0)\s*</validation_result>",
            response,
            re.IGNORECASE | re.DOTALL,
        )

        if not result_match:
            logger.warning(
                f"Validator response missing <validation_result> tag. Response: {response}"
            )
            # Default to valid on parse error to avoid blocking
            return True, ""

        # Parse result value
        result_value = result_match.group(1).lower().strip()
        is_valid = result_value in ["true", "yes", "1"]

        if is_valid:
            return True, ""

        # Extract reason and suggestion
        reason_match = re.search(
            r"<validation_reason[^>]*>\s*(.*?)\s*</validation_reason>",
            response,
            re.IGNORECASE | re.DOTALL,
        )

        suggestion_match = re.search(
            r"<validation_suggestion[^>]*>\s*(.*?)\s*</validation_suggestion>",
            response,
            re.IGNORECASE | re.DOTALL,
        )

        reason = reason_match.group(1).strip() if reason_match else ""
        suggestion = suggestion_match.group(1).strip() if suggestion_match else ""

        # Build feedback message
        feedback_parts = ["⚠️ **TodoWrite Validation Failed**"]

        if reason:
            feedback_parts.append(f"\n**Reason**: {reason}")

        if suggestion:
            feedback_parts.append(f"\n**Suggestion**: {suggestion}")

        feedback_parts.append(
            "\n\nPlease adjust your research plan based on the feedback."
        )

        feedback = "".join(feedback_parts)

        return False, feedback

    def _compress_old_user_messages(self, messages: list, agent_state) -> list:
        """
        Compress old user messages to reduce context size.

        Args:
            messages: List of conversation messages
            agent_state: Agent state containing global_storage and agent info

        Returns:
            List of messages with old user messages compressed
        """
        # Get workspace from global_storage
        workspace = agent_state.global_storage.get("workspace")
        if not workspace:
            logger.warning(
                "⚠️ No workspace found in global_storage, skipping compression"
            )
            return messages

        agent_id = agent_state.agent_id
        agent_name = agent_state.agent_name
        # Find all user message indices
        user_message_indices = []
        for idx, msg in enumerate(messages):
            if msg.get("role") in ["user", "tool"]:
                user_message_indices.append(idx)

        if len(user_message_indices) <= 1:
            # Only system/first user message exists, nothing to compress
            logger.info("📝 No user messages to compress (only first user message)")
            return messages

        # Identify messages to compress: exclude first user message and last N user messages
        first_user_idx = user_message_indices[0]
        messages_to_keep_uncompressed = set()

        # Always keep the first user message uncompressed
        messages_to_keep_uncompressed.add(first_user_idx)

        # Keep last N user messages uncompressed
        for idx in user_message_indices[-self.keep_last_n_user_messages :]:
            messages_to_keep_uncompressed.add(idx)

        # Identify messages to compress
        messages_to_compress = []
        for idx in user_message_indices:
            if idx not in messages_to_keep_uncompressed:
                messages_to_compress.append(idx)

        if not messages_to_compress:
            logger.info(
                f"📝 No user messages to compress (keeping first + last {self.keep_last_n_user_messages})"
            )
            return messages

        logger.info(
            f"📝 Compressing {len(messages_to_compress)} user message(s), keeping {len(messages_to_keep_uncompressed)} uncompressed"
        )

        # Create workspace directory if it doesn't exist
        workspace_dir = os.path.join(workspace, "compressed_messages")
        os.makedirs(workspace_dir, exist_ok=True)
        logger.info(f"📁 Using workspace directory: {workspace_dir}")

        # Compress each message
        compressed_messages = messages.copy()
        compressed_count = 0
        for idx in messages_to_compress:
            original_message = messages[idx]

            # Check if already compressed
            if original_message.get("_compressed"):
                logger.info(f"📝 Message at index {idx} already compressed, skipping")
                continue

            # Check if message is large enough to compress
            message_tokens = self.token_counter.count_tokens([original_message])
            if message_tokens < self.min_compress_tokens:
                logger.info(
                    f"📝 Message at index {idx} too small ({message_tokens} tokens < {self.min_compress_tokens}), skipping compression"
                )
                continue

            # Generate message ID
            message_id = (
                f"compressed_message_{agent_name}_{agent_id}_{str(uuid.uuid4())}"
            )

            # Create filename: agent_name_agent_id_message_id.json
            filename = f"{message_id}.json"
            filepath = os.path.join(workspace_dir, filename)

            # Save original message to file and global_storage
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    data = {
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "message_id": message_id,
                        "original_message": original_message,
                        "original_tokens": message_tokens,
                        "compressed_at": idx,
                    }
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    agent_state.global_storage.set(message_id, data)
                logger.info(f"💾 Saved original message to: {filepath}")
            except Exception as e:
                logger.error(f"❌ Failed to save message to {filepath}: {e}")
                continue

            # Create compressed version
            original_content = original_message.get("content", "")

            # Keep only first N characters as preview
            preview = original_content[: self.compressed_preview_chars]
            if len(original_content) > self.compressed_preview_chars:
                preview += "..."

            compressed_content = f"""<compressed_message>
This message has been compressed to save context space.

📊 Original size: {message_tokens} tokens
📝 Preview (first {self.compressed_preview_chars} chars):
<preview>
{preview}
</preview>
🔍 Full message saved to: {filepath}
</compressed_message>"""

            # Update message
            compressed_messages[idx] = {
                "role": original_message.get("role"),
                "content": compressed_content,
                "_compressed": True,
                "_message_id": message_id,
                "_original_filepath": filepath,
                "_original_tokens": message_tokens,
            }

            compressed_count += 1

        logger.info(
            f"✅ Successfully compressed {compressed_count} out of {len(messages_to_compress)} candidate messages"
        )
        return compressed_messages
