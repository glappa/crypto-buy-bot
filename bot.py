"""Telegram Buy Bot – postet Käufe eines Coins (Solana, Base, ETH, BSC) in Gruppen."""
import asyncio
import html
import logging
import os
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters

import db
import tracker

log = logging.getLogger("buybot")
Ctx = ContextTypes.DEFAULT_TYPE

HELP = """<b>🤖 Buy Bot – Befehle</b> (Einstellungen nur für Admins)

/setup &lt;CA&gt; [chain] – Coin tracken (solana, base, eth, bsc – sonst automatisch)
/minbuy &lt;usd&gt; – nur Käufe ab diesem Wert posten
/emoji &lt;emoji&gt; [usd] – Emoji und $ pro Emoji (Standard 🟢 je $10)
/name &lt;text&gt; – Projektname in den Posts
/media – als Antwort auf Bild/GIF/Video: Banner setzen (/media off = entfernen)
/link &lt;tg|x|web|buy&gt; &lt;url|off&gt; – Buttons unter den Posts
/whale &lt;usd&gt; – 🐳-Hinweis ab diesem Wert (0 = aus)
/pause · /resume – Posts pausieren / fortsetzen
/settings – aktuelle Einstellungen
/test – letzten echten Kauf als Beispiel posten
/stop – Tracking beenden"""


def key(update: Update, ctx: Ctx) -> tuple[int, int]:
    return ctx.bot.id, update.effective_chat.id


def cfg(update: Update, ctx: Ctx) -> dict:
    return db.get(key(update, ctx))


def save(update: Update, ctx: Ctx, **changes):
    db.save(key(update, ctx), {**cfg(update, ctx), **changes})


async def reply(update: Update, text: str) -> Message:
    return await update.effective_message.reply_html(text, disable_web_page_preview=True)


def num(args: list[str] | None, i: int = 0) -> float | None:
    try:
        return max(0.0, float(args[i].replace(",", ".").lstrip("$")))
    except (IndexError, TypeError, ValueError):
        return None


def admin(fn):
    """Lässt nur Gruppen-Admins (oder den Privatchat) Einstellungen ändern."""
    async def wrapper(update: Update, ctx: Ctx):
        chat, msg = update.effective_chat, update.effective_message
        if chat.type != "private" and not (msg.sender_chat and msg.sender_chat.id == chat.id):
            member = await chat.get_member(update.effective_user.id)
            if member.status not in ("administrator", "creator"):
                return await reply(update, "⛔ Nur Admins können den Bot einstellen.")
        return await fn(update, ctx)
    return wrapper


async def start(update: Update, ctx: Ctx):
    button = InlineKeyboardButton("➕ Zu Gruppe hinzufügen", url=f"https://t.me/{ctx.bot.username}?startgroup=true")
    await update.effective_message.reply_html(HELP, reply_markup=InlineKeyboardMarkup([[button]]))


@admin
async def setup(update: Update, ctx: Ctx):
    if not ctx.args:
        return await reply(update, "Nutzung: /setup &lt;CA&gt; [solana|base|eth|bsc]")
    net = ctx.args[1].lower() if len(ctx.args) > 1 else None
    net = tracker.ALIASES.get(net, net)
    if net and net not in tracker.NETS:
        return await reply(update, f"Unbekannte Chain. Möglich: {', '.join(tracker.NETS)}")
    msg = await reply(update, "🔎 Suche Token …")
    try:
        found = await tracker.find_token(ctx.args[0], net)
    except Exception as err:
        log.warning("Suche fehlgeschlagen: %s", err)
        found = None
    if not found:
        return await msg.edit_text("❌ Kein Pool gefunden. CA prüfen oder Chain angeben, z. B. /setup &lt;CA&gt; base",
                                   parse_mode="HTML")
    save(update, ctx, **found)
    await msg.edit_text(
        f"✅ Tracke jetzt <b>{html.escape(found['name'])}</b> (${html.escape(found['symbol'])}) auf {tracker.NETS[found['net']][0]}\n"
        f"Pool: <code>{found['pool']}</code>\n\nAnpassen mit /minbuy, /emoji, /name, /media, /link", parse_mode="HTML")


