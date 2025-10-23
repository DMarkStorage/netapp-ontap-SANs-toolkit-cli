#!/usr/bin/env python3
"""
ontap_san_tool.py — NetApp ONTAP SAN (LUN maps & igroups) CLI
This script provides a command-line interface to manage LUN mappings and initiator groups (igroups)
on a NetApp ONTAP storage system via its REST API.
It supports creating, listing, and deleting LUNs, igroups, and LUN mappings.
It uses environment variables for connection details and supports both basic auth and OAuth2.

Environment Variables:
    HOST:            ONTAP cluster or SVM management LIF (IP or FQDN)
    USER:            Username for authentication
    PASSWORD:        Password for authentication
    ONTAP_OAUTH_TOKEN: Optional OAuth2 bearer token for authentication
    INSECURE:       If set, disables TLS certificate verification
    
Usage:
    python ontap_san_tool.py <command> [options]
Commands:
    lun-create         Create a new LUN     
    lun-list           List existing LUNs
    lun-delete         Delete a LUN by UUID
    igroup-create      Create a new initiator group (igroup)
    igroup-list        List existing igroups
    igroup-add-initiators  Add initiators to an existing igroup
    lunmap-create      Create a LUN-to-igroup mapping
    lunmap-list        List existing LUN mappings
    lunmap-delete      Delete a LUN mapping


Docs:
- LUN maps: POST/GET/DELETE /api/protocols/san/lun-maps
- igroups:  POST /api/protocols/san/igroups, POST /api/protocols/san/igroups/{uuid}/initiators
- Auth:     HTTP Basic (or OAuth2 if configured)

Tested with Python 3.9+ and ONTAP 9.10+.
"""

import argparse
import base64
import json
import os
import requests
import sys
from typing import Dict, List, Optional
from dotenv import load_dotenv
import urllib3
import utils.utils as utils

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------- Utilities ----------

def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")

class OntapClient:
    def __init__(self, host: str, username: str, password: str,
                 verify_tls: bool = False, oauth_token: Optional[str] = None,
                 timeout: int = 30):
        self.base = f"https://{host}/api"
        self.timeout = timeout
        self.verify = verify_tls
        self.session = requests.Session()

        if oauth_token:
            self.session.headers.update({"Authorization": f"Bearer {oauth_token}"})
        else:
            auth = base64.b64encode(f"{username}:{password}".encode()).decode()
            self.session.headers.update({"Authorization": f"Basic {auth}"})
        self.session.headers.update({"accept": "application/json",
                                     "content-type": "application/json"})

    # ---- Generic helpers ----
    def _req(self, method: str, path: str, params=None, data=None) -> Dict:
        url = f"{self.base}{path}"
        r = self.session.request(method, url, params=params, data=data,
                                 timeout=self.timeout, verify=self.verify)
        if r.status_code >= 400:
            try:
                details = r.json()
            except Exception:
                details = r.text
            raise RuntimeError(f"{method} {path} failed: {r.status_code} {details}")
        if r.text.strip():
            return r.json()
        return {}

    def _paginate(self, path: str, params=None) -> List[Dict]:
        items = []
        query = dict(params or {})
        while True:
            resp = self._req("GET", path, params=query)
            records = resp.get("records", [])
            items.extend(records)
            next_link = resp.get("_links", {}).get("next", {}).get("href")
            if not next_link:
                break
            # next_link is usually a path with existing query
            # follow it as-is:
            path_only = next_link.split("/api", 1)[1]
            path_seg, _, qs = path_only.partition("?")
            path = f"/{path_seg}"
            new_params = {}
            if qs:
                for kv in qs.split("&"):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        new_params[k] = v
            query = new_params
        return items

    # ---- lun operations ----
    def lun_create(self, svm_name: str, volume_name: str, lun_name: str,
                   size_bytes: str, os_type: str = "linux") -> Dict:
        body = {
            "name": f"/vol/{volume_name}/{lun_name}",
            "os_type": os_type,
            "svm": {"name": svm_name},
            "space": {"size": utils.to_bytes(size_bytes)},
            }
        return self._req("POST", "/storage/luns?return_records=true", data=json.dumps(body))

    def lun_list(self, svm: Optional[str], volume: Optional[str], lun: Optional[str], fields: Optional[str]) -> List[Dict]:
        params = {}
        DEFAULT_FIELDS = "name,uuid,svm.name,status.state,location.volume.name,space.size"
        if svm:
            params["svm.name"] = svm
        if volume:
            params["location.volume.name"] = volume
        if lun:
            params["name"] = lun
        if not fields:
            params["fields"] = DEFAULT_FIELDS
        else:
            params["fields"] = fields
        return self._paginate("/storage/luns", params=params)

    def lun_delete_by_uuid(self, lun: str) -> None:
        self._req("DELETE", f"/storage/luns?uuid={lun}")

    # ---- igroup operations ----
    def igroup_create(self, svm_name: str, igroup_name: str, os_type: str = "linux", protocol: str = "mixed", initiators: dict = [], i_group: dict = []) -> Dict:
        body = {
                "name": igroup_name,
                "svm": {"name": svm_name},
                "os_type": os_type,
                "protocol": protocol,
                }
        if initiators:
            body.update({"initiators": [{"name": i} for i in initiators]})

        if i_group:
            body.update({"igroups": [{"name": i} for i in i_group]})

        return self._req("POST", "/protocols/san/igroups?return_records=true", data=json.dumps(body))

    def igroup_list(self, query: Optional[str] = None, fields: Optional[str] = None) -> List[Dict]:
        params = {}
        DEFAULT_FIELDS = "*,igroups,parent_igroups.name,lun_maps,os_type"
        if query:
            field, value = query
            params[field] = value
        params["fields"] = fields or DEFAULT_FIELDS
        return self._paginate("/protocols/san/igroups", params=params)

    def igroup_add_initiators(self, igroup: str, initiators: List[str]) -> Dict:
        body = {"records": [{"name": i} for i in initiators]}
        return self._req("POST",
                         f"/protocols/san/igroups/{igroup}/initiators",
                         data=json.dumps(body))

    # ---- LUN map operations ----
    def lunmap_create(self, svm_name: str, igroup_name: str, lun_path: str) -> Dict:
        """
        lun_path should look like: /vol/<volume_name>/<lun_name>
        """
        body = {
            "svm": {"name": svm_name},
            "igroup": {"name": igroup_name},
            "lun": {"name": lun_path}
        }
        return self._req("POST", "/protocols/san/lun-maps?return_records=true", data=json.dumps(body))

    def lunmap_list(self, svm_name: Optional[str] = None,
                    igroup_name: Optional[str] = None,
                    lun_path: Optional[str] = None) -> List[Dict]:
        params = {}
        if svm_name:
            params["svm.name"] = svm_name
        if igroup_name:
            params["igroup.name"] = igroup_name
        if lun_path:
            params["lun.name"] = lun_path

        # if params:
        params.setdefault(
            "fields",
            "svm.name,lun.name,lun.node.name,igroup.name,igroup.os_type,igroup.protocol,logical_unit_number"
        )
        return self._paginate("/protocols/san/lun-maps", params=params)

    def lunmap_delete(self, lun: str, igroup: str) -> None:
        params = {
            "lun.name": lun,
            "igroup.name": igroup
        }
        self._req("DELETE", f"/protocols/san/lun-maps", params=params)


