# ATP Scale down script
# Runs in region with instance Principal
# Runs additional region with profile
# Added Multi-threading

# Written by Andrew Gregory
# 2/14/2024 v1

# Generic Imports
import argparse
import logging    # Python Logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import time
import datetime
import json

# OCI Imports
from oci import config
from oci import database
from oci import identity
from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
from oci.database.models import UpdateAutonomousDatabaseDetails
from oci.resource_search import ResourceSearchClient
from oci.resource_search.models import StructuredSearchDetails, ResourceSummary
from oci.exceptions import ServiceError

import oci

# Constants
DEFAULT_SCHEDULE = "0,0,0,0,0,0,0,*,*,*,*,*,*,*,*,*,*,0,0,0,0,0,0,0"

# Helper function
def wait_for_available(dryrun:bool, database_client:database.DatabaseClient, db_id: str, start:bool):

    # Get updated
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_id
    ).data

    if start:
        if db.lifecycle_state == "STOPPED":
            # Start first
            logger.info(f'{"DRYRUN: " if dryrun else ""}Starting Autonomous DB: {db.display_name}')
            if dryrun:
                return
            database_client.start_autonomous_database(db.id)

    if dryrun:
        logger.debug("Not waiting for AVAILABLE")
        return
    # Waiting for AVAILABLE
    get_db_response = database_client.get_autonomous_database(db.id)
    oci.wait_until(database_client, get_db_response, 'lifecycle_state', 'AVAILABLE')

    logger.debug(f"Autonomous DB: {db.display_name} AVAILABLE")

# Threaded function
def database_work(db_id: str):

    # Sleep a sec
    time.sleep(0.5)

    # if True:
    #     return {"no-op": True}
    
    # Get reference
    db = database_client.get_autonomous_database(
        autonomous_database_id=db_id
        ).data
    
    # Return Val
    did_work = {}
    did_work["Detail"] = {"Name": f"{db.display_name}", "OCID": f"{db.id}", "Original CPU": f"{db.compute_model}", "License": f"{db.license_model}"}

    # Now try it
    try:
        # Show before
        logger.info(f"----{db_id}----Examine ({db.display_name})----------")
        logger.info(f'CPU Model: {db.compute_model} Dedicated: {db.is_dedicated} DG Role: {db.role}')
        logger.info(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs}")
        logger.info(f"License Model: {db.license_model} Edition: {db.database_edition} ")
        logger.info(f"----{db_id}----Start ({db.display_name})----------")

        if db.is_dedicated:
            logger.debug("Don't operate on dedicated")
            did_work["No-op"] = {"Dedicated": True}
            return did_work

        if db.role == "STANDBY":
            logger.debug("Don't operate on anything but primary")
            did_work["No-op"] = {"Role": f"{db.role}"}
            return did_work

        if db.is_free_tier:
            logger.debug("Don't operate on free ATP")
            did_work["No-op"] = {"Free": f"{db.is_free_tier}"}
            return did_work

        if db.lifecycle_state == "UNAVAILABLE":
            logger.debug("Don't operate on UNAVAILABLE DBs")
            did_work["No-op"] = {"Lifecycle": f"{db.lifecycle_state}"}

            return did_work

        # Compute Model - to ECPU
        logger.debug(f'CPU Model: {db.compute_model} Count: {db.compute_count if db.compute_model == "OCPU" else db.compute_count}')
        if db.compute_model == "OCPU":

            # Actual Conversion
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Converting ECPU Autonomous DB: {db.display_name}')

            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        backup_retention_period_in_days=15,
                        compute_model="ECPU"
                        )
                )
            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

            did_work["ECPU"] = {"convert": True}

            logger.info(f'{"DRYRUN: " if dryrun else ""}Converted ECPU Autonomous DB: {db.display_name}')

        # Storage - scale to GB
        logger.debug(f"Storage Name: {db.display_name} DB TB: {db.data_storage_size_in_tbs} Actual: {db.actual_used_data_storage_size_in_tbs} Allocated: {db.allocated_storage_size_in_tbs}")
        if not db.data_storage_size_in_tbs:
            logger.debug(f"Storage in GB Model - no action")
        else:
            # Figure out storage
            # Existing TB * 1024 (conversion) * 2 (allow extra)
            new_storage_gb = int(db.allocated_storage_size_in_tbs * 1024 * 2)
            new_storage_gb = 20 if new_storage_gb < 20 else new_storage_gb
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Scale Storage DB: {db.display_name} from {db.data_storage_size_in_tbs} TB to {new_storage_gb} GB (auto-scale)')

            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            # Actual scaling (2 ECPU, auto-scale, Storage auto-scale)
            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        is_auto_scaling_for_storage_enabled=True,
                        data_storage_size_in_gbs=new_storage_gb,
                        compute_count=2.0,
                        is_auto_scaling_enabled=True

                    )
                )
            did_work["Scale"] = {"convert": True, "GB": new_storage_gb}

            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Scale Storage DB: {db.display_name} completed')

        # License Model - BYOL and SE
        if db.license_model == "LICENSE_INCLUDED":
            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Update License DB: {db.display_name} to BYOL / SE')

            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        license_model="BRING_YOUR_OWN_LICENSE",
                        database_edition="STANDARD_EDITION"
                    )
                )

            did_work["License"] = {"BYOL": True, "SE": True}

            # Waiting for AVAILABLE
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Updated License DB: {db.display_name} to BYOL / SE')

        # Tagging - require Schedule Tag

        current_tags = db.defined_tags
        if "Schedule" in current_tags:
            logger.debug(f'Current Schedule: {current_tags["Schedule"]}')
            # Check tag for all 1
            schedule_tag = current_tags["Schedule"]
            if 'AnyDay' in schedule_tag:
                logger.debug(f'AnyDay tag: {schedule_tag["AnyDay"]}')
                if "0" in schedule_tag["AnyDay"]:
                    logger.debug("Compliant - will stop")
                else:
                    logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Not compliant({schedule_tag["AnyDay"]}) - will not stop - fixing')
                    current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}

                    # Start and wait if needed
                    wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

                    if not dryrun:
                        database_client.update_autonomous_database(
                            autonomous_database_id=db.id,
                            update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                                defined_tags=current_tags
                            )
                        )
                    wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)
                    did_work["Tag"] = {"default": True}

        else:
            # Add default tag to defined tags
            current_tags["Schedule"] = {"AnyDay" : DEFAULT_SCHEDULE}

            logger.info(f'>>>{"DRYRUN: " if dryrun else ""}Updating Tags DB: {db.display_name} to Schedule / AnyDay Default')

            # Start and wait if needed
            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=True)

            if not dryrun:
                database_client.update_autonomous_database(
                    autonomous_database_id=db.id,
                    update_autonomous_database_details=UpdateAutonomousDatabaseDetails(
                        defined_tags=current_tags
                    )
                )
            did_work["Tag"] = {"default": True}

            wait_for_available(dryrun=dryrun, database_client=database_client, db_id=db.id, start=False)

            logger.info(f'{"DRYRUN: " if dryrun else ""}Updated Tags DB: {db.display_name} to Schedule / AnyDay Default')

        logger.info(f"----{db_id}----Complete ({db.display_name})----------")
    except ServiceError as exc:
        logger.error(f"Failed to complete action for DB: {db.display_name} \nReason: {exc}")
        did_work["Error"] = {"Exception": exc.message}
    
    return did_work    
    # End main function

