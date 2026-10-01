"""Fetches buys from GeckoTerminal and posts them to the chats."""
import asyncio
import html
import logging
import math
import os
from datetime import datetime, timedelta, timezone

import httpx
from telegram import Bot
from telegram.error import BadRequest, ChatMigrated, Forbidden, NetworkError, RetryAfter, TelegramError

import db

log = logging.getLogger(__name__)
http = httpx.AsyncClient(base_url="https://api.geckoterminal.com/api/v2", timeout=20,
                         headers={"Accept": "application/json;version=20230302"})

# Key = GeckoTerminal network ID. "rpc" can be overridden with RPC_<KEY> in .env (e.g. RPC_BASE).
NETS = {
    "solana": {"name": "Solana", "icon": "🟣", "tx": "https://solscan.io/tx/{}", "wallet": "https://solscan.io/account/{}",
               "dex": "solana", "buy": "https://jup.ag/swap/SOL-{}", "rpc": "https://api.mainnet-beta.solana.com"},
    "base": {"name": "Base", "icon": "🔵", "tx": "https://basescan.org/tx/{}", "wallet": "https://basescan.org/address/{}",
             "dex": "base", "buy": "https://app.uniswap.org/swap?chain=base&outputCurrency={}",
             "rpc": "https://mainnet.base.org"},
    "eth": {"name": "Ethereum", "icon": "🔷", "tx": "https://etherscan.io/tx/{}", "wallet": "https://etherscan.io/address/{}",
            "dex": "ethereum", "buy": "https://app.uniswap.org/swap?chain=mainnet&outputCurrency={}",
            "rpc": "https://ethereum-rpc.publicnode.com"},
    "bsc": {"name": "BSC", "icon": "🔶", "tx": "https://bscscan.com/tx/{}", "wallet": "https://bscscan.com/address/{}",
            "dex": "bsc", "buy": "https://pancakeswap.finance/swap?outputCurrency={}",
            "rpc": "https://bsc-dataseed.bnbchain.org"},
}
ALIASES = {"sol": "solana", "ethereum": "eth", "bnb": "bsc"}
LINKS = {"tg": "💬 Telegram", "x": "𝕏 Twitter", "web": "🌐 Website", "buy": "🛒 Buy"}
MAX_POOLS = 5  # pools tracked per coin (each costs one API request per round)
REQUEST_GAP = 2.1  # seconds between GeckoTerminal requests (free API: ~30 requests/minute)
CATCH_UP = timedelta(minutes=float(os.getenv("CATCH_UP_MINUTES", "30")))  # post missed trades up to this old


async def get(path: str, **params) -> dict:
    return (await http.get(path, params=params)).raise_for_status().json()


def split_id(ident: str) -> tuple[str, str]:
    """GeckoTerminal IDs look like "<network>_<address>", e.g. "base_0xabc…"."""
    net, _, addr = ident.rpartition("_")
    return net, addr


def parse_pools(r: dict, ca: str) -> list[dict]:
    """All pools in a GeckoTerminal response that contain the CA, most liquidity first."""
    tokens = {t["id"]: t.get("attributes", {}) for t in r.get("included", [])}
    found = []
    for p in r.get("data", []):
        ids = [p["relationships"][k]["data"]["id"] for k in ("base_token", "quote_token")]
        if split_id(ids[1])[1].lower() == ca.lower():
            ids.reverse()  # our token is the quote token of this pool
        net, addr = split_id(ids[0])
        if net in NETS and addr.lower() == ca.lower():
            found.append({"ca": addr, "net": net, "pool": split_id(p["id"])[1],
                          "liq": float(p["attributes"].get("reserve_in_usd") or 0),
                          "name": tokens.get(ids[0], {}).get("name"), "symbol": tokens.get(ids[0], {}).get("symbol"),
                          "quote": tokens.get(ids[1], {}).get("symbol", "")})
    return sorted(found, key=lambda p: -p["liq"])


