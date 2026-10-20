"""Ordinary incremental working ledger with recent original turns, not a new method."""
import copy

from context_preservation import (LEDGER_PROMPT, LEDGER_TOOL, compact, parse_submission,
                                  render_memory, validate_ledger)
from native_memory_view import recorded_turns, retained_view
import json


def draft_messages(task, spans, selected, ledger, api_tools, page_limit):
    return [{'role': 'system', 'content': LEDGER_PROMPT},
            {'role': 'user', 'content': compact({
                'task': task,
                'memory': json.loads(render_memory(spans, selected, ledger, page_limit)),
                'available_api_schemas': api_tools})}]


class LedgerMemory:
    def __init__(self):
        self.selected, self.events = [], []
        self.seen, self.ledger = set(), None

    def prepare(self, conversation, task, api_tools, infer, count_tokens, config, save_event):
        spans = {s['id']: s for _, group in recorded_turns(conversation) for s in group}
        self.selected = self.selected + [sid for sid in spans if sid not in self.seen]
        self.seen.update(spans)
        messages, detail = retained_view(conversation, self.selected, self.ledger,
                                         page_limit=config['observation_page_characters'])
        self.selected = list(detail['retained_span_ids'])
        before_tokens = count_tokens(compact(messages[2:]))
        before, old_ledger = list(self.selected), copy.deepcopy(self.ledger)
        event_index = None
        if before_tokens > config['history_budget_tokens']:
            event = {'visible_before': before, 'visible_after': before,
                     'history_tokens_before': before_tokens, 'status': 'started',
                     'first_call_index': len(infer.calls), 'early_all_retained': False,
                     'ledger_before': old_ledger, 'ledger_after': old_ledger}
            self.events.append(event)
            event_index, initial_tokens = len(self.events) - 1, infer.tokens
            try:
                inputs = draft_messages(task, spans, before, old_ledger, api_tools,
                                        config['observation_page_characters'])
                message = infer.call('ledger', inputs, [LEDGER_TOOL])
                value = parse_submission(message, 'submit_ledger')
                previous_sources = {sid for item in (old_ledger or {}).get('items', [])
                                    for sid in item['source_ids']}
                ledger = validate_ledger(value, set(before) | previous_sources)
                recent = config['ledger_recent_spans']
                if type(recent) is not int or recent < 1:
                    raise ValueError('ledger retains at least one original span')
                keep = before[-recent:]
                messages, detail = retained_view(conversation, keep, ledger,
                                                 page_limit=config['observation_page_characters'])
                self.selected, self.ledger = list(detail['retained_span_ids']), copy.deepcopy(ledger)
                event.update(status='ok', requested_span_ids=list(keep),
                             visible_after=list(self.selected), ledger_after=copy.deepcopy(ledger),
                             semantics_verified=False)
            except (ValueError, KeyError, TypeError) as error:
                self.selected, self.ledger = before, old_ledger
                event.update(status='invalid_keep_original', error_type=type(error).__name__)
                messages, detail = retained_view(conversation, before, old_ledger,
                                                 page_limit=config['observation_page_characters'])
            except Exception as error:
                event.update(status='aborted', error_type=type(error).__name__)
                raise
            finally:
                event.update(calls=len(infer.calls) - event['first_call_index'],
                             known_tokens=infer.tokens - initial_tokens,
                             unknown_usage_calls=sum(c['status'] != 'ok'
                                 for c in infer.calls[event['first_call_index']:]))
                save_event(copy.deepcopy(self.events))
        after_tokens = count_tokens(compact(messages[2:])) if event_index is not None else before_tokens
        return messages, {**detail, 'history_tokens_before': before_tokens,
                          'history_tokens': after_tokens, 'history_budget': config['history_budget_tokens'],
                          'history_budget_overflow': after_tokens > config['history_budget_tokens'],
                          'compression_event_index': event_index,
                          'selection_rule': 'Ordinary incremental ledger plus recent original spans '
                                            'with whole-turn closure. Ledger is fallible; no hard size target.'}