# ---------- CLI ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="NetApp ONTAP SAN (LUN maps & igroups) tool")
    p.add_argument("--host", default=os.getenv("HOST"), help="Cluster/SVM management LIF (ip or fqdn)")
    p.add_argument("--user", default=os.getenv("USER"), help="Username (or set ONTAP_USER)")
    p.add_argument("--password", default=os.getenv("PASSWORD"),
                   help="Password (or set ONTAP_PASS)")
    p.add_argument("--oauth-token", default=os.getenv("ONTAP_OAUTH_TOKEN"),
                   help="OAuth2 bearer (optional; overrides basic auth)")
    p.add_argument("--insecure", action="store_true", help="Skip TLS verification")
    sub = p.add_subparsers(dest="cmd", required=True)

    # lun create
    ln = sub.add_parser("lun-create", help="Create a LUN")
    ln.add_argument("--svm", required=True, help="SVM name")
    ln.add_argument("--volume", required=True, help="Volume name (existing)")
    ln.add_argument("--lun", required=True, help="LUN name to create")
    ln.add_argument("--size", required=True, help="Size (e.g., 100G, 20M, 4096)")
    ln.add_argument("--os-type", default="linux", help="linux|windows|vmware|aix|…")
    ln.add_argument("--space-reserve", action="store_true", help="Enable space reservation")

    # lun list
    ll = sub.add_parser("lun-list", help="List LUNs (optionally filtered)")
    ll.add_argument("--svm", help="Filter by SVM name (svm.name)")
    ll.add_argument("--volume", help="Filter by Volume name (location.volume.name)")
    ll.add_argument("--lun", help="Filter by LUN name (exact path /vol/<vol>/<lun>)")
    ll.add_argument("--fields", help="Comma-separated field list to request via fields=... "
                                     "(e.g., name,uuid,svm.name,status.state,space.size)")

    #  lun delete
    ld = sub.add_parser("lun-delete", help="DELETE ONTAP LUNs")
    ld.add_argument("--uuid", required=True, help="LUN UUID to delete")


    # igroup create
    igc = sub.add_parser("igroup-create", help="Create an igroup")
    igc.add_argument("--svm", required=True, help="SVM name")
    igc.add_argument("--name", required=True, help="Igroup Name")
    igc.add_argument("os_type", default="linux", choices=["linux", "windows", "aix", "hpux", "solarix", "xen", "vmware", "hyperv"], help="OS type")
    igc.add_argument("protocol",  choices=["fcp", "iscsi", "mixed"], help="Protocol property")
    igc.add_argument("--initiator", nargs="*", help="List of initiators to add to the igroup")
    igc.add_argument("--i_group", nargs="*", help="List of initiator groups to add to the igroup")

    # igroup list
    igl = sub.add_parser("igroup-list", help="List ONTAP Initiator groups (optionally filtered)")
    igl.add_argument("--query_filter", nargs=2, help="Filter by field and value (e.g., --query_filter os_type linux)")
    igl.add_argument("--fields", help="Comma-separated field list to request via fields=... (e.g., igroups,parent_igroups,lun_maps)")

    # igroup add-initiators
    igi = sub.add_parser("igroup-add-initiators", help="Add initiators (IQN/WWPN) to an igroup")
    igi.add_argument("--igroup-uuid", required=True)
    igi.add_argument("--initiator", required=True, nargs="+",
                     help="One or more initiator names (e.g., iqn.1998-01.com.vmware:host-1 or 20:00:00:25:B5:11:22:33)")

    # lun-map create
    lmc = sub.add_parser("lunmap-create", help="Create LUN map (LUN ↔ igroup)")
    lmc.add_argument("--svm", required=True, help="SVM name")
    lmc.add_argument("--igroup", required=True, help="Igroup name")
    lmc.add_argument("--lun-path", required=True, help="e.g. /vol/vol1/lun1")

    # lun-map list
    lml = sub.add_parser("lunmap-list", help="List LUN maps")
    lml.add_argument("--svm", help="Filter by SVM name")
    lml.add_argument("--igroup", help="Filter by igroup name")
    lml.add_argument("--lun-path",  help="Filter by LUN path name (e.g. /vol/vol1/lun1)")

    # lun-map delete
    lmd = sub.add_parser("lunmap-delete", help="Delete a LUN map by UUID")
    lmd.add_argument("--lun", required=True, help="Enter the LUN path name of specific LUN")
    lmd.add_argument("--igroup", required=True, help="Enter the igroup name")

    return p

