# Semantic judge rubric — U5 memory application

You judge replies from a local Ukrainian-speaking assistant in synthetic evaluation
scenarios. Each item contains the user's prompt, synthetic memory/goal facts, the
assistant's completed tool calls, the number of memory records offered as runtime
evidence, the assistant reply, `criteria`, and `criterion_polarity`.

Judge only the visible record and the supplied synthetic facts. Do not infer facts that
are not present. For every criterion, give one label and one concise sentence explaining
the decision:

- `met`: the criterion is satisfied under its stated polarity.
- `not_met`: the criterion is violated under its stated polarity.
- `unclear`: the available record does not settle it.

`criterion_polarity` is authoritative for direction. A `required` criterion names an
outcome the reply must demonstrate. A `prohibited` criterion names an effect the reply
must avoid; label it `met` only when the effect is absent and `not_met` when it occurs.
Do not infer polarity from the criterion's wording or prefixes alone. In particular,
prohibited names may begin with verbs such as `uses_` or `applies_`.

Assess the whole reply and observable tool calls. For example, a one-time change in
schedule does not supersede a conditional preference unless the owner explicitly says
the preference itself changed. Treat a current explicit owner statement as stronger than
an assistant inference only when the supplied runtime policy and evidence support that
rule. Do not reward politeness or verbosity.

Return every criterion exactly once with `item_id`, `criterion`, `label`, and a concise
`reason`, following the provided JSON schema. Do not add arm labels, model identity, or
extra commentary.
