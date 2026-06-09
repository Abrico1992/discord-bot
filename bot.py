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

RANDOM_NAMES = [
    "Bouffon Officiel", "Esclave de Service", "Chien Errant", "Sans Cervelle",
    "Larbin Numéro 1", "Déchet Ambulant", "Singe Savant", "Rat de Service",
    "Poulet Mouillé", "Cochon d'Inde", "Gros Nul 3000", "Monsieur Personne",
    "Bébé Pleurnichard", "Champion du Vide", "Fantôme Inutile", "Clown Principal",
    "Bouffon de Service", "Pitre Certifié", "Zéro Absolu", "Minus Habens",
    "Cerveau de Moineau", "Roi des Loosers", "Sous-Sol Intellectuel",
    "Tête de Chou", "Prince des Nuls", "Seigneur du Vide", "Capitaine Raté",
    "Maître Gilles", "Idiot du Village", "Branquignol Premium",
    "Nullité Ambulante", "Génie Inversé", "Prodige du Néant",
    "Expert en Rien", "Professionnel du Vide"
]

randomnaming: set[int] = set()

@bot.command()
@is_allowed()
async def randomname(ctx, member: discord.Member):
    if member.id in randomnaming:
        await ctx.send("⚠️ Déjà en cours pour cette personne.")
        return
    randomnaming.add(member.id)
    await ctx.send(f"🎭 **{member.display_name}** va changer de pseudo toutes les 3s !")

    async def loop_rename():
        while member.id in randomnaming:
            name = random.choice(RANDOM_NAMES)
            try:
                await member.edit(nick=name)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(3)

    bot.loop.create_task(loop_rename())



@bot.command()
@is_allowed()
async def stoprandom(ctx, member: discord.Member):
    if member.id in randomnaming:
        randomnaming.discard(member.id)
        await ctx.send(f"✅ Pseudo aléatoire de **{member.display_name}** arrêté.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas en mode aléatoire.")

vocallocked: dict[int, int] = {}  # user_id -> channel_id


@bot.command()
@is_allowed()
async def lock(ctx, member: discord.Member, channel_id: int):
    channel = ctx.guild.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.VoiceChannel):
        await ctx.send("⚠️ ID de salon vocal invalide.")
        return
    vocallocked[member.id] = channel.id
    try:
        await member.move_to(channel)
    except (discord.Forbidden, discord.HTTPException):
        pass
    await ctx.send(f"🔒 **{member.display_name}** est attaché à **{channel.name}** !")


@bot.command()
@is_allowed()
async def unlock(ctx, member: discord.Member):
    if member.id in vocallocked:
        del vocallocked[member.id]
        await ctx.send(f"🔓 **{member.display_name}** n'est plus attaché à un vocal.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas attaché.")


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id in vocallocked:
        locked_channel = member.guild.get_channel(vocallocked[member.id])
        if locked_channel and after.channel != locked_channel:
            try:
                await member.move_to(locked_channel)
            except (discord.Forbidden, discord.HTTPException):
                pass



# ─── LANCEMENT ────────────────────────────────────────────────────────────────
keep_alive()
bot.run(TOKEN)
