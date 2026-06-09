import discord
from discord.ext import commands, tasks
import asyncio
import random
import os
import time
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

# ─── VARIABLES GLOBALES ───────────────────────────────────────────────────────
# whitelist_full : accès total à toutes les commandes
whitelist_full: set[int] = {OWNER_ID}
# whitelist_cmd : accès limité à certaines commandes {user_id: {cmd1, cmd2, ...}}
whitelist_cmd: dict[int, set[str]] = {}

leashed: dict[int, str] = {}
moving: set[int] = set()
randomnaming: set[int] = set()
vocallocked: dict[int, int] = {}
mutetoggling: set[int] = set()
spamming: set[int] = set()
blacklist: set[int] = set()

# Anti-spam : {user_id: [timestamps]}
message_timestamps: dict[int, list] = {}


# ─── CHECK PERMISSION ─────────────────────────────────────────────────────────
def is_allowed(cmd_name: str = None):
    async def predicate(ctx):
        uid = ctx.author.id
        # Accès total
        if uid in whitelist_full:
            return True
        # Accès limité à la commande spécifique
        if cmd_name and uid in whitelist_cmd and cmd_name in whitelist_cmd[uid]:
            return True
        await ctx.send("❌ Tu n'as pas la permission d'utiliser cette commande.")
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


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id in vocallocked:
        locked_channel = member.guild.get_channel(vocallocked[member.id])
        if locked_channel and after.channel != locked_channel:
            try:
                await member.move_to(locked_channel)
            except (discord.Forbidden, discord.HTTPException):
                pass


@bot.event
async def on_member_join(member):
    if member.id in blacklist:
        try:
            await member.ban(reason="Blacklisté automatiquement")
        except (discord.Forbidden, discord.HTTPException):
            pass


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()
    content_lower = content.lower()

    # ── "quoi" en fin de phrase ou seul ──
    if content_lower == "quoi" or content_lower.endswith("quoi") or content_lower.endswith("quoi?") or content_lower.endswith("quoi !") or content_lower.endswith("quoi!"):
        await message.channel.send("feur")

    # ── Tout en majuscules (5 lettres min pour éviter les faux positifs) ──
    letters = [c for c in content if c.isalpha()]
    if len(letters) >= 5 and all(c.isupper() for c in letters):
        await message.channel.send("cris pas fdp")

    # ── Anti-spam : 4 messages en moins de 5 secondes ──
    uid = message.author.id
    now = time.time()
    if uid not in message_timestamps:
        message_timestamps[uid] = []
    message_timestamps[uid] = [t for t in message_timestamps[uid] if now - t < 5]
    message_timestamps[uid].append(now)
    if len(message_timestamps[uid]) >= 4:
        await message.channel.send(f"respire mon reuf")
        message_timestamps[uid] = []

    await bot.process_commands(message)


# ─── COMMANDES ────────────────────────────────────────────────────────────────

@bot.command()
@is_allowed("ban")
async def ban(ctx, member: discord.Member, *, reason="Aucune raison"):
    try:
        await member.ban(reason=reason)
        await ctx.send(f"🔨 **{member}** a été banni. Raison : {reason}")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission de bannir **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors du ban de **{member}**.")


@bot.command()
@is_allowed("mute")
async def mute(ctx, member: discord.Member):
    if not member.voice:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas dans un salon vocal.")
        return
    try:
        await member.edit(mute=True)
        await ctx.send(f"🔇 **{member}** a été mute en vocal.")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission de mute **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors du mute de **{member}**.")


@bot.command()
@is_allowed("unmute")
async def unmute(ctx, member: discord.Member):
    if not member.voice:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas dans un salon vocal.")
        return
    try:
        await member.edit(mute=False)
        await ctx.send(f"🔊 **{member}** a été unmute.")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission d'unmute **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors de l'unmute de **{member}**.")


