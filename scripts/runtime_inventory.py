"""Ordinary binding/capability inventory for a possible stronger comparator.

This is not a new control policy. The expression adds no user bindings and never
formats values or invokes methods on user objects. Run only in the existing
isolated interpreter; this is not a security boundary for hostile Python code.
"""
import json

MAX_BINDINGS=128
TYPE_LABELS={'dict','list','tuple','set','frozenset','str','int','float','bool','none','module','function','other'}
RESERVED={'call_api','api_schemas','observations'}

# Function.__globals__ avoids relying on a user binding named globals. Builtins
# are obtained from the function's execution context. No assignment is injected.
INVENTORY_CODE = r'''
(lambda b,j,t,ns:
    (lambda pairs,labels:
        b.print(j.dumps({
            'eligible_binding_count': b.len(pairs),
            'truncated': b.len(pairs)>128,
            'bindings': [
                {'name':name, 'type':labels.get(b.type(value),'other'),
                 'length':b.len(value) if b.type(value) in (b.dict,b.list,b.tuple,b.set,b.frozenset) else None}
                for name,value in pairs[:128]]},sort_keys=True))
    )(
        b.sorted([(name,value) for name,value in ns.items()
            if b.type(name) is b.str and not name.startswith('_')
            and name not in ('call_api','api_schemas','observations')],key=lambda pair:pair[0]),
        {b.dict:'dict',b.list:'list',b.tuple:'tuple',b.set:'set',b.frozenset:'frozenset',
         b.str:'str',b.int:'int',b.float:'float',b.bool:'bool',b.type(None):'none',
         t.ModuleType:'module',t.FunctionType:'function'}
    )
)((lambda:0).__builtins__['__import__']('builtins'),
  (lambda:0).__builtins__['__import__']('json'),
  (lambda:0).__builtins__['__import__']('types'),
  (lambda:0).__globals__)
'''


def validate_inventory(data):
    if type(data) is not dict or set(data)!={'eligible_binding_count','truncated','bindings'}:
        raise ValueError('inventory fields differ')
    count=data['eligible_binding_count'];rows=data['bindings']
    if type(count) is not int or count<0 or type(rows) is not list or len(rows)!=min(count,MAX_BINDINGS):
        raise ValueError('inventory coverage differs')
    if type(data['truncated']) is not bool or data['truncated']!=(count>MAX_BINDINGS):
        raise ValueError('inventory truncation not disclosed')
    names=[]
    for row in rows:
        if type(row) is not dict or set(row)!={'name','type','length'}:
            raise ValueError('binding fields differ')
        name=row['name'];label=row['type'];length=row['length']
        if type(name) is not str or name.startswith('_') or name in RESERVED or label not in TYPE_LABELS:
            raise ValueError('binding identity differs')
        if label in ('dict','list','tuple','set','frozenset'):
            if type(length) is not int or length<0:raise ValueError('container length invalid')
        elif length is not None:raise ValueError('do not expose scalar values or lengths')
        names.append(name)
    if names!=sorted(set(names)):raise ValueError('binding names must be sorted and unique')
    return data


def format_inventory(data,visible_api_names):
    validate_inventory(data)
    names=sorted(set(visible_api_names))
    if any(type(name) is not str or len(name)>200 for name in names):raise ValueError('API identifier invalid')
    return ('Runtime inventory at this boundary. Values are not included; entries describe availability, not relevance or truth. '
            'Underscore-prefixed bindings and supplied runtime helpers are omitted. '
            'Only the first 128 eligible bindings are listed if truncated. '
            'Loaded API schemas can be inspected through api_schemas; other API descriptions must be acquired normally.\n'+
            json.dumps({'runtime':data,'loaded_api_schemas':names},sort_keys=True,ensure_ascii=False))
