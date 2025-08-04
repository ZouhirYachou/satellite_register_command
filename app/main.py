from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
import httpx
import html

app = FastAPI()

# Store capsule info temporarily across requests (in memory)
capsule_lookup = {}

@app.get("/", response_class=HTMLResponse)
async def form():
    return """
    <html>
        <head><title>API Login</title></head>
        <body>
            <h2>API Login Form</h2>
            <form method="post">
                <label>Satellite server URL (e.g. https://satellite.example.com): <input type="text" name="api_url" required /></label><br>
                <label>Username: <input type="text" name="username" required /></label><br>
                <label>Password: <input type="password" name="password" required /></label><br>
                <input type="submit" value="Login" />
            </form>
        </body>
    </html>
    """

@app.post("/", response_class=HTMLResponse)
async def handle_form(
    request: Request,
    api_url: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    activation_key: str = Form(None),
    capsule: str = Form(None)
):
    base_url = api_url.rstrip("/")
    keys_url = f"{base_url}/katello/api/organizations/1/activation_keys"
    capsules_url = f"{base_url}/api/v2/smart_proxies"
    registration_url = f"{base_url}/api/v2/registration_commands"

    async with httpx.AsyncClient(verify=False) as client:
        try:
            # Step 1: Fetch activation keys
            keys_response = await client.get(keys_url, auth=(username, password))
            keys_data = keys_response.json().get("results", [])
            keys_datalist = ""
            for key in keys_data:
                name = key.get("name", "Unnamed")
                keys_datalist += f'<option value="{name}">{name}</option>'

            # Step 2: Fetch capsules and details for each
            capsules_response = await client.get(capsules_url, auth=(username, password))
            capsules_data = capsules_response.json().get("results", [])

            capsules_datalist = ""
            global capsule_lookup
            capsule_lookup = {}  # reset lookup

            for capsule_info in capsules_data:
                capsule_id = capsule_info.get("id")
                capsule_name = capsule_info.get("name", "Unnamed Capsule")
                capsule_detail_url = f"{base_url}/api/v2/smart_proxies/{capsule_id}"
                detail_response = await client.get(capsule_detail_url, auth=(username, password))
                if detail_response.status_code == 200:
                    capsule_details = detail_response.json()
                    locations = capsule_details.get("locations", [])
                    location_name = locations[0]["name"] if locations else "Unknown"
                else:
                    location_name = "Unknown"

                display_name = f"{capsule_name} ({location_name})"
                capsule_lookup[display_name] = capsule_id
                capsules_datalist += f'<option value="{display_name}">{display_name}</option>'

            # If both AK and capsule were submitted, call registration_commands
            registration_result = ""
            if activation_key and capsule and capsule in capsule_lookup:
                capsule_id = capsule_lookup[capsule]

                payload = {
                    "registration_command": {
                        "smart_proxy_id": capsule_id,
                        "setup_insights": False,
                        "insecure": True,
                        "activation_key": activation_key
                    }
                }

                reg_response = await client.post(registration_url, auth=(username, password), json=payload)
                if reg_response.status_code == 200:
                    command_text = reg_response.json().get("registration_command", "No command returned.")
                    safe_command = html.escape(command_text)
                    registration_result = f"""
                    <h3>Registration Command:</h3>
                    <textarea rows="5" cols="100" readonly onclick="this.select()">{safe_command}</textarea>
                    <p><small>Click inside the box to select & copy.</small></p>
                    """
                else:
                    registration_result = f"<h3>Failed to get registration command</h3><pre>{reg_response.text}</pre>"

            # Final page output
            return f"""
            <html>
                <head><title>Activation Keys & Capsules</title></head>
                <body>
                    <h3>Select Activation Key and Capsule</h3>
                    <form method="post">
                        <input type="hidden" name="api_url" value="{html.escape(api_url)}" />
                        <input type="hidden" name="username" value="{html.escape(username)}" />
                        <input type="hidden" name="password" value="{html.escape(password)}" />

                        <label>Activation Key:</label><br>
                        <input list="activation_keys" name="activation_key" required />
                        <datalist id="activation_keys">{keys_datalist}</datalist><br><br>

                        <label>Capsule:</label><br>
                        <input list="capsules" name="capsule" required />
                        <datalist id="capsules">{capsules_datalist}</datalist><br><br>

                        <input type="submit" value="Generate Registration Command" />
                    </form>

                    <hr>
                    {registration_result}
                </body>
            </html>
            """

        except Exception as e:
            return f"<h3>Unexpected error:</h3><pre>{str(e)}</pre>"

