# LOGIC / VINCI Setup Guide

This guide explains how to configure all credentials, external APIs, and services required to run LOGIC.

---

## 1. Environment Variables (.env)
Create a `.env` file in the root directory with the following variables:

```env
API_KEY=your_primary_ai_gateway_or_provider_key
GROQ_API_KEY=gsk_your_groq_api_key
YDC_API_KEY=your_you_dot_com_search_api_key
TINYFISH_API_KEY=your_tinyfish_web_scraper_api_key
```

---

## 2. Google OAuth (Google Calendar, Drive & Gmail)
LOGIC interacts with Google Drive, Gmail, and Google Calendar via desktop OAuth 2.0 credentials.

### Step-by-Step Google Setup:
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `LOGIC-Assistant`).
3. Navigate to **APIs & Services > Library** and enable:
   - **Google Calendar API**
   - **Google Drive API**
   - **Gmail API**
4. Navigate to **APIs & Services > OAuth consent screen**:
   - Select **External** (or Internal for Workspace).
   - Fill in the App name and user support email.
   - Under **Scopes**, add:
     - `https://www.googleapis.com/auth/calendar`
     - `https://www.googleapis.com/auth/drive`
     - `https://www.googleapis.com/auth/gmail.readonly` (or `gmail.modify`)
   - Under **Test users**, add your own Google email address.
5. Navigate to **APIs & Services > Credentials**:
   - Click **+ CREATE CREDENTIALS** > **OAuth client ID**.
   - Application type: **Desktop app**.
   - Name: `LOGIC Desktop Client`.
   - Click **Create**, then click **Download JSON**.
6. Rename the downloaded file to `google_oauth.json` and place it in `logic_tools/oauth_token_files/google_oauth.json` (or repository root).
7. On first execution of any calendar/drive tool, a browser window will open to authenticate. Upon approval, `token.json` will be generated automatically.

---

## 3. GitHub Access Token
Used for repository inspection, code management, and git automation.

### How to generate a GitHub Token:
1. Go to [GitHub Token Settings](https://github.com/settings/tokens).
2. Click **Generate new token (classic)** or **Fine-grained token**.
3. Set expiration and select scopes:
   - `repo` (Full control of private repositories)
   - `read:user`
4. Generate and copy the token.
5. Create `logic_tools/github_access.json` with the following structure:
```json
{
  "username": "YourGitHubUsername",
  "token": "ghp_yourPersonalAccessTokenHere"
}
```

---

## 4. OmniRoute AI Gateway
LOGIC points its default base URL to `http://localhost:20128/v1` for routing across LLMs and token management.
- Run OmniRoute locally before starting LOGIC, OR
- Update `BASE_URL` in `logic.py` directly to your model provider (e.g. `https://api.openai.com/v1` or `https://openrouter.ai/api/v1`).

---

## 5. Verification
To verify all dependencies and credentials in one click, run:
```bash
python verify_setup.py
```