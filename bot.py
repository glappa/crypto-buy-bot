"""Telegram Buy Bot – posts buys of a coin (Solana, Base, ETH, BSC) to groups."""
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

HELP = """<b>🤖 Buy Bot – Commands</b> (settings are admin-only)

/setup &lt;CA&gt; [chain] – track a coin (solana, base, eth, bsc – auto-detected otherwise)
/minbuy &lt;usd&gt; – only post buys from this amount
/emoji &lt;emoji&gt; [usd] – emoji and $ per emoji (default 🟢 per $10)
/name &lt;text&gt; – project name shown in posts
/media – reply to an image/GIF/video: set banner (/media off = remove)
/link &lt;tg|x|web|buy&gt; &lt;url|off&gt; – links below posts
/whale &lt;usd&gt; – 🐳 alert from this amount (0 = off)
/sells – also post sells 🔴 (toggle, /sells on|off)
/pause · /resume – pause / resume posts
/settings – current settings
/test – post the latest real buy as a preview
/stop – stop tracking"""


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
    """Only group admins (or a private chat) may change settings."""
    async def wrapper(update: Update, ctx: Ctx):
        chat, msg = update.effective_chat, update.effective_message
        if chat.type != "private" and not (msg.sender_chat and msg.sender_chat.id == chat.id):
            member = await chat.get_member(update.effective_user.id)
            if member.status not in ("administrator", "creator"):
                return await reply(update, "⛔ Only admins can configure the bot.")
        return await fn(update, ctx)
    return wrapper


async def start(update: Update, ctx: Ctx):
    button = InlineKeyboardButton("➕ Add to group", url=f"https://t.me/{ctx.bot.username}?startgroup=true")
    await update.effective_message.reply_html(HELP, reply_markup=InlineKeyboardMarkup([[button]]))


@admin
async def setup(update: Update, ctx: Ctx):
    if not ctx.args:
        return await reply(update, "Usage: /setup &lt;CA&gt; [solana|base|eth|bsc]")
    net = ctx.args[1].lower() if len(ctx.args) > 1 else None
    net = tracker.ALIASES.get(net, net)
    if net and net not in tracker.NETS:
        return await reply(update, f"Unknown chain. Supported: {', '.join(tracker.NETS)}")
    msg = await reply(update, "🔎 Searching token …")
    try:
        found = await tracker.find_token(ctx.args[0], net)
    except Exception as err:
        log.warning("Search failed: %s", err)
        found = None
    if not found:
        return await msg.edit_text("❌ No pool found. Check the CA or specify the chain, e.g. /setup &lt;CA&gt; base",
                                   parse_mode="HTML")
    save(update, ctx, **found)
    await msg.edit_text(
        f"✅ Now tracking <b>{html.escape(found['name'])}</b> (${html.escape(found['symbol'])}) on {tracker.NETS[found['net']]['name']}\n"
        f"Pool: <code>{found['pool']}</code>\n\nCustomize with /minbuy, /emoji, /name, /media, /link", parse_mode="HTML")


def number_cmd(name: str, field: str, done: str):
    @admin
    async def cmd(update: Update, ctx: Ctx):
        value = num(ctx.args)
        if value is None:
            return await reply(update, f"Usage: /{name} &lt;usd&gt;, e.g. /{name} 50")
        save(update, ctx, **{field: value})
        await reply(update, done.format(value))
    return cmd


@admin
async def emoji(update: Update, ctx: Ctx):
    if not ctx.args or len(ctx.args[0]) > 10:
        return await reply(update, "Usage: /emoji 🚀 [usd per emoji]")
    changes = {"emoji": ctx.args[0]} | ({"step": step} if (step := num(ctx.args, 1)) else {})
    save(update, ctx, **changes)
    await reply(update, f"✅ {changes['emoji']} per ${cfg(update, ctx)['step']:g}")


@admin
async def name(update: Update, ctx: Ctx):
    title = " ".join(ctx.args)[:64] or None
    save(update, ctx, title=title)
    await reply(update, f"✅ Name: <b>{html.escape(title)}</b>" if title else "✅ Name reset")


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
        return await reply(update, "✅ Banner removed")
    found = media_of(msg) or media_of(msg.reply_to_message)
    if not found:
        return await reply(update, "Reply with /media to an image, GIF or video (or send it with /media as caption).")
    save(update, ctx, media=found)
    await reply(update, "✅ Banner saved – it will be attached to every buy.")


@admin
async def link(update: Update, ctx: Ctx):
    args = ctx.args or []
    if len(args) != 2 or args[0] not in tracker.LINKS or not (args[1] == "off" or args[1].startswith("https://")):
        return await reply(update, "Usage: /link &lt;tg|x|web|buy&gt; &lt;https://…|off&gt;")
    kind, url = args
    links = {k: v for k, v in cfg(update, ctx)["links"].items() if k != kind} | ({} if url == "off" else {kind: url})
    save(update, ctx, links=links)
    await reply(update, f"✅ Link {tracker.LINKS[kind]} {'removed' if url == 'off' else 'set'}")


