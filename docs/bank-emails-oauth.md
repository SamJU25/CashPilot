# Bank emails: browser sign-in for Gmail and Outlook

CashPilot reads bank alert emails from a mailbox the owner connects on the **Bank emails** page. For
Gmail and Outlook the owner can sign in on Google's or Microsoft's own page instead of typing a
password, using standard OAuth2 PKCE.

To enable 1-click browser sign-in for your organization, follow the 10-minute instructions below to register your app in Google Cloud or Microsoft Entra. Until configured, Gmail works with app passwords and standard IMAP.

What CashPilot receives: a refresh token for **reading mail only**. It is encrypted on disk with a key
kept in the operating system's credential store. Disconnecting deletes the key.

Redirect address used below: `http://127.0.0.1:8000/api/v1/mail/oauth/callback` (Google) and
`http://localhost:8000/api/v1/mail/oauth/callback` (Microsoft). Change `8000` if the backend runs on
another port.

## Google (Gmail), about 10 minutes

1. Go to <https://console.cloud.google.com/> and create a project, for example **CashPilot**.
2. **APIs & Services › Library**: search **Gmail API** and click **Enable**.
3. **Google Auth Platform › Branding** (older consoles: **OAuth consent screen**):
   - App name **CashPilot**, your support email, your developer contact email.
   - **Audience**: choose **External**. Leave the app in **Testing**.
   - **Test users**: add every Gmail address that will be connected as an alerts mailbox
     (up to 100). Only these can sign in while the app is in Testing.
4. **Data access › Add or remove scopes**: add `https://mail.google.com/` (shown as "Read, compose,
   send, and permanently delete all your email from Gmail"). It is the only Google scope that allows
   IMAP; CashPilot itself opens the mailbox read-only.
5. **Clients › Create client**: Application type **Desktop app**, name **CashPilot desktop**.
   Desktop clients accept any `127.0.0.1` port, so there is no redirect address to enter.
6. Copy the **Client ID** and **Client secret** into `.env.local`:
   ```
   GOOGLE_OAUTH_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
   ```

**Testing mode limits.** Google shows an "unverified app" warning (click *Continue*), and refresh tokens
of apps in Testing expire after **7 days**, so owners must sign in again weekly. Publishing the app
removes both, but `https://mail.google.com/` is a restricted scope: Google requires app verification
and a yearly third-party security assessment (CASA) before publishing to everyone.

## Microsoft (Outlook.com, Hotmail, Microsoft 365), about 10 minutes

1. Go to <https://entra.microsoft.com/> › **App registrations › New registration**.
   - Name **CashPilot**.
   - Supported account types: **Accounts in any organizational directory and personal Microsoft
     accounts**.
   - Redirect URI: platform **Public client/native (mobile & desktop)**, value
     `http://localhost/api/v1/mail/oauth/callback`. Microsoft ignores the port for `localhost`.
2. **API permissions › Add a permission › APIs my organization uses**: search **Office 365 Exchange
   Online** › **Delegated permissions** › tick **IMAP.AccessAsUser.All**. Also add **offline_access**
   from **Microsoft Graph › Delegated**. Click **Add permissions**.
3. Copy the **Application (client) ID** from **Overview** into `.env.local`:
   ```
   MICROSOFT_OAUTH_CLIENT_ID=00000000-0000-0000-0000-000000000000
   MICROSOFT_OAUTH_TENANT=common
   ```
   No client secret: CashPilot is a public client and uses PKCE.

Work accounts: the organisation's admin may need to approve the app, and IMAP must be enabled for the
mailbox in Exchange.

## After adding the ids

Restart the backend. On **Bank emails**, typing a Gmail or Outlook address now shows
**Sign in with Google** or **Sign in with Microsoft** instead of a password box.
