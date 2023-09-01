from oci import config
from oci import identity
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner

import argparse
import json
import os

# Find dynamic groups that have no policies associated with them
# Need to go through every policy in tenancy and look at statements
# Policies come from the other script - oci-policy-analyze-python.py - this script writes out its statements into a JSON-based cache file
# Please run this first so that the cache is populated.

# Lists
dynamic_group_statements = []

# Main Code

# Parse Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")

args = parser.parse_args()
verbose = args.verbose
profile = args.profile
use_instance_principals = args.instanceprincipal

if use_instance_principals:
    print(f"Using Instance Principal Authentication")
    signer = InstancePrincipalsSecurityTokenSigner()
    identity_client = identity.IdentityClient(config={}, signer=signer)
    tenancy_ocid = signer.tenancy_id
    print(f'Using tenancy OCID from Instance Profile: {tenancy_ocid}')
else:
    # Use a profile (must be defined)
    print(f"Using Profile Authentication: {profile}")
    config = config.from_file(profile_name=profile)
    identity_client = identity.IdentityClient(config)
    tenancy_ocid = config["tenancy"]
    print(f'Using tenancy OCID from profile: {tenancy_ocid}')

# Use the cache for policies
print(f'Attempting to load policies from cache')

if os.path.isfile(f'./.policy-dg-cache-{tenancy_ocid}.dat'):
    with open(f'./.policy-dg-cache-{tenancy_ocid}.dat', 'r') as filehandle:
        dynamic_group_statements = json.load(filehandle)
else:
    print(f"No available DG cache.  Please run policy analyzer to generate.")
    exit(1)

# Load DGs
dynamic_groups = []
page = None
while True:
    dynamic_groups_resp = identity_client.list_dynamic_groups(compartment_id=tenancy_ocid, limit=500, page=page)
    dynamic_groups.extend(dynamic_groups_resp.data)
    print(f"Got {len(dynamic_groups_resp.data)} - Next page: {dynamic_groups_resp.next_page}")
    page = dynamic_groups_resp.next_page if dynamic_groups_resp.has_next_page else None
    if not page:
        break

# for i,dg in enumerate(dynamic_groups):
#     print(f'Dyanmic Group {i}: {dg.name}')


# Loop DG
for i,dg in enumerate(dynamic_groups):
    result = list(filter(lambda statement: str(dg.name).casefold() in statement[0].casefold(),dynamic_group_statements))
    if len(result) == 0:
        print(f"Dynamic Group has no statements: {dg.name}: {dg.id}")