@admin
async def sells(update: Update, ctx: Ctx):
    arg = (ctx.args or [""])[0].lower()
    on = {"on": True, "off": False}.get(arg, not cfg(update, ctx)["sells"])
    save(update, ctx, sells=on)
    await reply(update, "🔴 Sells will be posted too" if on else "🟢 Only buys will be posted")


def pause_cmd(paused: bool):
    @admin
    async def cmd(update: Update, ctx: Ctx):
        save(update, ctx, paused=paused)
        await reply(update, "⏸ Paused" if paused else "▶️ Running again")
    return cmd


async def settings(update: Update, ctx: Ctx):
    c = cfg(update, ctx)
    if not c.get("pool"):
        return await reply(update, "No coin set up yet → /setup &lt;CA&gt;")
    links = ", ".join(tracker.LINKS[k] for k in c["links"]) or "–"
    whale = f"from ${c['whale']:g}" if c["whale"] else "off"
    await reply(update, (
        f"<b>⚙️ Settings</b>\n\nCoin: {html.escape(c['name'])} (${html.escape(c['symbol'])}) · {tracker.NETS[c['net']]['name']}\n"
        f"CA: <code>{c['ca']}</code>\nName: {html.escape(c['title'] or '–')}\n"
        f"Min. buy: ${c['min_buy']:g}\nEmoji: {c['emoji']} per ${c['step']:g}\n"
        f"Whale: {whale}\nSells: {'on' if c['sells'] else 'off'}\nBanner: {'yes' if c['media'] else 'no'}\n"
        f"Links: {links}\nStatus: {'⏸ paused' if c['paused'] else '▶️ active'}"))


@admin
async def test(update: Update, ctx: Ctx):
    c = cfg(update, ctx)
    if not c.get("pool"):
        return await reply(update, "No coin set up yet → /setup &lt;CA&gt;")
    try:
        buys = [t["attributes"] for t in await tracker.trades(c["net"], c["pool"]) if tracker.is_buy(c, t["attributes"])]
    except Exception as err:
        return await reply(update, f"⚠️ GeckoTerminal error: {html.escape(repr(err))}")
    if not buys:
        return await reply(update, "No buys found in the last 24 h.")
    holder = await tracker.is_new_holder(c, buys[0])
    await tracker.send(ctx.bot, key(update, ctx), c, tracker.render(c, buys[0], holder))


@admin
async def stop(update: Update, ctx: Ctx):
    db.delete(key(update, ctx))
    await reply(update, "🛑 Tracking stopped, settings deleted.")


async def membership(update: Update, ctx: Ctx):
    """Greets when added, cleans up when removed."""
    m = update.my_chat_member
    was_in = m.old_chat_member.status not in ("left", "kicked")
    now_in = m.new_chat_member.status not in ("left", "kicked")
    if now_in and not was_in:
        await ctx.bot.send_message(m.chat.id, "👋 Thanks for adding me! An admin can set me up with /setup <CA>. All commands: /help")
    elif was_in and not now_in:
        db.delete((ctx.bot.id, m.chat.id))


COMMANDS = [
    ("setup", setup, "Track a coin by CA"),
    ("minbuy", number_cmd("minbuy", "min_buy", "✅ Only posting buys from ${:g}"), "Minimum buy in $"),
    ("emoji", emoji, "Emoji and $ per emoji"),
    ("name", name, "Project name in posts"),
    ("media", media, "Set banner (image/GIF/video)"),
    ("link", link, "Set links below posts"),
    ("whale", number_cmd("whale", "whale", "✅ Whale alert from ${:g} (0 = off)"), "Whale threshold in $"),
    ("sells", sells, "Toggle sell posts"),
    ("pause", pause_cmd(True), "Pause posts"),
    ("resume", pause_cmd(False), "Resume posts"),
    ("settings", settings, "Show settings"),
    ("test", test, "Send a preview post"),
    ("stop", stop, "Stop tracking"),
    ("help", start, "Help"),
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
        raise SystemExit("BOT_TOKENS missing – see .env.example")
    db.init(os.getenv("DB_PATH", "buybot.db"))
    async with AsyncExitStack() as stack:
        bots = {}
        for token in tokens:  # several tokens = several bots, each with its own name/picture
            app = await stack.enter_async_context(build(token))
            await app.start()
            stack.push_async_callback(app.stop)
            await app.updater.start_polling(drop_pending_updates=True)
            stack.push_async_callback(app.updater.stop)
            await app.bot.set_my_commands([BotCommand(c, d) for c, _, d in COMMANDS])
            bots[app.bot.id] = app.bot
            log.info("@%s is running", app.bot.username)
        await tracker.run(bots, float(os.getenv("POLL_SECONDS", "15")))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
