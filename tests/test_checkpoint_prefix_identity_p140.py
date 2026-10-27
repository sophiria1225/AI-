import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_prefix_identity_p140 import (EVIDENCE_FIELD, PrefixIdentityError,
    canonical_prefix_evidence, representation_prefix_comparison)
from receipt_reasoning_history import digest


def fixture(reference='opaque-a'):
    message = {'role': 'assistant', 'content': '', 'reasoning_content': 'opaque text',
        'tool_calls': [{'id': reference, 'type': 'function',
                        'function': {'name': 'run_python', 'arguments': '{"code":"pass"}'}}]}
    focus = {'role': 'assistant', 'content': 'handwritten summary', 'reasoning_content': ''}
    records = [dict(call_id='call_001', role='agent', status='ok', request_sha256='1'*64,
                    message=message),
               dict(call_id='call_002', role='focus', status='ok', request_sha256='2'*64,
                    message=focus)]
    archive = [dict(role='system', content='fixture'), dict(role='user', content='fixture task'),
        copy.deepcopy(message), dict(role='tool', tool_call_id=reference, name='run_python',
            content=json.dumps({'span_id':'s1', 'observation':{'result':'handwritten'}}))]
    evidence = canonical_prefix_evidence(records, archive)
    first = dict(cutoff=3, opportunity_index=1, after_model_calls=2,
        summary_note_sha256='3'*64, summary_notes_sha256='4'*64,
        fragment_budget={'fragment_count':1})
    second = dict(after_model_calls=2, previous_cutoff=3, candidate_cutoff=5,
        accumulated_exposure=100, previous_focus_cost=90, first_checkpoint=first,
        prior_request_output_sequence=[{k:r[k] for k in ('call_id','role','status','request_sha256')}
            | {'known_assistant_message_sha256':digest(r['message'])} for r in records],
        all_prior_terminal_usage_known=True, prior_summary_notes_sha256='4'*64,
        **{EVIDENCE_FIELD:evidence})
    return records, archive, {'representation_second_opportunity':second}


