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
from nexau.archs.main_sub.agent_context import GlobalStorage
import logging

logger = logging.getLogger(__name__)


def update_citations(report_content: str, global_storage: GlobalStorage):
    """
    Update citations in the report.

    Args:
        report_content: Report content string
        global_storage: Global storage object that contains resources information

    Returns:
        tuple: (report_content, cite_id2cite_meta)
            - report_content: Original report content
            - cite_id2cite_meta: Mapping from citation IDs to citation metadata
    """

    def split_compound_citation_block(citation_block):
        """
        Split a compound citation block into individual citation blocks.
        Example: A block containing multiple citations is split into individual single-citation blocks.

        Returns:
            List of individual citation blocks
        """
        # Remove the outer 【】 characters
        inner_content = citation_block.strip("【】")

        # Split each citation entry by comma
        cite_items = [item.strip() for item in inner_content.split(",")]

        individual_blocks = []
        for item in cite_items:
            if "†" in item:
                # Citation with location information, such as 11†L26 or 11†S1
                individual_blocks.append(f"【{item}】")
            else:
                # Citation without location information, such as 11; default to S1
                cite_id = item.strip()
                if cite_id:  # Ensure the string is not empty
                    individual_blocks.append(f"【{cite_id}†S1】")

        return individual_blocks

    # Regex that matches every citation block: 【...】
    citation_block_pattern = r"【[^】]+】"

    # Find all citation blocks
    original_citation_blocks = re.findall(citation_block_pattern, report_content)
    logger.info(
        f"Found {len(original_citation_blocks)} original citation blocks in report"
    )

    # Split compound citation blocks and replace the original content
    replacement_map = {}  # Original citation block -> list of split citation blocks

    for original_block in original_citation_blocks:
        individual_blocks = split_compound_citation_block(original_block)
        replacement_map[original_block] = individual_blocks

        # Replace the original block in report_content with the split result
        replacement_text = "".join(individual_blocks)
        report_content = report_content.replace(original_block, replacement_text)

    # Collect all citation blocks again (each one is now individual)
    all_individual_blocks = []
    for blocks in replacement_map.values():
        all_individual_blocks.extend(blocks)

    logger.info(f"Split into {len(all_individual_blocks)} individual citation blocks")

    # Use the original simple regex to process the individual citation blocks
    # Regex matching citation formats such as , ,
    citation_pattern = r"【(\d+)†([LS]\d+(?:-[LS]\d+)?)】"

    # Extract all citations
    all_citations = re.findall(citation_pattern, report_content)
    logger.info(f"Found {len(all_citations)} individual citations in processed content")

    # Build the cite_id2cite_meta dictionary
    cite_id2cite_meta = {}

    with global_storage.lock_key("resources"):
        resources = global_storage.get("resources", {})
        id2url = {item["id"]: item["link"] for item in resources.values()}
        logger.info(f"Retrieved {len(resources)} resources from global storage")

        # Process each citation
        for cite_id, cite_location in all_citations:
            cite_key = f"【{cite_id}†{cite_location}】"
            try:
                cite_id = int(cite_id)
            except ValueError:
                logger.warning("convert cite id failed, delete it")
                report_content = report_content.replace(cite_key, "")
                continue
            cite_url = id2url.get(cite_id, "")
            if not cite_url:
                logger.warning(
                    f"Resource not found for citation ID: {cite_id}, delete it"
                )
                report_content = report_content.replace(cite_key, "")
                continue

            # Retrieve the corresponding citation metadata from resources
            if cite_url not in resources:
                logger.warning(
                    f"Resource not found for citation ID: {cite_id}, delete it"
                )
                report_content = report_content.replace(cite_key, "")
                continue

            resource = resources[cite_url]
            cite_title = resource.get("title", "")

            # Build cite_text (the citation location within the original content)
            if "S" in cite_location:
                try:
                    snippet_id = int(cite_location.replace("S", ""))
                except ValueError:
                    logger.warning("convert snippet id failed, delete it")
                    report_content = report_content.replace(cite_key, "")
                    continue
                if (
                    "snippet_id2content" not in resource
                    or snippet_id not in resource["snippet_id2content"]
                ):
                    logger.warning(
                        f"Snippet not found for citation ID: {cite_id}, delete it"
                    )
                    report_content = report_content.replace(cite_key, "")
                    continue
                cite_text = resource["snippet_id2content"][snippet_id]

            elif "L" in cite_location:
                try:
                    if "-" in cite_location:
                        line_id_start, line_id_end = cite_location.split("-")
                        line_id_start = int(line_id_start.replace("L", ""))
                        line_id_end = int(line_id_end.replace("L", ""))
                    else:
                        line_id_start = int(cite_location.replace("L", ""))
                        line_id_end = line_id_start
                except ValueError:
                    logger.warning("convert line id failed, delete it")
                    report_content = report_content.replace(cite_key, "")
                    continue
                if (
                    "line_id_2_content" not in resource
                    or line_id_start not in resource["line_id_2_content"]
                    or line_id_end not in resource["line_id_2_content"]
                ):
                    logger.warning(
                        f"Line not found for citation ID: {cite_id}, delete it"
                    )
                    report_content = report_content.replace(cite_key, "")
                    continue
                cite_text = ""
                for line_id in range(line_id_start, line_id_end + 1):
                    cite_text += resource["line_id_2_content"][line_id] + "\n\n"
                cite_text = cite_text.strip()
            else:
                logger.warning(f"Unknown citation location: {cite_location}, delete it")
                report_content = report_content.replace(cite_key, "")
                continue

            cite_id2cite_meta[cite_key] = {
                "cite_text": cite_text,
                "cite_url": cite_url,
                "cite_title": cite_title,
            }

    logger.info(f"Successfully processed {len(cite_id2cite_meta)} citations")
    if len(cite_id2cite_meta.keys()) == 0:
        return report_content, {}
    reference_seatction = "\n\n## References\n\n"
    for cite_key, cite_meta in cite_id2cite_meta.items():
        reference_seatction += (
            f"- {cite_key}: [{cite_meta['cite_title']}]({cite_meta['cite_url']})\n"
        )
    report_content = report_content.rstrip() + reference_seatction.rstrip()
    return report_content, cite_id2cite_meta
