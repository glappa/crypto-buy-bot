"""Fetches buys from GeckoTerminal and posts them to the chats."""
import asyncio
import html
import logging

import httpx
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import ChatMigrated, Forbidden, RetryAfter, TelegramError

import db

log = logging.getLogger(__name__)
http = httpx.AsyncClient(base_url="https://api.geckoterminal.com/api/v2", timeout=20,
                         headers={"Accept": "application/json;version=20230302"})

# GeckoTerminal ID: (name, TX link, wallet link, DexScreener ID, buy link)
NETS = {
    "solana": ("Solana", "https://solscan.io/tx/{}", "https://solscan.io/account/{}", "solana",
               "https://jup.ag/swap/SOL-{}"),
    "base": ("Base", "https://basescan.org/tx/{}", "https://basescan.org/address/{}", "base",
             "https://app.uniswap.org/swap?chain=base&outputCurrency={}"),
    "eth": ("Ethereum", "https://etherscan.io/tx/{}", "https://etherscan.io/address/{}", "ethereum",
            "https://app.uniswap.org/swap?chain=mainnet&outputCurrency={}"),
    "bsc": ("BSC", "https://bscscan.com/tx/{}", "https://bscscan.com/address/{}", "bsc",
            "https://pancakeswap.finance/swap?outputCurrency={}"),
}
ALIASES = {"sol": "solana", "ethereum": "eth", "bnb": "bsc"}
LINKS = {"tg": "💬 Telegram", "x": "𝕏 Twitter", "web": "🌐 Website", "buy": "🛒 Buy"}


async def get(path: str, **params) -> dict:
    return (await http.get(path, params=params)).raise_for_status().json()


def split_id(ident: str) -> tuple[str, str]:
    """GeckoTerminal IDs look like "<network>_<address>", e.g. "base_0xabc…"."""
    net, _, addr = ident.rpartition("_")
    return net, addr


def best_pool(r: dict, ca: str) -> dict | None:
    """Picks the pool with the most liquidity that contains the CA."""
    tokens = {t["id"]: t.get("attributes", {}) for t in r.get("included", [])}
    best, liq_max = None, -1.0
    for p in r.get("data", []):
        ids = [p["relationships"][k]["data"]["id"] for k in ("base_token", "quote_token")]
        if split_id(ids[1])[1].lower() == ca.lower():
            ids.reverse()  # our token is the quote token of this pool
        net, addr = split_id(ids[0])
        liq = float(p["attributes"].get("reserve_in_usd") or 0)
        if net in NETS and addr.lower() == ca.lower() and liq > liq_max:
            liq_max = liq
            best = {"ca": addr, "net": net, "pool": split_id(p["id"])[1], "name": tokens.get(ids[0], {}).get("name"),
                    "symbol": tokens.get(ids[0], {}).get("symbol"), "quote": tokens.get(ids[1], {}).get("symbol", "")}
    return best


async def find_token(ca: str, net: str | None = None) -> dict | None:
    """Global search first, then the token's pools on each chain as fallback."""
    sources = [("/search/pools", {"query": ca} | ({"network": net} if net else {}))]
    sources += [(f"/networks/{n}/tokens/{ca}/pools", {}) for n in ([net] if net else NETS)]
    best = None
    for path, params in sources:
        try:
            if best := best_pool(await get(path, include="base_token,quote_token", **params), ca):
                break
        except Exception as err:  # 404 = token not on this chain
            log.info("Lookup %s: %s", path, err)
    if best:  # token info: name/symbol fallback + supply for market cap (= supply * price)
        t = {}
        try:
            t = (await get(f"/networks/{best['net']}/tokens/{best['ca']}"))["data"]["attributes"]
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


def fmt(x: float, usd: bool = False) -> str:
    x, pre = float(x), "$" if usd else ""
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if x >= div:
            return f"{pre}{x / div:.2f}{suffix}"
    return f"{pre}{x:.4g}"


