import os
import json
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime
import base64
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load service account from Secret Manager
def get_service_account_credentials():
# In Cloud Run, this would come from Secret Manager
secret_name = os.getenv('SECRET_NAME', 'Simon-Service-Account-Key')

# For local testing or Cloud Run, you'd load from environment
# Assuming it's passed as base64 in an env var or loaded from Secret Manager
service_account_json = os.getenv('GOOGLE_CREDENTIALS')

if service_account_json:
service_account_info = json.loads(base64.b64decode(service_account_json))
else:
# Try loading from a file for local testing
with open('/var/secrets/google/key.json', 'r') as f:
service_account_info = json.load(f)

credentials = Credentials.from_service_account_info(
service_account_info,
scopes=['https://www.googleapis.com/auth/spreadsheets']
)
return credentials

def build_sheets_service():
credentials = get_service_account_credentials()
return build('sheets', 'v4', credentials=credentials)

# Team member file IDs
TEAM_MEMBERS = {
'Brian': '1Jd7txsaQ5yjGOSWciKj1vSU1E36K1jrFIUXlxXdZYpo',
'Josh': '175cUPTf4s3HwnFu_OWf4Hpf3DeVnJFShcKpvHpKLLWM',
'Mallory': '1PJzHXY85fL7OqT-CeE0o--KocI16NEaB6eUNGGN4SqM',
'Marie': '1Bf8-wHHYtVkrT366TMS5hx5dhT6f25OGNweVrdaRESo',
'Christine': '1B_oYXjYJxgbMilOVMrFJO_elyKFVQzwza08R-pzK-sw',
'Emma': '1KHIQuvsIKD8iRUDnDzBz7MsgArc1wSY16O7-qcpIXHA'
}

MASTER_SHEET_ID = '1SghZqhJr-DG_fFEC0EiPYqxf-eoqy8uKT_TdwOjlEPU'

# Tabs to consolidate (tabs that appear in all sheets)
CONSOLIDATED_TABS = [
'Contracts Signed',
'Contracts Started',
'Cancellation Details',
'Equipment - Rentals',
'Franchise Inquiries',
'Customer Complaints',
'Account Walkthroughs',
'Account Transfers',
'ALL APPOINTMENTS SET / PROPOSALS DELIVERED',
'Marketing Campaign Leads',
'Monthly Attendance'
]

def get_sheet_id_by_name(service, spreadsheet_id, sheet_name):
"""Get the numeric sheet ID by sheet name"""
result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
for sheet in result.get('sheets', []):
if sheet['properties']['title'] == sheet_name:
return sheet['properties']['sheetId']
return None

def get_last_row_with_data(service, spreadsheet_id, sheet_name):
"""Get the row number of the last row with data in a sheet"""
result = service.spreadsheets().values().get(
spreadsheetId=spreadsheet_id,
range=f"'{sheet_name}'!A:A"
).execute()

values = result.get('values', [])
return len(values) if values else 0

def get_new_rows(service, source_sheet_id, sheet_name, last_processed_row):
"""Get rows from last_processed_row+1 onwards"""
result = service.spreadsheets().values().get(
spreadsheetId=source_sheet_id,
range=f"'{sheet_name}'!A{last_processed_row + 1}:Z" # Arbitrary wide range
).execute()

return result.get('values', [])

def append_rows_to_master(service, sheet_name, rows):
"""Append rows to the master sheet"""
if not rows:
return None

result = service.spreadsheets().values().append(
spreadsheetId=MASTER_SHEET_ID,
range=f"'{sheet_name}'!A:Z",
valueInputOption='RAW',
body={'values': rows}
).execute()

return result

def copy_formatting(service, sheet_name, start_row, end_row):
"""Copy formatting from row above to newly appended rows"""
# Get sheet ID
sheet_id = get_sheet_id_by_name(service, MASTER_SHEET_ID, sheet_name)

if sheet_id is None:
logger.warning(f"Could not find sheet ID for {sheet_name}")
return

# Copy formatting from row above (start_row - 1) to the new rows
request = {
'requests': [
{
'copyPaste': {
'source': {
'sheetId': sheet_id,
'rowIndex': start_row - 2, # Row to copy from (0-indexed)
'columnIndex': 0,
'endRowIndex': start_row - 1,
'endColumnIndex': 26 # A-Z
},
'destination': {
'sheetId': sheet_id,
'rowIndex': start_row - 1, # Start pasting from here (0-indexed)
'columnIndex': 0
},
'pasteType': 'PASTE_FORMAT'
}
}
]
}

# Apply to all rows from start to end
for i in range(start_row - 1, end_row):
service.spreadsheets().batchUpdate(
spreadsheetId=MASTER_SHEET_ID,
body=request
).execute()

def load_tracking_log(service):
"""Load the consolidation tracking log from master sheet"""
try:
result = service.spreadsheets().values().get(
spreadsheetId=MASTER_SHEET_ID,
range="'Consolidation Log'!A:D"
).execute()

values = result.get('values', [])
log = {}

for row in values[1:]: # Skip header
if len(row) >= 4:
key = f"{row[0]}_{row[1]}" # team_member_sheet_name
log[key] = int(row[2]) # last processed row

return log
except Exception as e:
logger.info(f"Consolidation log not found or empty, starting fresh: {e}")
return {}

def save_tracking_log(service, log):
"""Save the consolidation tracking log to master sheet"""
rows = [['Team Member', 'Sheet Name', 'Last Processed Row', 'Last Updated']]

for key, value in log.items():
team_member, sheet_name = key.split('_', 1)
rows.append([team_member, sheet_name, value, datetime.utcnow().isoformat()])

service.spreadsheets().values().update(
spreadsheetId=MASTER_SHEET_ID,
range="'Consolidation Log'!A:D",
valueInputOption='RAW',
body={'values': rows}
).execute()

def consolidate():
"""Main consolidation logic"""
service = build_sheets_service()

logger.info("Starting Production Summary consolidation...")

# Load tracking log
log = load_tracking_log(service)

# Iterate through each team member
for team_member, source_sheet_id in TEAM_MEMBERS.items():
logger.info(f"Processing {team_member}'s workbook...")

# Iterate through each tab
for sheet_name in CONSOLIDATED_TABS:
log_key = f"{team_member}_{sheet_name}"
last_processed_row = log.get(log_key, 0)

try:
# Get new rows from source
new_rows = get_new_rows(service, source_sheet_id, sheet_name, last_processed_row)

if new_rows:
logger.info(f"Found {len(new_rows)} new rows in {team_member}/{sheet_name}")

# Append to master
result = append_rows_to_master(service, sheet_name, new_rows)

if result:
# Get the range of newly appended rows
updated_range = result.get('updates', {}).get('updatedRange', '')

# Update tracking log
last_row_in_source = get_last_row_with_data(service, source_sheet_id, sheet_name)
log[log_key] = last_row_in_source

logger.info(f"Appended {len(new_rows)} rows to {sheet_name}")

# TODO: Copy formatting from row above
# This will be handled in the next phase

except Exception as e:
logger.error(f"Error processing {team_member}/{sheet_name}: {e}")
continue

# Save updated tracking log
save_tracking_log(service, log)

logger.info("Consolidation complete!")
return {'status': 'success', 'message': 'Production Summary consolidated'}

def main():
result = consolidate()
print(json.dumps(result))

if __name__ == '__main__':
main()
