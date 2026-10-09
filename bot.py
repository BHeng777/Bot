import os, json, random, asyncio, time
import discord
from discord import app_commands

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
NPCS = json.load(open("market.json", encoding="utf-8"))
SEASONS = ["Spring", "Summer", "Autumn", "Winter"]

NPC_EMOJI = {"Arlette": "🎒", "Breda": "⚒️", "Hogan": "🐄", "Leaf": "🌱", "Neria": "📚", "Rendall": "🍺"}

client = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(client)
started = False


def current_season():
    # Not shown anywhere. The market only needs it to know which items can be in stock
    # (some items are only sold in certain seasons). Change it in Railway -> Variables -> SEASON.
    s = os.environ.get("SEASON", "Autumn").strip().capitalize()
    return s if s in SEASONS else "Autumn"


def roll(npc, season):
    # only items sold in this season
    items = [i for i in npc["items"] if season in i.get("seasons", SEASONS)]
    stock = {}
    # items with their own "chance" in market.json are rolled one by one
    for i in items:
        if "chance" in i and random.random() < i["chance"]:
            stock[i["name"]] = random.randint(*i["qty"])
    # items without a "chance" are picked at random (backup, "fill" in market.json)
    pool = [i for i in items if "chance" not in i]
    if pool:
        n = round(npc.get("fill", 0.7) * len(pool)) + random.randint(-1, 1)
        n = max(1, min(len(pool), n))
        picked = sorted(pool, key=lambda i: random.random() ** (1 / i.get("w", 1)), reverse=True)[:n]
        for i in picked:
            stock[i["name"]] = random.randint(*i["qty"])
    return stock


def field_text(stock):
    if not stock:
        return "*Sold out*"
    text = "\n".join(f"{n} ×{q}" for n, q in sorted(stock.items()))
    if len(text) > 1000:  # Discord limit is 1024 per field
        text = text[:1000].rsplit("\n", 1)[0] + "\n…"
    return text


def build(stocks, nexts):
    intervals = sorted({n["interval"] for n in NPCS})
    lines = []
    for iv in intervals:
        nxt = min(nexts[n["name"]] for n in NPCS if n["interval"] == iv)
        sign = "🔄" if iv <= 300 else "⏳"
        lines.append(f"{sign} **{iv // 60}-min shops** restock <t:{nxt}:R>")  # shows "in 5 minutes"
    embed = discord.Embed(title="🛒 The Portal — Market Board", description="\n".join(lines), color=0x2ECC71)
    for iv in intervals:
        embed.add_field(name=f"━━━  Every {iv // 60} minutes  ━━━", value="\u200b", inline=False)
        for npc in NPCS:
            if npc["interval"] != iv:
                continue
            name = npc["name"]
            embed.add_field(
                name=f"{NPC_EMOJI.get(name, '🛒')} {name}",
                value=field_text(stocks[name]),
                inline=True,
            )
    embed.set_footer(text="The Portal • Market Bot")
    embed.timestamp = discord.utils.utcnow()
    return embed


async def market_loop(ch):
    stocks, nexts = {}, {}
    msg = None
    while True:
        now = time.time()
        season = current_season()
        for npc in NPCS:
            n, iv = npc["name"], npc["interval"]
            if n not in nexts or now >= nexts[n]:
                stocks[n] = roll(npc, season)
                nexts[n] = (int(now) // iv + 1) * iv  # next clock slot, so restarts keep the timing
        embed = build(stocks, nexts)
        try:
            if msg is None:
                msg = await ch.send(embed=embed)
            else:
                await msg.edit(embed=embed)
        except Exception as e:
            print("send failed:", e)
            msg = None
        await asyncio.sleep(max(1, min(nexts.values()) - time.time() + 1))


@client.event
async def on_ready():
    global started
    if started:  # on_ready can fire again after a reconnect
        return
    started = True
    ch = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    try:  # removes the old /season and /weather commands from your server
        tree.clear_commands(guild=ch.guild)
        await tree.sync(guild=ch.guild)
    except Exception as e:
        print("command cleanup failed:", e)
    # remove old bot messages (including the old season/weather panel) so nothing is left over
    async for m in ch.history(limit=50):
        if m.author == client.user:
            await m.delete()
    asyncio.create_task(market_loop(ch))
    print("Bot ready")


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"])
