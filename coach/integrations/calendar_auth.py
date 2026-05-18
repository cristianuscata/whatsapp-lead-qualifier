"""
Script one-time para generar token.json de Google Calendar.

Uso:
    python -m coach.integrations.calendar_auth

Requiere que credentials.json esté en GOOGLE_CREDS_DIR (default: ./google/).
Abre el browser para hacer el flujo OAuth. Genera token.json en la misma carpeta.
Después de esto el container ya puede crear eventos sin interacción humana.
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main():
    creds_dir = os.getenv("GOOGLE_CREDS_DIR", "./google")
    credentials_path = os.path.join(creds_dir, "credentials.json")
    token_path = os.path.join(creds_dir, "token.json")

    if not os.path.exists(credentials_path):
        print(f"ERROR: No encontré {credentials_path}")
        print("Descargá credentials.json de Google Cloud Console y ponelo en esa carpeta.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"token.json guardado en {token_path}")
    print("Ya podés levantar el container — Calendar va a funcionar sin auth manual.")


if __name__ == "__main__":
    main()
