import functions_framework
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import json
from google.cloud import secretmanager

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SHEET_IDS = {
"brian": "1Jd7txsaQ5yjGOSWciKj1vSU1E36K1jrFIUXlxXdZYpo",
"josh": "175cUPTf4s3HwnFu_OWf4Hpf3DeVnJFShcKpvHpKLLWM",
"mallory": "1PJzHXY85fL7OqT-CeE0o--KocI16NEaB6eUNGGN4SqM",
"marie": "1Bf8-wHHYtVkrT366TMS5hx5dhT6f25OGNweVrdaRESo",
"christine": "1B_oYXjYJxgbMi1OVMrFJO_elyKFVQzwa08R-pzK-sw",
"emma": "1KHIQuvsIKD8iRUDnDzBz7MsgArc1wSY16O7-qcpIXHA"
}
MASTER_SHEET_ID = "1SghZqhJr-DG_fFEC0EiPYqxf-eoqy8uKT_TdwOjlEPU"

def get_secret(secret_id, version_id="latest"):
project_id = "simon-reporting-agent"
client = secretmanager.SecretManagerServiceClient()
name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
response = client.access_secret_version(request={"name": name})
return response.payload.data.decode("UTF-8")

@functions_framework.http
def consolidate_ps(request):
try:
secret_json = get_secret("simon-service-account-key")
service_account_info = json.loads(secret_json)
credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=credentials)
current_timestamp = datetime.utcnow().isoformat() + "Z"
consolidation_results = {"timestamp": current_timestamp, "team_members_processed": {}, "total_rows_added": 0, "errors": []}
try:
last_processed_response = sheets_service.spreadsheets().values().get(spreadsheetId=MASTER_SHEET_ID, range='Sheet1!A1').execute()
last_processed_values = last_processed_response.get('values', [])
last_processed = last_processed_values[0][0] if last_processed_values else None
except Exception as e:
last_processed = None
consolidation_results["errors"].append(f"Could not read Last Processed timestamp: {str(e)}")
for team_member, sheet_id in SHEET_IDS.items():
try:
sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=sheet_id, fields='sheets(properties(title)),modifiedTime').execute()
modified_time = sheet_metadata.get('modifiedTime', None)
sheet_values = sheets_service.spreadsheets().values().get(spreadsheetId=sheet_id, range='Sheet1').execute()
values = sheet_values.get('values', [])
if not values:
consolidation_results["team_members_processed"][team_member] = {"rows_added": 0, "last_modified": modified_time, "status": "No data"}
continue
rows_to_append = values[1:] if len(values) > 1 else []
if rows_to_append:
sheets_service.spreadsheets().values().append(spreadsheetId=MASTER_SHEET_ID, range='Sheet1!A:ZZ', valueInputOption='USER_ENTERED', body={'values': rows_to_append}).execute()
consolidation_results["team_members_processed"][team_member] = {"rows_added": len(rows_to_append), "last_modified": modified_time, "status": "Success"}
consolidation_results["total_rows_added"] += len(rows_to_append)
except Exception as e:
consolidation_results["errors"].append(f"Error processing {team_member}: {str(e)}")
consolidation_results["team_members_processed"][team_member] = {"rows_added": 0, "status": f"Error: {str(e)}"}
sheets_service.spreadsheets().values().update(spreadsheetId=MASTER_SHEET_ID, range='Sheet1!B1', valueInputOption='USER_ENTERED', body={'values': [[current_timestamp]]}).execute()
return {'statusCode': 200, 'body': json.dumps(consolidation_results)}
except Exception as e:
error_msg = f"Cloud Run Function error: {str(e)}"
return {'statusCode': 500, 'body': json.dumps({'error': error_msg})}