async def find_token(ca: str, net: str | None = None) -> dict | None:
    """Finds the coin's chain and all of its relevant pools (global search, then each chain as fallback)."""
    sources = [("/search/pools", {"query": ca} | ({"network": net} if net else {}))]
    sources += [(f"/networks/{n}/tokens/{ca}/pools", {}) for n in ([net] if net else NETS)]
    found, trouble = [], None
    for path, params in sources:
        try:
            if found := parse_pools(await get(path, include="base_token,quote_token", **params), ca):
                break
        except Exception as err:  # 4xx = token not on this chain, anything else = GeckoTerminal trouble
            log.info("Lookup %s: %r", path, err)
            status = getattr(getattr(err, "response", None), "status_code", 0)
            trouble = err if status == 429 or not 400 <= status < 500 else trouble
    if not found:
        if trouble:
            raise trouble
        return None
    net = found[0]["net"]
    try:  # complete pool list of the coin on that chain
        found = parse_pools(await get(f"/networks/{net}/tokens/{ca}/pools", include="base_token,quote_token"), ca) or found
    except Exception as err:
        log.info("Pool list for %s: %s", ca, err)
    top = found[0]
    pools = [p for p in found if p["net"] == net and p["liq"] >= top["liq"] * 0.02][:MAX_POOLS]  # skip dust pools
    best = {k: top[k] for k in ("ca", "net", "pool", "name", "symbol", "quote")}
    best["pools"] = {p["pool"]: p["quote"] for p in pools}
    t = {}  # token info: name/symbol fallback + supply for market cap (= supply * price)
    try:
        t = (await get(f"/networks/{net}/tokens/{best['ca']}"))["data"]["attributes"]
        best["supply"] = float(t["fdv_usd"]) / float(t["price_usd"])
    except Exception:
        best["supply"] = 0
    best["name"] = best["name"] or t.get("name") or "Token"
    best["symbol"] = best["symbol"] or t.get("symbol") or "?"
    return best


async def trades(net: str, pool: str) -> list[dict]:
    """Latest trades of the pool, newest first."""
    return (await get(f"/networks/{net}/pools/{pool}/trades"))["data"]


def is_buy(cfg: dict, t: dict) -> bool:
    to = t.get("to_token_address")
    return to.lower() == cfg["ca"].lower() if to else t["kind"] == "buy"


def is_sell(cfg: dict, t: dict) -> bool:
    frm = t.get("from_token_address")
    return frm.lower() == cfg["ca"].lower() if frm else t["kind"] == "sell"


async def rpc(net: str, method: str, params: list):
    url = os.getenv(f"RPC_{net.upper()}") or NETS[net]["rpc"]
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = (await http.post(url, json=body, headers={"Accept": "application/json"})).raise_for_status().json()
    if "error" in r:
        raise RuntimeError(r["error"])
    return r["result"]


