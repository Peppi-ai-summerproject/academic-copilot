# Telegram Webhook Deployment Setup

This document describes how HTTPS and Nginx reverse proxy were configured for the AI Academic Copilot Telegram webhook on the CSC virtual machine.

## Server

- Instance name: `academic-copilot-dev`
- Floating IP: `86.50.229.15`
- Public hostname: `academic-copilot.86-50-229-15.sslip.io`
- Backend port: `8000`
- Public HTTPS port: `443`

## Architecture

```text
Telegram
   |
   | HTTPS
   v
Nginx :443
   |
   | Reverse proxy
   v
FastAPI :8000


##  More

CSC Security Group Rules

The following inbound TCP ports must be open:

Port	Purpose
22	SSH
80	HTTP and Let's Encrypt validation
443	HTTPS
8000	Temporary direct backend access during development

For production, port 8000 should be removed from public ingress after confirming that all traffic passes through Nginx.

Install Nginx
sudo apt update
sudo apt install nginx -y
sudo systemctl enable nginx
sudo systemctl start nginx

Verify:

sudo systemctl status nginx
Nginx Reverse Proxy

Create:

/etc/nginx/sites-available/academic-copilot

Configuration:

server {
    listen 80;
    listen [::]:80;

    server_name academic-copilot.86-50-229-15.sslip.io;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}

Enable the configuration:

sudo ln -s /etc/nginx/sites-available/academic-copilot \
  /etc/nginx/sites-enabled/academic-copilot

sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
HTTPS Certificate

Install Certbot:

sudo apt install certbot python3-certbot-nginx -y

Request and configure the certificate:

sudo certbot --nginx \
  -d academic-copilot.86-50-229-15.sslip.io

The certificate files are stored under:

/etc/letsencrypt/live/academic-copilot.86-50-229-15.sslip.io/

Verify automatic renewal:

sudo certbot renew --dry-run
Verification

Backend:

https://academic-copilot.86-50-229-15.sslip.io

Swagger:

https://academic-copilot.86-50-229-15.sslip.io/docs

Useful checks:

sudo nginx -t
curl -I https://academic-copilot.86-50-229-15.sslip.io
sudo certbot certificates
Telegram Webhook URL

The planned webhook endpoint is:

https://academic-copilot.86-50-229-15.sslip.io/api/v1/telegram/webhook

The webhook must only be registered after the FastAPI endpoint has been implemented and tested.

Development Mode

Polling may be used during local development.

Webhook mode should be used on the CSC deployment.

Only one update delivery method should be active at a time. Stop polling before registering the production webhook.

Security Notes
Never commit the Telegram bot token.
Never commit files from /etc/letsencrypt.
Use a webhook secret token to validate Telegram requests.
Remove public access to port 8000 after the Nginx path is verified.

```bash
git add docs/deployment/telegram-webhook-setup.md
git commit -m "docs(deployment): document Telegram webhook infrastructure"
