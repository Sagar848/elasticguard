"""
ElasticGuard Notification & Approval System
Sends alerts to Discord/Slack/Email and handles remote approval flow
"""
import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from enum import Enum

import aiosmtplib
import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings

logger = structlog.get_logger()


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"


class ApprovalRequest:
    """Represents a pending approval for a cluster action."""

    def __init__(
        self,
        cluster_id: str,
        cluster_name: str,
        issue_title: str,
        issue_description: str,
        action_description: str,
        api_calls: List[Dict],
        cli_commands: List[str],
        risk_level: str,
        severity: str,
    ):
        self.id = str(uuid.uuid4())
        self.token = secrets.token_urlsafe(32)
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self.issue_title = issue_title
        self.issue_description = issue_description
        self.action_description = action_description
        self.api_calls = api_calls
        self.cli_commands = cli_commands
        self.risk_level = risk_level
        self.severity = severity
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(minutes=settings.APPROVAL_TIMEOUT_MINUTES)
        self.resolved_at: Optional[datetime] = None
        self.resolved_by: Optional[str] = None
        self.resolution_note: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def approve_url(self) -> str:
        return f"http://localhost:3000/approve/{self.id}?token={self.token}&action=approve"

    @property
    def reject_url(self) -> str:
        return f"http://localhost:3000/approve/{self.id}?token={self.token}&action=reject"

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "token": self.token,          # included so UI can approve directly
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster_name,
            "issue_title": self.issue_title,
            "issue_description": self.issue_description,
            "action_description": self.action_description,
            "api_calls": self.api_calls,
            "cli_commands": self.cli_commands,
            "risk_level": self.risk_level,
            "severity": self.severity,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
        }


# In-memory approval store (in production, use Redis/DB)
_pending_approvals: Dict[str, ApprovalRequest] = {}


def get_approval(approval_id: str) -> Optional[ApprovalRequest]:
    return _pending_approvals.get(approval_id)


def store_approval(req: ApprovalRequest):
    _pending_approvals[req.id] = req


def resolve_approval(approval_id: str, status: ApprovalStatus, token: str = "", resolved_by: str = "user") -> Optional[ApprovalRequest]:
    req = _pending_approvals.get(approval_id)
    if not req:
        return None
    # Token check: skip if token is empty (direct UI approval) or token matches
    if token and req.token != token:
        return None
    if req.is_expired:
        req.status = ApprovalStatus.EXPIRED
        return req
    req.status = status
    req.resolved_at = datetime.utcnow()
    req.resolved_by = resolved_by
    return req


def list_pending_approvals() -> List[ApprovalRequest]:
    now = datetime.utcnow()
    result = []
    for req in _pending_approvals.values():
        if req.is_expired and req.status == ApprovalStatus.PENDING:
            req.status = ApprovalStatus.EXPIRED
        result.append(req)
    return sorted(result, key=lambda x: x.created_at, reverse=True)


# ─── Notification Channels ────────────────────────────────────────────────────

