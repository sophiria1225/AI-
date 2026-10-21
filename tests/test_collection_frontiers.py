"""Adversarial cases for a descriptive monitor; not evidence of agent quality."""
import json
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_collection_frontiers import audit_spans


def schema(method='GET'):
    return dict(method=method, parameters=[
        dict(name='access_token', required=True, default=None),
        dict(name='query', required=False, default=None),
        dict(name='page_index', required=False, default=0),
        dict(name='page_limit', required=False, default=2)])


def span(args=None, data=None, name='app__list'):
    return dict(action=dict(name=name, arguments=json.dumps({'access_token':'SECRET', **(args or {})})),
                observation=dict(observation=json.dumps([1, 2] if data is None else data)))


class CollectionFrontierTests(unittest.TestCase):
    def audit(self, *events):
        return audit_spans({f's{i}': e for i, e in enumerate(events)},
                           {'app__list':schema(), 'app__write':schema('POST')})

    def test_explicit_defaults_and_empty_terminal(self):
        r=self.audit(span(),span({'page_index':1,'page_limit':2,'query':None},[]))
        self.assertEqual(len(r['groups']),1)
        self.assertEqual(r['groups'][0]['status'],'contiguous_terminal_observed')

    def test_filters_auth_and_page_size_are_distinct(self):
        r=self.audit(span(),span({'query':'different'}),span({'access_token':'OTHER'}),span({'page_limit':3}))
        self.assertEqual(len(r['groups']),4)
        public=json.dumps(r)
        for secret in ('SECRET','OTHER','different','access_token'):
            self.assertNotIn(secret,public)

    def test_full_page_is_not_a_proof_of_missing_items(self):
        r=self.audit(span())
        self.assertEqual(r['groups'][0]['status'],'no_terminal_observed')
        self.assertTrue(r['any_no_terminal_without_later_app_write'])

    def test_gap_and_large_page_not_exhaustive(self):
        for page in (2,10**12):
            r=self.audit(span(),span({'page_index':page},[]))
            self.assertEqual(r['groups'][0]['status'],'gap_before_terminal')

    def test_short_page_followed_by_data_is_inconsistent(self):
        r=self.audit(span(data=[1]),span({'page_index':1},[2]))
        self.assertEqual(r['groups'][0]['status'],'inconsistent_after_terminal')

    def test_changed_replay_cannot_certify_static_collection(self):
        r=self.audit(span(),span(data=[1]),span({'page_index':1},[]))
        self.assertEqual(r['groups'][0]['status'],'inconsistent_page_replay')

    def test_mutation_splits_epoch_even_when_result_is_error(self):
        r=self.audit(span(),span(name='app__write',data={'error':'unconfirmed'}),span({'page_index':1},[]))
        self.assertEqual(len(r['groups']),2)
        self.assertTrue(r['groups'][0]['later_same_app_write'])
        self.assertFalse(r['any_no_terminal_without_later_app_write'])
        self.assertEqual(r['groups'][1]['status'],'gap_before_terminal')

    def test_unknown_call_is_conservative_only_within_app(self):
        r=self.audit(span(),span(name='other__unknown'),span({'page_index':1},[]))
        self.assertEqual(len(r['groups']),1)
        r=self.audit(span(),span(name='app__unknown'),span({'page_index':1},[]))
        self.assertEqual(len(r['groups']),2)

    def test_errors_and_invalid_arguments_retained(self):
        events=[span(data={'error':'PRIVATE_CONTENT'}),span({'page_limit':0}),span({'page_index':True})]
        bad=span();bad['action']['arguments']='["SECRET"]';events.append(bad)
        bad=span();bad['action']['arguments']='{}';events.append(bad)
        events.append(span({'unsupported':'PRIVATE'}))
        r=self.audit(*events)
        self.assertEqual(len(r['unclassified_calls']),6)
        self.assertEqual(r['groups'][0]['status'],'inconclusive_response')
        self.assertNotIn('PRIVATE',json.dumps(r))

    def test_non_dispatched_and_over_limit(self):
        ignored=span();ignored['observation']={'error':'not sent'}
        r=self.audit(ignored,span(data=[1,2,3]))
        self.assertEqual(r['paginated_calls'],1)
        self.assertEqual(r['groups'][0]['status'],'over_limit_response')


if __name__=='__main__':
    unittest.main()
