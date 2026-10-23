"""Opt-in typed public API result protocol, not connected to historical workers.

The trusted source catches invocation exceptions at their origin. It never
classifies arbitrary returned text as an exception, retries an API, or promises
rollback. An invalid envelope leaves the outcome unknown and must stop dispatch.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import re

from context_preservation import validate_api_request

PROTOCOL='public-api-result-v1'
MAX_REPLY_BYTES=8*1024*1024


class InvalidExecutionEnvelope(ValueError):
    """The caller must not retry or dispatch another API after this error."""


class PublicApiInvocationError(RuntimeError):
    """A reported invocation exception, without a no-side-effects guarantee."""
    def __init__(self,error_type,message):
        self.error_type=error_type
        self.message=message
        super().__init__(f'{error_type}: {message}')


@dataclass(frozen=True)
class PublicApiResult:
    status: str
    value: object=None
    error_type: str | None=None
    error_message: str | None=None
    raw_reply_sha256: str=''

    def require_value(self):
        if self.status=='returned':return self.value
        raise PublicApiInvocationError(self.error_type,self.error_message)


def validate_nonce(nonce):
    if type(nonce)is not str or not re.fullmatch('[a-f0-9]{32}',nonce):
        raise ValueError('nonce_must_be_128_bit_lowercase_hex')


def validate_json_value(value):
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1
        if depth>64 or count>100000:raise ValueError('json_structure_limit')
        if type(item)is dict:
            if any(type(k)is not str for k in item):raise ValueError('json_object_keys_must_be_strings')
            pending.extend((v,depth+1) for v in item.values())
        elif type(item)is list:pending.extend((v,depth+1) for v in item)
        elif type(item)is float:
            if not math.isfinite(item):raise ValueError('nonfinite_json_number')
        elif item is not None and type(item)not in (str,int,bool):
            raise ValueError('not_a_json_value')


def trusted_invocation_code(call,docs,nonce):
    """Build only a documented public invocation with literal JSON arguments."""
    validate_nonce(nonce)
    app,api,args=validate_api_request(call,docs)
    # repr below is source quoting, not an evaluator for untrusted strings.
    validate_json_value(args)
    if len(json.dumps(args,allow_nan=False).encode())>MAX_REPLY_BYTES:
        raise ValueError('argument_size_limit')
    name='_public_api_result_'+nonce
    return f'''def {name}():
    import json as _json
    try:
        _value = apis.{app}.{api}(**{args!r})
    except Exception as _error:
        _packet = {{'protocol': {PROTOCOL!r}, 'nonce': {nonce!r}, 'status': 'raised',
                   'error': {{'type': type(_error).__name__, 'message': str(_error)}}}}
    else:
        _packet = {{'protocol': {PROTOCOL!r}, 'nonce': {nonce!r}, 'status': 'returned', 'value': _value}}
    print(_json.dumps(_packet, ensure_ascii=False, allow_nan=False))
try:
    {name}()
finally:
    del {name}
'''


def unique_object(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise InvalidExecutionEnvelope('duplicate_json_key')
        result[k]=v
    return result


def reject_constant(_):
    raise InvalidExecutionEnvelope('nonfinite_json_number')


def decode_reply(raw,nonce):
    validate_nonce(nonce)
    if type(raw)is not str:raise InvalidExecutionEnvelope('reply_size_or_type')
    try:encoded=raw.encode('utf-8')
    except UnicodeError:raise InvalidExecutionEnvelope('invalid_reply_encoding') from None
    if not 0<len(encoded)<=MAX_REPLY_BYTES:
        raise InvalidExecutionEnvelope('reply_size_or_type')
    try:
        packet=json.loads(raw,object_pairs_hook=unique_object,parse_constant=reject_constant)
        validate_json_value(packet)
    except (ValueError,TypeError,RecursionError) as exc:
        if isinstance(exc,InvalidExecutionEnvelope):raise
        raise InvalidExecutionEnvelope('not_one_complete_json_result') from None
    if (type(packet)is not dict or packet.get('protocol')!=PROTOCOL or packet.get('nonce')!=nonce):
        raise InvalidExecutionEnvelope('wrong_protocol_or_invocation')
    digest=hashlib.sha256(encoded).hexdigest()
    if packet.get('status')=='returned':
        if set(packet)!={'protocol','nonce','status','value'}:
            raise InvalidExecutionEnvelope('returned_shape')
        return PublicApiResult('returned',value=packet['value'],raw_reply_sha256=digest)
    if packet.get('status')=='raised':
        error=packet.get('error')
        if (set(packet)!={'protocol','nonce','status','error'} or type(error)is not dict
                or set(error)!={'type','message'} or type(error['type'])is not str
                or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',error['type'])
                or type(error['message'])is not str):
            raise InvalidExecutionEnvelope('raised_shape')
        return PublicApiResult('raised',error_type=error['type'],error_message=error['message'],
                               raw_reply_sha256=digest)
    raise InvalidExecutionEnvelope('unknown_execution_status')
