#!/usr/bin/env python3
"""
tududi-mattermost-notifier

External notification service for tududi that sends push notifications
via Mattermost webhooks.

Monitors the tududi SQLite database for new notifications and forwards
them to a configured Mattermost channel.
"""

import sqlite3
import json
import sys
import argparse
import requests
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Default configuration values
DEFAULT_CONFIG = {
    'mattermost': {
        'webhook_url': '',
        'timeout': 10,
    },
    'tududi': {
        'db_path': '/opt/tududi/data/production.sqlite3',
    },
    'state': {
        'path': './state/notifier_state.json',
    },
    'notifications': {
        'types': {
            'dueTasks': True,
            'overdueTasks': True,
            'dueProjects': True,
            'overdueProjects': True,
            'deferUntil': True,
        },
        'min_level': 'warning',
    },
    'logging': {
        'level': 'INFO',
        'file': './logs/notifier.log',
    },
    'options': {
        'check_interval_seconds': 300,
        'max_notifications_per_run': 50,
    },
}


class Notifier:
    """Main notifier class that handles configuration and notification sending."""
    
    def __init__(self, config_path: str):
        """Initialize notifier with configuration file."""
        self.config = self._load_config(config_path)
        self.db_path = self.config['tududi']['db_path']
        self.state_file = Path(self.config['state']['path'])
        self.webhook_url = self.config['mattermost']['webhook_url']
        self.timeout = self.config['mattermost']['timeout']
        self.min_level = self.config['notifications']['min_level']
        self.enabled_types = self.config['notifications']['types']
        self.max_notifications = self.config['options']['max_notifications_per_run']
        
        # Ensure directories exist
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        Path(self.config['logging']['file']).parent.mkdir(parents=True, exist_ok=True)
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load and merge configuration from YAML file with defaults."""
        config = DEFAULT_CONFIG.copy()
        
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f) or {}
                config = self._deep_merge(config, user_config)
        else:
            print(f"Warning: Config file {config_path} not found, using defaults")
        
        # Validate required fields
        if not config['mattermost']['webhook_url']:
            raise ValueError("mattermost.webhook_url is required in config.yaml")
        
        return config
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _load_state(self) -> Dict[str, str]:
        """Load state from file."""
        if self.state_file.exists():
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_check': '1970-01-01 00:00:00'}
    
    def _save_state(self, state: Dict[str, str]):
        """Save state to file."""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    
    def _get_new_notifications(self, last_check: str) -> List[Dict[str, Any]]:
        """Fetch new notifications from database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute('''
            SELECT id, type, level, title, message, sources, data, 
                   channel_sent_at, created_at
            FROM notifications 
            WHERE created_at > ?
              AND dismissed_at IS NULL
            ORDER BY created_at
        ''', (last_check,))
        
        notifications = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return notifications
    
    def _should_send_notification(self, notif: Dict[str, Any]) -> bool:
        """Check if notification should be sent based on configuration."""
        # Map notification type to config key
        type_mapping = {
            'task_due_soon': 'dueTasks',
            'task_overdue': 'overdueTasks',
            'project_due_soon': 'dueProjects',
            'project_overdue': 'overdueProjects',
            'task_deferred': 'deferUntil',
        }
        
        config_key = type_mapping.get(notif['type'])
        if not config_key:
            return False
        
        # Check if type is enabled
        if not self.enabled_types.get(config_key, False):
            return False
        
        # Check minimum level
        level_priority = {'info': 0, 'warning': 1, 'error': 2}
        notif_level = level_priority.get(notif['level'], 0)
        min_level = level_priority.get(self.min_level, 1)
        
        return notif_level >= min_level
    
    def _format_notification(self, notif: Dict[str, Any]) -> str:
        """Format notification for Mattermost."""
        emoji_map = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '🔴',
            'success': '✅',
        }
        
        emoji = emoji_map.get(notif['level'], '📌')
        
        type_labels = {
            'task_due_soon': 'Task Due Soon',
            'task_overdue': 'Task Overdue',
            'project_due_soon': 'Project Due Soon',
            'project_overdue': 'Project Overdue',
            'task_deferred': 'Task Activated',
        }
        
        label = type_labels.get(notif['type'], notif['type'])
        
        return f"{emoji} **{label}**\n\n{notif['message']}\n\n🕐 {notif['created_at']}"
    
    def _send_notification(self, notif: Dict[str, Any], dry_run: bool = False) -> bool:
        """Send notification to Mattermost."""
        text = self._format_notification(notif)
        
        if dry_run:
            print(f"[DRY-RUN] Would send:\n{text}\n")
            return True
        
        try:
            response = requests.post(
                self.webhook_url,
                json={'text': text},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"ERROR sending notification: {e}", file=sys.stderr)
            return False
    
    def run(self, verbose: bool = False, dry_run: bool = False):
        """Run the notifier."""
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
        state = self._load_state()
        last_check = state['last_check']
        
        if verbose:
            print(f"[{timestamp}] Last check: {last_check}")
        
        # Fetch new notifications
        notifications = self._get_new_notifications(last_check)
        
        if not notifications:
            if verbose:
                print(f"[{timestamp}] No new notifications")
            print(f"[{timestamp}] OK: no new notifications")
            return
        
        # Filter notifications
        filtered = [n for n in notifications if self._should_send_notification(n)]
        
        if verbose:
            print(f"[{timestamp}] Found {len(notifications)} notifications, {len(filtered)} to send")
        
        # Apply rate limiting
        if self.max_notifications > 0 and len(filtered) > self.max_notifications:
            print(f"[{timestamp}] WARNING: Limiting to {self.max_notifications} notifications (found {len(filtered)})")
            filtered = filtered[:self.max_notifications]
        
        # Send notifications
        sent = 0
        for notif in filtered:
            if self._send_notification(notif, dry_run):
                sent += 1
        
        # Update state
        state['last_check'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        self._save_state(state)
        
        if verbose:
            print(f"\n[{timestamp}] Sent: {sent} notifications")
        else:
            print(f"[{timestamp}] Sent: {sent} notifications")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='tududi-mattermost-notifier: Send tududi notifications to Mattermost'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be sent without actually sending'
    )
    
    args = parser.parse_args()
    
    try:
        notifier = Notifier(args.config)
        notifier.run(verbose=args.verbose, dry_run=args.dry_run)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
