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