@bot.command()
@is_allowed("timeout")
async def timeout(ctx, member: discord.Member, minutes: int = 5):
    from datetime import timedelta
    try:
        duration = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.timeout(duration)
        await ctx.send(f"⏱️ **{member}** a reçu un timeout de {minutes} minute(s).")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission de timeout **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors du timeout de **{member}**.")


@bot.command()
@is_allowed("rename")
async def rename(ctx, member: discord.Member, *, new_name: str):
    try:
        await member.edit(nick=new_name)
        await ctx.send(f"✏️ Pseudo de **{member}** changé en **{new_name}**.")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission de renommer **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors du renommage de **{member}**.")


@bot.command()
@is_allowed("dog")
async def dog(ctx, member: discord.Member):
    base = member.display_name
    if member.id in leashed:
        base = leashed[member.id].split(" (🦮")[0]
        await ctx.send(f"⚠️ **{member.display_name}** est déjà dog, mise à jour du pseudo.")
    forced = f"{base} (🦮 de {ctx.author.display_name})"
    leashed[member.id] = forced
    try:
        await member.edit(nick=forced)
        await ctx.send(f"🦮 **{member.display_name}** est maintenant en laisse !")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission de renommer **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors du dog de **{member}**.")


@bot.command()
@is_allowed("undog")
async def undog(ctx, member: discord.Member):
    if member.id in leashed:
        del leashed[member.id]
        try:
            await member.edit(nick=None)
        except (discord.Forbidden, discord.HTTPException):
            pass
        await ctx.send(f"✅ **{member.display_name}** n'est plus dog.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas dog.")


@bot.command()
@is_allowed("move")
async def move(ctx, member: discord.Member):
    voice_channels = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
    if len(voice_channels) < 2:
        await ctx.send("⚠️ Pas assez de salons vocaux.")
        return
    if member.id in moving:
        await ctx.send(f"⚠️ **{member.display_name}** est déjà en cours de déplacement.")
        return
    if not member.voice:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas dans un salon vocal.")
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
@is_allowed("stopmove")
async def stopmove(ctx, member: discord.Member):
    if member.id in moving:
        moving.discard(member.id)
        await ctx.send(f"✅ Déplacement de **{member.display_name}** arrêté.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas en cours de déplacement.")


@bot.command()
@is_allowed("lock")
async def lock(ctx, member: discord.Member, channel_id: int):
    channel = ctx.guild.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.VoiceChannel):
        await ctx.send("⚠️ ID de salon vocal invalide.")
        return
    if member.id in vocallocked:
        await ctx.send(f"⚠️ **{member.display_name}** est déjà lock, mise à jour du salon.")
    vocallocked[member.id] = channel.id
    try:
        await member.move_to(channel)
        await ctx.send(f"🔒 **{member.display_name}** est attaché à **{channel.name}** !")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission de déplacer **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors du lock (peut-être pas en vocal).")


@bot.command()
@is_allowed("unlock")
async def unlock(ctx, member: discord.Member):
    if member.id in vocallocked:
        del vocallocked[member.id]
        await ctx.send(f"🔓 **{member.display_name}** n'est plus attaché à un vocal.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas lock.")


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


@bot.command()
@is_allowed("name")
async def name(ctx, member: discord.Member):
    if member.id in randomnaming:
        await ctx.send(f"⚠️ **{member.display_name}** est déjà en name.")
        return
    randomnaming.add(member.id)
    await ctx.send(f"🎭 **{member.display_name}** va changer de pseudo toutes les 3s ! (`!unname @user` pour arrêter)")

    async def loop_rename():
        while member.id in randomnaming:
            rname = random.choice(RANDOM_NAMES)
            try:
                await member.edit(nick=rname)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(3)

    bot.loop.create_task(loop_rename())


@bot.command()
@is_allowed("unname")
async def unname(ctx, member: discord.Member):
    if member.id in randomnaming:
        randomnaming.discard(member.id)
        await ctx.send(f"✅ Name de **{member.display_name}** arrêté.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas en name.")


