"""Spotify authorization, to be run ONCE on the streamer's machine.

    python scripts/authorize_spotify.py

The script opens the browser, waits for Spotify to redirect back, then prints the
refresh token to paste into the .env (SPOTIFY_REFRESH_TOKEN). That token does not
expire: the bot uses it to mint access tokens on demand.

Prerequisites, in the Spotify dashboard (https://developer.spotify.com/dashboard):
  - create an app and grab its Client ID / Client Secret;
  - add EXACTLY this Redirect URI: http://127.0.0.1:8888/callback
    (Spotify no longer accepts "localhost", the loopback IP is required).
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

from spotify import SCOPES  # noqa: E402

REDIRECT_URI = "http://127.0.0.1:8888/callback"
HOST, PORT = "127.0.0.1", 8888

# Filled in by the HTTP handler, read by the main thread.
result: dict[str, str] = {}
done = threading.Event()
# Set before the server starts; the handler compares every callback against it.
expected_state = ""


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        query = urllib.parse.urlparse(self.path)
        if query.path != "/callback":
            self.send_error(404)
            return

        params = {k: v[0] for k, v in urllib.parse.parse_qs(query.query).items()}

        # Any process or web page on this machine can reach 127.0.0.1:8888 while
        # we wait. Requests whose state does not match ours are dropped here,
        # before they can overwrite the legitimate callback's parameters, and the
        # first valid callback wins.
        if not secrets.compare_digest(params.get("state", ""), expected_state) or done.is_set():
            self.send_error(403)
            return

        result.update(params)

        # The page is static: nothing from the query string is echoed back into
        # it, which would otherwise be a reflected-XSS foothold.
        if "code" in result:
            body = "<h2>All good!</h2><p>Head back to your terminal.</p>"
        else:
            body = "<h2>Authorization failed</h2><p>See the terminal for details.</p>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<html><body style='font-family:sans-serif'>{body}</body></html>".encode())
        done.set()

    def log_message(self, *args: object) -> None:
        pass  # Keep HTTP logs out of the script's output.


def exchange_code(code: str, client_id: str, client_secret: str) -> dict:
    payload = urllib.parse.urlencode(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI}
    ).encode()
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    request = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=payload,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Spotify rejected the code exchange ({exc.code}): {exc.read().decode()}")


def main() -> None:
    load_dotenv()
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in the .env first.")

    global expected_state
    expected_state = state = secrets.token_urlsafe(32)
    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            # Force the consent screen, useful when re-authorizing with new scopes.
            "show_dialog": "true",
        }
    )

    server = http.server.HTTPServer((HOST, PORT), CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("Opening the browser to authorize the application...")
    print(f"If nothing opens, paste this URL:\n\n{auth_url}\n")
    webbrowser.open(auth_url)

    if not done.wait(timeout=300):
        sys.exit("Timed out after 5 min: no redirect received.")
    server.shutdown()

    if "code" not in result:
        sys.exit(f"Authorization denied: {result.get('error', 'unknown error')}")
    # Re-checked here as well: the handler runs on another thread, and this keeps
    # the guarantee local to where the code is actually spent.
    if not secrets.compare_digest(result.get("state", ""), state):
        sys.exit("The 'state' parameter did not match, authorization aborted.")

    tokens = exchange_code(result["code"], client_id, client_secret)
    refresh = tokens.get("refresh_token")
    if not refresh:
        sys.exit("No refresh token in Spotify's response.")

    print("\nAdd this line to your .env:\n")
    print(f"SPOTIFY_REFRESH_TOKEN={refresh}\n")
    print("Then verify with:  python -m spotify <spotify link>")


if __name__ == "__main__":
    main()
