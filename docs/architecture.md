# ALLPLUS architecture

The Bot API polling handler and the Mini App HTTP server run in the same process and share one Telethon client, one workspace, and one SQLite database. The Mini App validates the original Telegram initData before returning account data. Its frontend does not receive the bot token, session, encryption key, or device authorization hash.

## Code map

- `app/auth` and `app/security` handle interactive login, session encryption, and Mini App authorization.
- `app/telegram_client` provides paginated MTProto reads, reconnect handling, and FloodWait handling.
- `app/services` owns synchronization, message and media operations, confirmation tickets, backups, workflow execution, and account statistics.
- `app/database` owns transactional SQLite migrations and local indexes. Account data remains scoped to the configured data directory.
- `app/handlers` renders the bot. `app/web.py` exposes owner-only HTTP endpoints. `miniapp` renders the Persian/English interface.

## Data and permissions

Dialog statistics, activity, favorites, tags, recent access and historical snapshots use SQLite. Message contents and media are loaded from Telegram on demand. Search history is encrypted. Device authorization hashes and short-lived command tickets remain in server memory. A fresh confirmation ticket expires after two minutes and is consumed before the operation. The bot and Mini App share the mutation coordinator.

The initial product manages one active account per process. To run a second isolated account, set a distinct `KILLER_PROFILE`, owner ID, bot token, encryption key and listener. Do not share a bot token across instances. Account switching within one interface is outside this deployment.

## Managed workflows and plugins

The scheduler provides periodic synchronization, new-session alerts, a daily dashboard summary, encrypted backups, and optional inactivity reports. Intervals apply per process. Activity records contain operation categories and results, without message content. Inactivity reports use the latest locally known dialog message date and may omit unavailable dates.

The plugin registry currently contains the built-in inactivity module with read access to local dialog metadata. Its adapter receives the local query output rather than a client or credentials. Untrusted third-party Python plugin loading and external code execution are outside the registry.

## HTTPS deployment

On a regular host, publish the Mini App behind a trusted reverse proxy pointing to a private Unix socket or loopback port. Use `--web-socket` or `--web-port 8765`. Supply the public URL as `KILLER_MINIAPP_URL` to show the launch button.

The cPanel adapter in `deploy/cpanel/api.php` proxies only the Mini App API to a socket under a private account directory. For the default host layout, put the static `miniapp/index.html`, `miniapp/assets/` and `api.php` in `~/public_html/killer/`, set the `killer-proxy` meta value to `api.php`, and keep the Python project in `~/killer-telegram`. Validate HTTPS and an unauthorized API response before enabling the Mini App button. The HTTPS origin needs a certificate valid for its public hostname.