# ─── MUTESPAM ─────────────────────────────────────────────────────────────────
@bot.command()
@is_allowed("mutespam")
async def mutespam(ctx, member: discord.Member):
    if member.id in mutetoggling:
        await ctx.send(f"⚠️ **{member.display_name}** est déjà en mutespam.")
        return
    if not member.voice:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas dans un salon vocal.")
        return
    mutetoggling.add(member.id)
    await ctx.send(f"🔇🔊 **{member.display_name}** va être mute/unmute en boucle ! (`!unmutespam @user` pour arrêter)")

    async def loop_mutetoggle():
        muted = False
        while member.id in mutetoggling:
            try:
                muted = not muted
                await member.edit(mute=muted)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(1)
        try:
            await member.edit(mute=False)
        except Exception:
            pass

    bot.loop.create_task(loop_mutetoggle())


@bot.command()
@is_allowed("unmutespam")
async def unmutespam(ctx, member: discord.Member):
    if member.id in mutetoggling:
        mutetoggling.discard(member.id)
        await ctx.send(f"✅ Mutespam de **{member.display_name}** arrêté.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas en mutespam.")


# ─── SPAM MP ──────────────────────────────────────────────────────────────────
@bot.command()
@is_allowed("spam")
async def spam(ctx, member: discord.Member, *, message: str):
    if member.id in spamming:
        await ctx.send(f"⚠️ **{member.display_name}** est déjà en spam MP.")
        return
    spamming.add(member.id)
    await ctx.send(f"📩 Spam MP lancé sur **{member.display_name}** ! (`!stopspam @user` pour arrêter)")

    async def loop_spam():
        while member.id in spamming:
            try:
                await member.send(message)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(1)

    bot.loop.create_task(loop_spam())


@bot.command()
@is_allowed("stopspam")
async def stopspam(ctx, member: discord.Member):
    if member.id in spamming:
        spamming.discard(member.id)
        await ctx.send(f"✅ Spam MP de **{member.display_name}** arrêté.")
    else:
        await ctx.send(f"⚠️ **{member.display_name}** n'est pas en spam MP.")


# ─── BLACKLIST ────────────────────────────────────────────────────────────────
@bot.command()
@is_allowed("bl")
async def bl(ctx, member: discord.Member, *, reason="Blacklisté"):
    if member.id in blacklist:
        await ctx.send(f"⚠️ **{member}** est déjà blacklisté.")
        return
    blacklist.add(member.id)
    try:
        await member.ban(reason=reason)
        await ctx.send(f"⛔ **{member}** a été blacklisté et banni définitivement.")
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission de bannir **{member}**.")
    except discord.HTTPException:
        await ctx.send(f"❌ Erreur lors du ban de **{member}**.")


@bot.command()
@is_allowed("unbl")
async def unbl(ctx, user_id: int):
    if user_id in blacklist:
        blacklist.discard(user_id)
        try:
            await ctx.guild.unban(discord.Object(id=user_id))
            await ctx.send(f"✅ **{user_id}** retiré de la blacklist et débanni.")
        except discord.Forbidden:
            await ctx.send(f"❌ Je n'ai pas la permission de débannir **{user_id}**.")
        except discord.HTTPException:
            await ctx.send(f"❌ Erreur lors du déban de **{user_id}**.")
    else:
        await ctx.send(f"⚠️ L'utilisateur **{user_id}** n'est pas blacklisté.")


# ─── AVB ──────────────────────────────────────────────────────────────────────
AVB_ROLE_ID = 1508954957762662520

