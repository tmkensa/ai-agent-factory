"""Machine-readable role contracts and allowlisted diagnostic codes."""
import re
import json
from factory.engine import FactoryError

SECRET = re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|(?:sk-|gh[pousr]_)[A-Za-z0-9_-]{16,}|(?:AKIA|ASIA)[A-Z0-9]{16}|(?:whsec_|[rps]k_(?:live|test)_)[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{35}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|(?:mysql|postgres(?:ql)?|mongodb(?:\+srv)?|redis)://[^/\s:@]+:[^@\s]+@",re.I)
CODES = {
    "Invalid plan":"INVALID_PLAN", "Invalid draft":"INVALID_DRAFT",
    "Invalid research output":"INVALID_RESEARCH", "Invalid finding":"INVALID_FINDING",
    "Unknown source":"UNKNOWN_SOURCE", "Unverified source quotation":"UNVERIFIED_QUOTE",
    "Invalid review":"INVALID_REVIEW", "Missing review checks":"MISSING_REVIEW_CHECKS",
    "Invalid check":"INVALID_CHECK", "Invalid review id or pass flag":"INVALID_REVIEW_ID",
    "Invalid critical list":"INVALID_CRITICAL_LIST", "Invalid text field":"INVALID_TEXT",
    "Role output must be an object":"INVALID_OBJECT", "Model output must be JSON object":"INVALID_OBJECT",
    "Invalid specialist output":"INVALID_SPECIALIST", "Specialist output limit":"SPECIALIST_OUTPUT_LIMIT",
}
RETRYABLE = frozenset(CODES.values()) | {"INVALID_JSON"}

def error_code(exc):
    if isinstance(exc, FactoryError):
        msg = str(exc)
        if msg in CODES: return CODES[msg]
        if msg.startswith("Potential secret detected"): return "SECRET_DETECTED"
        if re.fullmatch(r"HTTP [1-5][0-9]{2}; no automatic retry",msg):
            return "PROVIDER_HTTP_"+msg[5:8]
        return "FACTORY_POLICY_ERROR"
    if isinstance(exc,json.JSONDecodeError): return "INVALID_JSON"
    if isinstance(exc,TimeoutError): return "TIMEOUT"
    if isinstance(exc,OSError): return "TRANSPORT_ERROR"
    return "UNEXPECTED_ERROR"

def role_schema(role, count):
    def obj(properties):
        return {"type":"object","properties":properties,"required":list(properties),"additionalProperties":False}
    def arr(items, lo=0, hi=16):
        return {"type":"array","items":items,"minItems":lo,"maxItems":hi}
    def string(maximum):
        return {"type":"string","minLength":1,"maxLength":maximum}
    if role=="planner": return obj({"steps":arr(string(1000),1,8)})
    if role=="researcher": return obj({"findings":arr(obj({"source":string(80),"quote":string(1500)})),"limitations":string(2000)})
    if role=="executor": return obj({"draft":string(40000)})
    if role=="specialist": return obj({"text":string(3000)})
    return obj({"checks":arr(obj({"id":{"type":"integer","minimum":0,"maximum":count-1},"passed":{"type":"boolean"},"reason":string(2000)}),count,count),"critical":arr(string(2000),0,10),"feedback":string(4000)})
