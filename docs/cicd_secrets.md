# GitHub Secrets Required for CI/CD

To deploy successfully, the following secrets must be configured at:
Settings > Secrets and variables > Actions

## Hetzner SSH

| Secret | Description |
|--------|-------------|
| `HETZNER_HOST` | Server hostname or IP |
| `HETZNER_USER` | SSH username (e.g. `bruno`) |
| `HETZNER_SSH_KEY` | Private SSH key (full PEM content) |

## Database

| Secret | Description |
|--------|-------------|
| `DATABASE_URL` | Full Postgres URL with credentials |

## Kraken Spot

| Secret | Description |
|--------|-------------|
| `KRAKEN_API_KEY` | Kraken spot API key |
| `KRAKEN_API_SECRET` | Kraken spot API secret |

## Telegram Notifications

| Secret | Description |
|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |

## Kraken Futures (Phase 4A)

| Secret | Description |
|--------|-------------|
| `KRAKEN_FUTURES_API_KEY` | Demo or production key |
| `KRAKEN_FUTURES_API_SECRET` | Demo or production secret |

## How to add a secret

1. Go to Settings > Secrets and variables > Actions
2. Click "New repository secret"
3. Enter name (case sensitive) and value
4. Click "Add secret"

## Verification

After adding secrets, trigger a manual deploy via:
GitHub Actions > Deploy to Hetzner > Run workflow

You should receive a Telegram notification when the deploy completes.
