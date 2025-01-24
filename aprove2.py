import requests
import time
import logging

# GitLab personal access token with appropriate permissions
GITLAB_API_TOKEN = "secret"

# Base URL for GitLab API
BASE_URL = "https://gitlab.com/api/v4"

# Setup logging
logging.basicConfig(
    filename="merge_requests.log",  # Log file location
    level=logging.INFO,  # Log level
    format="%(asctime)s - %(levelname)s - %(message)s"  # Log format
)


# Define project groups
PROJECT_IDS_Images = [
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-mobi-image",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-dbcopy-image",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-module-image",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-system-image",
    "diemobiliar/it/dmi/datafactory/dmi-datafactory-base-image",
    "diemobiliar/swe/cdb/accessibility/cdb-accessibility-dbhawk-image",
    "diemobiliar/swe/cdb/accessibility/cdb-accessibility-dbhawkdb-image",
]

PROJECT_IDS_managementscripts = [
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-dbcopy-paclib",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-managementscripts-iaclib",
    "diemobiliar/it/dmi/datafactory/dmi-datafactory-iac-paclib",
]

PROJECT_IDS_sqlserver = [
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-sqlserver-iaclib",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-sqlserver-noaks-ownlaw-iaclib",
]

PROJECT_IDS_habcdb = [
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-habcdb-iaclib",
]

PROJECT_IDS_depency_free = [
    "diemobiliar/swe/cdb/cdb-application-aks-iac",
    "diemobiliar/swe/cdb/accessibility/cdb-accessibility-doc",
    "diemobiliar/swe/cdb/accessibility/cdb-accessibility-pevnet-iac/-/merge_requests",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-alerts-iac",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-doc",
    "diemobiliar/swe/cdb/mongodb/cdb-mongodb-platform-iac",
    "diemobiliar/swe/cdb/sit/cdb-sit-testing-service",
    "diemobiliar/swe/cdb/sit/cdb-sit-wiremock-iac",
    "diemobiliar/it/dmi/dmi-application-aks-iac",
    "diemobiliar/it/dmi/datafactory/dmi-datafactory-iac",
    "diemobiliar/it/dmi/datafactory/dmi-datafactory-doc",
    "diemobiliar/it/dmi/datafactory/dmi-datafactory-management-iac",
    "diemobiliar/it/dmi/datafactory/dmi-datafactory-renovate-job/-/merge_requests",
    "diemobiliar/it/dmi/testdatenmigration/dmi-testdatenmigration-jes-service",
    "diemobiliar/teams/dbat/dbat-renovatebot-job",
]

PROJECT_IDS_paclibs_depend = [
    "diemobiliar/swe/cdb/accessibility/cdb-accessibility-dbhawk-iac",
    "diemobiliar/swe/cdb/accessibility/cdb-accessibility-management-fn",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-aadpermittor-fn",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-management-fn",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-management-iac",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-mgmtapp-service",
    "diemobiliar/swe/cdb/backup/cdb-backup-2ndlevelbackup-iac",
    "diemobiliar/it/dmi/datafactory/dmi-datafactory-template-adfjob",
    "diemobiliar/it/dmi/testdatenmigration/dmi-testdatenmigration-adfjob",
]

PROJECT_IDS_sqlserver_depend = [
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-config-small-asql-iaclib",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-dbcopy-iac",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-dbexample-iac",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-sqldatabase-iaclib",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-sqldatabase-serverless-iaclib",
    "diemobiliar/swe/cdb/azuresql/cdb-azuresql-testapp-service",
]

HEADERS = {"Private-Token": GITLAB_API_TOKEN}


def get_latest_pipeline_status(project_id):
    """Fetch the latest pipeline status for the given project."""
    url = f"{BASE_URL}/projects/{requests.utils.quote(project_id, safe='')}/pipelines"
    response = requests.get(url, headers=HEADERS, params={"per_page": 1})
    response.raise_for_status()
    pipelines = response.json()
    if pipelines:
        return pipelines[0]["status"]
    return None


def check_pipelines_status(project_ids):
    """Check the statuses of pipelines for the given projects."""
    failed_projects = []
    for project_id in project_ids:
        try:
            status = get_latest_pipeline_status(project_id)
            print(f"Pipeline status for project {project_id}: {status}")
            if status not in ["success", "warning"]:  # Consider warning as an acceptable state
                failed_projects.append((project_id, status))
        except requests.exceptions.RequestException as e:
            print(f"Error fetching pipeline status for project {project_id}: {e}")
            failed_projects.append((project_id, "error"))
    
    return failed_projects  # Return a list of projects with non-successful pipelines



