import functions_framework
import json
from google.cloud import secretmanager

def get_secret(secret_id):
    project_id = "simon-reporting-agent"
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

@functions_framework.http
def consolidate_ps(request):
    try:
        secret_json = get_secret("simon-service-account-key")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    functions_framework.start(("0.0.0.0", port), debug=True, http_func=consolidate_ps)
