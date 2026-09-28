# 🤖 Crypto Buy Bot for Telegram

Posts every buy of a coin live to your Telegram group – just enter the **contract address (CA)**.

**Chains:** Solana · **Base** · Ethereum · BSC (auto-detected)

**Features**
- 💵 Buy value in $ and in SOL/ETH, tokens received, market cap, links to buyer + TX
- 🎚️ **Minimum buy** – e.g. only post buys from $50 (`/minbuy 50`)
- 🚀 Custom emoji + "$ per emoji" (bigger buys = longer emoji row)
- 🐳 Whale alert from an amount you choose
- 🏷️ **Custom project name and banner per group** (image, GIF or video)
- 🔗 Buttons: Chart (DexScreener), Buy, Telegram, X, Website
- ⏸ Pause/resume, preview post, settings overview via `/settings`
- 👥 **Several bots at once** – every project can have a bot with its own name and profile picture
- 🔒 Only group admins can change settings
- No API keys needed (data from [GeckoTerminal](https://www.geckoterminal.com))

This is what a post looks like:

```
My Project Buy!
🐳 WHALE BUY! 🐳
🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀

💵 $2.50K (0.71 ETH)
🪙 31.25M TST
👤 Buyer | TX
📊 MC $80.00K
[📈 Chart] [🛒 Buy]
[💬 Telegram] [𝕏 Twitter]
```

---

## 📖 Step-by-step guide

### Step 1 – Create the bot on Telegram (2 minutes)

1. In Telegram, open the chat with **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot`.
3. Enter a **name** (e.g. `Pepe Buy Bot`) – everyone will see it.
4. Enter a **username** ending in `bot` (e.g. `PepeBuyBot`).
5. BotFather sends you a **token** like `7123456789:AAH...`. **Keep it secret!**
6. Optional but recommended – in BotFather:
   - `/setuserpic` → choose your bot → send a profile picture (e.g. the project logo)
   - `/setdescription` → text people see before they start the bot

### Step 2 – Run the bot

The bot has to run on a computer, otherwise it won't post anything. Pick **one** option:

#### Option A – On your PC (for testing)

1. Install [Python 3.10+](https://www.python.org/downloads/) (Windows: tick **"Add Python to PATH"**).
2. Download this code: on GitHub click **"Code" → "Download ZIP"** and unzip it
   (or `git clone https://github.com/glappa/crypto-buy-bot`).
3. In the folder, copy `.env.example` and name the copy **`.env`**.
   Open it and paste your token:
   ```
   BOT_TOKENS=7123456789:AAH...
   ```
4. Open a terminal / command prompt in the folder and run:
   ```bash
   pip install -r requirements.txt
   python bot.py
   ```
5. If you see `@YourBot is running`, everything works. Keep the window open – closing it stops the bot.

#### Option B – 24/7 on a server (recommended)

**Railway (no own server needed):**
1. Fork this repo (or use it directly).
2. On [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo** → pick the repo.
3. **Variables** → `BOT_TOKENS` = your token.
4. Add a **volume** with mount path `/data` (so settings survive restarts).
5. Railway builds the `Dockerfile` automatically and starts the bot.

**Your own Linux server (VPS, e.g. Hetzner ~€4/month) with Docker:**
```bash
git clone https://github.com/glappa/crypto-buy-bot && cd crypto-buy-bot
cp .env.example .env && nano .env           # paste your token
docker build -t buybot .
docker run -d --name buybot --restart unless-stopped --env-file .env -v buybot-data:/data buybot
docker logs -f buybot                       # view logs
```

### Step 3 – Add the bot to your group

1. Open the chat with your bot and press **Start** → button **"➕ Add to group"** → choose the group.
   *(Alternatively: group → Info → Add members → search `@YourBot`.)*
2. **Make the bot an admin** (group → Info → Administrators → Add admin → your bot).
   It needs **no** special permissions – admin status just makes sure it reliably sees all commands and images.
3. The bot greets the group with a short message.

### Step 4 – Set up your coin (in the group, as admin)

```
/setup <CA>
```
Examples:
```
/setup 0x532f27101965dd16442E59d40670FaF5eBB142E4          ← Base (auto-detected)
/setup 0x6982508145454Ce325dDbE47a25d4ec3d2311933 eth      ← force a chain
/setup EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm        ← Solana
```
The bot automatically picks the pool with the most liquidity. Then use `/test` to see what a post looks like.

### Step 5 – Customize

| Command | Example | Effect |
|---|---|---|
| `/minbuy <usd>` | `/minbuy 50` | Only post buys from $50 |
| `/emoji <emoji> [usd]` | `/emoji 🚀 20` | 1 🚀 per $20 (max. 50) |
| `/name <text>` | `/name Pepe Army` | Project name in posts (empty `/name` = reset) |
| `/media` | *reply to an image/GIF/video* | Banner attached to every buy (`/media off` = remove) |
| `/link <tg\|x\|web\|buy> <url>` | `/link x https://x.com/pepe` | Button below posts (`off` instead of URL = remove) |
| `/whale <usd>` | `/whale 1000` | 🐳 alert from $1000 (`0` = off) |
| `/pause` · `/resume` | | Pause / resume posts |
| `/settings` | | Show all settings |
| `/test` | | Post the latest real buy as a preview |
| `/stop` | | Stop tracking and delete settings |
| `/help` | | Command overview |

**Setting a banner:** send an image/GIF/video to the group → **reply** to it with `/media`.
Or type `/media` as the caption when sending it.

---

## 🎨 Custom name & picture per project

Good to know: on Telegram a bot has **the same** name and profile picture everywhere –
it's technically impossible to change them per group. This bot solves it on two levels:

**1. Per group (automatic, one bot for everyone):**
Every group has its **own** settings: project name (`/name`), banner (`/media`), emoji, links, minimum buy, etc.
So in every group the posts look fully branded for that project.

**2. A separate bot per project (own name + profile picture):**
If the **bot itself** should be called e.g. "Pepe Buy Bot" with the Pepe logo:
1. Create a new bot for the project with @BotFather (step 1) and set its name/picture there.
2. Add the new token to `.env`, separated by a comma:
   ```
   BOT_TOKENS=111111:AAA...,222222:BBB...,333333:CCC...
   ```
3. Restart. **One** server now runs all bots at once – each with its own name, picture and groups.

To change the name or picture later: `/setname` or `/setuserpic` in BotFather.

---

## ❓ Troubleshooting

| Problem | Solution |
|---|---|
| Bot doesn't react to commands | Is `python bot.py` still running? Make the bot an admin. Try sending the command as `/setup@YourBot …`. |
| "No pool found" | Check the CA. Specify the chain: `/setup <CA> base`. Brand-new coins may take a few minutes to show up on GeckoTerminal. |
| "Only admins …" | Only group admins can configure the bot. |
| Buys arrive with a delay | Normal: the bot checks every ~15 s. Adjust `POLL_SECONDS` in `.env` (not below 10). |
| Market cap missing | GeckoTerminal doesn't know the token's supply yet – run `/setup` again later. |

**Notes**
- Only the pool with the most liquidity is tracked. Buys through other pools of the same coin won't show up.
- The free GeckoTerminal API allows ~30 requests/minute. Each coin uses one request per round – with many coins the intervals get longer automatically.

## 🗂️ Files

| File | Content |
|---|---|
| `bot.py` | Telegram commands and startup |
| `tracker.py` | Fetches and posts buys |
| `db.py` | Settings per group (SQLite) |
| `.env.example` | Template for token & options |
| `Dockerfile` | For servers/Railway |
