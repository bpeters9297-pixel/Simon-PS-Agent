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
    result = consolidate()
    return result

def get_credentials():
    """Load service account credentials from environment"""
    service_account_json = os.getenv('GOOGLE_CREDENTIALS')

    if service_account_json:
        service_account_info = json.loads(base64.b64decode(service_account_json))
    else:
        with open('/var/secrets/google/key.json', 'r') as f:
            service_account_info = json.load(f)

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    return credentials

def build_sheets_service():
    """Build and return Sheets API service"""
    credentials = get_credentials()
    return build('sheets', 'v4', credentials=credentials)

def sheet_exists(service, spreadsheet_id, sheet_name):
    """Check if a sheet exists"""
    try:
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in result.get('sheets', []):
            if sheet['properties']['title'] == sheet_name:
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking sheet existence: {e}")
        return False

def create_sheet(service, spreadsheet_id, sheet_name):
    """Create a new sheet"""
    try:
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
        logger.info(f"Created sheet: {sheet_name}")
        return True
    except Exception as e:
        logger.error(f"Error creating sheet: {e}")
        return False

def get_sheet_id_by_name(service, spreadsheet_id, sheet_name):
    """Get numeric sheet ID by sheet name"""
    try:
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in result.get('sheets', []):
            if sheet['properties']['title'] == sheet_name:
                return sheet['properties']['sheetId']
        return None
    except Exception as e:
        logger.error(f"Error getting sheet ID: {e}")
        return None

def get_last_row_with_data(service, spreadsheet_id, sheet_name):
    """Get the row count for a sheet"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A:A"
        ).execute()

        values = result.get('values', [])
        return len(values) if values else 0
    except Exception as e:
        logger.error(f"Error getting row count for {sheet_name}: {e}")
        return 0

def get_new_rows(service, source_sheet_id, sheet_name, last_processed_row):
    """Get rows after last_processed_row"""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=source_sheet_id,
            range=f"'{sheet_name}'!A{last_processed_row + 1}:Z1000"
        ).execute()

        return result.get('values', [])
    except Exception as e:
        logger.error(f"Error getting new rows from {sheet_name}: {e}")
        return []

def append_rows_to_master(service, sheet_name, rows):
    """Append rows to master sheet"""
    if not rows:
        return None

    try:
        result = service.spreadsheets().values().append(
            spreadsheetId=MASTER_SHEET_ID,
            range=f"'{sheet_name}'!A:Z",
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()

        return result
    except Exception as e:
        logger.error(f"Error appending rows to {sheet_name}: {e}")
        return None

def copy_formatting_for_rows(service, sheet_name, start_row_index, num_rows):
    """Copy formatting from row above to newly appended rows"""
    try:
        sheet_id = get_sheet_id_by_name(service, MASTER_SHEET_ID, sheet_name)

        if sheet_id is None:
            logger.warning(f"Could not find sheet ID for {sheet_name}")
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
    except Exception as e:
        logger.warning(f"Error copying formatting for {sheet_name}: {e}")

def load_tracking_log(service):
    """Load consolidation tracking log"""
    try:
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

        return log
    except Exception as e:
        logger.info(f"Consolidation log not accessible, starting fresh: {e}")
        return {}

def save_tracking_log(service, log):
    """Save consolidation tracking log"""
    try:
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
    except Exception as e:
        logger.error(f"Error saving tracking log: {e}")

def consolidate():
    """Main consolidation logic"""
    service = build_sheets_service()

    logger.info("Starting Production Summary consolidation...")

    # Ensure Consolidation Log sheet exists
    if not sheet_exists(service, MASTER_SHEET_ID, 'Consolidation Log'):
        logger.info("Creating Consolidation Log sheet...")
        create_sheet(service, MASTER_SHEET_ID, 'Consolidation Log')

    log = load_tracking_log(service)
    consolidated_count = 0

    for team_member, source_sheet_id in TEAM_MEMBERS.items():
        logger.info(f"Processing {team_member}'s workbook...")

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
                        # Update tracking log with current row count
                        last_row_in_source = get_last_row_with_data(service, source_sheet_id, sheet_name)
                        log[log_key] = last_row_in_source
                        consolidated_count += len(new_rows)

                        logger.info(f"Appended {len(new_rows)} rows to {sheet_name}. Updated tracking to row {last_row_in_source}")

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
                                logger.warning(f"Could not parse updated range: {updated_range}, {e}")

            except Exception as e:
                logger.error(f"Error processing {team_member}/{sheet_name}: {e}")
                continue

    save_tracking_log(service, log)

    logger.info(f"Consolidation complete! Consolidated {consolidated_count} rows.")
    return {'status': 'success', 'message': f'Consolidated {consolidated_count} rows'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
