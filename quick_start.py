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

"""Test the quick start example loading agent from YAML configuration."""

import argparse
import os
import logging
import dotenv
from datetime import datetime
from pathlib import Path
import json
import shutil

from nexau.archs.config.config_loader import load_agent_config
from nexau.archs.main_sub.agent_context import GlobalStorage
from nexdr.agents.html_creator.merge_slides import build_merged_presentation
from nexdr.utils.update_citation import update_citations


dotenv.load_dotenv()

# Create logger
logger = logging.getLogger()


def get_date():
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")


now_date = get_date()


def setup_logger(workspace: str):
    # Set logger level
    logger.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplication
    if logger.handlers:
        logger.handlers.clear()

    # Create file handler
    file_handler = logging.FileHandler(
        os.path.join(workspace, f"logs_{now_date}.log"), encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Set output format
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def research_agent_run(query: str, context: dict, global_storage: GlobalStorage):
    script_dir = Path(__file__).parent
    research_agent_config_path = str(
        script_dir / "configs/deep_research/deep_research.yaml"
    )
    agent = load_agent_config(
        research_agent_config_path,
        global_storage=global_storage,
    )
    agent.run(query, context=context)
    agent_id = agent.config.agent_id
    agent_name = agent.config.name
    trace_key = f"{agent_name}_{agent_id}_messages"
    deep_research_trace_history = global_storage.get(trace_key)[1:]
    return deep_research_trace_history


def markdown_report_agent_run(
    deep_research_trace_history: list[dict],
    context: dict,
    global_storage: GlobalStorage,
) -> tuple[str, str]:
    script_dir = Path(__file__).parent
    markdown_report_agent_config_path = str(
        script_dir / "configs/markdown_report_writer/report_writer.yaml"
    )
    agent = load_agent_config(
        markdown_report_agent_config_path,
        global_storage=global_storage,
    )
    message = "Please write a markdown report based on the research result."
    response = agent.run(message, history=deep_research_trace_history, context=context)
    report_content, citations = update_citations(response, global_storage)
    report_path = os.path.join(context["workspace"], "markdown_report.md")
    citation_path = os.path.join(context["workspace"], "citations.json")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    with open(citation_path, "w", encoding="utf-8") as f:
        json.dump(citations, f, ensure_ascii=False, indent=2)
    return report_path, citation_path


def html_report_agent_run(
    deep_research_trace_history: dict, context: dict, global_storage: GlobalStorage
) -> str:
    script_dir = Path(__file__).parent
    html_report_agent_config_path = str(
        script_dir / "configs/html_creator/html_creator.yaml"
    )
    agent = load_agent_config(
        html_report_agent_config_path,
        global_storage=global_storage,
    )
    message = "Please write a html presentation based on the research result."
    response = agent.run(message, history=deep_research_trace_history, context=context)
    workspace_root = context["workspace"]
    try:
        data = json.loads(response)
        filepath = data["data"]["filepath"]
        output_path = os.path.join(workspace_root, "html_report.html")
        shutil.copy(filepath, output_path)
        return output_path
    except Exception:
        agent_id = agent.config.agent_id
        agent_name = agent.config.name
        agent_key = f"{agent_name}_{agent_id}_html_creator_data"
        html_creator_data = global_storage.get(agent_key)
        slides = html_creator_data.get("slides", {})
        slide_name = html_creator_data.get("metadata", {}).get(
            "slide_name", "Presentation"
        )
        each_page_contents = []
        for slide in slides.values():
            each_page_contents.append(slide["content"])
        merged_html_content = build_merged_presentation(
            each_page_contents, title=slide_name
        )
        merged_html_filepath = os.path.join(workspace_root, "html_report.html")
        with open(merged_html_filepath, "w", encoding="utf-8") as f:
            f.write(merged_html_content)
        return merged_html_filepath


def agent_run(query: str, report_format: str, output_dir: str):
    start_time = datetime.now()
    request_id = f"request_{now_date}"
    workspace = os.path.abspath(output_dir)
    os.makedirs(workspace, exist_ok=True)
    global_storage = GlobalStorage()
    global_storage.set("request_id", request_id)
    global_storage.set("workspace", workspace)
    global_storage.set("date", now_date)
    context = {"date": now_date, "request_id": request_id, "workspace": workspace}

    deep_research_trace_history = research_agent_run(query, context, global_storage)
    if report_format == "markdown":
        report_path, citation_path = markdown_report_agent_run(
            deep_research_trace_history, context, global_storage
        )
    elif report_format == "html":
        report_path = html_report_agent_run(
            deep_research_trace_history, context, global_storage
        )
        citation_path = None
    else:
        raise ValueError(f"Invalid report format: {report_format}")
    logger.info(f"Report is saved at: {report_path}")
    final_state = {}
    final_state["report_path"] = report_path
    if citation_path:
        final_state["citation_path"] = citation_path
    for key, value in global_storage.items():
        try:
            json.dumps(value)  # try to serialize the value
            final_state[key] = value
        except (TypeError, ValueError):
            # If error, skip
            continue
    end_time = datetime.now()
    final_state["start_time"] = start_time.isoformat()
    final_state["end_time"] = end_time.isoformat()
    final_state["used_time"] = (end_time - start_time).total_seconds()
    final_state_path = os.path.join(workspace, "final_state.json")
    with open(final_state_path, "w") as f:
        json.dump(final_state, f, indent=4, ensure_ascii=False)
    logger.info(f"Final state is saved at: {final_state_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Test the quick start example loading agent from YAML configuration.",
    )
    parser.add_argument(
        "--query",
        type=str,
        required=True,
        help="Query to test the agent",
    )
    parser.add_argument(
        "--report_format",
        type=str,
        default="markdown",
        choices=["markdown", "html"],
        help="Report format: markdown, html",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=f"workspaces/workspace_{now_date}",
        help="Output directory to save the report",
    )
    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)
    setup_logger(args.output_dir)
    agent_run(args.query, args.report_format, args.output_dir)


if __name__ == "__main__":
    main()