class DiscordNotifier:
    """Send alerts to Discord channel via webhook or bot."""

    async def send_approval_request(self, req: ApprovalRequest) -> bool:
        if not settings.DISCORD_WEBHOOK_URL and not settings.DISCORD_BOT_TOKEN:
            return False

        severity_colors = {
            "critical": 0xFF0000,
            "high": 0xFF6600,
            "medium": 0xFFAA00,
            "low": 0x00AAFF,
        }
        color = severity_colors.get(req.severity.lower(), 0x888888)

        apis_text = "\n".join(
            f"`{a.get('method', 'GET')} {a.get('path', '?')}` - {a.get('description', '')}"
            for a in req.api_calls[:3]
        )
        if len(req.api_calls) > 3:
            apis_text += f"\n...and {len(req.api_calls) - 3} more"

        cli_text = "\n".join(f"`{cmd}`" for cmd in req.cli_commands[:3]) if req.cli_commands else ""

        embed = {
            "title": f"⚠️ ElasticGuard: Approval Required",
            "description": f"**Cluster:** {req.cluster_name}\n**Issue:** {req.issue_title}",
            "color": color,
            "fields": [
                {
                    "name": "📋 Issue Description",
                    "value": req.issue_description[:500],
                    "inline": False
                },
                {
                    "name": "🔧 Proposed Action",
                    "value": req.action_description,
                    "inline": False
                },
                {
                    "name": "🌐 Elasticsearch APIs",
                    "value": apis_text or "None",
                    "inline": False
                },
                {
                    "name": "⚠️ Risk Level",
                    "value": f"**{req.risk_level.upper()}**",
                    "inline": True
                },
                {
                    "name": "⏰ Expires",
                    "value": req.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
                    "inline": True
                },
                {
                    "name": "✅ Approve",
                    "value": f"[Click to Approve]({req.approve_url})",
                    "inline": True
                },
                {
                    "name": "❌ Reject",
                    "value": f"[Click to Reject]({req.reject_url})",
                    "inline": True
                },
            ],
            "footer": {"text": f"Approval ID: {req.id}"},
            "timestamp": req.created_at.isoformat(),
        }

        payload = {"embeds": [embed]}

        try:
            import httpx
            if settings.DISCORD_WEBHOOK_URL:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
                    resp.raise_for_status()
                    logger.info("Discord notification sent", approval_id=req.id)
                    return True

            elif settings.DISCORD_BOT_TOKEN and settings.DISCORD_CHANNEL_ID:
                headers = {
                    "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
                    "Content-Type": "application/json",
                }
                url = f"https://discord.com/api/v10/channels/{settings.DISCORD_CHANNEL_ID}/messages"
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    logger.info("Discord bot notification sent", approval_id=req.id)
                    return True

        except Exception as e:
            logger.error("Discord notification failed", error=str(e))

        return False

    async def send_resolution(self, req: ApprovalRequest) -> bool:
        if not settings.DISCORD_WEBHOOK_URL:
            return False
        try:
            import httpx
            status_emoji = "✅" if req.status == ApprovalStatus.APPROVED else "❌"
            payload = {
                "content": f"{status_emoji} **{req.status.value.upper()}**: {req.issue_title} on `{req.cluster_name}` by {req.resolved_by}"
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Discord resolution notification failed", error=str(e))
        return False


class SlackNotifier:
    """Send alerts to Slack channel."""

    async def send_approval_request(self, req: ApprovalRequest) -> bool:
        if not settings.SLACK_WEBHOOK_URL and not settings.SLACK_BOT_TOKEN:
            return False

        severity_emoji = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "🟡",
            "low": "🔵",
        }.get(req.severity.lower(), "❓")

        apis_text = "\n".join(
            f"• `{a.get('method')} {a.get('path')}` - {a.get('description', '')}"
            for a in req.api_calls[:3]
        )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{severity_emoji} ElasticGuard: Action Approval Required"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Cluster:*\n{req.cluster_name}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{req.severity.upper()}"},
                    {"type": "mrkdwn", "text": f"*Issue:*\n{req.issue_title}"},
                    {"type": "mrkdwn", "text": f"*Risk Level:*\n{req.risk_level.upper()}"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Description:*\n{req.issue_description[:300]}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Proposed Action:*\n{req.action_description}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*API Calls:*\n{apis_text or 'None'}"}
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve"},
                        "style": "primary",
                        "url": req.approve_url,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject"},
                        "style": "danger",
                        "url": req.reject_url,
                    }
                ]
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Approval ID: `{req.id}` | Expires: {req.expires_at.strftime('%H:%M UTC')}"}]
            }
        ]

        payload = {"blocks": blocks}

        try:
            import httpx
            if settings.SLACK_WEBHOOK_URL:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(settings.SLACK_WEBHOOK_URL, json=payload)
                    resp.raise_for_status()
                    logger.info("Slack notification sent", approval_id=req.id)
                    return True

            elif settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
                headers = {
                    "Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}",
                    "Content-Type": "application/json",
                }
                payload["channel"] = settings.SLACK_CHANNEL_ID
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://slack.com/api/chat.postMessage",
                        json=payload, headers=headers
                    )
                    resp.raise_for_status()
                    logger.info("Slack bot notification sent", approval_id=req.id)
                    return True

        except Exception as e:
            logger.error("Slack notification failed", error=str(e))

        return False


