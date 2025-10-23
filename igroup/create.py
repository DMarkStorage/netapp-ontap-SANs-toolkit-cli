#!/usr/bin/env python3
import argparse, base64, json, requests, sys
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

def create_initiators(headers, base, params, svm, initiator, os_type, protocol):

    resp = requests.post(f"{base}/protocols/san/igroups?return_records=true", headers= headers, json=params, verify=False, timeout=10)

    if resp.status_code >= 400:
        print(f"ERROR {resp.status_code} : {resp.text}", file=sys.stderr); sys.exit(1)

    print("Igroup creation successful!")
    print("--"*30)
    print(f"{'Igroup Name':25} {'Protocol':10} {'OS-Type':15} ")
    print("--"*30)
    if "records" in resp.json() and resp.json()["num_records"] > 0:
        for record in resp.json()["records"]:
            name = record.get('name', '')
            protocol = record.get('protocol', '')
            os_type = record.get('os_type', '')
            print(f"{name[:]:25} {protocol[:10]:10} {os_type[:15]:15}")
    print("--"*30)

def main():

    ap = argparse.ArgumentParser(description="Create ONTAP igroups")
    ap.add_argument("--svm", required=True, help="SVM name")
    ap.add_argument("--igroup", required=True, help="Igroup Name")
    ap.add_argument("os_type", choices=["linux", "windows", "aix", "hpux", "solarix", "xen", "vmware", "hyperv"], help="OS type")
    ap.add_argument("protocol",  choices=["fcp", "iscsi", "mixed"], help="Protocol property")
    ap.add_argument("--initiator", nargs="*", help="List of initiators to add to the igroup")
    ap.add_argument("--initiator_group", nargs="*", help="List of initiators groups to add to the igroup")


    args = ap.parse_args()

    params = {
        "svm": {"name": args.svm},
        "name": args.igroup,
        "os_type": args.os_type,
        "protocol": args.protocol,
    }

    if args.initiator:
        params.update({"initiators": [{"name": i} for i in args.initiator]})

    if args.initiator_group:
        params.update({"igroups": [{"name": i} for i in args.initiator_group]})

    host, user, pw = load_env()
    headers = auth_header(user, pw)
    base = f"https://{host}/api"

    create_initiators(headers=headers, base=base, params=params, svm=args.svm, initiator=args.initiator, os_type=args.os_type, protocol=args.protocol)

if __name__ == "__main__":
    main()


