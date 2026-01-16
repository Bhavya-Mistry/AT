# [get_token.py]
from google_auth_oauthlib.flow import InstalledAppFlow
import json
import os

# Scopes required
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_refresh_token():
    if not os.path.exists('client_secret.json'):
        print("Error: client_secret.json not found!")
        return

    # 1. Setup the flow
    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json', SCOPES)
    
    print("Launching browser... please log in.")
    
    # 2. FORCE PORT 8080 HERE
    # This prevents the random number (like 58516) from appearing
    creds = flow.run_local_server(port=8080)

    # 3. Save the result
    data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

    with open('token.json', 'w') as f:
        f.write(json.dumps(data, indent=4))
    
    print("\nSUCCESS! Saved to token.json")

if __name__ == '__main__':
    get_refresh_token()