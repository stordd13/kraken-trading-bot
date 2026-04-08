# Telegram Alerts — Setup & Reference

## Setup

### 1. Create a Telegram bot
1. Open Telegram, search for `@BotFather`
2. Send `/newbot`, follow prompts
3. Copy the bot token (format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

### 2. Get your chat ID
1. Start a conversation with your new bot (send `/start`)
2. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` in the JSON response
4. That number is your chat ID

### 3. Configure environment
```bash
# In .env (never commit this file!)
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789
```

## Alert Types

| Alert | Trigger | Silent? |
|-------|---------|---------|
| Bot Started | KrakenBot startup | No |
| Bot Stopped | KrakenBot shutdown | No |
| Trade Fill | BUY/SELL order executed | No |
| Limit Order Placed | Limit order submitted | Yes |
| Crash Protector | Price drop >= threshold | No |
| Runtime Error | Fatal exception in main loop | No |
| Daily Summary | Cron at 23:00 UTC | No |
| Strategy Tick | BUY/SELL/FILTERED signals | Filtered=Yes |

## Message Format

All messages use HTML parse mode. Example trade fill:
```
🟢 BUY FILLED
Strategy: supertrend_4h
Pair: BTC/USDC
Amount: 0.0012 BTC
Price: 83,150
Cost: 100.00 USDC (fee: 0.10 USDC)
```

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `TELEGRAM_ENABLED` | `false` | Master toggle |
| `TELEGRAM_BOT_TOKEN` | (empty) | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | (empty) | Chat ID to send to |
| `TELEGRAM_DAILY_SUMMARY_HOUR_UTC` | `23` | Hour (0-23) for daily summary |

## Error Handling

- The notifier **never** raises exceptions — all errors are caught and logged
- If Telegram API is unreachable, messages are silently dropped
- Rate limiting via asyncio lock prevents Telegram 429 errors
- Messages are truncated to 4096 chars (Telegram limit)
- All notification calls are fire-and-forget (`asyncio.create_task`) — they never block trading
