import re, sys


def to_bytes(s: str) -> int:
    """
    Converts a human-readable size string (e.g., 100G, 20M) to bytes.
    """
    m = re.fullmatch(r"\s*(\d+)([KMGTP]?)\s*", s, re.I)
    if not m: raise ValueError("Invalid size format (e.g., 100G, 20M, 4096)")
    n, suf = int(m.group(1)), m.group(2).upper()
    mult = {"":1,"K":1024,"M":1024**2,"G":1024**3,"T":1024**4,"P":1024**5}[suf]
    return n * mult

def from_bytes(n: int) -> str:
    """
    Converts a byte count (int) into a human-readable size string.
    Examples:
        10737418240 -> "10G"
        536870912   -> "512M"
        4096        -> "4K"
        512         -> "512"
    """
    if n is None:
        return ''
    if not isinstance(n, (int, float)):
        raise TypeError("Expected an integer number of bytes")

    units = ['', 'K', 'M', 'G', 'T', 'P']
    for unit in units:
        if abs(n) < 1024 or unit == 'P':
            # Drop decimals if it's an even number (e.g., 512M not 512.0M)
            return f"{int(n):.0f}{unit}" if n.is_integer() else f"{n:.1f}{unit}"
        n /= 1024

    return f"{n:.1f}{unit}".rstrip('0').rstrip('.')

# ----- LUN MAPPING -----
def lunmap_display_summary(records: list) -> None:
    print(f"{'Vserver':15} {'PATH':35} {'UUID':40} {'NODE':15} {'Igroup':15} {'Igroup-UUID':40} {'OS_TYPE':10} {'PROTOCOL':10} {'LUNID':5}")
    print("-" *200)
    
    for record in records:
        name = record.get('svm', {}).get('name', '')
        lun = record.get('lun', {}).get('name', '')
        lunuuid = record.get('lun', {}).get('uuid', '')
        node = record.get('lun', {}).get('node', {}).get('name', '')
        igroup = record.get('igroup', {}).get('name', '')
        igroup_uuid = record.get('igroup', {}).get('uuid', '')
        os_type = record.get('igroup', {}).get('os_type', '')
        protocol = record.get('igroup', {}).get('protocol', '')
        lunid = record.get('logical_unit_number', '')
        print(f"{name:15} {lun:35} {lunuuid:40} {node:15} {igroup:15} {igroup_uuid:40} {os_type:10} {protocol:10} {lunid:3} ")
    print("-" * 200)

def lunmap_create_response_summary(resp: dict) -> None:
    """
    Prints a summary of the LUN mapping creation response.
    """
    record = resp["records"][0]
    name = record.get('svm', {}).get('name', '')
    lun = record.get('lun', {}).get('name', '')
    node = record.get('lun', {}).get('node', {}).get('name', '')
    igroup = record.get('igroup', {}).get('name', '')
    ig_os_type = record.get('igroup', {}).get('os_type', '')
    protocol = record.get('igroup', {}).get('protocol', '')
    lunid = record.get('logical_unit_number', '')

    print("LUN mapping creation successful!")
    print("---"*25)
    print(f"LUN {lun} in {node} mapped to igroup {igroup} on SVM {name} with LUN ID {lunid}.")
    print(f"Igroup OS Type: {ig_os_type},\nProtocol: {protocol}")
    print("---"*25)


# ----- LUNS -----
def lun_create_response_summary(resp: dict) -> None:
    """
    Prints a summary of the LUN creation response.
    """
    size = resp["records"][0].get('space', {}).get('size', '')
    
    record = resp["records"][0]
    lun_path= record.get('name', {})
    lun = record.get('location', {}).get('logical_unit', '')
    uuid = record.get('uuid', 'N/A')
    Volume = record.get('location', {}).get('volume', {}).get('name', '')
    size = from_bytes(size) if size is not None else ''
    os_Type = record.get('os_type', '')
    svm = record.get('svm', {}).get('name', '')

    print("LUN creation successful!")
    print(f" {'LUN':20} {'LUN Path':35}  {'SVM':10} {'UUID':36} {'VOLUME':15} {'SIZE':10} {'OS-Type':10} ")
    print("---"*47)

    print(f"{lun:20} {lun_path:35} {svm:10} {uuid:38} {Volume:15} {size:10} {os_Type:10} ")
    print("---"*47)


def lun_list_summary(records: list) -> None:
    """
    Prints a summary table of LUN records.
    """
    if records:
        print("-" * 120)
        print(f"{'NAME':35} {'UUID':36} {'   STATE':10} {'SVM':10} {'VOL':12} {'SIZE(B)'}")
        print("-" * 120)
        for rec in records:
            name  = rec.get("name", "")
            uuid  = rec.get("uuid", "")
            state = rec.get("status", {}).get("state", "")
            svm   = rec.get("svm", {}).get("name", "")
            vol   = rec.get("location", {}).get("volume", {}).get("name", "")
            sizeb = from_bytes(rec.get("space", {}).get("size", ""))
            print(f"{name[:35]:35} {uuid[:36]:38} {state[:8]:8} {svm[:10]:10} {vol[:12]:12} {sizeb}")
        print("-" * 120)

# ----- IGROUPS -----
def create_igroup_response_summary(resp: dict) -> None:
    print(resp)
    print("Igroup creation successful!")
    print("--" * 30)
    print(f"{'Igroup Name':25} {'Protocol':10} {'OS-Type':15} ")
    print("--" * 30)
    if "records" in resp and resp["num_records"] > 0:
        for record in resp["records"]:
            name = record.get('name', '')
            protocol = record.get('protocol', '')
            os_type = record.get('os_type', '')
            print(f"{name[:]:25} {protocol[:10]:10} {os_type[:15]:15}")
    print("--" * 30)

def igroup_display_summary(records: list) -> None:
    """
    Prints a summary table of LUN mapping records.

    Pretty-print igroup records in a formatted table.
    
    """
    print()
    if len(records) == 0:
        print("*"*51)
        print("*                                                 *")
        print("*   No Igroups found matching the criteria.      *")
        print("*                                                 *")
        print("*"*51)
        sys.exit(0)

    print(f"Retrieved {len(records)} igroups record(s).")

    def pick(d, dotted_key, default=""):
        """Pick nested dict key using dot notation (e.g., svm.name)."""
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
        """Join any of the possible name fields (name/wwpn/iqn) found in item dicts."""
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
        """Format LUN map entries as 'L#:path'."""
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
        """Format parent igroup names as a comma-separated list."""
        if not isinstance(parents, list):
            return "-"
        names = [p.get("name") for p in parents if isinstance(p, dict) and p.get("name")]
        return ", ".join(names) if names else "-"

    def wrap_text(text, width):
        """Wrap long text (e.g., initiator lists) into multiple lines."""
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
        map_lines = wrap_text(maps, 80)
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
