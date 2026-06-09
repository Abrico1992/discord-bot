import discord
from discord.ext import commands, tasks
import asyncio
import random
import os
from threading import Thread
from flask import Flask

# ─── KEEP ALIVE ───────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot en ligne ✅"

def run_server():
    app.run(host="0.0.0.0", port=3000)

def keep_alive():
    t = Thread(target=run_server)
    t.daemon = True
    t.start()

# ─── CONFIG ───────────────────────────────────────────────────────────────────
OWNER_ID = 1508260531943772310
TOKEN = os.environ.get("DISCORD_TOKEN")

# ─── SETUP ────────────────────────────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

whitelist: set[int] = {OWNER_ID}
leashed: dict[int, str] = {}
moving: set[int] = set()


# ─── CHECK PERMISSION ─────────────────────────────────────────────────────────
def is_allowed():
    async def predicate(ctx):
        if ctx.author.id in whitelist:
            return True
        await ctx.send("❌ Tu n'as pas la permission d'utiliser ce bot.")
        return False
    return commands.check(predicate)


# ─── BOUCLE LAISSE (toutes les 5s) ────────────────────────────────────────────
@tasks.loop(seconds=5)
async def check_leashes():
    for guild in bot.guilds:
        for user_id, forced_name in list(leashed.items()):
            member = guild.get_member(user_id)
            if member and member.display_name != forced_name:
                try:
                    await member.edit(nick=forced_name)
                except discord.Forbidden:
                    pass


# ─── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    check_leashes.start()
    print(f"✅ Connecté en tant que {bot.user}")


@bot.event
async def on_member_update(before, after):
    if after.id in leashed and after.display_name != leashed[after.id]:
        try:
            await after.edit(nick=leashed[after.id])
        except discord.Forbidden:
            pass


# ─── COMMANDES ────────────────────────────────────────────────────────────────

@bot.command()
@is_allowed()
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    await member.ban(reason=reason)
    await ctx.send(f"🔨 **{member}** a été banni. Raison : {reason}")


@bot.command()
@is_allowed()
async def mute(ctx, member: discord.Member):
    await member.edit(mute=True)
    await ctx.send(f"🔇 **{member}** a été mute en vocal.")


@bot.command()
@is_allowed()
async def unmute(ctx, member: discord.Member):
    await member.edit(mute=False)
    await ctx.send(f"🔊 **{member}** a été unmute.")


@bot.command()
@is_allowed()
async def timeout(ctx, member: discord.Member, minutes: int = 5):
    from datetime import timedelta
    duration = discord.utils.utcnow() + timedelta(minutes=minutes)
    await member.timeout(duration)
    await ctx.send(f"⏱️ **{member}** a reçu un timeout de {minutes} minute(s).")


@bot.command()
@is_allowed()
async def rename(ctx, member: discord.Member, *, new_name: str):
    await member.edit(nick=new_name)
    await ctx.send(f"✏️ Pseudo de **{member}** changé en **{new_name}**.")


@bot.command()
@is_allowed()
async def leash(ctx, member: discord.Member):
    base = member.display_name
    if member.id in leashed:
        base = leashed[member.id].split(" (🦮")[0]
    forced = f"{base} (🦮 de {ctx.author.display_name})"
    leashed[member.id] = forced
    try:
        await member.edit(nick=forced)
    except discord.Forbidden:
        pass
    await ctx.send(f"🦮 **{member.display_name}** est maintenant en laisse !")


@bot.command()
@is_allowed()
async def unleash(ctx, member: discord.Member):
    if member.id in leashed:
        del leashed[member.id]
        await ctx.send(f"✅ **{member.display_name}** n'est plus en laisse.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas en laisse.")


@bot.command()
@is_allowed()
async def move(ctx, member: discord.Member):
    voice_channels = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
    if len(voice_channels) < 2:
        await ctx.send("⚠️ Pas assez de salons vocaux.")
        return
    if member.id in moving:
        await ctx.send("⚠️ Cette personne est déjà en cours de déplacement.")
        return
    moving.add(member.id)
    await ctx.send(f"🌀 **{member.display_name}** va être déplacé en boucle ! (`!stopmove @user` pour arrêter)")

    async def loop_move():
        while member.id in moving:
            if member.voice:
                channel = random.choice(voice_channels)
                try:
                    await member.move_to(channel)
                except (discord.Forbidden, discord.HTTPException):
                    pass
            await asyncio.sleep(0.5)

    bot.loop.create_task(loop_move())


@bot.command()
@is_allowed()
async def stopmove(ctx, member: discord.Member):
    if member.id in moving:
        moving.discard(member.id)
        await ctx.send(f"✅ Déplacement de **{member.display_name}** arrêté.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas en cours de déplacement.")


@bot.command()
@is_allowed()
async def wl(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Seul le propriétaire peut modifier la whitelist.")
        return
    whitelist.add(member.id)
    await ctx.send(f"✅ **{member}** ajouté à la whitelist.")


@bot.command()
@is_allowed()
async def unwl(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if member.id == OWNER_ID:
        await ctx.send("❌ Impossible de retirer le propriétaire.")
        return
    whitelist.discard(member.id)
    await ctx.send(f"✅ **{member}** retiré de la whitelist.")


@bot.command(name="help")
@is_allowed()
async def help_cmd(ctx):
    embed = discord.Embed(title="📋 Commandes du bot", color=0x2b2d31)
    embed.add_field(name="🔨 Modération", value="""
`!ban @user [raison]` — Bannir un membre
`!mute @user` — Mute vocal
`!unmute @user` — Unmute vocal
`!timeout @user [minutes]` — Timeout (défaut: 5 min)
""", inline=False)
    embed.add_field(name="✏️ Pseudo / Laisse", value="""
`!rename @user [pseudo]` — Changer le pseudo
`!leash @user` — Mettre en laisse (pseudo forcé + 🦮)
`!unleash @user` — Retirer la laisse
""", inline=False)
    embed.add_field(name="🌀 Vocal", value="""
`!move @user` — Déplacer en boucle dans des vocaux aléatoires
`!stopmove @user` — Arrêter les déplacements
""", inline=False)
    embed.add_field(name="⚙️ Whitelist (owner seulement)", value="""
`!wl @user` — Autoriser un utilisateur
`!unwl @user` — Retirer l'autorisation
""", inline=False)
    await ctx.send(embed=embed)


# ─── LANCEMENT ────────────────────────────────────────────────────────────────
keep_alive()
bot.run(TOKEN)
