#!/usr/bin/env python3
"""
ONTAP SAN Igroup Management Script
==================================

This script automates the creation of SAN initiator groups (igroups) in NetApp ONTAP
via REST API calls. It reads authentication and connection details (HOST, USER, PASSWORD)
from a `.env` file located two directories above the script.

Features:
---------
- Creates a new igroup within a specified SVM.
- Supports adding one or more initiators at creation time.
- Supports nesting other igroups within a new igroup.
- Provides formatted output of the created igroup details.

Environment Variables:
----------------------
HOST        - ONTAP management IP or hostname
USER        - Username for ONTAP API access
PASSWORD    - Password for ONTAP API access

Example Usage:
--------------
Create an igroup with initiators and nested igroups:

    python create_igroup.py --svm svm_data --igroup linux_igroup \
        linux iscsi --initiator iqn.1991-05.com.ms:host1 iqn.1991-05.com.ms:host2 \
        --initiator_group prod_igroup

"""

import argparse, base64, json, os, sys, requests
from dotenv import load_dotenv
import urllib3
from pathlib import Path 

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env():
    script_dir = Path(__file__).resolve().parent
    dotenv_path = (script_dir / '..' / '..' / '.env').resolve()
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Attempting to load .env from: {dotenv_path}")
    host = os.getenv("HOST")
    user = os.getenv("USER")
    pw   = os.getenv("PASSWORD")
    missing = [k for k, v in [("HOST", host), ("USER/USERNAME", user), ("PASSWORD", pw)] if not v]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}. Set them or create a .env", file=sys.stderr)
        sys.exit(1)
    return host, user, pw


def auth_header(user, password):
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {creds}",
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
    """
    Fetch all records from /protocols/san/igroups, following _links.next.href.

    Notes:
      - We send `params` on the first request.
      - For subsequent pages, we follow the absolute/relative href the API gives us,
        and stop sending `params` (next link already encodes the cursor).
    """
    items = []
    url = f"{base_api}/protocols/san/igroups"
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

def display_igroups(records):
    print()
    if len(records) == 0:
        print("*"*51)
        print("*                                                 *")
        print("*   No Igroups found matching the criteria.      *")
        print("*                                                 *")
        print("*"*51)
        sys.exit(0)

        # Friendly summary
    print(f"Retrieved {len(records)} igroups record(s).")

    # Helper: dotted-key picker (e.g., "svm.name")
    def pick(d, dotted_key, default=""):
        cur = d
        for part in dotted_key.split("."):
            if isinstance(cur, dict):
                cur = cur.get(part, None)
            else:
                cur = None
            if cur is None:
                return default
        return cur

    def join_names(items, *name_keys, default="-", sep=", "):
        """Join any of the possible keys (name/wwpn/iqn) found in item dicts."""
        if not isinstance(items, list):
            return default
        vals = []
        for it in items:
            if not isinstance(it, dict):
                continue
            for k in name_keys:
                v = it.get(k)
                if v:
                    vals.append(v)
                    break
        return sep.join(vals) if vals else default

    def fmt_lun_maps(lun_maps):
        """Format LUN maps as 'L#:path'."""
        if not isinstance(lun_maps, list):
            return "-"
        out = []
        for m in lun_maps:
            if not isinstance(m, dict):
                continue
            lnum = m.get("logical_unit_number")
            lun = m.get("lun", {}) if isinstance(m.get("lun", {}), dict) else {}
            lpath = lun.get("name", "")
            if lpath or lnum is not None:
                if lnum is not None and lpath:
                    out.append(f"{lnum}:{lpath}")
                elif lpath:
                    out.append(lpath)
                else:
                    out.append(str(lnum))
        return ", ".join(out) if out else "-"

    def fmt_parent_igroups(parents):
        if not isinstance(parents, list):
            return "-"
        names = [p.get("name") for p in parents if isinstance(p, dict) and p.get("name")]
        return ", ".join(names) if names else "-"

    def wrap_text(text, width):
        """Wrap text manually with indentation for multiline columns."""
        if text == "-":
            return [text]
        lines = []
        current = ""
        for part in text.split(", "):
            if len(current) + len(part) + 2 > width:
                lines.append(current.rstrip(", "))
                current = part + ", "
            else:
                current += part + ", "
        if current:
            lines.append(current.rstrip(", "))
        return lines

    # Print header
    print("-" * 160)
    print(f"{'VSERVER':35} {'IGROUP':20} {'PROTOCOL':9} {'OS_TYPE':10} {'INITIATORS':45} {'PARENT_IGROUPS':25} {'MAPS':}")
    print("-" * 160)

    for rec in records:
        if not isinstance(rec, dict):
            continue

        vserver = pick(rec, "svm.name", "")
        igroup = rec.get("name", "")
        protocol = rec.get("protocol", "")
        os_type = rec.get("os_type", "")

        initiators = join_names(rec.get("initiators", []), "name", "wwpn", "iqn")
        parent_igroups = fmt_parent_igroups(rec.get("parent_igroups", []))
        maps = fmt_lun_maps(rec.get("lun_maps", []))

        initiator_lines = wrap_text(initiators, 45)
        map_lines = wrap_text(maps, 80)  # wrap LUN maps too

        # Determine the number of lines to print for this record
        max_lines = max(len(initiator_lines), len(map_lines))

        for i in range(max_lines):
            vs = vserver if i == 0 else ""
            ig = igroup if i == 0 else ""
            pr = protocol if i == 0 else ""
            os = os_type if i == 0 else ""
            pa = parent_igroups if i == 0 else ""

            init_line = initiator_lines[i] if i < len(initiator_lines) else ""
            map_line = map_lines[i] if i < len(map_lines) else ""

            print(f"{vs:35} {ig:20} {pr:9} {os:10} {init_line:45} {pa:25} {map_line}")

    print("-" * 160)



def main():
    host, user, password = load_env()

    ap = argparse.ArgumentParser(description="List ONTAP Initiator groups (optionally filtered)")
    ap.add_argument("--query_filter", nargs=2, help="Filter by field and value (name, os_type, protocol,igroups.name etc.) (e.g., --query_filter os_type linux)")
    ap.add_argument("--fields", help="Comma-separated field list to request via fields=... "
                                     "(e.g., igroups,parent_igroups, lun_maps)")
    ap.add_argument("--verify", action="store_true", help="Verify TLS certs")
    args = ap.parse_args()

    headers = auth_header(user, password)
    base_api = f"https://{host}/api"

    # Build query params
    params = {}
    DEFAULT_FIELDS = "*,igroups,parent_igroups.name,lun_maps,os_type"
    if args.query_filter:
        field, value = args.query_filter
        params[field] = value
        
    if not args.fields:
        params["fields"] = DEFAULT_FIELDS
    else:
        params["fields"] = args.fields

    # Pull all pages
    records = paginate_all(base_api, headers, params=params, verify=args.verify)

    display_igroups(records)


    # Full JSON (for tooling / parsing)
    # print("\nFull JSON response:")
    # print(json.dumps(records, indent=2))


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"HTTP ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