class ProtocolIdentityTests(unittest.TestCase):
    def test_ids_only_canonical_equal_strict_false_and_inputs_unchanged(self):
        ra, aa, a = fixture('first'); rb, ab, b = fixture('second')
        saved = copy.deepcopy((ra, aa, a, rb, ab, b))
        result = representation_prefix_comparison(a,b)
        self.assertIs(result['strict_match'], False)
        self.assertIs(result['canonical_match'], True)
        self.assertEqual((ra, aa, a, rb, ab, b), saved)

    def test_exact_original_is_also_exact(self):
        _, _, a=fixture()
        self.assertEqual((representation_prefix_comparison(a,a)['strict_match'],
                          representation_prefix_comparison(a,a)['canonical_match']),(True,True))

    def test_every_non_reference_assistant_value_is_preserved(self):
        for field in ('content','reasoning_content','name','arguments'):
            with self.subTest(field=field):
                records, archive, b=fixture('different')
                message=records[0]['message']
                if field in ('content','reasoning_content'):message[field]+=' changed'
                else:message['tool_calls'][0]['function'][field]+=' changed'
                archive[2]=copy.deepcopy(message)
                archive[3]['name']=message['tool_calls'][0]['function']['name']
                evidence=canonical_prefix_evidence(records,archive)
                second=b['representation_second_opportunity'];second[EVIDENCE_FIELD]=evidence
                second['prior_request_output_sequence'][0]['known_assistant_message_sha256']=digest(message)
                self.assertIs(representation_prefix_comparison(fixture()[2],b)['canonical_match'],False)

    def test_raw_evidence_digest_must_bind_original(self):
        _, _, a=fixture();_, _, b=fixture('b')
        b['representation_second_opportunity'][EVIDENCE_FIELD]['sequence'][0]['raw_assistant_message_sha256']='f'*64
        self.assertIs(representation_prefix_comparison(a,b)['canonical_match'],False)

    def test_every_other_fixed_prefix_dimension_remains_strict(self):
        for field,value in [('accumulated_exposure',101),('previous_focus_cost',91),
                            ('candidate_cutoff',6),('previous_cutoff',4),
                            ('all_prior_terminal_usage_known',False)]:
            with self.subTest(field=field):
                _,_,a=fixture();_,_,b=fixture('b');b['representation_second_opportunity'][field]=value
                self.assertIs(representation_prefix_comparison(a,b)['canonical_match'],False)

    def test_request_status_and_sequence_order_not_normalized(self):
        for key,value in [('request_sha256','f'*64),('status','error'),('call_id','call_002')]:
            with self.subTest(key=key):
                _,_,a=fixture();_,_,b=fixture('b')
                b['representation_second_opportunity']['prior_request_output_sequence'][0][key]=value
                self.assertIs(representation_prefix_comparison(a,b)['canonical_match'],False)

    def test_invalid_empty_missing_or_unbound_reference_fails(self):
        for value in ('',None,'unbound'):
            with self.subTest(value=value):
                records,archive,_=fixture();archive[3]['tool_call_id']=value
                with self.assertRaises(PrefixIdentityError):canonical_prefix_evidence(records,archive)
        records,archive,_=fixture();records[0]['message']['tool_calls'][0]['id']=''
        with self.assertRaises(PrefixIdentityError):canonical_prefix_evidence(records,archive)

    def test_duplicate_and_unclosed_turn_fails(self):
        records,archive,_=fixture()
        second=copy.deepcopy(records[0]);second['call_id']='call_003';records.append(second)
        archive.extend(copy.deepcopy(archive[2:]))
        with self.assertRaises(PrefixIdentityError):canonical_prefix_evidence(records,archive)
        records,archive,_=fixture()
        with self.assertRaises(PrefixIdentityError):canonical_prefix_evidence(records,archive[:-1])

    def test_observation_content_not_normalized(self):
        records,archive,b=fixture('b');archive[3]['content']=json.dumps({'span_id':'s1','observation':{'result':'different'}})
        b['representation_second_opportunity'][EVIDENCE_FIELD]=canonical_prefix_evidence(records,archive)
        self.assertIs(representation_prefix_comparison(fixture()[2],b)['canonical_match'],False)

    def test_focus_output_is_not_normalized(self):
        records,archive,b=fixture('b');records[1]['message']['content']+=' changed'
        b['representation_second_opportunity'][EVIDENCE_FIELD]=canonical_prefix_evidence(records,archive)
        b['representation_second_opportunity']['prior_request_output_sequence'][1]['known_assistant_message_sha256']=digest(records[1]['message'])
        self.assertIs(representation_prefix_comparison(fixture()[2],b)['canonical_match'],False)

    def test_invalid_evidence_and_boolean_count_fail_closed(self):
        _,_,a=fixture()
        for change in ('missing','invalid','bool'):
            with self.subTest(change=change):
                _,_,b=fixture('b');s=b['representation_second_opportunity']
                if change=='missing':s.pop(EVIDENCE_FIELD)
                elif change=='invalid':s[EVIDENCE_FIELD]={'validation_status':'invalid'}
                else:s[EVIDENCE_FIELD]['record_count']=True
                self.assertIs(representation_prefix_comparison(a,b)['canonical_match'],False)

    def test_no_boundary_not_equal(self):
        r=representation_prefix_comparison({}, {})
        self.assertIsNone(r['strict_match']);self.assertIsNone(r['canonical_match'])

    def test_focus_tool_call_unknown_status_extra_archive_fail(self):
        for change in ('focus_call','unknown','suffix'):
            records,archive,_=fixture()
            if change=='focus_call':records[1]['message']['tool_calls']=copy.deepcopy(records[0]['message']['tool_calls'])
            elif change=='unknown':records[0]['status']='error'
            else:archive.append(dict(role='user',content='unbound'))
            with self.subTest(change=change),self.assertRaises(PrefixIdentityError):canonical_prefix_evidence(records,archive)

    def test_no_tool_actor_and_malformed_argument_string_preserved(self):
        records,archive,_=fixture();records[0]['message']['tool_calls'][0]['function']['arguments']='not JSON'
        archive[2]=copy.deepcopy(records[0]['message'])
        self.assertEqual(canonical_prefix_evidence(records,archive)['protocol_call_count'],1)
        records[0]['message'].pop('tool_calls');archive[2]=copy.deepcopy(records[0]['message'])
        archive[3]=dict(role='user',content=json.dumps({'span_id':'s1','observation':{}}))
        self.assertEqual(canonical_prefix_evidence(records,archive)['protocol_call_count'],0)

    def test_multiple_call_bijection_preserves_order(self):
        records,archive,_=fixture('a')
        second=copy.deepcopy(records[0]['message']['tool_calls'][0]);second['id']='b'
        records[0]['message']['tool_calls'].append(second)
        archive[2]=copy.deepcopy(records[0]['message'])
        returned=copy.deepcopy(archive[3]);returned['tool_call_id']='b';archive.append(returned)
        first=canonical_prefix_evidence(records,archive)
        records[0]['message']['tool_calls'][0]['id']='x'
        records[0]['message']['tool_calls'][1]['id']='y'
        archive[2]=copy.deepcopy(records[0]['message'])
        archive[3]['tool_call_id']='x';archive[4]['tool_call_id']='y'
        renamed=canonical_prefix_evidence(records,archive)
        self.assertEqual(first['canonical_archive_sha256'],renamed['canonical_archive_sha256'])
        self.assertEqual(first['sequence'][0]['canonical_assistant_message_sha256'],
                         renamed['sequence'][0]['canonical_assistant_message_sha256'])
        archive[3],archive[4]=archive[4],archive[3]
        with self.assertRaises(PrefixIdentityError):canonical_prefix_evidence(records,archive)

    def test_malformed_prefix_metadata_fails_closed(self):
        _,_,a=fixture()
        for malformed in (None, [], {'representation_second_opportunity':True}):
            result=representation_prefix_comparison(a,malformed)
            self.assertIs(result['canonical_match'],False)
        _,_,b=fixture('b')
        b['representation_second_opportunity']['prior_request_output_sequence'][0]=False
        self.assertIs(representation_prefix_comparison(a,b)['canonical_match'],False)


if __name__ == '__main__':
    unittest.main()
