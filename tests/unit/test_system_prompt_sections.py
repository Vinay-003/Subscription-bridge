from __future__ import annotations

from subscription_bridge.api.openai.message_converter import (
    COMPACT_SYSTEM_BUDGET_TOKENS,
    SYSTEM_CONTEXT_TAG,
    SYSTEM_CONTRACT_TAG,
    compact_system_prompt,
    delta_reference_note,
    render_system_prompt,
    split_system_prompt,
)

SKILLS_SECTION = "<available_skills>\n" + "".join(
    f"  <skill>\n    <name>skill-{i}</name>\n    <description>{'x' * 80}</description>\n  </skill>\n"
    for i in range(6)
) + "</available_skills>"

BACKGROUND = "# Core Mandates\n" + ("You must keep responses concise.\n" * 12)
TOOLS = "\nYou have access to tools. Available tools:\n" + "".join(
    f"- tool_{i}: description of tool {i} covering arguments and when to use it\n" for i in range(8)
)
RULES = "\n\n# Final Reminder\n" + ("Answer only from the prompt and stay under four lines.\n" * 8)


def test_split_at_available_skills_boundary() -> None:
    text = BACKGROUND + SKILLS_SECTION + TOOLS + RULES
    part1, part2 = split_system_prompt(text)
    assert part1.endswith("</available_skills>")
    assert part2.startswith("You have access to tools.")
    assert "skill-0" in part1
    assert "Answer only from the prompt" in part2


def test_split_at_tool_instruction_when_no_skills() -> None:
    text = BACKGROUND + RULES + TOOLS
    part1, part2 = split_system_prompt(text)
    assert "Available tools" not in part1
    assert part2.startswith("You have access to tools.")


def test_split_falls_back_to_paragraph_break() -> None:
    text = ("Background statement about who the agent is.\n" * 30).strip()
    text += "\n\n" + ("Operating rule for how the agent must behave.\n" * 30).strip()
    part1, part2 = split_system_prompt(text)
    assert part1 and part2
    assert "Background statement" in part1
    assert "Operating rule" in part2


def test_split_returns_single_section_for_short_prompt() -> None:
    part1, part2 = split_system_prompt("You are a coder.")
    assert part1 == "You are a coder."
    assert part2 == ""


def test_split_empty_prompt() -> None:
    assert split_system_prompt("   ") == ("", "")


def test_render_wraps_both_sections_in_tags() -> None:
    text = BACKGROUND + SKILLS_SECTION + TOOLS + RULES
    rendered = render_system_prompt(text)
    assert rendered.startswith(f"<{SYSTEM_CONTEXT_TAG}>")
    assert f"</{SYSTEM_CONTEXT_TAG}>\n\n<{SYSTEM_CONTRACT_TAG}>" in rendered
    assert rendered.endswith(f"</{SYSTEM_CONTRACT_TAG}>")


def test_render_leaves_unsplittable_prompt_unchanged() -> None:
    prompt = "You are a coder."
    assert render_system_prompt(prompt) == prompt


def test_compact_drops_background_and_keeps_rules_bounded() -> None:
    text = BACKGROUND + SKILLS_SECTION + RULES + TOOLS
    compacted = compact_system_prompt(text)
    assert "skill-0" not in compacted
    assert "# Final Reminder" in compacted
    assert len(compacted) < len(text)
    assert len(compacted) <= (COMPACT_SYSTEM_BUDGET_TOKENS * 4) + 1024


def test_compact_preserves_tool_contract() -> None:
    text = BACKGROUND + SKILLS_SECTION + TOOLS
    compacted = compact_system_prompt(text)
    assert "You have access to tools." in compacted
    assert "- tool_0: description of tool 0" in compacted


def test_compact_uses_guidelines_section_when_present() -> None:
    text = "# Operational Guidelines\n" + ("Do the safe thing first.\n" * 40) + TOOLS
    compacted = compact_system_prompt(text)
    assert compacted.index("# Operational Guidelines") > compacted.index("Earlier conversation turns")
    assert "You have access to tools." in compacted


def test_compact_bounds_long_prompt() -> None:
    long_rules = "\n\n".join(
        f"## Section {i}\n" + ("rule text for compaction budget\n" * 40) for i in range(60)
    )
    text = "# Operational Guidelines\n" + long_rules + TOOLS
    compacted = compact_system_prompt(text)
    assert len(compacted) <= COMPACT_SYSTEM_BUDGET_TOKENS * 4 + len(TOOLS) + 256
    assert "You have access to tools." in compacted


def test_compact_short_prompt_keeps_content() -> None:
    compacted = compact_system_prompt("You are a coder.")
    assert "You are a coder." in compacted
    assert "Earlier conversation turns" in compacted


def test_delta_reference_note_with_tools_points_at_first_message() -> None:
    note = delta_reference_note(True)
    assert note.startswith("\n\n[Reminder")
    assert "first message" in note
    assert f"<{SYSTEM_CONTEXT_TAG}>" in note
    assert f"<{SYSTEM_CONTRACT_TAG}>" in note
    assert '{"tool_calls": [{"function": {"name": "<tool name from the first message>"' in note
    assert "no access to local files" in note


def test_delta_reference_note_without_tools_omits_tool_contract() -> None:
    note = delta_reference_note(False)
    assert note.startswith("\n\n[Reminder")
    assert "tool_calls" not in note
    assert SYSTEM_CONTRACT_TAG in note


def test_switch_compaction_prompt_has_template_and_first_message_exclusion() -> None:
    from subscription_bridge.api.openai.message_converter import (
        build_switch_compaction_prompt,
    )

    prompt = build_switch_compaction_prompt()
    for section in (
        "## Objective",
        "## Requirements",
        "## Decisions",
        "### Completed",
        "### Active",
        "### Blocked",
        "## Next Move",
        "## Relevant Files",
        "## Important Context",
    ):
        assert section in prompt
    assert "summarize the conversation above" in prompt
    assert "Summarize only what the user and the assistant said and did." in prompt
    assert "first message of this conversation (its system prompt)" in prompt
    assert "do not mention, restate, or carry forward any of them" in prompt
    assert "Do not continue the task or call tools." in prompt
    assert "Do not mention the summary process" in prompt


def test_local_history_excerpt_keeps_recent_tail_and_roles() -> None:
    from types import SimpleNamespace

    from subscription_bridge.api.openai.message_converter import local_history_excerpt

    messages = [
        SimpleNamespace(role="system", content="secret system rules"),
        SimpleNamespace(role="user", content="cover me"),
        SimpleNamespace(role="assistant", content="covered"),
    ]
    excerpt = local_history_excerpt(messages)
    assert excerpt.startswith("Previous conversation:")
    assert "User: cover me" in excerpt
    assert "Assistant: covered" in excerpt
    assert "secret system rules" not in excerpt


def test_local_history_excerpt_truncates_long_history() -> None:
    from types import SimpleNamespace

    from subscription_bridge.api.openai.message_converter import local_history_excerpt

    messages = [
        SimpleNamespace(role="user", content=f"turn {i} " + ("x" * 800))
        for i in range(60)
    ]
    excerpt = local_history_excerpt(messages, limit_chars=2000)
    assert excerpt.startswith("Previous conversation (truncated to the most recent part):")
    assert len(excerpt) < 3000
    assert "turn 59" in excerpt
    assert "turn 0 " not in excerpt


def test_local_history_excerpt_empty_history_is_empty() -> None:
    from subscription_bridge.api.openai.message_converter import local_history_excerpt

    assert local_history_excerpt([]) == ""
