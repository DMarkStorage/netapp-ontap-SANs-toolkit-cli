#!/usr/bin/env python3
"""
ONTAP LUN Mapping Utility

This script automates the process of creating a LUN-to-igroup mapping on a NetApp ONTAP cluster 
using the REST API. It reads connection credentials (HOST, USER, PASSWORD) from a `.env` file 
and allows users to specify the SVM, LUN, and igroup via command-line arguments.

Features:
    - Secure authentication via HTTP Basic Auth
    - Automatic .env loading for cluster credentials
    - Option to disable SSL certificate verification for testing
    - Clear success and error reporting

Example usage:
    python lun_map.py --svm mySVM --igroup linux_igroup --lun data_lun --insecure
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


def create(base, headers, params, verify):
    url = f"{base}protocols/san/lun-maps"
    resp = requests.post(url, headers=headers, json=params, verify=verify, timeout=10)

    if resp.status_code >= 400:
        print(f"ERROR! {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    print(
        f"LUN {params['lun']['name']} mapped to igroup {params['igroup']['name']} "
        f"on SVM {params['svm']['name']} successfully."
    )


def main(host, user, pw):
    ap = argparse.ArgumentParser(
        description="Create LUN mapping in ONTAP",
        epilog="Note: The cluster must have active SAN-capable LIFs (iSCSI or FCP)."
    )
    ap.add_argument("--svm", required=True, help="SVM name")
    ap.add_argument("--igroup", required=True, help="Igroup name")
    ap.add_argument("--lun", required=True, help="LUN name")
    ap.add_argument("--insecure", action="store_true", help="Disable SSL verification")
    args = ap.parse_args()

    # Note: This logic disables SSL verification when --insecure is used
    verify = not args.insecure

    headers = auth_header(user, pw)
    base = f"https://{host}/api/"

    params = {
        "svm": {"name": args.svm},
        "igroup": {"name": args.igroup},
        "lun": {"name": args.lun}
    }

    create(base, headers, params, verify)


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
