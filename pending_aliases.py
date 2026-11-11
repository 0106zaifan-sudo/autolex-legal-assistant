"""批次内确定性稀疏别名；只检测抄写错误，不纠错或替换来源。"""
import re
from typing import Annotated
from pydantic import Field,field_validator,ValidationInfo
from pydantic_core import PydanticCustomError
from ai_analysis import StrictModel
from multidoc_ai import digest

ALIAS_VERSION='pending-alias-map/1'
ALPHABET='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
assert len(ALPHABET)==32
ALIAS_PATTERN=re.compile(r'^P_['+ALPHABET+r']{4}$')
AliasText=Annotated[str,Field(pattern=ALIAS_PATTERN.pattern)]
MAX_ALIASES=96
CAPACITY=32**3

class AliasError(ValueError):pass

class AliasSelection(StrictModel):
 anchor_alias:AliasText
 evidence_aliases:list[AliasText]=Field(min_length=1,max_length=4)
 reasoning:str=Field(min_length=1,max_length=600)
 @field_validator('anchor_alias','evidence_aliases')
 @classmethod
 def current_enum(cls,value,info:ValidationInfo):
  allowed=(info.context or {}).get('allowed_aliases')
  values=value if isinstance(value,list) else [value]
  if allowed is not None and any(x not in allowed for x in values):
   raise PydanticCustomError('alias_not_in_catalog','别名不属于本批可信映射')
  return value

def build_alias_map(catalog,context_sha256):
 entries=catalog['entries']
 if len(entries)>min(MAX_ALIASES,CAPACITY):raise AliasError('alias_capacity_exceeded')
 if catalog['sha256']!=digest({k:v for k,v in catalog.items() if k!='sha256'}):raise AliasError('alias_source_catalog_invalid')
 seed=bytes.fromhex(digest([ALIAS_VERSION,context_sha256,catalog['sha256']]))
 start=int.from_bytes(seed[:2],'big')%CAPACITY
 step=(int.from_bytes(seed[2:4],'big')%CAPACITY)|1
 if step in (1,CAPACITY-1):step=3
 salt=seed[4]&31
 rows=[]
 for i,entry in enumerate(entries):
  n=(start+i*step)%CAPACITY
  a,b,c=(n>>10)&31,(n>>5)&31,n&31
  code=''.join(ALPHABET[x] for x in (a,b,c,a^b^c^salt))
  rows.append({'alias':'P_'+code,'candidate_id':entry['candidate_id']})
 if len({r['alias'] for r in rows})!=len(rows):raise AliasError('alias_collision')
 value={'version':ALIAS_VERSION,'context_sha256':context_sha256,'source_catalog_sha256':catalog['sha256'],
        'alphabet':ALPHABET,'min_symbol_distance':2,'entries':rows}
 return {**value,'sha256':digest(value)}

def safe_alias(value):
 return value if isinstance(value,str) and ALIAS_PATTERN.fullmatch(value) else 'rejected_alias'