def number_cmd(name: str, field: str, done: str):
    @admin
    async def cmd(update: Update, ctx: Ctx):
        value = num(ctx.args)
        if value is None:
            return await reply(update, f"Nutzung: /{name} &lt;usd&gt;, z. B. /{name} 50")
        save(update, ctx, **{field: value})
        await reply(update, done.format(value))
    return cmd


@admin
async def emoji(update: Update, ctx: Ctx):
    if not ctx.args or len(ctx.args[0]) > 10:
        return await reply(update, "Nutzung: /emoji 🚀 [usd pro Emoji]")
    changes = {"emoji": ctx.args[0]} | ({"step": step} if (step := num(ctx.args, 1)) else {})
    save(update, ctx, **changes)
    await reply(update, f"✅ {changes['emoji']} je ${cfg(update, ctx)['step']:g}")


@admin
async def name(update: Update, ctx: Ctx):
    title = " ".join(ctx.args)[:64] or None
    save(update, ctx, title=title)
    await reply(update, f"✅ Name: <b>{html.escape(title)}</b>" if title else "✅ Name zurückgesetzt")


def media_of(msg: Message | None) -> dict | None:
    if msg and msg.animation:
        return {"type": "animation", "id": msg.animation.file_id}
    if msg and msg.photo:
        return {"type": "photo", "id": msg.photo[-1].file_id}
    if msg and msg.video:
        return {"type": "video", "id": msg.video.file_id}
    return None


@admin
async def media(update: Update, ctx: Ctx):
    msg = update.effective_message
    if ctx.args and ctx.args[0] == "off":
        save(update, ctx, media=None)
        return await reply(update, "✅ Banner entfernt")
    found = media_of(msg) or media_of(msg.reply_to_message)
    if not found:
        return await reply(update, "Antworte mit /media auf ein Bild, GIF oder Video (oder schicke es mit /media als Text).")
    save(update, ctx, media=found)
    await reply(update, "✅ Banner gespeichert – wird bei jedem Kauf mitgeschickt.")


@admin
async def link(update: Update, ctx: Ctx):
    args = ctx.args or []
    if len(args) != 2 or args[0] not in tracker.LINKS or not (args[1] == "off" or args[1].startswith("https://")):
        return await reply(update, "Nutzung: /link &lt;tg|x|web|buy&gt; &lt;https://…|off&gt;")
    kind, url = args
    links = {k: v for k, v in cfg(update, ctx)["links"].items() if k != kind} | ({} if url == "off" else {kind: url})
    save(update, ctx, links=links)
    await reply(update, f"✅ Button {tracker.LINKS[kind]} {'entfernt' if url == 'off' else 'gesetzt'}")


def pause_cmd(paused: bool):
    @admin
    async def cmd(update: Update, ctx: Ctx):
        save(update, ctx, paused=paused)
        await reply(update, "⏸ Pausiert" if paused else "▶️ Läuft wieder")
    return cmd


async def settings(update: Update, ctx: Ctx):
    c = cfg(update, ctx)
    if not c.get("pool"):
        return await reply(update, "Noch kein Coin eingerichtet → /setup &lt;CA&gt;")
    links = ", ".join(tracker.LINKS[k] for k in c["links"]) or "–"
    whale = f"ab ${c['whale']:g}" if c["whale"] else "aus"
    await reply(update, (
        f"<b>⚙️ Einstellungen</b>\n\nCoin: {html.escape(c['name'])} (${html.escape(c['symbol'])}) · {tracker.NETS[c['net']][0]}\n"
        f"CA: <code>{c['ca']}</code>\nName: {html.escape(c['title'] or '–')}\n"
        f"Min. Kauf: ${c['min_buy']:g}\nEmoji: {c['emoji']} je ${c['step']:g}\n"
        f"Whale: {whale}\nBanner: {'ja' if c['media'] else 'nein'}\n"
        f"Links: {links}\nStatus: {'⏸ pausiert' if c['paused'] else '▶️ aktiv'}"))