def wait_for_successful_pipelines(project_ids, check_interval=60):
    """Wait until all pipelines in the group are successful."""
    while True:
        failed_projects = check_pipelines_status(project_ids)
        if not failed_projects:
            print("All pipelines are successful. Proceeding...")
            break
        else:
            print("\nThe following projects do not have successful pipelines:")
            for project_id, status in failed_projects:
                print(f" - {project_id}: {status}")
            print(f"Retrying in {check_interval} seconds...\n")
            time.sleep(check_interval)


def get_merge_requests(project_id):
    """Fetch open merge requests for the given project."""
    url = f"{BASE_URL}/projects/{requests.utils.quote(project_id, safe='')}/merge_requests"
    params = {"state": "opened"}
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def approve_merge_request(project_id, merge_request_iid):
    """Approve a merge request."""
    url = f"{BASE_URL}/projects/{requests.utils.quote(project_id, safe='')}/merge_requests/{merge_request_iid}/approve"
    response = requests.post(url, headers=HEADERS)
    response.raise_for_status()
    print(f"Approved MR IID: {merge_request_iid} in project {project_id}")


def merge_merge_request(project_id, merge_request_iid):
    """Merge a merge request."""
    url = f"{BASE_URL}/projects/{requests.utils.quote(project_id, safe='')}/merge_requests/{merge_request_iid}/merge"
    response = requests.put(url, headers=HEADERS)
    response.raise_for_status()
    print(f"Merged MR IID: {merge_request_iid} in project {project_id}")


def process_project(project_id):
    """Process all open merge requests for a single project."""
    processed_mrs = []  # Store processed MR numbers
    try:
        # Fetch all open merge requests
        merge_requests = get_merge_requests(project_id)

        if not merge_requests:
            print(f"No open merge requests found for project {project_id}.")
            logging.info(f"No open merge requests found for project {project_id}.")
            return

        # Log project ID and corresponding MR IDs
        print(f"Project {project_id} has the following open merge requests:")
        logging.info(f"Project {project_id} has the following open merge requests:")
        for mr in merge_requests:
            print(f" - Merge Request ID: {mr['iid']}")
            logging.info(f" - Merge Request ID: {mr['iid']}")

        for mr in merge_requests:
            mr_iid = mr["iid"]
            # Log the MR before processing
            print(f"Processing MR IID: {mr_iid} in project {project_id}")
            logging.info(f"Processing MR IID: {mr_iid} in project {project_id}")

            # Only process "renovate" MRs
            if "renovate" in mr["title"].lower():
                # Approve the merge request
                approve_merge_request(project_id, mr_iid)

                # Merge the merge request
                merge_merge_request(project_id, mr_iid)

                # Add to the processed list
                processed_mrs.append(mr_iid)

    except requests.exceptions.RequestException as e:
        logging.error(f"An error occurred for project {project_id}: {e}")

    # Log processed MR numbers at the end
    if processed_mrs:
        logging.info(f"Processed MRs for project {project_id}: {', '.join(map(str, processed_mrs))}")
    else:
        logging.info(f"No MRs processed for project {project_id}.")



def process_project_group(group_name, project_ids):
    """Process a group of projects: Handle MRs first, then check pipelines."""
    print(f"\n--- Processing Group: {group_name} ---")

    # Process each project in the group
    for project_id in project_ids:
        
        
        # Process the project if the user agrees
        print(f"Processing project: {project_id}")
        process_project(project_id)

    # After processing all projects, check if pipelines are successful
    print(f"\nWaiting for pipelines in '{group_name}' to complete...")
    wait_for_successful_pipelines(project_ids)

    input(f"Press Enter to continue to the next group ({group_name})...\n")



def main():
    project_groups = {
        "Images": PROJECT_IDS_Images,
        "Management Scripts": PROJECT_IDS_managementscripts,
        "SQL Server": PROJECT_IDS_sqlserver,
        "HABCDB": PROJECT_IDS_habcdb,
        "Dependency-Free": PROJECT_IDS_depency_free,
        "PACLibs Depend": PROJECT_IDS_paclibs_depend,
        "SQL Server Depend": PROJECT_IDS_sqlserver_depend,
    }
    for group_name, project_ids in project_groups.items():
        process_project_group(group_name, project_ids)


if __name__ == "__main__":
    main()
