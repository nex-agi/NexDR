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

from typing import Annotated
import arxiv
from nexdr.agents.deep_research.update_search_resources import update_search_resources
from nexau.archs.main_sub.agent_context import GlobalStorage
from nexdr.agents.tool_types import create_success_tool_result, create_error_tool_result


def arxiv_search_papers(
    keywords: Annotated[
        str, "The keywords to search for. Use comma to separate multiple keywords."
    ],
    categories: Annotated[
        list[str] | None,
        "The categories to search for. Default is None. Supported categories are e.g. 'cs.LG', 'cs.AI', 'cs.CL'.",
    ] = None,
    max_results: Annotated[
        int,
        "The number of results to return. Default is 10.",
    ] = 10,
    sort_by: Annotated[
        str,
        "The field to sort the results by. Default is 'submittedDate'.",
    ] = "submittedDate",
    sort_order: Annotated[
        str,
        "The order to sort the results by. Default is 'descending'.",
    ] = "descending",
    global_storage: GlobalStorage = None,
) -> str:
    """
    Search arXiv papers.

    Args:
        keywords: List of keywords.
        categories: List of arXiv categories (e.g. ['cs.LG', 'cs.AI', 'cs.CL'], optional).
        max_results: Maximum number of results.
        sort_by: Sorting field (submittedDate, lastUpdatedDate, relevance).
        sort_order: Sorting order (ascending, descending).

    Returns:
        Retrieved paper information.
    """
    try:
        # Build the query string
        query_parts = []

        # Add keyword queries
        if keywords:
            keywords = keywords.split(",")
            keyword_parts = []
            for keyword in keywords:
                keyword_parts.append(f'all:"{keyword}"')
            query_parts.append(f"({' OR '.join(keyword_parts)})")

        # Add category queries
        if categories:
            category_parts = []
            for category in categories:
                category_parts.append(f"cat:{category}")
            query_parts.append(f"({' OR '.join(category_parts)})")

        # Return an error if no query parameters are provided
        if not query_parts:
            return "No keywords or categories provided"

        # Combine the query parts with AND between keywords and categories
        query = " AND ".join(query_parts)

        def search_arxiv():
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=getattr(
                    arxiv.SortCriterion,
                    sort_by,
                    arxiv.SortCriterion.SubmittedDate,
                ),
                sort_order=getattr(
                    arxiv.SortOrder,
                    sort_order.title(),
                    arxiv.SortOrder.Descending,
                ),
            )

            papers = []
            for result in search.results():
                paper_info = {
                    "title": result.title,
                    "authors": [author.name for author in result.authors],
                    "snippet": (
                        result.summary[:200] + "..."
                        if len(result.summary) > 200
                        else result.summary
                    ),
                    "published": result.published.isoformat(),
                    "updated": result.updated.isoformat() if result.updated else None,
                    "arxiv_id": result.entry_id.split("/")[-1],
                    "link": result.pdf_url,
                    "categories": result.categories,
                    "primary_category": result.primary_category,
                    "comment": result.comment,
                    "journal_ref": result.journal_ref,
                    "doi": result.doi,
                }
                papers.append(paper_info)

            return papers

        # Execute the search asynchronously in the thread pool
        papers = search_arxiv()
        papers = update_search_resources(papers, global_storage)
        data = {
            "arxiv_search_papers_result": papers,
        }
        message = "Successfully searched arxiv papers"
        tool_result = create_success_tool_result(data, message, "arxiv_search_papers")
        return tool_result

    except Exception as e:
        error = f"Error occurred: {e} when searching arxiv papers"
        message = "Failed to search arxiv papers"
        tool_result = create_error_tool_result(error, message, "arxiv_search_papers")
        return tool_result
