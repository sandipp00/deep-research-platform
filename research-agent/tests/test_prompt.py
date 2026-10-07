from research_agent.agent import graph


def test_prompt_requires_grounding_in_tool_results():
    prompt = graph._RESEARCH_SYSTEM_PROMPT
    assert "## Grounding Rules" in prompt
    assert "MUST be answered from tool results" in prompt
    assert "web_search" in prompt.split("## Tool Usage Guidelines")[0]


def test_prompt_uses_product_name():
    assert "Lumen" in graph._RESEARCH_SYSTEM_PROMPT
    assert "Alvoff" not in graph._RESEARCH_SYSTEM_PROMPT
