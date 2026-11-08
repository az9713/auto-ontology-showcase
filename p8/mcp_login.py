"""P8 arm O: get and refresh an OAuth token for the auto-ontology MCP server, so `claude -p` can run headless.

  python -I mcp_login.py            # 1 browser sign-in (DCR + PKCE), saves mcp_token.json
  python -I mcp_login.py --refresh  # refresh grant, no browser; writes mcp_auth.json (mcp-config with the header)

mcp_token.json and mcp_auth.json hold secrets: never print them. Output shows status and expiry only.
"""
import base64, hashlib, http.server, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request, webbrowser

AS = "http://localhost:3000/api/auth/oauth2"
RESOURCE = "http://localhost:3003/mcp"
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, "mcp_token.json")
AUTH_CFG = os.path.join(HERE, "mcp_auth.json")


def post(url: str, data: dict, as_json: bool = False) -> dict:
    body = json.dumps(data).encode() if as_json else urllib.parse.urlencode(data).encode()
    ctype = "application/json" if as_json else "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, body, {"Content-Type": ctype, "Accept": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from {url}: {e.read()[:400]!r}")


def save(tok: dict, client_id: str) -> None:
    tok = {"client_id": client_id, "access_token": tok["access_token"],
           "refresh_token": tok.get("refresh_token"), "expires_at": time.time() + tok.get("expires_in", 0)}
    with open(TOKEN_FILE, "w") as f:
        json.dump(tok, f)
    cfg = {"mcpServers": {"auto-ontology": {"type": "http", "url": RESOURCE,
                                            "headers": {"Authorization": "Bearer " + tok["access_token"]}}}}
    with open(AUTH_CFG, "w") as f:
        json.dump(cfg, f)
    left = tok["expires_at"] - time.time()
    print(f"token saved; expires in {left:.0f} s; refresh token: {bool(tok['refresh_token'])}")
    req = urllib.request.Request(AS + "/userinfo", headers={"Authorization": "Bearer " + tok["access_token"]})
    print("userinfo:", urllib.request.urlopen(req, timeout=30).status)


got: dict = {}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        if "code" in q or "error" in q:
            got.update(q)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"P8 sign-in received. You can close this tab.")

    def log_message(self, *a):
        pass


def login() -> None:
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)  # port 0: Windows reserves fixed ports (WinError 10013 on 8765)
    srv.timeout = 1
    redirect = f"http://localhost:{srv.server_address[1]}/callback"
    reg = post(AS + "/register", {"client_name": "p8-arm-o", "redirect_uris": [redirect],
                                  "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                                  "token_endpoint_auth_method": "none"}, as_json=True)
    client_id = reg["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = AS + "/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect, "state": state,
        "scope": "openid profile email offline_access", "code_challenge": challenge,
        "code_challenge_method": "S256", "resource": RESOURCE, "prompt": "consent"})
    print("Opening the browser. If it does not open, paste this URL:\n" + url)
    webbrowser.open(url)
    end = time.time() + 600
    while not got and time.time() < end:
        srv.handle_request()
    if not got:
        sys.exit("no callback in 600 s")
    if got.get("state") != state or "error" in got:
        sys.exit(f"bad callback: error={got.get('error')} state_ok={got.get('state') == state}")
    tok = post(AS + "/token", {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": redirect,
                               "client_id": client_id, "code_verifier": verifier, "resource": RESOURCE})
    save(tok, client_id)


def refresh() -> None:
    old = json.load(open(TOKEN_FILE))
    tok = post(AS + "/token", {"grant_type": "refresh_token", "refresh_token": old["refresh_token"],
                               "client_id": old["client_id"], "resource": RESOURCE})
    tok.setdefault("refresh_token", old["refresh_token"])  # ponytail: keep old one if the AS does not rotate
    save(tok, old["client_id"])


if __name__ == "__main__":
    refresh() if "--refresh" in sys.argv else login()
