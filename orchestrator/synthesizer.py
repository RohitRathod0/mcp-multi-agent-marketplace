from mistralai import Mistral

from shared.mistral_utils import REQUEST_TIMEOUT_MS, call_mistral_with_retry

# Reasoning: What the user sees when the router called no tool at all. Returned WITHOUT
# consulting the model, because the only reliable way to stop a language model inventing
# facts it has no source for is to not ask it for an answer in the first place.
NO_GROUNDING_ANSWER = (
    "I couldn't answer that from the marketplace systems — no pricing, inventory, or "
    "risk tool returned data for this request, so I have nothing to base an answer on. "
    "This may be because the product or seller isn't in our records, or the question "
    "falls outside the policies in the knowledge base. Please rephrase, or escalate to a "
    "human operator."
)


def synthesize(messages: list, client: Mistral, model_name: str, tool_calls: list | None = None) -> str:
    """Ask Mistral to produce a clean final answer using the tool results already in message history."""
    # Reasoning: This guard exists because of two real hallucinations caught by the
    # 20-query audit. Asked for a competitor price and for a product's SKU, the router
    # called no tool, and the synthesis prompt below — which says "Based on the tool
    # results above" unconditionally — presupposed results that did not exist. The model
    # dutifully complied by inventing them: fictional competitors at fictional prices, a
    # fabricated SKU and supplier, each introduced with the words "based on the tool
    # results". Instructing a model not to add outside information cannot help when the
    # prompt itself asserts that evidence is present. So when nothing was retrieved, we
    # do not ask.
    if not tool_calls:
        return NO_GROUNDING_ANSWER

    # Reasoning: We append a final instruction telling Mistral to now write its user-facing
    # response. The full message history (with tool results) is already present.
    synthesis_prompt = (
        "Based on the tool results above, write a clear, helpful, and concise answer for the user. "
        "Cite the specific data points from the tool results. "
        "Do NOT add information that was not in the tool results. "
        # Reasoning: The audit also caught the model inventing a confidence threshold
        # ('below the 0.8 threshold' when the real floor is 0.30). Numbers are the claims
        # users are least able to sanity-check, so they get called out explicitly.
        "Do NOT invent identifiers, prices, suppliers, or numeric thresholds: every number "
        "and identifier you state must appear in the tool results above. "
        "If a tool reported INSUFFICIENT_GROUNDING, LOW_CONFIDENCE_ESCALATION_REQUIRED, or "
        "that a record was not found, report exactly that and recommend escalation — do not "
        "substitute your own knowledge."
    )

    synthesis_messages = messages + [{"role": "user", "content": synthesis_prompt}]

    # Reasoning: Call Mistral without tools this time — we just want a plain text answer.
    # Retries on rate limits (429) rather than falling back to canned text.
    # Reasoning: Bounded request — without timeout_ms a stalled connection hangs the whole
    # run silently instead of raising something the retry wrapper can act on.
    response = call_mistral_with_retry(lambda: client.chat.complete(
        model=model_name,
        messages=synthesis_messages,
        timeout_ms=REQUEST_TIMEOUT_MS,
    ))

    return response.choices[0].message.content
