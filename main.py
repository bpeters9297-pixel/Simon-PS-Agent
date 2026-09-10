# Test deployment - Sept 10
import os
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import base64
import logging
from flask import Flask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Tabs to consolidate
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

app = Flask(__name__)

@app.route('/')
def trigger_consolidation():
    """Endpoint for Cloud Scheduler to trigger consolidation"""
    print("=" * 80)
    print("TRIGGER_CONSOLIDATION: Endpoint called by Cloud Scheduler")
    print("=" * 80)
    result = consolidate()
    print(f"TRIGGER_CONSOLIDATION: Returning result: {result}")
    return result

def get_credentials():
    """Load service account credentials from environment"""
    print("\n>>> GET_CREDENTIALS: Starting")
    
    service_account_json = os.getenv('GOOGLE_CREDENTIALS')
    print(f">>> GET_CREDENTIALS: GOOGLE_CREDENTIALS env var present: {bool(service_account_json)}")

    try:
        if service_account_json:
            print(">>> GET_CREDENTIALS: Loading from base64-encoded env var")
            service_account_info = json.loads(base64.b64decode(service_account_json))
        else:
            print(">>> GET_CREDENTIALS: Loading from /var/secrets/google/key.json")
            with open('/var/secrets/google/key.json', 'r') as f:
                service_account_info = json.load(f)

        print(f">>> GET_CREDENTIALS: Loaded service account for project: {service_account_info.get('project_id', 'UNKNOWN')}")
        
        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        print(">>> GET_CREDENTIALS: Credentials created successfully")
        return credentials
    except Exception as e:
        print(f">>> GET_CREDENTIALS: ERROR - {str(e)}")
        raise

def build_sheets_service():
    """Build and return Sheets API service"""
    print("\n>>> BUILD_SHEETS_SERVICE: Building Sheets API service")
    try:
        credentials = get_credentials()
        service = build('sheets', 'v4', credentials=credentials)
        print(">>> BUILD_SHEETS_SERVICE: Service built successfully")
        return service
    except Exception as e:
        print(f">>> BUILD_SHEETS_SERVICE: ERROR - {str(e)}")
        raise

def sheet_exists(service, spreadsheet_id, sheet_name):
    """Check if a sheet exists"""
    try:
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in result.get('sheets', []):
            if sheet['properties']['title'] == sheet_name:
                print(f">>> SHEET_EXISTS: Sheet '{sheet_name}' found in spreadsheet")
                return True
        print(f">>> SHEET_EXISTS: Sheet '{sheet_name}' NOT found in spreadsheet")
        return False
    except Exception as e:
        print(f">>> SHEET_EXISTS: ERROR checking {sheet_name}: {e}")
        return False

def create_sheet(service, spreadsheet_id, sheet_name):
    """Create a new sheet"""
    try:
        print(f">>> CREATE_SHEET: Creating sheet '{sheet_name}'")
        request = {
            'requests': [
                {
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }
            ]
        }
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=request
        ).execute()
        print(f">>> CREATE_SHEET: Successfully created sheet '{sheet_name}'")
        return True
    except Exception as e:
        print(f">>> CREATE_SHEET: ERROR creating {sheet_name}: {e}")
        return False

def get_sheet_id_by_name(service, spreadsheet_id, sheet_name):
    """Get numeric sheet ID by sheet name"""
    try:
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in result.get('sheets', []):
            if sheet['properties']['title'] == sheet_name:
                sheet_id = sheet['properties']['sheetId']
                print(f">>> GET_SHEET_ID: Found sheet ID {sheet_id} for '{sheet_name}'")
                return sheet_id
        print(f">>> GET_SHEET_ID: Sheet '{sheet_name}' not found")
        return None
    except Exception as e:
        print(f">>> GET_SHEET_ID: ERROR for {sheet_name}: {e}")
        return None

