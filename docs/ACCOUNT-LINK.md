# Polymarket US account linking

The Account panel retrieves a private USD balance, buying power, and position count. These values never change paper capital, strategy inputs, order sizing, or the reference wallet. There is no live-order or transfer endpoint in this connection.

## This installation

The dashboard can reuse the existing Windows DPAPI-encrypted file at the parent SupahTrade project's `data/connections/polymarket-us.dpapi`. It reads but does not modify or copy that file. Windows must run it under the original user's account. Click **Link saved account**, or **Refresh account** after a restart. Authentication is verified before the panel reports Connected.

## Standalone installation

Use Python 3.10+ and an existing maintained Node.js runtime with Ed25519 support (tested here with Node 22.22.3). No npm or pip packages are required. Put your own Polymarket US developer key ID and base64 secret in the local `.env` as `WEATHERLAB_POLYMARKET_KEY_ID` and `WEATHERLAB_POLYMARKET_SECRET_KEY`. Restart the dashboard, then select **Link saved account**. Alternatively set `WEATHERLAB_POLYMARKET_DPAPI_PATH` to your existing local encrypted file. Create or manage your credentials yourself at https://polymarket.us/developer. Never paste secrets in chat or include them in ZIPs.

## Transport and storage

Only authenticated GET requests to `https://api.polymarket.us/v1/account/balances` and `/v1/portfolio/positions` are allowed. Redirects are rejected. Each request uses the documented millisecond timestamp, method and path signed with Ed25519. The signer receives the seed through stdin, not process arguments, and uses Node's built-in crypto module. Its environment excludes NODE_OPTIONS and NODE_PATH. The saved dashboard link contains only a boolean. API responses are cached in process memory and refreshed on demand; account data is not exported with paper journals or packages.

Balances are snapshots with a verification timestamp. The position count covers the returned page; a plus sign denotes incomplete pagination coverage. Positions failure can leave a verified balance with an explicit coverage notice. Failed balance authentication removes prior displayed amounts. After restart the link is unverified until refreshed. Disconnect removes only the dashboard link; it does not delete or revoke your existing credentials.

Read-only describes the dashboard's transport allowlist, not the permissions granted to your underlying API credential. Those permissions have not been independently audited. Use the minimum permissions the platform supports. The connection is loopback-only and CSRF-protected, but is not an operating-system sandbox.

Official reference: https://docs.polymarket.us/api-reference/authentication

## Verification

51 unit tests pass including the RFC 8032 Ed25519 vector, rejected write paths and redirects, secret redaction, finite balance validation, cached reads, and disconnect behavior. On September 15, 2026, this installation authenticated successfully against both official account endpoints. This is account-read verification, not order-execution verification.
