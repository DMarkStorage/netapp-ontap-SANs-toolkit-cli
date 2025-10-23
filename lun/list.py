#!/usr/bin/env python3
"""
List ONTAP LUNs (optionally filtered by SVM, volume, LUN name).

Usage:
    python lun_list.py
    python lun_list.py --svm svm1
    python lun_list.py --svm svm1 --volume vol_app
    python lun_list.py --svm svm1 --fields name,uuid,svm.name,status.state,space.size

Environment (.env supported):
    HOST, USER or USERNAME, PASSWORD
"""

import argparse, base64, json, os, sys, requests
from dotenv import load_dotenv
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env_or_die():
    script_dir = Path(__file__).resolve().parent
    dotenv_path = (script_dir / '..' / '..' / '.env').resolve()
    load_dotenv(dotenv_path=dotenv_path)
    host = os.getenv("HOST")
    user = os.getenv("USER")
    pw = os.getenv("PASSWORD")
    missing = [k for k, v in [("HOST", host), ("USER/USERNAME", user), ("PASSWORD", pw)] if not v]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}. Set them or create a .env", file=sys.stderr)
        sys.exit(1)
    return host, user, pw

def auth_header(user, pw):
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
    }

def get_page(url, headers, params=None, verify=False, timeout=15):
    """One GET with error handling; returns (json, next_href or None)."""
    r = requests.get(url, headers=headers, params=params, verify=verify, timeout=timeout)
    if r.status_code >= 400:
        raise requests.HTTPError(f"{r.status_code} {r.text}", response=r)
    data = r.json()
    next_href = (data.get("_links") or {}).get("next", {}).get("href")
    return data, next_href


def paginate_all(base_api, headers, params=None, verify=False):
    items = []
    url = f"{base_api}/storage/luns"
    data, next_href = get_page(url, headers, params=params, verify=verify)
    items.extend(data.get("records", []))

    while next_href:
        # next_href is typically a path beginning with /api/...
        if next_href.startswith("http"):
            url = next_href
        else:
            # Build absolute URL from base and next path
            if next_href.startswith("/"):
                url = f"{base_api.split('/api')[0]}{next_href}"
            else:
                url = f"{base_api}/{next_href.lstrip('/')}"
        data, next_href = get_page(url, headers, params=None, verify=verify)
        items.extend(data.get("records", []))

    return items


def main():
    host, user, password = load_env_or_die()

    ap = argparse.ArgumentParser(description="List ONTAP LUNs (optionally filtered)")
    ap.add_argument("--svm", help="Filter by SVM name (svm.name)")
    ap.add_argument("--volume", help="Filter by Volume name (location.volume.name)")
    ap.add_argument("--lun", help="Filter by LUN name (exact path /vol/<vol>/<lun>)")
    ap.add_argument("--fields", help="Comma-separated field list to request via fields=... "
                                     "(e.g., name,uuid,svm.name,status.state,space.size)")
    ap.add_argument("--verify", action="store_true", help="Verify TLS certs")
    args = ap.parse_args()

    headers = auth_header(user, password)
    base_api = f"https://{host}/api"

    # Build query params
    params = {}
    DEFAULT_FIELDS = "name,uuid,svm.name,status.state,location.volume.name,space.size"
    if args.svm:
        params["svm.name"] = args.svm
    if args.volume:
        params["location.volume.name"] = args.volume
    if args.lun:
        params["name"] = args.lun
    if not args.fields:
        params["fields"] = DEFAULT_FIELDS
    else:
        params["fields"] = args.fields

    # Pull all pages
    records = paginate_all(base_api, headers, params=params, verify=args.verify)

    # Friendly summary
    print(f"Retrieved {len(records)} LUN record(s).")
    if records:
        # Print a concise summary table for quick eyeballing
        def pick(d, key, default=""):
            # supports nested like 'svm'->'name' via dotted "svm.name"
            if "." in key:
                cur = d
                for part in key.split("."):
                    if isinstance(cur, dict):
                        cur = cur.get(part, {})
                    else:
                        cur = {}
                return cur if cur != {} else default
            return d.get(key, default)

        print("-" * 80)
        print(f"{'NAME':35} {'UUID':36} {'   STATE':8} {'SVM':10} {'VOL':12} {'SIZE(B)'}")
        print("-" * 80)
        for rec in records:
            name  = rec.get("name", "")
            uuid  = rec.get("uuid", "")
            state = pick(rec, "status.state", "")
            svm   = pick(rec, "svm.name", "")
            vol   = pick(rec, "location.volume.name", "")
            sizeb = pick(rec, "space.size", "")
            print(f"{name[:35]:35} {uuid[:36]:36} {state[:8]:8} {svm[:10]:10} {vol[:12]:12} {sizeb}")
        print("-" * 80)




if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"HTTP ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
