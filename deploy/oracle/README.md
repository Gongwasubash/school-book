# Deploy to Oracle Cloud Always Free

This app (torch + embeddings + FAISS, ~2GB RAM) fits Oracle's **Always Free ARM tier** (4 OCPU / 24GB RAM, never sleeps, no time limit).

## 1. Create an Oracle Cloud account

1. Go to https://signup.oraclecloud.com
2. Sign up with an email + credit card (required for identity verification — **you are never charged** on Always Free resources)
3. Select your home region (choose the one closest to you; you can't change it later)

## 2. Create the VM

1. Go to **Compute → Instances → Create instance**
2. Name: `aibooks`
3. Image: **Ubuntu 24.04** (Canonical)
4. Shape: click **Edit** → check **"Shape series: Ampere"** → select **VM.Standard.A1.Flex** with **4 OCPU / 24 GB RAM** (stays within Always Free)
5. Add SSH keys: paste your **public key** (or let Oracle generate a key pair and download the private key)
6. Click **Create**

Wait ~2 minutes for the instance to boot. Note the **Public IP address** (e.g. `129.146.xxx.xxx`).

> Network security list: your instance's default VCN allows SSH (22) and HTTP/HTTPS (80/443) inbound. That's all we need.

## 3. Upload the app from Windows

The deployment package is at `C:\Users\acer\AppData\Local\Temp\opencode\space-ai-books-portal\` (code + all textbooks).

Open PowerShell and run (replace IP and key path):

```powershell
scp -r "C:\Users\acer\AppData\Local\Temp\opencode\space-ai-books-portal\*" ubuntu@129.146.xxx.xxx:/opt/aibooks/
```

If you get a permission error for `/opt`, run once over SSH first: `ssh ubuntu@IP "sudo mkdir -p /opt/aibooks && sudo chown ubuntu /opt/aibooks"`

## 4. Provision the server

```bash
ssh ubuntu@129.146.xxx.xxx
sudo bash /opt/aibooks/deploy/oracle/provision.sh
```

This installs Python 3.11 + all deps (CPU torch), sets up a systemd service, firewall, and nginx reverse proxy. It finishes by creating `/opt/aibooks/.env`.

## 5. Add your API keys

```bash
sudo nano /opt/aibooks/.env
```

Paste your real values (get them from your local `E:\rag sys\medical-chatbot-refactored\.env` and `mistral_api_key.json`):

```
HF_TOKEN=...
GROQ_API_KEY=...
QWEN_BASE_URL=...
QWEN_API_KEY=none
QWEN_MODEL_NAME=Qwen/Qwen3.8-27B
MISTRAL_API_KEY=...
TEXTBOOK_ROOT=/opt/aibooks/Nepal Textbooks Grade 1-10
```

Then restart:

```bash
sudo systemctl restart aibooks
```

## 6. Verify

```bash
curl http://127.0.0.1:8000/api/books
```

You should see JSON with the textbook list. From your browser:

```
http://129.146.xxx.xxx/api/books
```

## 7. Add HTTPS (recommended, free)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx
```

You'll need a domain pointing at the IP (e.g. a free one from duckdns.org). Then the frontend can use `https://your-domain/api`.

## 8. Point the frontend at it

In `frontend/src/App.jsx`, change the API base from `http://127.0.0.1:8000` to your server URL, then deploy the frontend to Vercel.

## Useful commands

```bash
sudo systemctl status aibooks      # service status
sudo journalctl -u aibooks -f      # live logs
sudo systemctl restart aibooks     # restart after .env change
```

## Costs

Nothing. Always Free ARM (4 OCPU/24GB) + boot volume (200GB) + internet egress are free for the life of the account.