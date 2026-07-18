# Week 2 Research: Telegram Bot API

## Overview

This research document covers issue #12: Study Telegram Bot API.

The goal is to understand Telegram Bot API fundamentals and how webhooks can be used as the primary user interface for the academic copilot.

## Objectives

- Learn Bot API fundamentals
- Understand webhooks
- Explore messaging workflow

## Acceptance Criteria

- Bot architecture documented
- Basic example prepared
- Research summary completed

## What is Telegram Bot API?

Telegram Bot API lets developers create bots that interact with users through Telegram messaging.

Key ideas:

- Bots communicate over HTTPS.
- Bots can receive updates via polling or webhooks.
- Bots send messages, receive commands, and respond to user input.

## Webhook workflow

1. Telegram sends an update to the bot webhook URL.
2. The backend receives the update payload.
3. The bot processes the update.
4. The backend optionally responds or calls additional services.
5. The bot sends messages back to the user.

## Why webhooks?

- Webhooks are more efficient than polling.
- Telegram delivers updates immediately.
- The backend can scale with standard HTTP requests.

## Repo implementation

The repository contains a webhook demo:

- `backend/app/telegram/webhook_demo.py` defines the webhook endpoint.
- `backend/tests/test_telegram_webhook.py` verifies webhook receipt.

This implementation shows the minimum viable webhook flow:

- Accept an incoming update
- Verify it contains `update_id`
- Return a simple acknowledgement

## Use cases for Academic Copilot

- Receive student questions from Telegram
- Send course updates, reminders, and tutoring notes
- Use Telegram as the primary user interface for chat and commands

## Key findings

- Telegram webhooks are suitable for realtime notifications and conversational workflows.
- The bot architecture should separate Telegram handling from application logic.
- The backend can use Telegram updates to trigger MCP tool calls or database queries.

## Conclusions

Telegram Bot API is a valid interface for the academic copilot.
The current webhook demo is a strong base, and the next step is to connect it with academic services and agent workflows.
