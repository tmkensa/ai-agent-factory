"""Operator-authorized HTTPS and MCP evidence. No model-controlled tool calls."""
import hashlib
import http.client
import ipaddress
import json
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlsplit
from factory.engine import require
from .providers import request
from .workspace import safe_text

class PlainText(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style","noscript","template"): self.hidden+=1
    def handle_endtag(self, tag):
        if tag in ("script","style","noscript","template") and self.hidden: self.hidden-=1
    def handle_data(self,data):
        if not self.hidden and data.strip(): self.parts.append(data.strip())

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip): super().__init__(host,timeout=20); self.ip=ip
    def connect(self):
        raw=socket.create_connection((self.ip,443),timeout=self.timeout)
        try: self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception: raw.close(); raise

def fetch(url,allowed_host):
    p=urlsplit(url)
    require(p.scheme=="https" and p.hostname==allowed_host and p.port in (None,443) and not p.username and not p.password and not p.fragment and not p.query,"URL outside exact HTTPS allowlist")
    require(p.hostname and re.fullmatch(r"[A-Za-z0-9.-]+",p.hostname),"Invalid hostname")
    ips={row[4][0] for row in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)}
    require(ips and all(ipaddress.ip_address(ip).is_global and not ipaddress.ip_address(ip).is_multicast and not ipaddress.ip_address(ip).is_reserved for ip in ips),"Nonpublic destination denied")
    conn=PinnedHTTPS(p.hostname,sorted(ips)[0])
    try:
        conn.request("GET",(p.path or "/")+("?"+p.query if p.query else ""),headers={"Accept":"text/html,text/plain,application/json","User-Agent":"AI-Agent-Factory/0.3"})
        r=conn.getresponse(); require(r.status==200,"HTTPS fetch failed or redirect denied")
        typ=r.getheader("Content-Type", "").split(";")[0].lower()
        require(typ in {"text/html","text/plain","application/json"},"Unsupported content type")
        require(r.getheader("Content-Encoding","identity")=="identity","Compressed response denied")
        raw=r.read(250_001); require(len(raw)<=250_000,"Evidence exceeds byte limit")
        text=raw.decode("utf-8",errors="replace")
        if typ=="text/html": parser=PlainText(); parser.feed(text); text="\n".join(parser.parts)
        require(bool(text.strip()),"Empty evidence")
        return {"id":"web:"+p.hostname[:42]+":"+hashlib.sha256(url.encode()).hexdigest()[:24],"text":safe_text(("Source URL: "+url+"\n"+text.strip())[:12000])}
    finally: conn.close()

class MCP:
    """Restricted JSON-only modern MCP subset; trusted loopback server only."""
    VERSION="2026-07-28"
    def __init__(self,port,allowed):
        require(type(port) is int and 1<=port<=65535,"Invalid local MCP port")
        require(isinstance(allowed,list) and all(isinstance(n,str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",n) for n in allowed),"Invalid tool allowlist")
        self.port=port; self.allowed=set(allowed)
    def rpc(self,method,params):
        require(method in {"tools/list","tools/call"},"Unsupported MCP method")
        meta={"io.modelcontextprotocol/protocolVersion":self.VERSION,"io.modelcontextprotocol/clientInfo":{"name":"ai-agent-factory","version":"0.3.0"},"io.modelcontextprotocol/clientCapabilities":{}}
        h={"Accept":"application/json, text/event-stream","MCP-Protocol-Version":self.VERSION,"Mcp-Method":method}
        if method=="tools/call": h["Mcp-Name"]=params["name"]
        r=request("127.0.0.1","/mcp",{"jsonrpc":"2.0","id":1,"method":method,"params":{**params,"_meta":meta}},h,30,self.port)
        require(r.get("jsonrpc")=="2.0" and r.get("id")==1 and "error" not in r,"MCP RPC error")
        result=r["result"]; require(result.get("resultType")=="complete" and not result.get("isError"),"MCP incomplete or failed; no retry")
        return result
    def tools(self):
        r=self.rpc("tools/list",{}); require(not r.get("nextCursor"),"Paginated list not supported")
        return [t for t in r["tools"] if t.get("name") in self.allowed]
    def call(self,name,args,approved=False):
        require(approved is True and name in self.allowed,"MCP invocation requires explicit approval and allowlist")
        require(isinstance(args,dict) and len(json.dumps(args,allow_nan=False))<=16000,"Invalid tool arguments")
        safe_text(json.dumps(args,ensure_ascii=False,allow_nan=False))
        matches=[t for t in self.tools() if t["name"]==name]
        require(len(matches)==1,"Tool not uniquely available")
        t=matches[0]
        require(t.get("annotations",{}).get("readOnlyHint") is True,"Only operator-trusted read-only annotated tools supported")
        require("x-mcp-header" not in json.dumps(t.get("inputSchema",{})),"Custom parameter headers unsupported")
        r=self.rpc("tools/call",{"name":name,"arguments":args})
        items=r.get("content",[]); require(all(i.get("type")=="text" for i in items),"Only text evidence supported")
        text="\n".join(i["text"] for i in items)
        require(0<len(text)<=12000,"Empty or oversized MCP evidence")
        return {"id":"mcp:"+name[:75],"text":safe_text(text)}
