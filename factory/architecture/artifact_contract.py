"""Deterministic checks for explicit, machine-readable cross-artifact references.

This is not a PHP/SQL parser. The producer must supply a complete reference manifest;
omitted references are not discovered. A pass attests only to the declared references.
"""
import re
from factory.engine import require
from .governance import canonical, digest, enforce_text

NAME=re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,95}\Z")
TYPES={"string","integer","number","boolean","object","array","datetime","bytes"}

def name(value):
    return isinstance(value,str) and bool(NAME.fullmatch(value))

def check(contract, references):
    require(isinstance(contract,dict) and set(contract)=={"version","entities","enums"} and type(contract["version"]) is int and contract["version"]==1,"Invalid artifact contract")
    require(isinstance(references,dict) and set(references)=={"version","fields","enum_values"} and type(references["version"]) is int and references["version"]==1,"Invalid reference manifest")
    enforce_text(canonical(contract)); enforce_text(canonical(references))
    entities=contract["entities"]; enums=contract["enums"]
    require(isinstance(entities,dict) and 1<=len(entities)<=128 and isinstance(enums,dict) and len(enums)<=128,"Invalid entity/enum budget")
    for entity,fields in entities.items():
        require(name(entity) and isinstance(fields,dict) and 1<=len(fields)<=128,"Invalid entity")
        for field,spec in fields.items():
            require(name(field) and isinstance(spec,dict) and set(spec)=={"type","nullable"} and isinstance(spec["type"],str) and spec["type"] in TYPES and type(spec["nullable"]) is bool,"Invalid field declaration")
    for enum,values in enums.items():
        require(name(enum) and isinstance(values,list) and 1<=len(values)<=128 and all(isinstance(x,str) and 0<len(x)<=128 for x in values) and len(set(values))==len(values),"Invalid enum declaration")
    fields=references["fields"]; values=references["enum_values"]
    require(isinstance(fields,list) and isinstance(values,list) and 1<=len(fields)+len(values)<=1000,"Invalid reference budget")
    issues=[]; seen=set()
    def issue(code,ref):
        issues.append({"code":code,"id":ref["id"]})
    def identity(ref):
        require(name(ref["id"]) and ref["id"] not in seen,"Invalid or duplicate reference ID")
        seen.add(ref["id"])
    for ref in fields:
        require(isinstance(ref,dict) and set(ref)=={"id","entity","field","type","writes_null"},"Invalid field reference")
        identity(ref)
        require(name(ref["entity"]) and name(ref["field"]) and isinstance(ref["type"],str) and ref["type"] in TYPES and type(ref["writes_null"]) is bool,"Invalid field reference values")
        if ref["entity"] not in entities: issue("UNKNOWN_ENTITY",ref); continue
        if ref["field"] not in entities[ref["entity"]]: issue("UNKNOWN_FIELD",ref); continue
        field=entities[ref["entity"]][ref["field"]]
        if ref["type"]!=field["type"]: issue("FIELD_TYPE_MISMATCH",ref)
        if ref["writes_null"] and not field["nullable"]: issue("NULL_NOT_ALLOWED",ref)
    for ref in values:
        require(isinstance(ref,dict) and set(ref)=={"id","enum","value"},"Invalid enum reference")
        identity(ref)
        require(name(ref["enum"]) and isinstance(ref["value"],str) and 0<len(ref["value"])<=128,"Invalid enum reference values")
        if ref["enum"] not in enums: issue("UNKNOWN_ENUM",ref)
        elif ref["value"] not in enums[ref["enum"]]: issue("UNKNOWN_ENUM_VALUE",ref)
    return {"passed":not issues,"checked":len(seen),"issues":issues,"contract_digest":digest(contract),"references_digest":digest(references),"scope":"Declared references only; no source parsing or runtime proof"}