# Only if called in Main
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    parser.add_argument("-pr", "--profile", help="Config Profile, named", default="DEFAULT")
    parser.add_argument("-ip", "--instanceprincipal", help="Use Instance Principal Auth - negates --profile", action="store_true")
    parser.add_argument("--dryrun", help="Dry Run - no action", action="store_true")
    parser.add_argument("-t", "--threads", help="Concurrent Threads (def=5)", type=int, default=5)

    args = parser.parse_args()
    verbose = args.verbose
    profile = args.profile
    use_instance_principals = args.instanceprincipal
    dryrun = args.dryrun
    threads = args.threads

    # Logging Setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(threadName)s] %(levelname)s %(message)s')
    logger = logging.getLogger('oci-scale-atp')
    if verbose:
        logger.setLevel(logging.DEBUG)

    logger.info(f'Using profile {profile} with Logging level {"DEBUG" if verbose else "INFO"}')

    # Client creation
    if use_instance_principals:
        print(f"Using Instance Principal Authentication")
        signer = InstancePrincipalsSecurityTokenSigner()
        database_client = database.DatabaseClient(config={}, signer=signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
        search_client = ResourceSearchClient(config={}, signer=signer)
    else:
        # Use a profile (must be defined)
        print(f"Using Profile Authentication: {profile}")
        config = config.from_file(profile_name=profile)

        # Create the OCI Client to use
        database_client = database.DatabaseClient(config, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
        search_client = ResourceSearchClient(config)

    # Main routine
    # Grab all ATP Serverless
    # Loop through
    # Ensure:
    # 1) Updated to ECPU
    # 2) License is BYOL / Standard
    # 3) Storage is scaled down
    # 4) Tags for AnyDay are there and not 1,1,1


    # Get ATP (Search)
    atp_db = search_client.search_resources(
        search_details=StructuredSearchDetails(
            type = "Structured",
            query='query autonomousdatabase resources return allAdditionalFields where (workloadType="ATP")'
        ),
        limit=1000
    ).data

    # Build a list of IDs
    db_ocids = []
    for i,db_it in enumerate(atp_db.items, start=1):
        db_ocids.append(db_it.identifier)

    with ThreadPoolExecutor(max_workers = threads) as executor:
        results = executor.map(database_work, db_ocids)
        logger.info(f"Kicked off {threads} threads for parallel execution - adjust as necessary")
    
    # Write to file
    datestring = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
    filename = f'oci-atp-scale-down-{datestring}.json'
    with open(filename,"w") as outfile:

        for result in results:
            logger.info(f"Result: {result}")
            outfile.write(json.dumps(result, indent=2))

    logging.info(f"Script complete - wrote JSON to {filename}.")