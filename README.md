# NetApp ONTAP SAN Tool

A command-line tool for managing NetApp ONTAP SAN resources (LUNs, igroups, and LUN mappings) via the ONTAP REST API.

## Features

- **LUN Management**: Create, list, and delete LUNs
- **Initiator Groups**: Create and manage igroups, add initiators
- **LUN Mappings**: Map LUNs to igroups for host access
- Supports Basic Authentication and OAuth2
- Automatic pagination for large result sets

## Requirements

- Python 3.9+
- NetApp ONTAP 9.10+
- Required packages: `requests`, `python-dotenv`, `urllib3`

## Installation

```bash
pip install requests python-dotenv urllib3
```

## Configuration

Set environment variables in a `.env` file or export them:

```bash
HOST=your-ontap-cluster.example.com
USER=admin
PASSWORD=your-password
# Optional:
ONTAP_OAUTH_TOKEN=your-oauth-token
INSECURE=1  # Skip TLS verification (not recommended for production)
```

## Usage

### LUN Operations

```bash
# Create a LUN
python ontap_san_tool.py lun-create --svm svm1 --volume vol1 --lun lun1 --size 100G --os-type linux

# List LUNs
python ontap_san_tool.py lun-list --svm svm1

# Delete a LUN
python ontap_san_tool.py lun-delete --uuid <lun-uuid>
```

### Initiator Group Operations

```bash
# Create an igroup
python ontap_san_tool.py igroup-create --svm svm1 --name igroup1 linux iscsi

# Add initiators to igroup
python ontap_san_tool.py igroup-add-initiators --igroup-uuid <uuid> --initiator iqn.1998-01.com.vmware:host-1

# List igroups
python ontap_san_tool.py igroup-list
```

### LUN Mapping Operations

```bash
# Create a LUN mapping
python ontap_san_tool.py lunmap-create --svm svm1 --igroup igroup1 --lun-path /vol/vol1/lun1

# List LUN mappings
python ontap_san_tool.py lunmap-list --svm svm1

# Delete a LUN mapping
python ontap_san_tool.py lunmap-delete --lun /vol/vol1/lun1 --igroup igroup1
```

## Authentication

The tool supports two authentication methods:
- **Basic Auth**: Using username and password (default)
- **OAuth2**: Using bearer token (set `ONTAP_OAUTH_TOKEN`)

## License

[Add your license here]