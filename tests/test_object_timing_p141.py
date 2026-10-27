"""Handwritten P141 boundary and transport tests; no external model or API."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_object_timing_p141 import MODES, base_mode_for, prompt_policy_for, trigger_decision
from checkpoint_object_timing_preflight_p141 import synthetic_transport_cases
from object_timing_prefix_p141 import timing_prefix_comparison, STATE_FIELDS
from checkpoint_prefix_identity_p140 import VERSION


def entry(n, offer, *, role=None, status='ok'):
    state = {k: 'a'*64 if k.endswith('_sha256') else 0 for k in STATE_FIELDS}
    state.update(opportunities=1, revision=1, cutoff=4, last_closed_turns=5,
                 previous_focus_cost=100, measured_input_tokens=14000, accumulated_exposure=120)
    seq = [dict(call_id=f'call_{i:03d}', role='agent', status='ok', request_sha256='b'*64,
                raw_assistant_message_sha256='c'*64, canonical_assistant_message_sha256='d'*64)
           for i in range(1,n+1)]
    identity = dict(version=VERSION, validation_status='valid', record_count=n,agent_calls=n,
                    focus_calls=0,protocol_call_count=n,raw_archive_sha256='e'*64,
                    canonical_archive_sha256='f'*64,sequence=seq)
    return dict(after_model_calls=n,offer=offer,state=state,identity=identity,
                next_dispatch=dict(call_id=f'call_{n+1:03d}',role=role or ('focus' if offer else 'agent'),status=status))


def pair():
    return (dict(checkpoint_representation_mode=MODES[1],timing_decision_prefixes=[entry(3,False)]),
            dict(checkpoint_representation_mode=MODES[2],timing_decision_prefixes=[entry(3,True)]))


class ObjectTimingPureTests(unittest.TestCase):
    def test_TDO_threshold_mapping_and_shared_object_prompt(self):
        from checkpoint_delta_envelope_p140 import OBJECT_DELTA_SUMMARY_PROMPT as previous
        from checkpoint_object_timing_p141 import OBJECT_DELTA_SUMMARY_PROMPT as current
        self.assertEqual(current, previous)
        self.assertEqual([base_mode_for(m) for m in MODES],
                         ['threshold_recursive','threshold_delta','exposure_delta'])
        self.assertEqual([prompt_policy_for(m) for m in MODES],
                         ['original','explicit_delta_object','explicit_delta_object'])
        args=dict(opportunities=1,fresh_turns=3,eligible_raw=True,measured_input_tokens=14000,
                  accumulated_exposure=120,previous_focus_cost=100)
        self.assertFalse(trigger_decision(mode=MODES[1],**args)['offer'])
        self.assertTrue(trigger_decision(mode=MODES[2],**args)['offer'])

    def test_first_common_max_two_and_five_transport_shapes(self):
        cases=synthetic_transport_cases()
        self.assertEqual(len(cases),5)
        self.assertEqual(sum(c['role']=='focus' for c in cases),3)
        for mode in MODES:
            args=dict(mode=mode,fresh_turns=3,eligible_raw=True,measured_input_tokens=16384,
                      accumulated_exposure=0,previous_focus_cost=None)
            self.assertTrue(trigger_decision(opportunities=0,**args)['offer'])
            self.assertFalse(trigger_decision(opportunities=2,**args)['offer'])

    def test_first_actual_timing_boundary_not_second_focus_alignment(self):
        a,b=pair(); result=timing_prefix_comparison(a,b)
        self.assertTrue(result['canonical_match']);self.assertTrue(result['actual_dispatch_diverged'])
        self.assertEqual(result['after_model_calls'],3)
        a['timing_decision_prefixes'].append(entry(8,True)) # Later cutoff need not coincide.
        self.assertEqual(timing_prefix_comparison(a,b),result)

    def test_ID_only_strict_difference_is_separate(self):
        a,b=pair();b['timing_decision_prefixes'][0]['identity']['raw_archive_sha256']='1'*64
        b['timing_decision_prefixes'][0]['identity']['sequence'][0]['raw_assistant_message_sha256']='2'*64
        out=timing_prefix_comparison(a,b)
        self.assertFalse(out['strict_match']);self.assertTrue(out['canonical_match'])

    def test_changed_request_content_or_state_not_normalized(self):
        for kind in ('request','content','state'):
            a,b=pair();e=b['timing_decision_prefixes'][0]
            if kind=='state':e['state']['accumulated_exposure']+=1
            else:e['identity']['sequence'][0]['request_sha256' if kind=='request' else 'canonical_assistant_message_sha256']='9'*64
            self.assertFalse(timing_prefix_comparison(a,b)['canonical_match'])

    def test_unsent_and_unknown_dispatch_not_known_intervention(self):
        a,b=pair();b['timing_decision_prefixes'][0]['next_dispatch']['role']='agent'
        self.assertFalse(timing_prefix_comparison(a,b)['actual_dispatch_diverged'])
        a,b=pair();b['timing_decision_prefixes'][0]['next_dispatch']['status']='error'
        result=timing_prefix_comparison(a,b)
        self.assertTrue(result['actual_dispatch_diverged']);self.assertFalse(result['both_dispatches_known'])

    def test_malformed_or_missing_prefix_fails_closed(self):
        for change in ('bool','badid','unknown','missing'):
            a,b=pair();e=b['timing_decision_prefixes'][0]
            if change=='bool':e['state']['previous_focus_cost']=True
            elif change=='badid':e['identity']['sequence'][0]['call_id']='wrong'
            elif change=='unknown':e['identity']['sequence'][0]['status']='error'
            else:del e['state']['cutoff']
            self.assertFalse(timing_prefix_comparison(a,b)['canonical_match'])
        a,b=pair();a['timing_decision_prefixes']=[]
        self.assertIsNone(timing_prefix_comparison(a,b)['canonical_match'])

if __name__=='__main__':unittest.main()
