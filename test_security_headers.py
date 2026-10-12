"""Security header tests for the Indonesia Economic Dashboard.

Run:  python3 test_security_headers.py

Covers the header set graded by securityheaders.com, including the negative
cases that a naive "is the header present?" test would miss:
  - HSTS MUST be absent over plain HTTP (sending it there can pin a browser to
    a scheme the host does not serve).
  - The CSP nonce MUST match the nonce on the inline <script> blocks, and MUST
    differ between responses (a reused nonce is as good as 'unsafe-inline').
"""
import re
import sys

import app as dashboard

HTTPS = "https://inthiseconomy.choirulhaq.com"
HTTP = "http://inthiseconomy.choirulhaq.com"

REQUIRED_HEADERS = [
    "Content-Security-Policy",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
    "Cross-Origin-Opener-Policy",
    "Cross-Origin-Resource-Policy",
]

passed = failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {label}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def nonce_of(csp):
    m = re.search(r"'nonce-([^']+)'", csp or "")
    return m.group(1) if m else None


def main():
    client = dashboard.app.test_client()

    print("\n[1] Every security header present over HTTPS")
    r = client.get("/", base_url=HTTPS)
    check("dashboard returns 200", r.status_code == 200, f"got {r.status_code}")
    for h in REQUIRED_HEADERS:
        check(f"{h} present", r.headers.get(h), "missing")

    print("\n[2] Header values")
    check("X-Content-Type-Options == nosniff",
          r.headers.get("X-Content-Type-Options") == "nosniff")
    check("X-Frame-Options == DENY", r.headers.get("X-Frame-Options") == "DENY")
    check("Referrer-Policy set",
          r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin")
    check("COOP == same-origin",
          r.headers.get("Cross-Origin-Opener-Policy") == "same-origin")
    check("CORP == same-origin",
          r.headers.get("Cross-Origin-Resource-Policy") == "same-origin")
    check("Permissions-Policy denies camera",
          "camera=()" in (r.headers.get("Permissions-Policy") or ""))

    print("\n[3] HSTS over HTTPS, and ABSENT over plain HTTP")
    check("HSTS present over https", r.headers.get("Strict-Transport-Security"))
    check("HSTS max-age is 1 year",
          "max-age=31536000" in (r.headers.get("Strict-Transport-Security") or ""))
    check("HSTS has includeSubDomains",
          "includeSubDomains" in (r.headers.get("Strict-Transport-Security") or ""))
    check("HSTS has NO preload (owner decision, not a default)",
          "preload" not in (r.headers.get("Strict-Transport-Security") or ""))
    r_http = client.get("/", base_url=HTTP)
    check("HSTS ABSENT over http", r_http.headers.get("Strict-Transport-Security") is None,
          f"got {r_http.headers.get('Strict-Transport-Security')}")

    print("\n[4] ProxyFix: X-Forwarded-Proto drives is_secure")
    r_fwd = client.get("/", headers={"X-Forwarded-Proto": "https"})
    check("XFP=https -> HSTS sent (proves ProxyFix wired)",
          r_fwd.headers.get("Strict-Transport-Security") is not None)
    r_spoof = client.get("/", headers={"X-Forwarded-Proto": "https,http"})
    check("spoofed XFP=https,http -> HSTS withheld (trust exactly 1 hop)",
          r_spoof.headers.get("Strict-Transport-Security") is None)

    print("\n[5] CSP content")
    csp = r.headers.get("Content-Security-Policy") or ""
    check("CSP has NO script-src 'unsafe-inline'",
          "script-src 'unsafe-inline'" not in csp, csp[:160])
    check("CSP has NO script-src * wildcard", "script-src *" not in csp)
    check("CSP script-src carries a nonce", "'nonce-" in csp)
    check("CSP allows the Plotly CDN in script-src",
          "https://cdn.plot.ly" in csp)
    check("CSP allows jsDelivr for styles",
          "https://cdn.jsdelivr.net" in csp)
    check("CSP frame-ancestors 'none'", "frame-ancestors 'none'" in csp)
    check("CSP object-src 'none'", "object-src 'none'" in csp)
    check("CSP base-uri 'self'", "base-uri 'self'" in csp)
    check("CSP form-action 'self'", "form-action 'self'" in csp)

    print("\n[6] Nonce actually applied to every inline <script>")
    html = r.get_data(as_text=True)
    csp_nonce = nonce_of(csp)
    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.I)
    check("inline <script> blocks found", len(inline) > 0, "none found")
    missing = [t for t in inline if f'nonce="{csp_nonce}"' not in t]
    check(f"all {len(inline)} inline scripts carry the CSP nonce",
          not missing, f"missing on {len(missing)}: {missing[:2]}")
    # Plotly emits a bare <script> per chart; a nonce-less one is blocked in-browser.
    bare = [t for t in inline if not re.search(r"nonce=", t, re.I)]
    check("no bare <script> without nonce", not bare, f"{len(bare)} bare")

    print("\n[7] Nonce is fresh per response")
    r2 = client.get("/", base_url=HTTPS)
    n2 = nonce_of(r2.headers.get("Content-Security-Policy"))
    check("nonce differs between responses", csp_nonce != n2,
          f"reused {csp_nonce}")
    check("nonce is long enough (>=16 chars)",
          csp_nonce and len(csp_nonce) >= 16, f"len={len(csp_nonce or '')}")

    print("\n[8] Headers also on non-HTML routes")
    for path in ("/healthz", "/health", "/download/csv"):
        rr = client.get(path, base_url=HTTPS)
        check(f"{path} 200", rr.status_code == 200, f"got {rr.status_code}")
        check(f"{path} has nosniff",
              rr.headers.get("X-Content-Type-Options") == "nosniff")
        check(f"{path} has CSP", bool(rr.headers.get("Content-Security-Policy")))
        check(f"{path} has HSTS", bool(rr.headers.get("Strict-Transport-Security")))

    print("\n[9] Content still renders (headers must not break the page)")
    check("KPI value rendered", "kpi-value" in html)
    check("chart div present", "plotly" in html)
    check("no empty JS assignment (const x = ;)",
          not re.search(r"(?:const|let|var)\s+\w+\s*=\s*;", html))

    print(f"\n=== {passed}/{passed + failed} PASS ===")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
