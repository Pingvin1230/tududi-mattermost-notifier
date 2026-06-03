# tududi-mattermost-notifier

External notification service for [tududi](https://github.com/chrisvel/tududi) that sends push notifications via Mattermost webhooks.

## Overview

This tool monitors the tududi SQLite database for new notifications and forwards them to a Mattermost channel via webhook. It's designed to run as a cron job, checking for new notifications every few minutes.

### Features

- ✅ Real-time push notifications via Mattermost
- ✅ Configurable notification types (tasks, projects, overdue, due soon)
- ✅ Customizable notification levels (info, warning, error)
- ✅ State tracking to avoid duplicate notifications
- ✅ Simple YAML configuration
- ✅ Lightweight (no external dependencies beyond Python standard library + requests)

## How It Works

```
┌─────────────┐
│   tududi    │
│  scheduler  │
│ (every 15m) │
└──────┬──────┘
       │
       │ Creates notifications
       ▼
┌─────────────┐
│ notifications│
│    table     │
└──────┬──────┘
       │
       │ Reads new notifications
       ▼
┌─────────────┐
│  notifier   │
│ (every 5m)  │
└──────┬──────┘
       │
       │ Sends via webhook
       ▼
┌─────────────┐
│ Mattermost  │
│   webhook   │
└─────────────┘
```

## Installation

### Prerequisites

- Python 3.7+
- `requests` library

### Steps

1. **Clone or download this repository**

```bash
git clone https://github.com/yourusername/tududi-mattermost-notifier.git
cd tududi-mattermost-notifier
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure the notifier**

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your settings (see Configuration section below).

4. **Set up Mattermost webhook** (see next section)

5. **Test the notifier**

```bash
python notifier.py --verbose --dry-run
```

6. **Set up cron job**

```bash
# Edit crontab
crontab -e

# Add this line to run every 5 minutes
*/5 * * * * cd /path/to/tududi-mattermost-notifier && /usr/bin/python3 notifier.py >> logs/notifier.log 2>&1
```

## Setting Up Mattermost Webhook

### Step 1: Create an Incoming Webhook

1. Log in to your Mattermost instance as an admin
2. Go to **Main Menu** → **Integrations** → **Incoming Webhooks**
3. Click **Add Incoming Webhook**
4. Fill in the details:
   - **Title**: `tududi Notifications` (or any name you prefer)
   - **Description**: `Notifications from tududi task manager`
   - **Channel**: Select the channel where notifications should appear (e.g., `town-square`)
   - **Lock to this channel**: ✅ Recommended (for security)
5. Click **Save**
6. **Copy the webhook URL** - it will look like:
   ```
   https://mattermost.example.com/hooks/abc123def456
   ```

### Step 2: Configure the Notifier

Paste the webhook URL into your `config.yaml`:

```yaml
mattermost:
  webhook_url: "https://mattermost.example.com/hooks/abc123def456"
```

### Step 3: Test the Webhook

You can test the webhook directly from the command line:

```bash
curl -X POST https://mattermost.example.com/hooks/abc123def456 \
  -H 'Content-Type: application/json' \
  -d '{"text": "🎉 Test notification from tududi-mattermost-notifier!"}'
```

If successful, you should see the message in your Mattermost channel.

## Configuration

The notifier uses a YAML configuration file (`config.yaml`). See `config.example.yaml` for a complete example.

### Basic Configuration

```yaml
# Mattermost webhook settings
mattermost:
  webhook_url: "https://mattermost.example.com/hooks/your-webhook-id"
  timeout: 10  # seconds

# tududi database path
tududi:
  db_path: "/opt/tududi/data/production.sqlite3"

# State file (tracks last check timestamp)
state:
  path: "./state/notifier_state.json"

# Notification settings
notifications:
  # Which notification types to send
  types:
    dueTasks: true           # Tasks due soon
    overdueTasks: true       # Overdue tasks
    dueProjects: true        # Projects due soon
    overdueProjects: true    # Overdue projects
    deferUntil: true         # Deferred tasks that became active
  
  # Minimum notification level to send
  # Options: info, warning, error
  min_level: "warning"

# Logging
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "./logs/notifier.log"

# Additional options
options:
  check_interval_seconds: 300  # How often to check (for logging purposes)
  max_notifications_per_run: 50  # Limit notifications per run (prevent spam)
```

### Notification Types

The notifier supports the same notification types as tududi's built-in notification preferences:

| Type | Description | Default |
|------|-------------|---------|
| `dueTasks` | Tasks with due date within 24 hours | ✅ enabled |
| `overdueTasks` | Tasks past their due date | ✅ enabled |
| `dueProjects` | Projects with due date within 24 hours | ✅ enabled |
| `overdueProjects` | Projects past their due date | ✅ enabled |
| `deferUntil` | Deferred tasks that reached their defer date | ✅ enabled |

### Notification Levels

Each notification has a severity level:

- **`info`**: General information (e.g., task due in 20 hours)
- **`warning`**: Important reminders (e.g., task due in 2 hours)
- **`error`**: Critical alerts (e.g., task overdue)

Set `min_level` to filter out less important notifications:

```yaml
notifications:
  min_level: "warning"  # Only send warning and error notifications
```

## Usage

### Manual Execution

```bash
# Run with verbose output
python notifier.py --verbose

# Dry run (don't actually send notifications)
python notifier.py --verbose --dry-run

# Check current state
cat state/notifier_state.json
```

### Viewing Logs

```bash
# Tail the log file
tail -f logs/notifier.log

# View recent entries
tail -50 logs/notifier.log
```

### Troubleshooting

**No notifications appearing?**

1. Check that tududi's scheduler is running:
   ```bash
   docker logs tududi | grep scheduler
   ```

2. Verify notifications exist in the database:
   ```bash
   sqlite3 /opt/tududi/data/production.sqlite3 \
     "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 5;"
   ```

3. Check the notifier logs:
   ```bash
   tail -100 logs/notifier.log
   ```

4. Reset state to re-process all notifications:
   ```bash
   rm state/notifier_state.json
   python notifier.py --verbose
   ```

**Webhook not working?**

1. Test the webhook directly:
   ```bash
   curl -X POST https://mattermost.example.com/hooks/your-id \
     -H 'Content-Type: application/json' \
     -d '{"text": "test"}'
   ```

2. Check webhook URL in `config.yaml`

3. Verify Mattermost webhook is not expired or disabled

## Example Notifications

### Task Due Soon

```
⚠️ **Task Due Soon**

Your task "Review quarterly report" is due in 2 hours

🕐 2026-06-02 14:30:00
```

### Task Overdue

```
🔴 **Task Overdue**

Your task "Submit expense report" was due yesterday

🕐 2026-06-01 09:00:00
```

### Project Due Soon

```
⚠️ **Project Due Soon**

Your project "Website redesign" is due tomorrow

🕐 2026-06-02 18:00:00
```

## Development

### Project Structure

```
tududi-mattermost-notifier/
├── README.md                 # This file
├── config.example.yaml       # Example configuration
├── requirements.txt          # Python dependencies
├── .gitignore               # Git ignore rules
├── LICENSE                  # MIT license
├── notifier.py              # Main script
├── logs/                    # Log files (created at runtime)
└── state/                   # State tracking (created at runtime)
```

### Running Tests

```bash
# Test with dry run
python notifier.py --verbose --dry-run

# Test specific configuration
python notifier.py --config my-config.yaml --verbose
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- [tududi](https://github.com/chrisvel/tududi) - A simple, self-hosted task and project management app
- [Mattermost](https://mattermost.com/) - Secure collaboration for technical teams

## Support

For issues and questions:
- Open an issue on GitHub
- Check the troubleshooting section in this README
