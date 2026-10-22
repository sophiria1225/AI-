"""Posthoc structural reuse probe; not an executable cache correctness contract.

An identifier-shaped field can be a foreign key. Equal historical values do not
establish current truth. The index is built before looking at the current reply,
and conflicting past values are never resolved with the current reply as oracle.
"""
from collections import defaultdict
import copy
import json


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def identifier(name,value):
    return (type(name) is str and (name.endswith('_id') or name=='file_path')
            and type(value) in (str,int))


def auth_scope(arguments):
    # Conservative opaque partition, not a claimed identity provider.
    return canonical({k:v for k,v in arguments.items() if any(
        token in k.lower() for token in ('token','password','credential','api_key','authorization'))})


class RecordIndex:
    def __init__(self,max_nodes=50000,max_depth=20):
        self.records=defaultdict(list)
        self.exact={}
        self.max_nodes=max_nodes;self.max_depth=max_depth
        self.invalidations=0;self.bounded_scans=0

    def invalidate(self):
        self.records.clear();self.exact.clear();self.invalidations+=1

    @staticmethod
    def request_key(name,arguments):
        return name,canonical(arguments)

    def assess(self,name,arguments,value):
        app=name.split('__',1)[0];scope=auth_scope(arguments)
        exact=self.exact.get(self.request_key(name,arguments))
        row={'exact_previous_request':exact is not None,
             'exact_reply_content_equal':exact==canonical(value) if exact is not None else None,
             'eligible_identity_shape':False,'candidate_records':0,'candidate_fields':0,
             'other_auth_candidate_records':0,
             'conflicting_prior_fields':0,'matching_current_fields':0,'different_current_fields':0,
             'missing_current_fields':0,'matching_fields_from_different_api':0,
             'matching_nonidentity_fields_from_different_api':0,
             'full_current_object_covered':False,'all_current_fields_from_different_api':False}
        if type(value) is not dict:return row
        identities=[(key,val) for key,val in arguments.items() if identifier(key,val)
                    and key in value and canonical(value[key])==canonical(val)]
        if len(identities)!=1:return row
        key,val=identities[0];row['eligible_identity_shape']=True
        candidates=self.records.get((app,scope,key,canonical(val)),[])
        row['candidate_records']=len(candidates)
        row['other_auth_candidate_records']=sum(len(records) for (a,s,k,v),records in self.records.items()
            if a==app and s!=scope and k==key and v==canonical(val))
        # The set is based only on historical records, including conflicting ones.
        fields=defaultdict(lambda:defaultdict(set))
        for source,record in candidates:
            for field,item in record.items():fields[field][canonical(item)].add(source)
        row['candidate_fields']=len(fields)
        row['conflicting_prior_fields']=sum(len(v)>1 for v in fields.values())
        for field,item in value.items():
            versions=fields.get(field,{})
            if len(versions)!=1:
                row['missing_current_fields']+=1
                continue
            observed,sources=next(iter(versions.items()))
            if observed!=canonical(item):
                row['different_current_fields']+=1
            else:
                row['matching_current_fields']+=1
                if any(source!=name for source in sources):
                    row['matching_fields_from_different_api']+=1
                    row['matching_nonidentity_fields_from_different_api']+=int(field!=key)
        row['full_current_object_covered']=bool(value) and row['matching_current_fields']==len(value)
        row['all_current_fields_from_different_api']=bool(value) and row['matching_fields_from_different_api']==len(value)
        return row

    def add(self,name,arguments,value):
        app=name.split('__',1)[0];scope=auth_scope(arguments);count=0;bounded=False
        self.exact[self.request_key(name,arguments)]=canonical(value)

        def visit(obj,depth):
            nonlocal count,bounded
            count+=1
            if count>self.max_nodes or depth>self.max_depth:
                bounded=True;return
            if type(obj) is dict:
                # No claim that any one *_id is the primary key.
                saved=copy.deepcopy(obj)
                for key,val in obj.items():
                    if identifier(key,val):
                        self.records[(app,scope,key,canonical(val))].append((name,saved))
                for child in obj.values():visit(child,depth+1)
            elif type(obj) is list:
                for child in obj:visit(child,depth+1)
        visit(value,0)
        self.bounded_scans+=int(bounded)
