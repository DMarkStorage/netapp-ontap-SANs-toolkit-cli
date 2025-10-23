#!/usr/bin/env python3
"""
ONTAP SAN LUN Mapping Utility

This script interacts with the NetApp ONTAP REST API to list LUN mappings
and display detailed mapping information, including associated igroups,
OS types, protocols, and LUN IDs.

Environment variables for cluster connection (`HOST`, `USER`, `PASSWORD`)
are loaded from a `.env` file two directories above the script location.

Usage Examples:
---------------
    # List all LUN mappings
    python list_lun_maps.py

    # List mappings for a specific LUN
    python list_lun_maps.py --lun vol1/lun1

    # Show UUIDs instead of detailed parameters
    python list_lun_maps.py --uuid

    # Disable SSL verification
    python list_lun_maps.py --insecure
"""

import argparse
import base64
import json
import os
import sys
import requests
from dotenv import load_dotenv
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


def auth_header(user, password):
    creds = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Basic {creds}",
    }


def display_lunmaps(records, uuid, params):
    """
    Display formatted LUN mapping results returned from ONTAP REST API.

    Depending on the provided arguments, this function prints one of:
        * Detailed mapping view (with OS type, protocol, LUN ID)
        * UUID-based mapping view
        * Simple SVM/LUN/Igroup mapping view

    Args:
        records (requests.Response): Response object from the REST API call.
        uuid (bool): Whether to display UUIDs in the output.
        params (dict): Optional filter parameters used for the API query.

    Exits:
        SystemExit: after displaying data (this function terminates execution).
    """
    print()
    if records.json().get("num_records", 0) == 0:
        print("*" * 51)
        print("*                                                 *")
        print("*   No LUN mappings found matching the criteria.  *")
        print("*                                                 *")
        print("*" * 51)
        sys.exit(0)

    if params:
        print(f"{'Vserver':15} {'PATH':35} {'NODE':15} {'Igroup':15} {'OS_TYPE':10} {'PROTOCOL':10} {'LUNID':5}")
        print("---" * 40)
        if "records" in records.json():
            for record in records.json()["records"]:
                name = record.get('svm', {}).get('name', '')
                lun = record.get('lun', {}).get('name', '')
                node = record.get('lun', {}).get('node', {}).get('name', '')
                igroup = record.get('igroup', {}).get('name', '')
                os_type = record.get('igroup', {}).get('os_type', '')
                protocol = record.get('igroup', {}).get('protocol', '')
                lunid = record.get('logical_unit_number', '')
                print(f"{name:15} {lun:35} {node:15} {igroup:15} {os_type:10} {protocol:10} {lunid:3} ")
        print("\n")
        print("---" * 40)
        sys.exit(0)

    if uuid:
        print(f"{'Vserver':15} {'PATH':35} {'LUN UUID':40} {'Igroup':15} {'Igroup UUID':40}")
        print("---" * 50)
        if "records" in records.json() and records.json()["num_records"] > 0:
            for record in records.json()["records"]:
                name = record.get('svm', {}).get('name', '')
                lun = record.get('lun', {}).get('name', '')
                lun_uuid = record.get('lun', {}).get('uuid', '')
                igroup = record.get('igroup', {}).get('name', '')
                igroup_uuid = record.get('igroup', {}).get('uuid', '')
                print(f"{name[:15]:15} {lun[:35]:35} {lun_uuid:40} {igroup[:15]:15} {igroup_uuid:40}")
        print("---" * 50)
        sys.exit(0)

    print(f"{'Vserver':15} {'PATH':35} {'Igroup':15}")
    print("--" * 30)
    if "records" in records.json() and records.json()["num_records"] > 0:
        for record in records.json()["records"]:
            name = record.get('svm', {}).get('name', '')
            lun = record.get('lun', {}).get('name', '')
            igroup = record.get('igroup', {}).get('name', '')
            print(f"{name:15} {lun:35} {igroup:15}")
    print("--" * 30)


def list_lun_maps(base, headers, verify, uuid, params=None):
    url = f"{base}protocols/san/lun-maps"

    if params:
        params.setdefault(
            "fields",
            "svm.name,lun.name,lun.node.name,igroup.name,igroup.os_type,igroup.protocol,logical_unit_number"
        )
    resp = requests.get(url, headers=headers, params=params, verify=verify, timeout=10)
    if resp.status_code >= 400:
        print(f"ERROR! {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    display_lunmaps(resp, uuid, params)


def main(host, user, pw):
    ap = argparse.ArgumentParser(
        description="List ONTAP LUN mappings",
        epilog="Cluster must have SAN-capable data LIFs (iSCSI or FCP)."
    )
    ap.add_argument("--lun", help="Enter the LUN path name of specific LUN")
    ap.add_argument("--igroup", help="Enter the igroup name")
    ap.add_argument("--uuid", action="store_true", help="Show UUIDs of LUNs and igroups")
    ap.add_argument("--insecure", action="store_true", help="Disable SSL verification")
    ap.add_help = True

    args = ap.parse_args()
    params = {}
    if args.lun:
        params["lun.name"] = args.lun
    if args.igroup:
        params["igroup.name"] = args.igroup

    headers = auth_header(user, pw)
    base = f"https://{host}/api/"

    list_lun_maps(base, headers, args.insecure, args.uuid, params=params)


if __name__ == "__main__":
    try:
        host, user, password = load_env()
        main(host, user, password)
    except requests.HTTPError as e:
        print(f"HTTP ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
