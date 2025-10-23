#!/usr/bin/env python3
"""
ONTAP LUN Deletion Utility

This script allows you to safely delete a LUN (Logical Unit Number) from a NetApp ONTAP system
via its REST API. It authenticates using credentials defined in a `.env` file, retrieves the
LUN’s details for confirmation, and performs deletion only upon user confirmation.

Environment Variables (via .env):
    HOST       - Management IP or hostname of the ONTAP system
    USER       - Username for ONTAP API authentication
    PASSWORD   - Password for ONTAP API authentication

Example Usage:
    python del_lun.py --uuid 1234abcd-56ef-78gh-90ij-klmnopqrstuv
"""

import argparse
import base64
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


def del_lun(headers, base, uuid):

    resp = requests.delete(f"{base}/storage/luns/{uuid}", headers=headers, verify=False, timeout=10)
    if resp.status_code >= 400:
        print(f"ERROR {resp.status_code} : {resp.text}", file=sys.stderr)
        sys.exit(1)
    print("LUN DELETED!")


def get_lun(headers, base, uuid):

    resp = requests.get(f"{base}/storage/luns?uuid={uuid}", headers=headers, verify=False, timeout=10)
    if resp.status_code >= 400:
        print(f"ERROR {resp.status_code} : {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json().get("records", [])


def main():

    ap = argparse.ArgumentParser(description="DELETE ONTAP LUNs")
    ap.add_argument("--uuid", required=True, help="LUN UUID to delete")
    args = ap.parse_args()

    host, user, pw = load_env()
    headers = auth_header(user, pw)
    base = f"https://{host}/api"

    records = get_lun(headers, base, args.uuid)
    if records:
        print("LUN To be DELETED ⚠ :")
        print("--" * 15)
        print(f"UUID : {records[0].get('uuid', '')}")
        print(f"Name : {records[0].get('name', '')}")
        print("--" * 15)

    prompt = input("Are you sure to DELETE this LUN? Type 'yes' to confirm: ")
    if prompt.lower() != "yes":
        print("Aborting... No changes made!")
        sys.exit(0)

    del_lun(headers=headers, base=base, uuid=args.uuid)


if __name__ == "__main__":
    main()
