#!/usr/bin/env python3
"""
ONTAP LUN Map Deletion Utility

This script allows administrators to query and delete LUN mappings
from a NetApp ONTAP storage system via the REST API.

It uses credentials and management IP loaded from a `.env` file and
performs authenticated REST API calls over HTTPS.

Typical workflow:
1. The script queries a LUN mapping based on a provided LUN path and igroup name.
2. It displays the LUN mapping information.
3. It prompts the user for confirmation before deleting the mapping.
4. If confirmed, it sends a DELETE request to remove the LUN mapping.

Environment variables expected in `.env`:
    HOST=<ONTAP management IP or hostname>
    USER=<ONTAP API username>
    PASSWORD=<ONTAP API password>

Example:
    python delete_lun.py --lun /vol/testvol/lun1 --igroup linux_igroup
"""

import argparse
import base64
import json
import requests
import sys
from dotenv import load_dotenv
import os
import urllib3
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env():
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


def del_lun(headers, base, params):
    resp = requests.delete(f"{base}/protocols/san/lun-maps",
                           headers=headers, params=params,
                           verify=False, timeout=10)

    if resp.status_code >= 400:
        print(f"ERROR {resp.status_code} : {resp.text}", file=sys.stderr)
        sys.exit(1)

    print("LUN MAP DELETED!")


def get_lun(headers, base, params):
    params.setdefault(
        "fields",
        "svm.name,lun.name,lun.node.name,igroup.name,igroup.os_type,igroup.protocol,logical_unit_number"
    )
    resp = requests.get(f"{base}/protocols/san/lun-maps",
                        headers=headers, params=params,
                        verify=False, timeout=10)
    if resp.status_code >= 400:
        print(f"ERROR {resp.status_code} : {resp.text}", file=sys.stderr)
        sys.exit(1)

    return resp.json().get("records", [])


def main():
    ap = argparse.ArgumentParser(description="DELETE ONTAP LUNs")
    ap.add_argument("--lun", help="Enter the LUN path name of specific LUN")
    ap.add_argument("--igroup", help="Enter the igroup name")

    args = ap.parse_args()

    host, user, pw = load_env()
    headers = auth_header(user, pw)
    base = f"https://{host}/api"

    params = {
        "lun.name": args.lun,
        "igroup.name": args.igroup
    }

    records = get_lun(headers, base, params=params)
    if records:
        print("LUN map To be DELETED ⚠ ⚠ : ")
        print(f"{'Vserver':15} {'LUN':35} {'NODE':15} {'Igroup':15} {'OS_TYPE':10} {'PROTOCOL':10} {'LUNID':5}")
        print("---" * 40)
        name = records[0].get('svm', {}).get('name', '')
        lun = records[0].get('lun', {}).get('name', '')
        node = records[0].get('lun', {}).get('node', {}).get('name', '')
        igroup = records[0].get('igroup', {}).get('name', '')
        os_type = records[0].get('igroup', {}).get('os_type', '')
        protocol = records[0].get('igroup', {}).get('protocol', '')
        lunid = records[0].get('logical_unit_number', '')
        print(f"{name:15} {lun:35} {node:15} {igroup:15} {os_type:10} {protocol:10} {lunid:3} ")
        print("\n")
        print("---" * 40)

    prompt = input("Are you sure to DELETE this LUN? type 'yes' to confirm: ")
    if prompt.lower() != "yes":
        print("Aborting... No changes made!")
        sys.exit(0)

    del_lun(headers=headers, base=base, params=params)


if __name__ == "__main__":
    main()