def main():
    args = build_parser().parse_args()

    client = OntapClient(
        host=args.host or "",
        username=args.user or "",
        password=args.password or "",
        oauth_token=args.oauth_token,
        verify_tls= args.insecure
    )

    try:

        if args.cmd == "igroup-create":
            resp = client.igroup_create(args.svm, args.name, args.os_type, args.protocol, args.initiator, args.i_group)
            utils.create_igroup_response_summary(resp)

        elif args.cmd == "igroup-list":
            recs = client.igroup_list(args.query_filter, args.fields)
            utils.igroup_display_summary(recs)

        elif args.cmd == "igroup-add-initiators":
            resp = client.igroup_add_initiators(args.igroup, args.initiator)
            print(json.dumps(resp, indent=2))

        elif args.cmd == "lunmap-create":
            resp = client.lunmap_create(args.svm, args.igroup, args.lun_path)
            utils.lunmap_create_response_summary(resp)

        elif args.cmd == "lunmap-list":
            recs = client.lunmap_list(args.svm, args.igroup, args.lun_path)
            utils.lunmap_display_summary(recs)
            # print(json.dumps(recs, indent=2))

        elif args.cmd == "lunmap-delete":
            client.lunmap_delete(args.lun, args.igroup)
            print(json.dumps({"deleted": f"{args.lun} map to {args.igroup}"}, indent=2))

        elif args.cmd == "lun-create":
            resp = client.lun_create(args.svm, args.volume, args.lun,
                                     args.size, args.os_type)
            utils.lun_create_response_summary(resp)
            # print(json.dumps(resp, indent=2))
        
        elif args.cmd == "lun-list":
            records = client.lun_list(args.svm, args.volume, args.lun,
                                     args.fields)
            utils.lun_list_summary(records)

        elif args.cmd == "lun-delete":
            client.lun_delete_by_uuid(args.uuid)
            print(json.dumps({"deleted": args.uuid}, indent=2))

        else:
            
            print(args.cmd + " not implemented yet.", file=sys.stderr)
            sys.exit(1)


    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":

    load_dotenv()
    main()
