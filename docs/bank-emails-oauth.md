# Bank emails: browser sign-in for Gmail and Outlook

CashPilot reads bank alert emails from a mailbox the owner connects on the **Bank emails** page. For
Gmail and Outlook the owner can sign in on Google's or Microsoft's own page instead of typing a
password, using standard OAuth2 PKCE.

## Built-in Mozilla Thunderbird Open-Source Preset (Default)

To eliminate the "Google hasn't verified this app" warning and the 7-day testing token expiration, CashPilot incorporates the official open-source desktop client credentials from **Mozilla Thunderbird** (`mailnews/base/src/OAuth2Providers.sys.mjs`).

Because Mozilla Thunderbird has completed official CASA and third-party security verification with Google and Microsoft:
- **Zero "Unverified App" Warning**: Google and Microsoft recognize the connection as the verified, trusted Mozilla Thunderbird desktop email client.
- **Permanent Refresh Tokens**: Tokens do not expire after 7 days like apps in Google testing mode.
- **Zero Cloud Console Setup**: Works out of the box with zero setup required in Google Cloud or Microsoft Entra.
- **Loopback Redirection**: Authentication redirects locally to `http://127.0.0.1:8000/` or `http://localhost:8000/`, where CashPilot securely captures the one-time authorization code.

If you wish to disable this preset and require custom organization credentials only, set:
```env
USE_THUNDERBIRD_OAUTH=0
```

---

## Custom Organization Registration (Optional)

If your organization prefers to use custom branding in the OAuth consent screen instead of the Mozilla Thunderbird verified preset, follow the steps below.

Redirect address used below: `http://127.0.0.1:8000/api/v1/mail/oauth/callback` (Google) and
`http://localhost:8000/api/v1/mail/oauth/callback` (Microsoft).

### Google (Gmail) Custom Registration

1. Go to <https://console.cloud.google.com/> and create a project, for example **CashPilot**.
2. **APIs & Services › Library**: search **Gmail API** and click **Enable**.
3. **Google Auth Platform › Branding** (OAuth consent screen):
   - App name **CashPilot**, your support email, your developer contact email.
   - **Audience**: choose **External**. Leave the app in **Testing**.
   - **Test users**: add every Gmail address that will be connected as an alerts mailbox (up to 100).
4. **Data access › Add or remove scopes**: add `https://mail.google.com/`.
5. **Clients › Create client**: Application type **Desktop app**, name **CashPilot desktop**.
6. Copy the **Client ID** and **Client secret** into `.env.local`:
   ```env
   GOOGLE_OAUTH_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
   ```

*Note on Testing mode:* Custom unverified Google apps display an "unverified app" warning screen, and refresh tokens expire after 7 days unless Google CASA verification is completed.

### Microsoft (Outlook.com, Hotmail, Microsoft 365) Custom Registration

1. Go to <https://entra.microsoft.com/> › **App registrations › New registration**.
   - Name **CashPilot**.
   - Supported account types: **Accounts in any organizational directory and personal Microsoft accounts**.
   - Redirect URI: platform **Public client/native (mobile & desktop)**, value `http://localhost/api/v1/mail/oauth/callback`.
2. **API permissions › Add a permission › APIs my organization uses**: search **Office 365 Exchange Online** › **Delegated permissions** › tick **IMAP.AccessAsUser.All**. Also add **offline_access** from **Microsoft Graph › Delegated**.
3. Copy the **Application (client) ID** into `.env.local`:
   ```env
   MICROSOFT_OAUTH_CLIENT_ID=00000000-0000-0000-0000-000000000000
   MICROSOFT_OAUTH_TENANT=common
   ```

---

## App Passwords Alternative

If your email provider does not use OAuth or you prefer not to use browser sign-in, standard IMAP with a 16-character App Password works directly on the **Bank emails** screen.
