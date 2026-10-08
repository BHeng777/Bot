import os, json, random, asyncio, time
import discord
from discord import app_commands

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
NPCS = json.load(open("market.json", encoding="utf-8"))
SEASONS = ["Spring", "Summer", "Autumn", "Winter"]
STATE_FILE = "season.json"

client = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(client)
started = False
import os, json, random, asyncio, time
import discord
from discord import app_commands

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
NPCS = json.load(open("market.json", encoding="utf-8"))
SEASONS = ["Spring", "Summer", "Autumn", "Winter"]
STATE_FILE = "season.json"

# look of the board
NPC_EMOJI = {"Arlette": "🎒", "Breda": "⚒️", "Hogan": "🐄", "Leaf": "🌱", "Neria": "📚", "Rendall": "🍺"}
SEASON_LOOK = {  # icon, embed color
    "Spring": ("🌸", 0x57F287),
    "Summer": ("☀️", 0xF1C40F),
    "Autumn": ("🍂", 0xE67E22),
    "Winter": ("❄️", 0x5DADE2),
}

client = discord.Client(intents=discord.Intents.default())
tree = app_commands.CommandTree(client)
started = False

# ---------- season ----------
# Starts on Autumn. Use /season in Discord to set it.
# Optional: set SEASON_MINUTES (Railway -> Variables) and the bot moves to the next
# season by itself every that many real minutes, counting from when /season was used.
state = {"season": "Autumn", "since": time.time()}
try:
    state.update(json.load(open(STATE_FILE)))
except Exception:
    pass