def render(cfg: dict, t: dict) -> str:
    _, tx_url, wallet_url, *_ = NETS[cfg["net"]]
    usd, e = float(t["volume_in_usd"]), html.escape
    price = float(t.get("price_to_in_usd") or 0)
    lines = [
        f"<b>{e(cfg['title'] or cfg['name'])} Buy!</b>",
        cfg["emoji"] * (min(50, max(1, int(usd // cfg["step"]))) if cfg["step"] else 1),
        "",
        f"💵 <b>{fmt(usd, True)}</b> ({fmt(t['from_token_amount'])} {e(cfg['quote'])})",
        f"🪙 {fmt(t['to_token_amount'])} {e(cfg['symbol'])}",
        f"👤 <a href=\"{wallet_url.format(t['tx_from_address'])}\">Buyer</a>"
        f" | <a href=\"{tx_url.format(t['tx_hash'])}\">TX</a>",
    ]
    if cfg.get("supply") and price:
        lines.append(f"📊 MC {fmt(cfg['supply'] * price, True)}")
    if cfg["whale"] and usd >= cfg["whale"]:
        lines.insert(1, "🐳 <b>WHALE BUY!</b> 🐳")
    return "\n".join(lines)


def buttons(cfg: dict) -> InlineKeyboardMarkup:
    *_, dex, buy_url = NETS[cfg["net"]]
    links = {"📈 Chart": f"https://dexscreener.com/{dex}/{cfg['pool']}", LINKS["buy"]: buy_url.format(cfg["ca"])}
    links |= {LINKS[k]: url for k, url in cfg["links"].items()}
    items = [InlineKeyboardButton(label, url=url) for label, url in links.items()]
    return InlineKeyboardMarkup([items[i:i + 2] for i in range(0, len(items), 2)])


async def send(bot: Bot, key: tuple[int, int], cfg: dict, text: str):
    kw = {"chat_id": key[1], "caption" if cfg["media"] else "text": text,
          "parse_mode": "HTML", "reply_markup": buttons(cfg)}
    try:
        if m := cfg["media"]:
            await getattr(bot, f"send_{m['type']}")(**{m["type"]: m["id"]}, **kw)
        else:
            await bot.send_message(disable_web_page_preview=True, **kw)
    except RetryAfter as err:
        await asyncio.sleep(err.retry_after)
        await send(bot, key, cfg, text)
    except ChatMigrated as err:  # group was upgraded to a supergroup
        db.delete(key)
        db.save((key[0], err.new_chat_id), cfg)
        await send(bot, (key[0], err.new_chat_id), cfg, text)
    except Forbidden:  # bot was removed
        db.delete(key)
    except TelegramError as err:
        log.warning("Sending to %s failed: %s", key[1], err)


async def run(bots: dict[int, Bot], interval: float):
    seen: dict[tuple[str, str], set[str]] = {}
    while True:
        pools: dict[tuple[str, str], list] = {}
        for key, cfg in db.chats.items():
            if key[0] in bots and cfg.get("pool") and not cfg["paused"]:
                pools.setdefault((cfg["net"], cfg["pool"]), []).append(key)
        for p in seen.keys() - pools.keys():  # forget paused pools -> no backfill on resume
            del seen[p]
        for p, keys in pools.items():
            try:
                data = await trades(*p)
            except Exception as err:
                log.warning("Trades %s: %s", p, err)
                continue
            new = [t["attributes"] for t in reversed(data) if t["id"] not in seen[p]] if p in seen else []
            seen[p] = {t["id"] for t in data}
            for t in new:
                for key in keys:
                    cfg = db.chats.get(key)
                    try:
                        if cfg and is_buy(cfg, t) and float(t["volume_in_usd"]) >= cfg["min_buy"]:
                            await send(bots[key[0]], key, cfg, render(cfg, t))
                    except Exception as err:  # never let one odd trade stop the bot
                        log.warning("Skipping trade %s: %r", t.get("tx_hash"), err)
            await asyncio.sleep(2.1)  # GeckoTerminal allows ~30 requests/minute
        await asyncio.sleep(interval)
