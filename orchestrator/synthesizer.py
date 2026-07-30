import anthropic

def synthesize(messages: list, client: anthropic.Anthropic, model_name: str) -> str:
    """Ask Claude to produce a clean final answer using the tool results already in message history."""
    # Reasoning: We append a final instruction telling Claude to now write its user-facing response.
    # The full message history (with tool results) is already present, so Claude has all context.
    synthesis_prompt = (
        "Based on the tool results above, write a clear, helpful, and concise answer for the user. "
        "Cite the specific data points from the tool results. "
        "Do NOT add information that was not in the tool results."
    )

    synthesis_messages = messages + [{"role": "user", "content": synthesis_prompt}]

    # Reasoning: Call Claude without tools this time — we just want a plain text answer.
    response = client.messages.create(
        model=model_name,
        max_tokens=1024,
        messages=synthesis_messages
    )

    return response.content[0].text
