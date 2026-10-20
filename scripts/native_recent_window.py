"""A deterministic recent-history baseline; no model-based compression."""
from context_preservation import compact
from native_memory_view import recorded_turns, retained_view


def recent_window(conversation, count_tokens, history_budget=4096, page_limit=24000):
    if type(history_budget) is not int or history_budget < 1:
        raise ValueError('positive history budget required')
    turns = recorded_turns(conversation)
    all_ids = [s['id'] for _, spans in turns for s in spans]
    counts = []

    def candidate(ids):
        messages, detail = retained_view(conversation, ids, page_limit=page_limit)
        text = compact(messages[2:])  # Excludes fixed task/system and API schemas.
        tokens = count_tokens(text)
        if type(tokens) is not int or tokens < 0:
            raise ValueError('tokenizer returned an invalid length')
        counts.append({'selected_spans': len(detail['retained_span_ids']),
                       'history_tokens': tokens})
        return messages, detail, tokens

    full = candidate(all_ids)
    if full[2] <= history_budget or len(turns) <= 1:
        chosen = full
    else:
        # Keep at least the latest whole response, even if it exceeds the proxy
        # budget. Never sever a tool request/result pair to force a fit.
        chosen = candidate([s['id'] for s in turns[-1][1]])
        if chosen[2] <= history_budget:
            for start in range(len(turns) - 2, -1, -1):
                attempt = candidate([s['id'] for _, group in turns[start:] for s in group])
                if attempt[2] > history_budget:
                    break
                chosen = attempt
    messages, detail, tokens = chosen
    return messages, {**detail, 'history_tokens': tokens, 'history_budget': history_budget,
                      'history_budget_overflow': tokens > history_budget,
                      'token_count_requests': len(counts), 'candidate_counts': counts,
                      'selection_rule': 'Full if within budget, otherwise newest whole turns '
                                        'until the first candidate exceeding the proxy budget; '
                                        'always retain the newest whole turn.'}
