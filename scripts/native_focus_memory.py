"""FOCUS-based retention on original native turns; an adapted existing baseline."""
import copy
import json

from analyze_focus_shortcircuit import all_retained_certificate
from context_preservation import FOCUS_PROMPT, FOCUS_TOOL, compact, parse_submission, render_memory, select_focus
from native_memory_view import recorded_turns, retained_view


def draft_messages(task, spans, selected, api_tools, page_limit):
    user = compact({'task': task,
                    'memory': json.loads(render_memory(spans, selected, page_limit=page_limit)),
                    'available_api_schemas': api_tools})
    return [{'role': 'system', 'content': FOCUS_PROMPT}, {'role': 'user', 'content': user}]


class FocusMemory:
    def __init__(self):
        self.selected = []
        self.seen = set()
        self.events = []

    def prepare(self, conversation, task, api_tools, infer, count_tokens, config, save_event):
        spans = {s['id']: s for _, group in recorded_turns(conversation) for s in group}
        self.selected = self.selected + [sid for sid in spans if sid not in self.seen]
        self.seen.update(spans)
        messages, detail = retained_view(conversation, self.selected,
                                         page_limit=config['observation_page_characters'])
        self.selected = list(detail['retained_span_ids'])
        before_tokens = count_tokens(compact(messages[2:]))
        before = list(self.selected)
        event_index = None
        if before_tokens > config['history_budget_tokens']:
            event = {'visible_before': before, 'visible_after': before,
                     'history_tokens_before': before_tokens, 'status': 'started',
                     'first_call_index': len(infer.calls), 'drafts': [],
                     'early_all_retained': False}
            self.events.append(event)
            event_index = len(self.events) - 1
            initial_tokens = infer.tokens
            try:
                # API definitions are also available to the executor outside its
                # transcript. Include those public definitions as inert data;
                # only the selection submission tool is callable by this role.
                inputs = draft_messages(task, spans, before, api_tools,
                                        config['observation_page_characters'])
                drafts = []
                for _ in range(config['focus_rollouts']):
                    response = infer.call('focus', inputs, [FOCUS_TOOL])
                    draft = parse_submission(response, 'submit_selection')
                    drafts.append(draft)
                    certified = all_retained_certificate(
                        drafts, before, config['focus_rollouts'], config['focus_threshold'])
                    event['drafts'].append({'call_id': infer.calls[-1]['id'],
                                            'all_retained_certificate': certified})
                    if certified:
                        event['early_all_retained'] = True
                        keep = before
                        break
                else:
                    keep, _ = select_focus(drafts, before, config['focus_threshold'])
                messages, detail = retained_view(conversation, keep,
                                                 page_limit=config['observation_page_characters'])
                self.selected = list(detail['retained_span_ids'])
                event.update(status='ok', requested_span_ids=list(keep),
                             visible_after=list(self.selected))
            except (ValueError, KeyError, TypeError) as error:
                # Invalid memory is never executed or silently repaired.
                self.selected = before
                event.update(status='invalid_keep_original', error_type=type(error).__name__)
                messages, detail = retained_view(conversation, before,
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
                          'selection_rule': 'Existing FOCUS citation threshold plus rescue, whole-turn '
                                            'closure, certified all-retained early exit; no hard size target.'}