def get_last_row_with_data(service, spreadsheet_id, sheet_name):
    """Get the row count for a sheet"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A:A"
        ).execute()

        values = result.get('values', [])
        row_count = len(values) if values else 0
        print(f">>> GET_LAST_ROW: Sheet '{sheet_name}' has {row_count} rows")
        return row_count
    except Exception as e:
        print(f">>> GET_LAST_ROW: ERROR for {sheet_name}: {e}")
        return 0

def get_new_rows(service, source_sheet_id, sheet_name, last_processed_row):
    """Get rows after last_processed_row"""
    try:
        print(f">>> GET_NEW_ROWS: Fetching rows after row {last_processed_row} from '{sheet_name}'")
        result = service.spreadsheets().values().get(
            spreadsheetId=source_sheet_id,
            range=f"'{sheet_name}'!A{last_processed_row + 1}:Z1000"
        ).execute()

        new_rows = result.get('values', [])
        print(f">>> GET_NEW_ROWS: Found {len(new_rows)} new rows in '{sheet_name}'")
        return new_rows
    except Exception as e:
        print(f">>> GET_NEW_ROWS: ERROR fetching from {sheet_name}: {e}")
        return []

def append_rows_to_master(service, sheet_name, rows):
    """Append rows to master sheet"""
    if not rows:
        print(f">>> APPEND_ROWS: No rows to append for '{sheet_name}'")
        return None

    try:
        print(f">>> APPEND_ROWS: Appending {len(rows)} rows to '{sheet_name}' in master sheet")
        result = service.spreadsheets().values().append(
            spreadsheetId=MASTER_SHEET_ID,
            range=f"'{sheet_name}'!A:Z",
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()

        print(f">>> APPEND_ROWS: Successfully appended rows. Updated range: {result.get('updates', {}).get('updatedRange', 'N/A')}")
        return result
    except Exception as e:
        print(f">>> APPEND_ROWS: ERROR appending to {sheet_name}: {e}")
        return None

def copy_formatting_for_rows(service, sheet_name, start_row_index, num_rows):
    """Copy formatting from row above to newly appended rows"""
    try:
        print(f">>> COPY_FORMATTING: Copying formatting for {num_rows} rows starting at row {start_row_index}")
        sheet_id = get_sheet_id_by_name(service, MASTER_SHEET_ID, sheet_name)

        if sheet_id is None:
            print(f">>> COPY_FORMATTING: Could not find sheet ID for '{sheet_name}', skipping formatting")
            return

        # Copy formatting from the row above the new rows
        requests = []
        for i in range(num_rows):
            requests.append({
                'copyPaste': {
                    'source': {
                        'sheetId': sheet_id,
                        'rowIndex': start_row_index - 1,
                        'columnIndex': 0,
                        'endRowIndex': start_row_index,
                        'endColumnIndex': 26
                    },
                    'destination': {
                        'sheetId': sheet_id,
                        'rowIndex': start_row_index + i,
                        'columnIndex': 0
                    },
                    'pasteType': 'PASTE_FORMAT'
                }
            })

        if requests:
            service.spreadsheets().batchUpdate(
                spreadsheetId=MASTER_SHEET_ID,
                body={'requests': requests}
            ).execute()
            print(f">>> COPY_FORMATTING: Successfully copied formatting for {num_rows} rows")
    except Exception as e:
        print(f">>> COPY_FORMATTING: WARNING - {e}")

def load_tracking_log(service):
    """Load consolidation tracking log"""
    try:
        print("\n>>> LOAD_TRACKING_LOG: Loading consolidation tracking log")
        result = service.spreadsheets().values().get(
            spreadsheetId=MASTER_SHEET_ID,
            range="'Consolidation Log'!A:D"
        ).execute()

        values = result.get('values', [])
        log = {}

        for row in values[1:]:
            if len(row) >= 3:
                try:
                    key = f"{row[0]}_{row[1]}"
                    log[key] = int(row[2])
                except (ValueError, IndexError):
                    continue

        print(f">>> LOAD_TRACKING_LOG: Loaded {len(log)} tracking entries")
        return log
    except Exception as e:
        print(f">>> LOAD_TRACKING_LOG: Not accessible or empty, starting fresh: {e}")
        return {}

def save_tracking_log(service, log):
    """Save consolidation tracking log"""
    try:
        print(f"\n>>> SAVE_TRACKING_LOG: Saving {len(log)} tracking entries")
        rows = [['Team Member', 'Sheet Name', 'Last Processed Row', 'Last Updated']]

        for key, value in sorted(log.items()):
            parts = key.split('_', 1)
            if len(parts) == 2:
                team_member, sheet_name = parts
                rows.append([team_member, sheet_name, value, datetime.utcnow().isoformat()])

        service.spreadsheets().values().update(
            spreadsheetId=MASTER_SHEET_ID,
            range="'Consolidation Log'!A:D",
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()
        print(f">>> SAVE_TRACKING_LOG: Successfully saved tracking log")
    except Exception as e:
        print(f">>> SAVE_TRACKING_LOG: ERROR - {e}")

def consolidate():
    """Main consolidation logic"""
    print("\n" + "=" * 80)
    print("CONSOLIDATE: Main consolidation function started")
    print("=" * 80)
    
    try:
        print(">>> CONSOLIDATE: Building Sheets API service")
        service = build_sheets_service()
        print(">>> CONSOLIDATE: Service built successfully")

        print("\n>>> CONSOLIDATE: Starting Production Summary consolidation...")

        # Ensure Consolidation Log sheet exists
        print(">>> CONSOLIDATE: Checking if 'Consolidation Log' sheet exists")
        if not sheet_exists(service, MASTER_SHEET_ID, 'Consolidation Log'):
            print(">>> CONSOLIDATE: 'Consolidation Log' sheet does not exist, creating it...")
            create_sheet(service, MASTER_SHEET_ID, 'Consolidation Log')
        else:
            print(">>> CONSOLIDATE: 'Consolidation Log' sheet already exists")

        print("\n>>> CONSOLIDATE: Loading tracking log")
        log = load_tracking_log(service)
        consolidated_count = 0

        print(f"\n>>> CONSOLIDATE: Processing {len(TEAM_MEMBERS)} team members")
        for team_member, source_sheet_id in TEAM_MEMBERS.items():
            print(f"\n>>> CONSOLIDATE: ========== Processing {team_member} ==========")

            for sheet_name in CONSOLIDATED_TABS:
                log_key = f"{team_member}_{sheet_name}"
                last_processed_row = log.get(log_key, 0)
                print(f">>> CONSOLIDATE: Processing {sheet_name} (last processed row: {last_processed_row})")

                try:
                    # Get new rows from source
                    new_rows = get_new_rows(service, source_sheet_id, sheet_name, last_processed_row)

                    if new_rows:
                        print(f">>> CONSOLIDATE: Appending {len(new_rows)} new rows from {team_member}/{sheet_name}")

                        # Append to master
                        result = append_rows_to_master(service, sheet_name, new_rows)

                        if result:
                            # Update tracking log with current row count
                            last_row_in_source = get_last_row_with_data(service, source_sheet_id, sheet_name)
                            log[log_key] = last_row_in_source
                            consolidated_count += len(new_rows)

                            print(f">>> CONSOLIDATE: ✓ Successfully appended {len(new_rows)} rows. Updated tracking to row {last_row_in_source}")

                            # Copy formatting from row above
                            updated_range = result.get('updates', {}).get('updatedRange', '')
                            if updated_range:
                                try:
                                    range_parts = updated_range.split('!')
                                    if len(range_parts) > 1:
                                        cell_range = range_parts[1].split(':')
                                        if cell_range:
                                            start_cell = cell_range[0]
                                            start_row = int(''.join(c for c in start_cell if c.isdigit()))
                                            copy_formatting_for_rows(service, sheet_name, start_row, len(new_rows))
                                except Exception as e:
                                    print(f">>> CONSOLIDATE: WARNING - Could not parse updated range: {updated_range}, {e}")
                        else:
                            print(f">>> CONSOLIDATE: ✗ Failed to append rows to {sheet_name}")

                    else:
                        print(f">>> CONSOLIDATE: No new rows in {sheet_name} (up to date)")

                except Exception as e:
                    print(f">>> CONSOLIDATE: ✗ ERROR processing {team_member}/{sheet_name}: {e}")
                    import traceback
                    print(traceback.format_exc())
                    continue

        print(f"\n>>> CONSOLIDATE: Saving tracking log with {len(log)} entries")
        save_tracking_log(service, log)

        print("\n" + "=" * 80)
        print(f"CONSOLIDATE: ✓ COMPLETE! Consolidated {consolidated_count} total rows.")
        print("=" * 80)
        
        return {'status': 'success', 'message': f'Consolidated {consolidated_count} rows'}
    
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"CONSOLIDATE: ✗ CRITICAL ERROR: {str(e)}")
        print("=" * 80)
        import traceback
        print(traceback.format_exc())
        return {'status': 'error', 'message': str(e)}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
