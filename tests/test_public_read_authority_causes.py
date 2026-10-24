"""Historical evidence must not be mistaken for live authority."""
import unittest

from test_public_read_opportunity import records, source, target, SONG, LIBRARY
from public_read_opportunity import analyze as availability
from public_read_authority_causes import analyze


class PublicReadAuthorityCauseTests(unittest.TestCase):
    def inspect(self, calls):
        data = records(calls)
        old = availability(*data, execution_scope='fixture')
        return analyze(*data, old['targets'])

    def test_future_source_is_not_historical_evidence(self):
        result = self.inspect([target(), source()])
        t = result['targets'][0]
        self.assertEqual(t['missing_authority_reason'], 'target_not_previously_observed_in_current_sources')
        self.assertEqual(t['prior_source_records'], 0)
        self.assertIsNone(t['latest_eligible_ordinal'])

    def test_known_read_named_invalidation_is_identified_but_not_exempted(self):
        result = self.inspect([source(), ('api_docs__show_app_descriptions',{},[], 'returned'), target()])
        t = result['targets'][0]
        self.assertEqual(t['missing_authority_reason'], 'previous_eligible_observation_invalidated')
        self.assertEqual(t['invalidating_operations_since'], [dict(event_ordinal=2,
            api='api_docs__show_app_descriptions',receipt_status='returned')])
        self.assertTrue(t['latest_prior_fields_equal_later_response'])
        self.assertFalse(t['historical_values_are_authority'])
        self.assertFalse(t['effect_exemption_established'])

    def test_actual_changed_value_does_not_erase_original_invalidation(self):
        changed = dict(SONG, title='new value')
        t = self.inspect([source(), ('spotify__like_song',{}, {}, 'returned'), target(changed)])['targets'][0]
        self.assertEqual(t['missing_authority_reason'], 'previous_eligible_observation_invalidated')
        self.assertFalse(t['latest_prior_fields_equal_later_response'])

    def test_other_identity_is_not_counted_as_prior_observation(self):
        result = self.inspect([source([dict(LIBRARY[0],song_id=9)]), target()])
        self.assertEqual(result['targets'][0]['prior_source_records'],0)

    def test_incomplete_history_is_not_misreported_as_erased_authority(self):
        t = self.inspect([source([{'song_id':1,'title':'synthetic'}]), target()])['targets'][0]
        self.assertEqual(t['missing_authority_reason'],'previous_records_not_individually_eligible')
        self.assertEqual(t['prior_individually_eligible_records'],0)

    def test_complete_baseline_and_surviving_partial_are_preserved(self):
        result = self.inspect([source(),target(),target()])
        self.assertEqual([t['missing_authority_reason'] for t in result['targets']],
                         ['original_partial','original_complete'])
        self.assertEqual(result['targets'][1]['prior_complete_records'],1)
        self.assertEqual(result['new_authorities_granted'],0)

    def test_known_exception_remains_known_without_value_confirmation(self):
        t = self.inspect([source(), ('other__read',{},None,'raised'), target(None,'raised')])['targets'][0]
        self.assertIsNone(t['latest_prior_fields_equal_later_response'])
        self.assertEqual(t['invalidating_operations_since'][0]['receipt_status'],'raised')

    def test_unknown_state_remains_unknown_after_new_source(self):
        t = self.inspect([source(),('other__write',{},None,'unknown'),source(),target()])['targets'][0]
        self.assertEqual(t['missing_authority_reason'],'original_unknown_state')
        self.assertEqual(t['latest_eligible_ordinal'],3)
        self.assertFalse(t['historical_values_are_authority'])

    def test_changed_or_missing_frozen_target_is_rejected(self):
        data = records([source(),target()])
        old = availability(*data,execution_scope='fixture')['targets']
        with self.assertRaises(ValueError): analyze(*data,[])
        old[0]['request_sha256']='changed'
        with self.assertRaises(ValueError): analyze(*data,old)


if __name__ == '__main__':unittest.main()
