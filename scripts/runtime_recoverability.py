"""Bounded value-equality witnesses for structured historical stdout.

Only matching builtin values are witnessed. This is not semantic relevance,
source provenance, current external truth, or permission to remove an output.
Probe routes/digests are private; publish aggregate counts only.
"""
import ast
import json

CORE = r'''
import hashlib
import json
import math

MAX_NODES=20000
MAX_DEPTH=24
MAX_ROOTS=128
MAX_MATCHES=8
MAX_SCALAR_BYTES=65536

class Unwitnessed(ValueError):
    pass

def fingerprint(value, budget, path=(), matches=None, targets=None, active=None, depth=0):
    if active is None: active=set()
    budget[0]-=1
    if budget[0]<0 or depth>MAX_DEPTH:
        raise Unwitnessed('inspection_bound')
    kind=type(value)
    if value is None: encoded=b'n'
    elif kind is bool: encoded=b'b1' if value else b'b0'
    elif kind is int: encoded=b'i'+str(value).encode()
    elif kind is float:
        if not math.isfinite(value): raise Unwitnessed('nonfinite')
        encoded=b'f'+value.hex().encode()
    elif kind is str:
        if len(value)>MAX_SCALAR_BYTES: raise Unwitnessed('scalar_bound')
        encoded=b's'+value.encode('utf-8')
        if len(encoded)>MAX_SCALAR_BYTES+1: raise Unwitnessed('scalar_bound')
    elif kind in (dict,list,tuple):
        identity=id(value)
        if identity in active: raise Unwitnessed('cycle')
        active.add(identity)
        try:
            pieces=[]
            if kind is dict:
                for key,child in value.items():
                    if type(key) is not str: raise Unwitnessed('nonstring_key')
                    kd=fingerprint(key,budget,active=active,depth=depth+1)
                    vd=fingerprint(child,budget,path+(('key',key),),matches,targets,active,depth+1)
                    pieces.append(kd+vd)
                pieces.sort()
                tag=b'd'
            else:
                tag=b'l' if kind is list else b't'
                for i,child in enumerate(value):
                    pieces.append(fingerprint(child,budget,path+(('index',i),),matches,targets,active,depth+1))
            encoded=tag+b''.join(pieces)
        finally: active.remove(identity)
    else: raise Unwitnessed('unsupported_type')
    digest=hashlib.sha256(encoded).digest()
    if matches is not None and targets is not None:
        for label in targets.get(digest.hex(),[]):
            if len(matches[label])<MAX_MATCHES:
                matches[label].append(list(path))
    return digest

def scan(scope, targets):
    by_digest={}
    for label,digest in targets.items():
        by_digest.setdefault(digest,[]).append(label)
    matches={label:[] for label in targets}
    roots=sorted(n for n in scope if type(n) is str and n.isidentifier()
                 and not n.startswith('_') and n not in ('call_api','observations'))
    budget=[MAX_NODES];unsupported={};inspected=0
    for name in roots[:MAX_ROOTS]:
        inspected+=1
        try:
            fingerprint(scope[name],budget,(('root',name),),matches,by_digest)
        except Unwitnessed as exc:
            reason=str(exc);unsupported[reason]=unsupported.get(reason,0)+1
        if budget[0]<0:break
    return {'matches':matches,'eligible_roots':len(roots),'inspected_roots':inspected,
            'nodes_inspected':min(MAX_NODES,MAX_NODES-budget[0]),
            'root_limit_reached':len(roots)>MAX_ROOTS,
            'node_limit_reached':budget[0]<0,'unwitnessed_roots':unsupported}
'''
exec(CORE)


def parse_structured_stdout(text):
    """A whole JSON/Python literal only; never regex-extract a convenient piece."""
    if type(text) is not str or not text.strip() or len(text)>65536:
        raise ValueError('empty_or_oversized')
    def object_pairs(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate_key')
            result[key]=value
        return result
    try:
        value=json.loads(text,object_pairs_hook=object_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        syntax='json'
    except json.JSONDecodeError:
        tree=ast.parse(text.strip(),mode='eval')
        if sum(1 for _ in ast.walk(tree))>20000:raise ValueError('ast_bound')
        for node in ast.walk(tree):
            if isinstance(node,ast.Dict):
                keys=[ast.literal_eval(k) for k in node.keys]
                if any(type(k) is not str for k in keys) or len(set(keys))!=len(keys):
                    raise ValueError('duplicate_or_nonstring_key')
        value=ast.literal_eval(tree);syntax='python_literal'
    digest=fingerprint(value,[MAX_NODES]).hex()
    return {'syntax':syntax,'digest':digest}


def probe_source(targets):
    """Run in a separate exec namespace, keeping agent bindings unchanged."""
    if type(targets) is not dict or len(targets)>64:
        raise ValueError('target_count')
    for key,digest in targets.items():
        if (type(key) is not str or not key.isidentifier() or len(key)>100
                or type(digest) is not str or len(digest)!=64
                or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('invalid_target')
    code=CORE+'\nprint(json.dumps(scan(snapshot_scope, targets),sort_keys=True))\n'
    return ('(lambda b,ns:b.exec('+repr(code)+
            ", {'__builtins__':b,'snapshot_scope':ns,'targets':"+repr(targets)+'}))'+
            "((lambda:0).__builtins__['__import__']('builtins'),(lambda:0).__globals__)" )


def resolve_witness(scope,path,expected_digest):
    """Recheck a private route at use time; a previous match is not a lease."""
    if type(path) is not list or not path or path[0][0]!='root':
        raise ValueError('invalid_path')
    value=scope[path[0][1]]
    for kind,key in path[1:]:
        if kind=='key' and type(value) is dict and type(key) is str:value=value[key]
        elif kind=='index' and type(value) in (list,tuple) and type(key) is int and 0<=key<len(value):value=value[key]
        else:raise ValueError('path_no_longer_valid')
    if fingerprint(value,[MAX_NODES]).hex()!=expected_digest:
        raise ValueError('value_no_longer_matches')
    return value
