from collections.abc import Callable

import pytest
import respx
from httpx import Response

from finalboss.config import LlmConfig, NetworkConfig
from finalboss.http import BoundedHttpClient
from finalboss.llm.editor import (
    OpenRouterEditor,
    OpenRouterLinkedInEditor,
    deterministic_editorial,
    ensure_editorial_coverage,
)
from finalboss.models import EditorialItem, EditorialResult, LinkedInDraft, Story


def test_deterministic_editorial_is_grounded(make_story: Callable[..., Story]) -> None:
    stories = [make_story(index) for index in range(1, 4)]
    result = deterministic_editorial(stories, top_n=2)
    assert [item.item_id for item in result.items] == [story.id for story in stories[:2]]
    assert len(result.forecast_lines) == 2
    assert result.forecast_confidence == "low"


def test_short_model_result_is_backfilled_with_grounded_candidates(
    make_story: Callable[..., Story],
) -> None:
    stories = [make_story(index) for index in range(1, 4)]
    partial = deterministic_editorial(stories[:1], top_n=1).model_copy(
        update={"forecast_confidence": "medium"}
    )
    result = ensure_editorial_coverage(partial, stories, top_n=3)
    assert [item.item_id for item in result.items] == [story.id for story in stories]
    assert result.forecast_confidence == "medium"
    assert "grounded backup" in result.items[-1].uncertainty


def test_editor_rejects_unknown_and_duplicate_ids(make_story: Callable[..., Story]) -> None:
    story = make_story()
    item = EditorialItem(
        item_id=story.id,
        importance=90,
        eli5="A model learned a useful new trick in a documented release.",
        why_it_matters="The capability could lower cost for developers.",
        category="models",
        confidence="high",
    )
    valid = EditorialResult(
        items=[item],
        forecast_lines=[
            "More technical details are likely next week.",
            "Adoption may begin slowly.",
        ],
        forecast_confidence="low",
        evidence_item_ids=[story.id],
    )
    OpenRouterEditor._validate_ids(valid, {story.id})

    duplicate = valid.model_copy(update={"items": [item, item]})
    with pytest.raises(ValueError, match="duplicate"):
        OpenRouterEditor._validate_ids(duplicate, {story.id})

    unknown = valid.model_copy(update={"items": [item.model_copy(update={"item_id": "invented"})]})
    with pytest.raises(ValueError, match="unknown"):
        OpenRouterEditor._validate_ids(unknown, {story.id})

    linkedin = LinkedInDraft(
        topic="A cheaper reasoning model changes the deployment question",
        post_lines=[
            "A cheaper reasoning model changes the deployment question.",
            "The release describes stronger reasoning at a lower operating cost.",
            "That could let more teams test advanced workflows without a large budget.",
            "I would compare it with the current baseline before changing a roadmap.",
            "Which workflow would you test first?",
        ],
        why_now="The documented release creates a timely question for AI builders.",
        evidence_item_ids=[story.id],
    )
    OpenRouterLinkedInEditor._validate_ids(linkedin, {story.id})
    with pytest.raises(ValueError, match="LinkedIn evidence"):
        OpenRouterLinkedInEditor._validate_ids(
            linkedin.model_copy(update={"evidence_item_ids": ["invented"]}),
            {story.id},
        )


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_editor_uses_strict_grounded_output(
    make_story: Callable[..., Story],
) -> None:
    story = make_story()
    response = {
        "items": [
            {
                "item_id": story.id,
                "importance": 88,
                "eli5": "A lab made a reasoning model cheaper and easier to run.",
                "why_it_matters": "Developers can use stronger AI with a smaller budget.",
                "category": "models",
                "confidence": "high",
                "uncertainty": "",
            }
        ],
        "forecast_lines": [
            "Independent benchmarks will probably appear next week.",
            "Developers may begin comparing real-world cost and speed.",
        ],
        "forecast_confidence": "medium",
        "evidence_item_ids": [story.id],
    }
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"content": __import__("json").dumps(response)}}]},
        )
    )
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(network) as client:
        result = await OpenRouterEditor(
            LlmConfig(model="test/model", prompt_version="test-v1", max_attempts=1),
            client,
            api_key="secret",
        ).edit([story], top_n=20)
    assert result.items[0].item_id == story.id
    request_payload = __import__("json").loads(route.calls[0].request.content)
    assert request_payload["response_format"]["json_schema"]["strict"] is True
    assert request_payload["provider"]["require_parameters"] is True
    item_schema = request_payload["response_format"]["json_schema"]["schema"]["properties"]["items"]
    assert item_schema["minItems"] == item_schema["maxItems"] == 1
    assert "url" not in item_schema["items"]["properties"]
    assert (
        "linkedin_draft"
        not in request_payload["response_format"]["json_schema"]["schema"]["properties"]
    )


@pytest.mark.asyncio
@respx.mock
async def test_linkedin_editor_uses_small_strict_grounded_output(
    make_story: Callable[..., Story],
) -> None:
    story = make_story()
    editorial = EditorialItem(
        item_id=story.id,
        importance=88,
        eli5="A lab made a reasoning model cheaper and easier to run.",
        why_it_matters="Developers can use stronger AI with a smaller budget.",
        category="models",
        confidence="high",
    )
    response = {
        "topic": "A cheaper reasoning model changes the deployment question",
        "post_lines": [
            "A cheaper reasoning model changes the deployment question.",
            "The release describes stronger reasoning at a lower operating cost.",
            "That could let more teams test advanced workflows without a large budget.",
            "I would compare it with the current baseline before changing a roadmap.",
            "Which workflow would you test first?",
        ],
        "why_now": "The documented release creates a timely question for AI builders.",
        "evidence_item_ids": [story.id],
    }
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"content": __import__("json").dumps(response)}}]},
        )
    )
    network = NetworkConfig(user_agent="FinalBossTest/1.0 (+https://example.com)")
    async with BoundedHttpClient(network) as client:
        result = await OpenRouterLinkedInEditor(
            LlmConfig(model="test/model", prompt_version="test-v1", max_attempts=1),
            client,
            api_key="secret",
        ).edit([(story, editorial, 90.0)])
    assert result.evidence_item_ids == [story.id]
    request_payload = __import__("json").loads(route.calls[0].request.content)
    linkedin_schema = request_payload["response_format"]["json_schema"]["schema"]["properties"][
        "post_lines"
    ]
    assert linkedin_schema["minItems"] == 4
    properties = request_payload["response_format"]["json_schema"]["schema"]["properties"]
    assert "impression_potential" not in properties
    assert "model_confidence" not in properties
    assert "url" not in request_payload["messages"][1]["content"]