@bot.command()
@is_allowed("avb")
async def avb(ctx, member: discord.Member):
    role = ctx.guild.get_role(AVB_ROLE_ID)
    if not role:
        await ctx.send("❌ Le rôle AVB est introuvable sur ce serveur.")
        return
    if role in member.roles:
        await ctx.send(f"⚠️ **{member.display_name}** a déjà le rôle {role.name}.")
        return
    try:
        await member.add_roles(role)
        await ctx.send(f"✅ **{member.display_name}** a reçu le rôle **{role.name}** !")
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas la permission d'attribuer ce rôle.")
    except discord.HTTPException:
        await ctx.send("❌ Une erreur est survenue lors de l'attribution du rôle.")


# ─── HACK (troll) ─────────────────────────────────────────────────────────────
HACK_LINES = [
    "```",
    "[~] Initializing hack sequence...",
    "[~] Bypassing firewall... DONE",
    "[~] Accessing Discord servers... DONE",
    "[~] Extracting user token... ██████████ 100%",
    "[~] Decrypting password hash... DONE",
    "[~] Fetching IP address... 192.168.{}.{}".format(random.randint(0,255), random.randint(0,255)),
    "[~] Retrieving personal data... DONE",
    "[~] Uploading to remote server...",
    "```",
]

@bot.command()
@is_allowed("hack")
async def hack(ctx, member: discord.Member):
    msg = await ctx.send(f"🖥️ Hacking **{member.display_name}**...")
    await asyncio.sleep(1)
    lines_so_far = ["```"]
    steps = [
        "[~] Initializing hack sequence...",
        "[~] Bypassing firewall... DONE",
        "[~] Accessing Discord API... DONE",
        f"[~] Extracting user token... ██████████ 100%",
        f"[~] Decrypting password hash... DONE",
        f"[~] Fetching IP address... {random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}",
        f"[~] Location detected... {random.choice(['Paris, FR', 'Lyon, FR', 'Marseille, FR', 'Toulouse, FR'])}",
        "[~] Retrieving personal files... ██████████ 100%",
        "[~] Uploading data to remote server...",
        f"[~] HACK COMPLETE. {member.display_name} has been compromised.",
    ]
    for step in steps:
        lines_so_far.append(step)
        display = "\n".join(lines_so_far) + "\n```"
        await msg.edit(content=display)
        await asyncio.sleep(1.2)