def current_season():
    mins = os.environ.get("SEASON_MINUTES")
    if not mins:
        return state["season"]
    steps = int((time.time() - state["since"]) // (float(mins) * 60))
    return SEASONS[(SEASONS.index(state["season"]) + steps) % 4]


@tree.command(name="season", description="Set the current game season")
@app_commands.default_permissions(manage_guild=True)
@app_commands.choices(season=[app_commands.Choice(name=s, value=s) for s in SEASONS])
async def season_cmd(interaction: discord.Interaction, season: app_commands.Choice[str]):
    state["season"] = season.value
    state["since"] = time.time()
    try:
        json.dump(state, open(STATE_FILE, "w"))
    except Exception:
        pass
    await interaction.response.send_message(
        f"Season set to {season.value}. It applies from the next restock.", ephemeral=True
    )


# ---------- market ----------
def roll(npc, season):
    # only items sold in this season
    items = [i for i in npc["items"] if season in i.get("seasons", SEASONS)]
    stock = {}
    # 1) items with their own "chance" in market.json are rolled one by one
    for i in items:
        if "chance" in i and random.random() < i["chance"]:
            stock[i["name"]] = random.randint(*i["qty"])
    # 2) items without a "chance" are picked at random (guess, see "fill")
    pool = [i for i in items if "chance" not in i]
    if pool:
        n = round(npc.get("fill", 0.7) * len(pool)) + random.randint(-1, 1)
        n = max(1, min(len(pool), n))
        # weighted pick without repeats ("w" below 1 = shows up less often)
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


def build(stocks, nexts, season):
    icon, color = SEASON_LOOK[season]
    intervals = sorted({n["interval"] for n in NPCS})
    lines = [f"{icon} **Season:** {season}"]
    for iv in intervals:
        nxt = min(nexts[n["name"]] for n in NPCS if n["interval"] == iv)
        sign = "🔄" if iv <= 300 else "⏳"
        lines.append(f"{sign} **{iv // 60}-min shops** restock <t:{nxt}:R>")  # shows "in 5 minutes"
    embed = discord.Embed(title="🛒 The Portal — Market Board", description="\n".join(lines), color=color)
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
        embed = build(stocks, nexts, season)
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
    try:  # makes /season show up in your server right away
        tree.copy_global_to(guild=ch.guild)
        await tree.sync(guild=ch.guild)
    except Exception as e:
        print("command sync failed:", e)
    # remove old bot messages so a restart doesn't leave duplicates
    async for m in ch.history(limit=50):
        if m.author == client.user:
            await m.delete()
    asyncio.create_task(market_loop(ch))
    print("Bot ready")


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"])

# ---------- season ----------
# Starts on Autumn. Use /season in Discord to set it.
# Optional: set SEASON_MINUTES (Railway -> Variables) and the bot moves to the next
# season by itself every that many real minutes, counting from when /season was used.
state = {"season": "Autumn", "since": time.time()}
try:
    state.update(json.load(open(STATE_FILE)))
except Exception:
    pass


def current_season():
    mins = os.environ.get("SEASON_MINUTES")
    if not mins:
        return state["season"]
    steps = int((time.time() - state["since"]) // (float(mins) * 60))
    return SEASONS[(SEASONS.index(state["season"]) + steps) % 4]


@tree.command(name="season", description="Set the current game season")
@app_commands.default_permissions(manage_guild=True)
@app_commands.choices(season=[app_commands.Choice(name=s, value=s) for s in SEASONS])
async def season_cmd(interaction: discord.Interaction, season: app_commands.Choice[str]):
    state["season"] = season.value
    state["since"] = time.time()
    try:
        json.dump(state, open(STATE_FILE, "w"))
    except Exception:
        pass
    await interaction.response.send_message(
        f"Season set to {season.value}. It applies from the next restock.", ephemeral=True
    )


# ---------- market ----------
def roll(npc, season):
    # only items sold in this season
    items = [i for i in npc["items"] if season in i.get("seasons", SEASONS)]
    if not items:
        return {}
    # "fill" = share of the shop that is in stock each restock (a guess from screenshots)
    n = round(npc.get("fill", 0.7) * len(items)) + random.randint(-1, 1)
    n = max(1, min(len(items), n))
    # weighted random pick without repeats ("w" below 1 = shows up less often)
    picked = sorted(items, key=lambda i: random.random() ** (1 / i.get("w", 1)), reverse=True)[:n]
    return {i["name"]: random.randint(*i["qty"]) for i in picked}


def build(npc, stock, prev, season, nxt):
    # bold = new since the last restock (a guess at what the main server's bold means)
    new = sorted(n for n in stock if prev is not None and n not in prev)
    old = sorted(n for n in stock if n not in new)
    lines = [f"**{n}** ×{stock[n]}" for n in new] + [f"{n} ×{stock[n]}" for n in old]
    text = "\n".join(lines) or "Nothing in stock"
    text += f"\n\nNext restock <t:{nxt}:R>"  # Discord shows this as "in 5 minutes"
    embed = discord.Embed(title=f"{npc['name']} - Open", description=text, color=0x2ECC71)
    embed.set_footer(text=f"Season: {season}")
    return embed


async def npc_loop(npc, ch):
    iv = npc["interval"]
    msg = None
    prev = None
    while True:
        season = current_season()
        stock = roll(npc, season)
        nxt = (int(time.time()) // iv + 1) * iv  # next clock slot, so restarts keep the timing
        embed = build(npc, stock, prev, season, nxt)
        try:
            if msg is None:
                msg = await ch.send(embed=embed)
            else:
                await msg.edit(embed=embed)
        except Exception as e:
            print(f"{npc['name']}: send failed: {e}")
            msg = None
        prev = stock
        await asyncio.sleep(max(1, nxt - time.time() + 1))


@client.event
async def on_ready():
    global started
    if started:  # on_ready can fire again after a reconnect
        return
    started = True
    ch = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    try:  # makes /season show up in your server right away
        tree.copy_global_to(guild=ch.guild)
        await tree.sync(guild=ch.guild)
    except Exception as e:
        print("command sync failed:", e)
    # remove old bot messages so a restart doesn't leave duplicates
    async for m in ch.history(limit=50):
        if m.author == client.user:
            await m.delete()
    for npc in NPCS:
        asyncio.create_task(npc_loop(npc, ch))
        await asyncio.sleep(0.5)  # keeps the NPCs in order in the channel
    print("Bot ready")


if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"])
