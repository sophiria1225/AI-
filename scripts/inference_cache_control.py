"""Small, explicit slot-state controls for bounded local inference experiments."""
import copy


SCHEDULE=('cold_1','warm_1','warm_2','cold_2','warm_3','cold_3')


def require_idle(slots):
    if (type(slots) is not list or len(slots)!=1 or slots[0].get('id')!=0
            or slots[0].get('is_processing') is not False):
        raise ValueError('require one explicitly idle slot 0')


def validate_erasure(result):
    if (type(result) is not dict or result.get('id_slot')!=0
            or type(result.get('n_erased')) is not int or result['n_erased']<0):
        raise ValueError('slot-erasure response is not confirmed')
    return result['n_erased']


def request_for(original, plan):
    if (plan['schedule']!=list(SCHEDULE) or plan['max_calls']!=6
            or plan['max_output_tokens']!=256 or original.get('seed')!=plan['seed']
            or original.get('cache_prompt') is not True or original.get('stream') is not False):
        raise ValueError('outside fixed calibration schedule')
    request=copy.deepcopy(original)
    request['max_tokens']=plan['max_output_tokens']
    return request


def cache_measurement(label, response, expected_input):
    if response.get('status')!='ok': raise ValueError('terminal usage is unknown')
    timing=response.get('timings')
    if (not isinstance(timing,dict) or response['input_tokens']!=expected_input
            or type(timing.get('cache_n')) is not int or type(timing.get('prompt_n')) is not int
            or timing['cache_n']<0 or timing['prompt_n']<0
            or timing['cache_n']+timing['prompt_n']!=expected_input
            or timing['cache_n']!=response.get('cached_input_tokens')
            or timing.get('predicted_n')!=response['output_tokens']):
        raise ValueError('inconsistent measured input/cache counts')
    if label not in SCHEDULE: raise ValueError('unknown calibration label')
    valid=timing['cache_n']==0 if label.startswith('cold_') else timing['cache_n']>=expected_input-1
    return {'state_confirmed':valid,'cached_tokens':timing['cache_n'],
            'processed_tokens':timing['prompt_n'],'input_tokens':expected_input,
            'output_tokens':response['output_tokens'],
            'prompt_seconds':timing['prompt_ms']/1000,'decode_seconds':timing['predicted_ms']/1000}
