"""Handwritten structure and failure tests; never use saved trajectories/native code."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_checkpoint_prefix_exposure as d


def request(turns=5, *, multi=False, no_tool=False):
    messages = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'task'},
        {'role': 'user', 'content': json.dumps(dict(checkpoint_kind='ordinary_fallible_summary',
            semantics_verified=False, summary={f: [] for f in d.FIELDS}))}]
    for n in range(turns):
        if no_tool and n == 0:
            messages.extend([{'role': 'assistant', 'content': 'text'}, {'role': 'user', 'content': 'fallback'}])
            continue
        calls = [dict(id=f'turn{n}_{j}', type='function', function=dict(name='run_python', arguments='{}'))
                 for j in range(2 if multi and n == 1 else 1)]
        messages.append(dict(role='assistant', content='', reasoning_content='synthetic', tool_calls=calls))
        messages.extend(dict(role='tool', tool_call_id=c['id'], content='synthetic result') for c in calls)
    messages.append(dict(role='user', content=d.NO_TIME_NOTICE+'{"remaining":{"calls":3}}\n</whole_task_budget_v1>'))
    return dict(messages=messages, tools=[{'synthetic': True}], seed=57, stream=False,
                max_tokens=4096, chat_template_kwargs={'enable_thinking': True})


class PrefixTests(unittest.TestCase):
    def test_only_prefix_removed(self):
        original = request()
        saved = deepcopy(original)
        reduced, m = d.remove_eligible(original)
        self.assertEqual(original, saved)
        self.assertEqual((m['eligible_closed_turns'], m['removed_message_count']), (3, 6))
        self.assertEqual(reduced['messages'], original['messages'][:3]+original['messages'][9:])
        self.assertEqual({k:v for k,v in original.items() if k != 'messages'},
                         {k:v for k,v in reduced.items() if k != 'messages'})

    def test_two_recent_empty_prefix(self):
        original = request(2)
        reduced, m = d.remove_eligible(original)
        self.assertEqual(reduced, original)
        self.assertEqual(m['eligible_closed_turns'], 0)
        self.assertEqual(m['removed_UTF8_bytes'], 0)

    def test_pair_boundaries_not_fixed_message_count(self):
        original = request(5, multi=True, no_tool=True)
        reduced, m = d.remove_eligible(original)
        self.assertEqual(m['removed_message_count'], 7)
        self.assertEqual(reduced['messages'][3:], original['messages'][10:])

    def test_malformed_pair_rejected(self):
        original = request()
        original['messages'][4]['tool_call_id'] = 'mismatch'
        with self.assertRaisesRegex(ValueError, 'matching_tool_results'):
            d.remove_eligible(original)

    def test_incomplete_or_too_short_rejected(self):
        with self.assertRaisesRegex(ValueError, 'two_retained'):
            d.remove_eligible(request(1))
        original = request()
        del original['messages'][-2]
        with self.assertRaisesRegex(ValueError, 'incomplete_turn'):
            d.remove_eligible(original)

    def test_extra_summary_or_notice_rejected(self):
        for index, value in ((2, 'unrecognized'), (-1, 'unrecognized')):
            with self.subTest(index=index):
                original = request()
                original['messages'][index]['content'] = value
                with self.assertRaises(ValueError):
                    d.remove_eligible(original)

    def test_nontext_media_rejected(self):
        original = request()
        original['messages'][4]['content'] = [{'type': 'image_url'}]
        with self.assertRaisesRegex(ValueError, 'plain_text'):
            d.remove_eligible(original)

    def test_window_actual_actor_before_next_focus(self):
        controls = [dict(status='checkpoint_decided', accepted=True, revision=1, cutoff=22,
                         after_model_calls=13),
                    dict(status='checkpoint_offered', after_model_calls=22),
                    dict(status='checkpoint_decided', accepted=True, revision=2, cutoff=40,
                         after_model_calls=23)]
        checks = [dict(call_id=f'call_{n:03}', role='focus' if n in (13,23) else 'agent')
                  for n in range(1, 32)]
        window, selected = d.first_window(controls, checks)
        self.assertEqual([r['call_id'] for r in selected], [f'call_{n:03}' for n in range(14,23)])
        self.assertEqual(window['next_offer_after_model_calls'],22)
        self.assertEqual(d.first_window([], checks),(None,[]))

    def test_next_rejected_opportunity_still_ends_window(self):
        controls = [dict(status='checkpoint_decided', accepted=True, revision=1, cutoff=8,
                         after_model_calls=5), dict(status='checkpoint_offered',after_model_calls=8)]
        checks = [dict(call_id=f'call_{n:03}', role='agent') for n in range(1,12)]
        _, selected = d.first_window(controls, checks)
        self.assertEqual([x['call_id'] for x in selected], ['call_006','call_007','call_008'])

    def test_native_original_must_match_usage(self):
        x = dict(input_tokens=3, tokens=[1,2,3], media_files=0,
                 session_controls={'grammar':'x'},parsed_non_message_parameters={'seed':57})
        y = dict(x, input_tokens=2, tokens=[1,3])
        self.assertEqual(d.validate_counts(x,y,3),1)
        with self.assertRaisesRegex(ValueError,'original_usage'):
            d.validate_counts(x,y,4)
        y['session_controls'] = {'grammar':'changed'}
        with self.assertRaisesRegex(ValueError,'grammar_or_parameters'):
            d.validate_counts(x,y,3)

    def test_negative_template_delta_is_not_negative_policy_exposure(self):
        self.assertEqual(d.exposure_totals([5, -3, 0, 2]), dict(signed=4, positive_part=7))
        self.assertEqual(d.exposure_totals([-3]), dict(signed=-3, positive_part=0))

    def test_effective_template_does_not_substitute_raw_gguf_template(self):
        source = dict(effective_template_sha256='c'*64, template_sha256='1'*64)
        self.assertEqual(d.effective_render_plan(source)['effective_template_sha256'], 'c'*64)
        with self.assertRaises(KeyError):
            d.effective_render_plan(dict(template_sha256='1'*64))

    def test_failure_persists_all_four_and_no_sensitive_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tests').mkdir()
            (root/'tests/test_checkpoint_prefix_exposure_diagnosis.py').write_text('synthetic')
            out=root/'new'
            with patch.object(d,'prepare',side_effect=ValueError('private payload must not escape')):
                with self.assertRaises(ValueError):d.run(root,root,out)
            result=json.loads((out/'result.json').read_text())
            self.assertEqual([x['run_id'] for x in result['cells']],list(d.RUNS))
            self.assertEqual(result['status'],'failed')
            self.assertNotIn('private payload',(out/'result.json').read_text())
            with self.assertRaises(FileExistsError):d.run(root,root,out)


if __name__ == '__main__':
    unittest.main()