# ─── WHITELIST ────────────────────────────────────────────────────────────────
@bot.command()
async def wl(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if member.id in whitelist_full:
        await ctx.send(f"⚠️ **{member}** a déjà un accès total.")
        return
    whitelist_full.add(member.id)
    # Retirer les accès limités s'il en avait
    whitelist_cmd.pop(member.id, None)
    await ctx.send(f"✅ **{member}** a maintenant accès à toutes les commandes.")


@bot.command()
async def unwl(ctx, member: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if member.id == OWNER_ID:
        await ctx.send("❌ Impossible de retirer le propriétaire.")
        return
    if member.id not in whitelist_full and member.id not in whitelist_cmd:
        await ctx.send(f"⚠️ **{member}** n'a aucune permission.")
        return
    whitelist_full.discard(member.id)
    whitelist_cmd.pop(member.id, None)
    await ctx.send(f"✅ Toutes les permissions de **{member}** ont été retirées.")


@bot.command()
async def wlcmd(ctx, member: discord.Member, *cmds: str):
    """Donne accès limité à certaines commandes. Usage: !wlcmd @user cmd1 cmd2"""
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if member.id in whitelist_full:
        await ctx.send(f"⚠️ **{member}** a déjà un accès total, inutile de limiter.")
        return
    if not cmds:
        await ctx.send("⚠️ Précise au moins une commande. Ex: `!wlcmd @user ban mute`")
        return
    if member.id not in whitelist_cmd:
        whitelist_cmd[member.id] = set()
    whitelist_cmd[member.id].update(cmds)
    liste = ", ".join(f"`!{c}`" for c in whitelist_cmd[member.id])
    await ctx.send(f"✅ **{member}** peut maintenant utiliser : {liste}")


@bot.command()
async def unwlcmd(ctx, member: discord.Member, *cmds: str):
    """Retire l'accès à certaines commandes. Usage: !unwlcmd @user cmd1 cmd2"""
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if not cmds:
        await ctx.send("⚠️ Précise au moins une commande. Ex: `!unwlcmd @user ban mute`")
        return
    if member.id not in whitelist_cmd:
        await ctx.send(f"⚠️ **{member}** n'a aucune permission limitée.")
        return
    for c in cmds:
        whitelist_cmd[member.id].discard(c)
    if not whitelist_cmd[member.id]:
        del whitelist_cmd[member.id]
        await ctx.send(f"✅ Toutes les permissions limitées de **{member}** ont été retirées.")
    else:
        liste = ", ".join(f"`!{c}`" for c in whitelist_cmd[member.id])
        await ctx.send(f"✅ Permissions mises à jour. **{member}** peut encore : {liste}")


@bot.command()
async def perms(ctx, member: discord.Member):
    """Voir les permissions d'un utilisateur."""
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Seul le propriétaire peut voir les permissions.")
        return
    if member.id in whitelist_full:
        await ctx.send(f"🔓 **{member}** a un accès **total** à toutes les commandes.")
    elif member.id in whitelist_cmd:
        liste = ", ".join(f"`!{c}`" for c in whitelist_cmd[member.id])
        await ctx.send(f"🔑 **{member}** a accès uniquement à : {liste}")
    else:
        await ctx.send(f"⛔ **{member}** n'a aucune permission.")


# ─── HELP ─────────────────────────────────────────────────────────────────────
@bot.command(name="help")
@is_allowed("help")
async def help_cmd(ctx):
    embed = discord.Embed(title="📋 Commandes du bot", color=0x2b2d31)

    embed.add_field(name="🔨 Modération", value="""
`!ban @user [raison]` — Bannir un membre
`!mute @user` — Mute vocal
`!unmute @user` — Unmute vocal
`!timeout @user [minutes]` — Timeout (défaut: 5 min)
`!hack @user` — 👀
""", inline=False)

    embed.add_field(name="✏️ Pseudo / Laisse", value="""
`!rename @user [pseudo]` — Changer le pseudo
`!dog @user` — Mettre en laisse (pseudo forcé + 🦮)
`!undog @user` — Retirer la laisse
`!name @user` — Pseudo aléatoire toutes les 3s
`!unname @user` — Arrêter le pseudo aléatoire
""", inline=False)

    embed.add_field(name="🌀 Vocal", value="""
`!move @user` — Déplacer en boucle dans des vocaux aléatoires
`!stopmove @user` — Arrêter les déplacements
`!lock @user [channel_id]` — Bloquer dans un salon vocal
`!unlock @user` — Débloquer du salon vocal
`!mutespam @user` — Mute/unmute en boucle
`!unmutespam @user` — Arrêter le mutespam
""", inline=False)

    embed.add_field(name="📩 Spam MP", value="""
`!spam @user [message]` — Spammer un membre en MP
`!stopspam @user` — Arrêter le spam MP
""", inline=False)

    embed.add_field(name="🎖️ Rôles", value="""
`!avb @user` — Donner le rôle AVB à un membre
""", inline=False)

    embed.add_field(name="⛔ Blacklist", value="""
`!bl @user [raison]` — Blacklister et bannir définitivement
`!unbl [user_id]` — Retirer de la blacklist et débannir
""", inline=False)

    embed.add_field(name="⚙️ Whitelist (owner seulement)", value="""
`!wl @user` — Accès total à toutes les commandes
`!unwl @user` — Retirer toutes les permissions
`!wlcmd @user cmd1 cmd2` — Accès limité à des commandes précises
`!unwlcmd @user cmd1 cmd2` — Retirer l'accès à des commandes précises
`!perms @user` — Voir les permissions d'un utilisateur
""", inline=False)

    await ctx.send(embed=embed)


# ─── LANCEMENT ────────────────────────────────────────────────────────────────
keep_alive()
bot.run(TOKEN)