async def is_new_holder(cfg: dict, t: dict) -> bool:
    """True if the buyer's current balance is (about) just this buy, i.e. they held nothing before."""
    net, owner, ca = cfg["net"], t["tx_from_address"], cfg["ca"]
    try:
        if net == "solana":
            accounts = (await rpc(net, "getTokenAccountsByOwner", [owner, {"mint": ca}, {"encoding": "jsonParsed"}]))["value"]
            balance = sum(float(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmountString"]) for a in accounts)
        else:  # ERC-20: balanceOf(owner) and decimals()
            call = lambda data: rpc(net, "eth_call", [{"to": ca, "data": data}, "latest"])  # noqa: E731
            raw, decimals = await asyncio.gather(call("0x70a08231" + owner[2:].lower().rjust(64, "0")), call("0x313ce567"))
            balance = int(raw, 16) / 10 ** int(decimals, 16)
        return 0 < balance <= float(t["to_token_amount"]) * 1.01
    except Exception as err:
        log.info("Holder check failed for %s: %r", owner, err)
        return False


def amount(x) -> str:
    """Readable number without scientific notation: 1,234,567 · 352 · 1.5 · 0.000084"""
    x = float(x)
    if x >= 1000:
        return f"{x:,.0f}"
    if x <= 0:
        return "0"
    decimals = 2 if x >= 1 else 3 - math.floor(math.log10(x))  # 4 significant digits below 1
    return f"{x:.{decimals}f}".rstrip("0").rstrip(".")


def render(cfg: dict, t: dict, new_holder: bool = False) -> str:
    n, e = NETS[cfg["net"]], html.escape
    a = lambda url, label: f'<a href="{e(url)}">{label}</a>'  # noqa: E731
    usd, buyer, sell = float(t["volume_in_usd"]), t["tx_from_address"], is_sell(cfg, t)
    # on a sell our token is the "from" side: tokens sold -> quote received
    tokens, paid = (t["from_token_amount"], t["to_token_amount"]) if sell else (t["to_token_amount"], t["from_token_amount"])
    price = float(t.get("price_from_in_usd" if sell else "price_to_in_usd") or 0)
    word = "Sell" if sell else "Buy"
    links = {"📈 Chart": f"https://dexscreener.com/{n['dex']}/{cfg['pool']}", LINKS["buy"]: n["buy"].format(cfg["ca"])}
    links |= {LINKS[k]: url for k, url in cfg["links"].items()}  # a custom buy link replaces the default one
    lines = [
        f"{n['icon']} | <b>{e(cfg['title'] or cfg['name'])}</b>",
        "",
        f"<b>{e(cfg['symbol'])} {word}!</b>",
        ("🔴" if sell else cfg["emoji"]) * (min(50, max(1, int(usd // cfg["step"]))) if cfg["step"] else 1),
        "",
        f"💲 {amount(paid)} {e(cfg['quote'])} (${usd:,.2f})",
        f"🪙 {amount(tokens)} {e(cfg['symbol'])}",
        f"👤 {a(n['wallet'].format(buyer), f'{buyer[:6]}...{buyer[-4:]}')} | {a(n['tx'].format(t['tx_hash']), 'Txn')}",
    ]
    if new_holder:
        lines.append("✅ New Holder")
    if cfg.get("supply") and price:
        lines.append(f"📊 Market Cap <b>${cfg['supply'] * price:,.0f}</b>")
    lines += ["", " | ".join(a(url, label) for label, url in links.items())]
    if cfg["whale"] and usd >= cfg["whale"]:
        lines.insert(3, f"🐳 <b>WHALE {word.upper()}!</b> 🐳")
    return "\n".join(lines)


async def send(bot: Bot, key: tuple[int, int], cfg: dict, text: str, tries: int = 3) -> bool:
    """Posts to the chat; retries and falls back to text-only so a trade is never silently lost."""
    kw = {"chat_id": key[1], "caption" if cfg["media"] else "text": text, "parse_mode": "HTML"}
    try:
        if m := cfg["media"]:
            await getattr(bot, f"send_{m['type']}")(**{m["type"]: m["id"]}, **kw)
        else:
            await bot.send_message(disable_web_page_preview=True, **kw)
        return True
    except RetryAfter as err:  # Telegram flood limit -> wait and send again
        log.warning("Flood limit in chat %s, waiting %ss", key[1], err.retry_after)
        await asyncio.sleep(err.retry_after)
        return await send(bot, key, cfg, text, tries)
    except ChatMigrated as err:  # group was upgraded to a supergroup
        log.info("Chat %s migrated to %s", key[1], err.new_chat_id)
        db.save((key[0], err.new_chat_id), db.chats.get(key, cfg))
        db.delete(key)
        return await send(bot, (key[0], err.new_chat_id), cfg, text, tries)
    except Forbidden:  # bot was removed
        log.warning("Bot was removed from chat %s – settings deleted", key[1])
        db.delete(key)
    except BadRequest as err:
        if cfg["media"]:  # e.g. banner no longer valid -> still post the trade
            log.warning("Banner failed in chat %s (%s) – posting without banner", key[1], err)
            return await send(bot, key, {**cfg, "media": None}, text, tries)
        log.error("Telegram rejected post in chat %s: %s", key[1], err)
    except NetworkError as err:
        if tries > 1:
            log.warning("Network error in chat %s (%s) – retrying", key[1], err)
            await asyncio.sleep(3)
            return await send(bot, key, cfg, text, tries - 1)
        log.error("Sending to chat %s failed: %s", key[1], err)
    except TelegramError as err:
        log.error("Sending to chat %s failed: %s", key[1], err)
    return False


def too_old(t: dict) -> bool:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(t["block_timestamp"].replace("Z", "+00:00")) > CATCH_UP
    except Exception:  # unknown/missing timestamp -> rather post it
        return False


async def handle(bots: dict[int, Bot], keys: list, quote: str, t: dict):
    """Decides for every chat whether to post the trade – and logs each decision."""
    holder = None  # checked once per buy, only if some chat posts it
    for key in keys:
        if not (cfg := db.chats.get(key)):
            continue
        cfg = {**cfg, "quote": quote}  # quote token of the pool this trade happened in
        buy, usd = is_buy(cfg, t), float(t["volume_in_usd"])
        what = f"{'BUY' if buy else 'SELL' if is_sell(cfg, t) else 'OTHER'} ${usd:,.2f} {cfg['symbol']} tx {t['tx_hash']}"
        if not buy and not (cfg["sells"] and is_sell(cfg, t)):
            log.info("%s -> chat %s: skipped (sells off)", what, key[1])
        elif usd < cfg["min_buy"]:
            log.info("%s -> chat %s: skipped (below min $%s)", what, key[1], f"{cfg['min_buy']:g}")
        else:
            if holder is None:
                holder = buy and await is_new_holder(cfg, t)
            ok = await send(bots[key[0]], key, cfg, render(cfg, t, holder))
            log.info("%s -> chat %s: %s", what, key[1], "posted" if ok else "FAILED")


async def upgrade(bots: dict[int, Bot]):
    """Coins set up before multi-pool tracking get their full pool list once."""
    for key, cfg in list(db.chats.items()):
        if key[0] in bots and cfg.get("pool") and "pools" not in cfg:
            if found := await find_token(cfg["ca"], cfg["net"]):
                db.save(key, {**cfg, "pools": found["pools"]})
                log.info("Chat %s now tracks %d pool(s) of %s", key[1], len(found["pools"]), cfg["symbol"])


async def run(bots: dict[int, Bot], interval: float):
    await upgrade(bots)
    seen = db.load_seen()
    while True:
        pools: dict[tuple[str, str], tuple[str, list]] = {}
        for key, cfg in db.chats.items():
            if key[0] in bots and cfg.get("pool") and not cfg["paused"]:
                for pool, quote in (cfg.get("pools") or {cfg["pool"]: cfg["quote"]}).items():
                    pools.setdefault((cfg["net"], pool), (quote, []))[1].append(key)
        for p in seen.keys() - pools.keys():  # forget paused/removed pools -> no backfill on resume
            del seen[p]
            db.save_seen(p, None)
        for p, (quote, keys) in pools.items():
            try:
                data = await trades(*p)
            except Exception as err:  # nothing is lost: missed trades are picked up next round
                log.warning("Trades %s: %r – retrying next round", p, err)
                continue
            if p in seen:
                new = [t["attributes"] for t in reversed(data) if t["id"] not in seen[p]]
                if old := sum(map(too_old, new)):
                    log.info("Pool %s:%s – %d missed trade(s) older than %s not posted", *p, old, CATCH_UP)
                for t in new:
                    try:
                        if not too_old(t):
                            await handle(bots, keys, quote, t)
                    except Exception as err:  # never let one odd trade stop the bot
                        log.exception("Trade %s could not be handled: %r", t.get("tx_hash"), err)
            else:
                log.info("Now watching pool %s:%s (%d chat(s))", *p, len(keys))
            seen[p] = {t["id"] for t in data}
            db.save_seen(p, seen[p])
            await asyncio.sleep(REQUEST_GAP)
        await asyncio.sleep(interval)
