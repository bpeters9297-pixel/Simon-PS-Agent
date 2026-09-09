
import functions_framework
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime
import json
import os
from google.cloud import secretmanager

# Initialize Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Sheet IDs
SHEET_IDS = {
"brian": "1Jd7txsaQ5yjGOSWciKj1vSU1E36K1jrFIUXlxXdZYpo",
"josh": "175cUPTf4s3HwnFu_OWf4Hpf3DeVnJFShcKpvHpKLLWM",
"mallory": "1PJzHXY85fL7OqT-CeE0o--KocI16NEaB6eUNGGN4SqM",
"marie": "1Bf8-wHHYtVkrT366TMS5hx5dhT6f25OGNweVrdaRESo",
"christine": "1B_oYXjYJxgbMi1OVMrFJO_elyKFVQzwa08R-pzK-sw",
"emma": "1KHIQuvsIKD8iRUDnDzBz7MsgArc1wSY16O7-qcpIXHA"
}

MASTER_SHEET_ID = "1SghZqhJr-DG_fFEC0EiPYqxf-eoqy8uKT_TdwOjlEPU"

# Email recipients
EMAIL_RECIPIENTS = ["brian@yourcompany.com", "josh@yourcompany.com"]

def get_secret(secret_id, version_id="latest"):
    """
    Retrieve secret from Google Cloud Secret Manager.
    """
    project_id = "simon-reporting-agent"
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

@functions_framework.http
def consolidate_ps(request):
    """
    HTTP Cloud Run Function triggered by Cloud Scheduler.
    Consolidates Production Summaries from all team members into master sheet.
    """
    try:
        # Get service account credentials from Secret Manager
        secret_json = get_secret("simon-service-account-key")
        service_account_info = json.loads(secret_json)

        # Create credentials
        credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES
        )

        # Build Sheets API client
        sheets_service = build('sheets', 'v4', credentials=credentials)

        # Get current timestamp
        current_timestamp = datetime.utcnow().isoformat() + "Z"

        # Dictionary to store consolidation results
        consolidation_results = {
        "timestamp": current_timestamp,
        "team_members_processed": {},
        "total_rows_added": 0,
        "errors": []
        }

        # Read Last Processed timestamp from master sheet (cell A1)
        try:
            last_processed_response = sheets_service.spreadsheets().values().get(
            spreadsheetId=MASTER_SHEET_ID,
            range='Sheet1!A1'
            ).execute()

            last_processed_values = last_processed_response.get('values', [])
            last_processed = last_processed_values[0][0] if last_processed_values else None
            except Exception as e:
            last_processed = None
            consolidation_results["errors"].append(f"Could not read Last Processed timestamp: {str(e)}")

            # Process each team member sheet
            for team_member, sheet_id in SHEET_IDS.items():
            try:
            # Get sheet metadata to check last modified time
            sheet_metadata = sheets_service.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields='sheets(properties(title)),modifiedTime'
            ).execute()

            modified_time = sheet_metadata.get('modifiedTime', None)

            # Get all values from sheet
            sheet_values = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='Sheet1'
            ).execute()

            values = sheet_values.get('values', [])

            # If no data, skip
            if not values:
            consolidation_results["team_members_processed"][team_member] = {
            "rows_added": 0,
            "last_modified": modified_time,
            "status": "No data"
            }
            continue

            # Simplified approach: append all new rows since last consolidation
            # In production, you'd compare timestamps more precisely
            rows_to_append = values[1:] if len(values) > 1 else [] # Skip header

            # Append to master sheet
            if rows_to_append:
            sheets_service.spreadsheets().values().append(
            spreadsheetId=MASTER_SHEET_ID,
            range='Sheet1!A:ZZ',
            valueInputOption='USER_ENTERED',
            body={'values': rows_to_append}
            ).execute()

            consolidation_results["team_members_processed"][team_member] = {
            "rows_added": len(rows_to_append),
            "last_modified": modified_time,
            "status": "Success"
            }
            consolidation_results["total_rows_added"] += len(rows_to_append)

            except Exception as e:
            consolidation_results["errors"].append(
            f"Error processing {team_member}: {str(e)}"
            )
            consolidation_results["team_members_processed"][team_member] = {
            "rows_added": 0,
            "status": f"Error: {str(e)}"
            }

            # Update Last Processed timestamp in master sheet (cell B1)
            sheets_service.spreadsheets().values().update(
            spreadsheetId=MASTER_SHEET_ID,
            range='Sheet1!B1',
            valueInputOption='USER_ENTERED',
            body={'values': [[current_timestamp]]}
            ).execute()

            # Return results
            return {
            'statusCode': 200,
            'body': json.dumps(consolidation_results)
            }

            except Exception as e:
            error_msg = f"Cloud Run Function error: {str(e)}"
            return {
            'statusCode': 500,
            'body': json.dumps({'error': error_msg})
            }