#!/usr/bin/env python3

"""

Create a LUN on a NetApp ONTAP cluster using the REST API.

This script automates the creation of a Logical Unit Number (LUN) within a
specified Storage Virtual Machine (SVM) and volume. It connects securely to
the ONTAP cluster using credentials defined in a .env file or provided
environment variables.

Typical use cases:
    • Provisioning new block storage for virtual machines, databases, or apps
    • Automating SAN storage setup as part of deployment workflows

Usage:
    python lun_create.py --svm <svm_name> --volume <volume_name> \
                         --lun <lun_name> --size <size> [--os-type <type>] [--insecure]

Example:
    python lun_create.py --svm svm1 --volume vol_app --lun db_lun01 --size 200G --os-type vmware

Arguments:
    --svm         Name of the SVM where the LUN will be created.
    --volume      Target volume that will contain the LUN.
    --lun         Logical Unit Name (unique identifier for the LUN).
    --size        LUN size (supports suffixes: K, M, G, T, P).
    --os-type     Operating system type (e.g., linux, vmware, windows).
    --insecure    Skip TLS certificate verification (use for lab environments).

Env (.env is supported):
  HOST, USER, PASSWORD   (USERNAME is also accepted for USER)

"""

import argparse, base64, json, requests, sys, re
from dotenv import load_dotenv
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env():
    load_dotenv()
    host = os.getenv("HOST")
    user = os.getenv("USER") or os.getenv("USERNAME")
    pw   = os.getenv("PASSWORD")
    missing = [k for k, v in [("HOST", host), ("USER/USERNAME", user), ("PASSWORD", pw)] if not v]
    if missing:
        print(f"❌ Missing env vars: {', '.join(missing)}. Set them or create a .env", file=sys.stderr)
        sys.exit(1)
    return host, user, pw


def to_bytes(s: str) -> int:
    m = re.fullmatch(r"\s*(\d+)([KMGTP]?)\s*", s, re.I)
    if not m: raise ValueError("Invalid size (e.g., 100G, 20M, 4096)")
    n, suf = int(m.group(1)), m.group(2).upper()
    mult = {"":1,"K":1024,"M":1024**2,"G":1024**3,"T":1024**4,"P":1024**5}[suf]
    return n*mult

def auth_header(user, pw):
    return {
        "Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
    }

def main():
    ap = argparse.ArgumentParser(description="Create a LUN on ONTAP (REST)")
    ap.add_argument("--svm", required=True, help="SVM name")
    ap.add_argument("--volume", required=True, help="Volume name (existing)")
    ap.add_argument("--lun", required=True, help="LUN name to create")
    ap.add_argument("--size", required=True, help="Size (e.g., 100G, 20M, 4096)")
    ap.add_argument("--os-type", default="linux", help="linux|windows|vmware|aix|…")
    ap.add_argument("--space-reserve", action="store_true", help="Enable space reservation")
    args = ap.parse_args()

    host, user, passwd = load_env()


    size_bytes = to_bytes(args.size)

    headers = {"accept": "application/json", "content-type": "application/json"}
    headers.update(auth_header(user, passwd))
    base = f"https://{host}/api"

    body = {
        "name": f"/vol/{args.volume}/{args.lun}",
        "os_type": args.os_type,
        "svm": {"name": args.svm},
        "space": {"size": size_bytes}
    }

    r = requests.post(f"{base}/storage/luns?return_records=true", headers=headers, json=body, verify=False, timeout=30)
    if r.status_code >= 400:
        print(f"ERROR {r.status_code}: {r.text}", file=sys.stderr); sys.exit(1)

    resp = r.json()
    if "records" in resp and len(resp["records"]) > 0:
        print("LUN creation successful!")
        print("----------------------------------------------------")
        print(f"LUN Path: {resp['records'][0].get('name', 'N/A')}")
        print(f"UUID: {resp['records'][0].get('uuid', 'N/A')}")
        print(f"Volume: {args.volume}")
        print(f"Size (bytes): {size_bytes}")
        print(f"OS Type: {args.os_type}")
        print(f"SVM: {args.svm}")
        print("----------------------------------------------------")

        # If there’s a _links or job link (asynchronous operation)
        if "_links" in resp and "self" in resp["_links"]:
            print(f"LUN details link: {resp['_links']['self']['href']}")
            

if __name__ == "__main__":
    main()


