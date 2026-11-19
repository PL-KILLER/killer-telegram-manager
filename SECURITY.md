# Security

Run this application under an OS account you control. Set the owner to your Telegram user ID. The bot and Mini App enforce the same owner. The Mini App accepts Telegram-signed initData for a limited time and keeps it in browser memory. Publish the Mini App through HTTPS and keep the Python listener on loopback or a private Unix socket.

Use an OS secret manager or protected environment configuration for Bot API and MTProto credentials. Restrict permissions on any local environment file and the data directory. Retain the Fernet key separately from any exported backups. Rotate any credential that was disclosed before releasing a copy of the project.

Enter phone codes and two-step verification passwords in the trusted local terminal. QR sign-in shows a short-lived Telegram login token on stdout. Use a private terminal without recording, shared panels, tee, logging, or screen sharing. Do not forward codes or QR images through the bot.

The encrypted MTProto session and application database have different purposes. Exports and backups contain no session key or Telegram login session. Local metadata can include private chat titles, IDs, tags and search configuration. Bot responses pass through Telegram, while Mini App responses pass through your HTTPS origin.

Report a suspected vulnerability privately to the repository maintainer. Include the affected source file, impact, and a minimal example that uses test accounts and synthetic data. Share no credentials or account exports.