@admin
async def test(update: Update, ctx: Ctx):
    c = cfg(update, ctx)
    if not c.get("pool"):
        return await reply(update, "Noch kein Coin eingerichtet → /setup &lt;CA&gt;")
    buys = [t["attributes"] for t in await tracker.trades(c["net"], c["pool"]) if tracker.is_buy(c, t["attributes"])]
    if not buys:
        return await reply(update, "Keine Käufe in den letzten 24 h gefunden.")
    await tracker.send(ctx.bot, key(update, ctx), c, tracker.render(c, buys[0]))


@admin
async def stop(update: Update, ctx: Ctx):
    db.delete(key(update, ctx))
    await reply(update, "🛑 Tracking beendet, Einstellungen gelöscht.")


async def membership(update: Update, ctx: Ctx):
    """Begrüßt beim Hinzufügen, räumt beim Entfernen auf."""
    m = update.my_chat_member
    was_in = m.old_chat_member.status not in ("left", "kicked")
    now_in = m.new_chat_member.status not in ("left", "kicked")
    if now_in and not was_in:
        await ctx.bot.send_message(m.chat.id, "👋 Danke! Ein Admin kann mich mit /setup <CA> einrichten. Alle Befehle: /help")
    elif was_in and not now_in:
        db.delete((ctx.bot.id, m.chat.id))


COMMANDS = [
    ("setup", setup, "Coin per CA tracken"),
    ("minbuy", number_cmd("minbuy", "min_buy", "✅ Poste nur Käufe ab ${:g}"), "Mindestkauf in $"),
    ("emoji", emoji, "Emoji und $ pro Emoji"),
    ("name", name, "Projektname in den Posts"),
    ("media", media, "Banner (Bild/GIF/Video) setzen"),
    ("link", link, "Link-Buttons setzen"),
    ("whale", number_cmd("whale", "whale", "✅ Whale-Hinweis ab ${:g} (0 = aus)"), "Whale-Grenze in $"),
    ("pause", pause_cmd(True), "Posts pausieren"),
    ("resume", pause_cmd(False), "Posts fortsetzen"),
    ("settings", settings, "Einstellungen anzeigen"),
    ("test", test, "Beispiel-Post senden"),
    ("stop", stop, "Tracking beenden"),
    ("help", start, "Hilfe"),
]


def build(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    for command, handler, _ in COMMANDS:
        app.add_handler(CommandHandler(command, handler))
    media_filter = (filters.PHOTO | filters.ANIMATION | filters.VIDEO) & filters.CaptionRegex(r"^/media\b")
    app.add_handler(MessageHandler(media_filter, media))
    app.add_handler(ChatMemberHandler(membership))
    return app


async def main():
    load_dotenv()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    tokens = [t.strip() for t in os.getenv("BOT_TOKENS", os.getenv("BOT_TOKEN", "")).split(",") if t.strip()]
    if not tokens:
        raise SystemExit("BOT_TOKENS fehlt – siehe .env.example")
    db.init(os.getenv("DB_PATH", "buybot.db"))
    async with AsyncExitStack() as stack:
        bots = {}
        for token in tokens:  # mehrere Tokens = mehrere Bots mit eigenem Namen/Bild
            app = await stack.enter_async_context(build(token))
            await app.start()
            stack.push_async_callback(app.stop)
            await app.updater.start_polling(drop_pending_updates=True)
            stack.push_async_callback(app.updater.stop)
            await app.bot.set_my_commands([BotCommand(c, d) for c, _, d in COMMANDS])
            bots[app.bot.id] = app.bot
            log.info("@%s läuft", app.bot.username)
        await tracker.run(bots, float(os.getenv("POLL_SECONDS", "15")))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
