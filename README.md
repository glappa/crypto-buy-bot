# 🤖 Telegram Buy Bot

Postet jeden Kauf eines Coins live in deine Telegram-Gruppe – einfach die **Contract Address (CA)** eingeben.

**Chains:** Solana · **Base** · Ethereum · BSC (wird automatisch erkannt)

**Features**
- 💵 Kaufwert in $ und in SOL/ETH, erhaltene Tokens, Market Cap, Links zu Käufer + TX
- 🎚️ **Mindestkauf** – z. B. erst ab $50 posten (`/minbuy 50`)
- 🚀 Eigenes Emoji + „$ pro Emoji“ (größere Käufe = längere Emoji-Reihe)
- 🐳 Whale-Hinweis ab einem frei wählbaren Betrag
- 🏷️ **Pro Gruppe eigener Projektname und eigenes Banner** (Bild, GIF oder Video)
- 🔗 Buttons: Chart (DexScreener), Kaufen, Telegram, X, Website
- ⏸ Pausieren/Fortsetzen, Test-Post, Einstellungen per `/settings`
- 👥 **Mehrere Bots gleichzeitig** – jedes Projekt kann einen Bot mit eigenem Namen und Profilbild haben
- 🔒 Nur Gruppen-Admins können Einstellungen ändern
- Keine API-Keys nötig (Daten von [GeckoTerminal](https://www.geckoterminal.com))

So sieht ein Post aus:

```
Mein Projekt Buy!
🐳 WHALE BUY! 🐳
🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀

💵 $2.50K (0.71 ETH)
🪙 31.25M TST
👤 Käufer | TX
📊 MC $80.00K
[📈 Chart] [🛒 Kaufen]
[💬 Telegram] [𝕏 Twitter]
```

---

## 📖 Schritt-für-Schritt-Anleitung

### Schritt 1 – Bot bei Telegram erstellen (2 Minuten)

1. Öffne in Telegram den Chat mit **[@BotFather](https://t.me/BotFather)**.
2. Schreibe `/newbot`.
3. Gib einen **Namen** ein (z. B. `Pepe Buy Bot`) – den sehen alle.
4. Gib einen **Username** ein, der auf `bot` endet (z. B. `PepeBuyBot`).
5. BotFather schickt dir einen **Token** wie `7123456789:AAH...`. **Geheim halten!**
6. Optional, aber empfohlen – im BotFather:
   - `/setuserpic` → Bot wählen → Profilbild (z. B. Projekt-Logo) schicken
   - `/setdescription` → Text, den man sieht, bevor man den Bot startet

### Schritt 2 – Bot starten

Der Bot muss auf einem Rechner laufen, sonst postet er nichts. Wähle **eine** Variante:

#### Variante A – Auf deinem PC (zum Testen)

1. [Python 3.10+](https://www.python.org/downloads/) installieren (Windows: Haken bei **„Add Python to PATH“** setzen).
2. Diesen Code herunterladen: auf GitHub oben **„Code“ → „Download ZIP“** und entpacken
   (oder `git clone https://github.com/glappa/crypto-buy-bot`).
3. Im Ordner die Datei `.env.example` kopieren und die Kopie **`.env`** nennen.
   Öffnen und deinen Token eintragen:
   ```
   BOT_TOKENS=7123456789:AAH...
   ```
4. Terminal/Eingabeaufforderung im Ordner öffnen und ausführen:
   ```bash
   pip install -r requirements.txt
   python bot.py
   ```
5. Erscheint `@DeinBot läuft`, ist alles gut. Fenster offen lassen – schließt du es, stoppt der Bot.

#### Variante B – 24/7 auf einem Server (empfohlen)

**Railway (ohne eigenen Server):**
1. Dieses Repo forken (oder direkt nutzen).
2. Auf [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo** → Repo wählen.
3. **Variables** → `BOT_TOKENS` = dein Token.
4. **Volume** hinzufügen, Mount-Pfad `/data` (damit Einstellungen nach Neustarts erhalten bleiben).
5. Railway baut das `Dockerfile` automatisch und startet den Bot.

**Eigener Linux-Server (VPS, z. B. Hetzner ~4 €/Monat) mit Docker:**
```bash
git clone https://github.com/glappa/crypto-buy-bot && cd crypto-buy-bot
cp .env.example .env && nano .env           # Token eintragen
docker build -t buybot .
docker run -d --name buybot --restart unless-stopped --env-file .env -v buybot-data:/data buybot
docker logs -f buybot                       # Logs ansehen
```

### Schritt 3 – Bot in die Gruppe einladen

1. Öffne den Chat mit deinem Bot und drücke **Start** → Button **„➕ Zu Gruppe hinzufügen“** → Gruppe wählen.
   *(Alternativ: Gruppe → Info → Mitglieder hinzufügen → `@DeinBot` suchen.)*
2. **Bot zum Admin machen** (Gruppe → Info → Administratoren → Admin hinzufügen → Bot).
   Er braucht **keine** besonderen Rechte – Admin sorgt nur dafür, dass er alle Befehle und Bilder zuverlässig sieht.
3. Der Bot begrüßt die Gruppe mit einer kurzen Nachricht.

### Schritt 4 – Coin einrichten (in der Gruppe, als Admin)

```
/setup <CA>
```
Beispiele:
```
/setup 0x532f27101965dd16442E59d40670FaF5eBB142E4          ← Base (wird erkannt)
/setup 0x6982508145454Ce325dDbE47a25d4ec3d2311933 eth      ← Chain erzwingen
/setup EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm        ← Solana
```
Der Bot sucht automatisch den Pool mit der meisten Liquidität. Danach mit `/test` prüfen, wie ein Post aussieht.

### Schritt 5 – Anpassen

| Befehl | Beispiel | Wirkung |
|---|---|---|
| `/minbuy <usd>` | `/minbuy 50` | Nur Käufe ab $50 posten |
| `/emoji <emoji> [usd]` | `/emoji 🚀 20` | 1 🚀 pro $20 (max. 50) |
| `/name <text>` | `/name Pepe Army` | Projektname im Post (`/name` leer = zurücksetzen) |
| `/media` | *Antwort auf Bild/GIF/Video* | Banner, das bei jedem Kauf mitkommt (`/media off` = entfernen) |
| `/link <tg\|x\|web\|buy> <url>` | `/link x https://x.com/pepe` | Button unter den Posts (`off` statt URL = entfernen) |
| `/whale <usd>` | `/whale 1000` | 🐳-Hinweis ab $1000 (`0` = aus) |
| `/pause` · `/resume` | | Posts anhalten / weiter |
| `/settings` | | Alle Einstellungen anzeigen |
| `/test` | | Letzten echten Kauf als Beispiel posten |
| `/stop` | | Tracking beenden und Einstellungen löschen |
| `/help` | | Befehlsübersicht |

**Banner setzen:** Bild/GIF/Video in die Gruppe schicken → darauf **antworten** mit `/media`.
Oder direkt beim Senden `/media` als Bildunterschrift schreiben.

---

## 🎨 Eigener Name & eigenes Bild pro Projekt

Wichtig zu wissen: Bei Telegram hat ein Bot **überall denselben** Namen und dasselbe Profilbild –
das lässt sich technisch nicht pro Gruppe ändern. Dieser Bot löst das auf zwei Ebenen:

**1. Pro Gruppe (automatisch, ein Bot für alle):**
Jede Gruppe hat ihre **eigenen** Einstellungen: Projektname (`/name`), Banner (`/media`), Emoji, Links, Mindestkauf usw.
Die Posts sehen damit in jeder Gruppe komplett nach dem jeweiligen Projekt aus.

**2. Eigener Bot pro Projekt (eigener Name + Profilbild):**
Soll auch der **Bot selbst** z. B. „Pepe Buy Bot“ mit Pepe-Logo heißen:
1. Für das Projekt bei @BotFather einen neuen Bot erstellen (Schritt 1) und dort Name/Bild setzen.
2. Den neuen Token mit Komma in die `.env` eintragen:
   ```
   BOT_TOKENS=111111:AAA...,222222:BBB...,333333:CCC...
   ```
3. Bot neu starten. **Ein** Server betreibt jetzt alle Bots gleichzeitig – jeder mit eigenem Namen, Bild und eigenen Gruppen.

Name oder Bild später ändern: im BotFather `/setname` bzw. `/setuserpic`.

---

## ❓ Probleme?

| Problem | Lösung |
|---|---|
| Bot reagiert nicht auf Befehle | Läuft `python bot.py` noch? Bot zum Admin machen. Befehl evtl. als `/setup@DeinBot …` senden. |
| „Kein Pool gefunden“ | CA prüfen. Chain angeben: `/setup <CA> base`. Ganz neue Coins brauchen evtl. ein paar Minuten, bis GeckoTerminal sie kennt. |
| „Nur Admins …“ | Nur Gruppen-Admins dürfen den Bot einstellen. |
| Käufe kommen mit Verzögerung | Normal: Der Bot fragt alle ~15 s ab. `POLL_SECONDS` in der `.env` anpassen (nicht unter 10). |
| Market Cap fehlt | GeckoTerminal kennt die Supply des Tokens noch nicht – `/setup` später erneut ausführen. |

**Hinweise**
- Getrackt wird der Pool mit der meisten Liquidität. Käufe über andere Pools desselben Coins erscheinen nicht.
- Die kostenlose GeckoTerminal-API erlaubt ~30 Anfragen/Minute. Pro Coin wird eine Anfrage pro Durchlauf gestellt – bei vielen Coins werden die Abstände automatisch größer.

## 🗂️ Dateien

| Datei | Inhalt |
|---|---|
| `bot.py` | Telegram-Befehle und Start |
| `tracker.py` | Käufe abfragen und posten |
| `db.py` | Einstellungen pro Gruppe (SQLite) |
| `.env.example` | Vorlage für Token & Optionen |
| `Dockerfile` | Für Server/Railway |