class EmailNotifier:
    """Send alerts via email with approval links."""

    async def send_approval_request(self, req: ApprovalRequest) -> bool:
        if not settings.SMTP_HOST or not settings.NOTIFICATION_EMAILS:
            return False

        recipients = [e.strip() for e in settings.NOTIFICATION_EMAILS.split(",") if e.strip()]
        if not recipients:
            return False

        severity_color = {
            "critical": "#FF0000",
            "high": "#FF6600",
            "medium": "#FFAA00",
            "low": "#0088CC",
        }.get(req.severity.lower(), "#888888")

        apis_html = "".join(
            f"<li><code>{a.get('method')} {a.get('path')}</code> — {a.get('description', '')}</li>"
            for a in req.api_calls[:5]
        )

        cli_html = "".join(
            f"<li><code>{cmd}</code></li>"
            for cmd in req.cli_commands[:3]
        ) if req.cli_commands else "<li>None</li>"

        html_body = f"""
<!DOCTYPE html>
<html>
<head><style>
  body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
  .card {{ background: white; border-radius: 8px; padding: 24px; max-width: 600px; margin: auto; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  .header {{ background: {severity_color}; color: white; padding: 16px; border-radius: 8px 8px 0 0; margin: -24px -24px 24px; }}
  .header h1 {{ margin: 0; font-size: 20px; }}
  .badge {{ display: inline-block; background: {severity_color}; color: white; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
  .section {{ margin: 16px 0; padding: 12px; background: #f9f9f9; border-radius: 4px; border-left: 3px solid {severity_color}; }}
  .btn {{ display: inline-block; padding: 12px 24px; border-radius: 6px; text-decoration: none; color: white; font-weight: bold; margin: 8px 8px 8px 0; }}
  .btn-approve {{ background: #22c55e; }}
  .btn-reject {{ background: #ef4444; }}
  code {{ background: #eee; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 13px; }}
  ul {{ margin: 8px 0; padding-left: 20px; }}
</style></head>
<body>
<div class="card">
  <div class="header">
    <h1>⚠️ ElasticGuard: Approval Required</h1>
  </div>

  <p><strong>Cluster:</strong> {req.cluster_name} &nbsp; <span class="badge">{req.severity.upper()}</span></p>
  <p><strong>Issue:</strong> {req.issue_title}</p>

  <div class="section">
    <strong>📋 Description</strong>
    <p>{req.issue_description}</p>
  </div>

  <div class="section">
    <strong>🔧 Proposed Action</strong>
    <p>{req.action_description}</p>
  </div>

  <div class="section">
    <strong>🌐 Elasticsearch API Calls</strong>
    <ul>{apis_html}</ul>
  </div>

  <div class="section">
    <strong>💻 CLI Commands (run on server)</strong>
    <ul>{cli_html}</ul>
  </div>

  <div class="section">
    <strong>⚠️ Risk Level:</strong> <span class="badge">{req.risk_level.upper()}</span>
    <br><strong>⏰ Expires:</strong> {req.expires_at.strftime("%Y-%m-%d %H:%M UTC")}
  </div>

  <div style="text-align: center; margin-top: 24px;">
    <a href="{req.approve_url}" class="btn btn-approve">✅ APPROVE</a>
    <a href="{req.reject_url}" class="btn btn-reject">❌ REJECT</a>
  </div>

  <p style="color: #999; font-size: 12px; margin-top: 24px;">
    Approval ID: {req.id}<br>
    You can also manage this in the <a href="http://localhost:3000/approvals">ElasticGuard UI</a>
  </p>
</div>
</body>
</html>
"""

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{req.severity.upper()}] ElasticGuard: {req.issue_title} — Approval Required"
            msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
            msg["To"] = ", ".join(recipients)

            msg.attach(MIMEText(html_body, "html"))

            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASS,
                start_tls=True,
            )

            logger.info("Email notification sent", approval_id=req.id, recipients=recipients)
            return True

        except Exception as e:
            logger.error("Email notification failed", error=str(e))
            return False


class NotificationManager:
    """Orchestrates all notification channels."""

    def __init__(self):
        self.discord = DiscordNotifier()
        self.slack = SlackNotifier()
        self.email = EmailNotifier()

    async def send_approval_request(self, req: ApprovalRequest) -> Dict[str, bool]:
        """Send approval request to all configured channels."""
        store_approval(req)

        results = await asyncio.gather(
            self.discord.send_approval_request(req),
            self.slack.send_approval_request(req),
            self.email.send_approval_request(req),
            return_exceptions=True,
        )

        return {
            "discord": results[0] is True,
            "slack": results[1] is True,
            "email": results[2] is True,
        }

    async def send_resolution_notification(self, req: ApprovalRequest) -> None:
        """Notify that an approval was resolved."""
        await self.discord.send_resolution(req)

    async def send_alert(self, title: str, message: str, severity: str = "high") -> None:
        """Send a simple alert (no approval required)."""
        severity_emoji = {"critical": "🚨", "high": "⚠️", "medium": "🟡", "low": "🔵"}.get(severity, "📢")

        payload = {"content": f"{severity_emoji} **ElasticGuard Alert** | {title}\n{message}"}

        try:
            import httpx
            if settings.DISCORD_WEBHOOK_URL:
                async with httpx.AsyncClient() as client:
                    await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
        except Exception as e:
            logger.warning("Alert send failed", error=str(e))


notification_manager = NotificationManager()
