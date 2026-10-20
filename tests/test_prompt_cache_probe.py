import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from local_llama import payload_for
from probe_prompt_cache import payload_config, public_body


class PromptCacheControls(unittest.TestCase):
    def test_only_output_limit_and_cache_switch_change_saved_request(self):
        model = dict(model='test', num_ctx=65536, num_predict=4096, seed=42, temperature=1.0)
        source = payload_for(model, [{'role': 'user', 'content': 'PRIVATE_INPUT'}], ['TOOL'])
        for stage in ('warm', 'target'):
            config = payload_config({'model': model}, source, stage)
            actual = payload_for(config, source['messages'], source['tools'])
            self.assertEqual(actual, dict(source, max_tokens=1, cache_prompt=stage == 'target'))
        source['top_p'] = 0.3
        with self.assertRaises(ValueError):
            payload_config({'model': model}, source, 'target')

    def test_public_progress_cannot_promote_inference_to_task_success(self):
        state = dict(status='complete', known_total_tokens=40, unknown_usage_calls=0,
                     model_text='PRIVATE_OUTPUT', evaluator='PRIVATE_RESULT', rows=[dict(
                         pair=1, variant='original', stage='target', input_tokens=39,
                         cached_input_tokens=10, processed_input_tokens=29, prompt_seconds=1,
                         model_text='PRIVATE_REASONING')])
        body = public_body(state)
        self.assertNotIn('PRIVATE_', body)
        self.assertIn('環境操作・最終評価は0回', body)
        state['rows'][0]['variant'] = 'PRIVATE_VARIANT'
        with self.assertRaises(ValueError):
            public_body(state)


if __name__ == '__main__':
    unittest.main()
