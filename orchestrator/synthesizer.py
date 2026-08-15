from mistralai import Mistral
from shared.mistral_utils import call_mistral_with_retry

def synthesize(messages: list, client: Mistral, model_name: str) -> str:
    """Ask Mistral to produce a clean final answer using the tool results already in message history."""
    # Reasoning: We append a final instruction telling Mistral to now write its user-facing response.
    # The full message history (with tool results) is already present, so the model has all context.
    synthesis_prompt = (
        "Based on the tool results above, write a clear, helpful, and concise answer for the user. "
        "Cite the specific data points from the tool results. "
        "Do NOT add information that was not in the tool results."
    )

    synthesis_messages = messages + [{"role": "user", "content": synthesis_prompt}]

    # Reasoning: Call Mistral without tools this time — we just want a plain text answer.
    # Retries on rate limits (429) rather than falling back to canned text.
    response = call_mistral_with_retry(lambda: client.chat.complete(
        model=model_name,
        messages=synthesis_messages
    ))

    return response.choices[0].message.content
