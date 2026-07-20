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
OWNER_IDS = {1524948006632165437, 1368269462087794888}
TOKEN = os.environ.get("DISCORD_TOKEN")
EMBED_COLOR = 0x2b2d31

# Commandes valides (pour vérifier /wlcmd et /unwlcmd)
VALID_COMMANDS = {
    "ban", "mute", "unmute", "timeout", "rename", "dog", "undog", "move", "stopmove",
    "lock", "unlock", "name", "unname", "mutespam", "unmutespam", "spam", "stopspam",
    "bl", "unbl", "avb", "derank", "hack", "off", "say", "help",
}

# Paires de commandes opposées : ajouter l'une ajoute automatiquement l'autre
OPPOSITE_COMMANDS = {
    "mute": "unmute", "unmute": "mute",
    "dog": "undog", "undog": "dog",
    "name": "unname", "unname": "name",
    "move": "stopmove", "stopmove": "move",
    "lock": "unlock", "unlock": "lock",
    "mutespam": "unmutespam", "unmutespam": "mutespam",
    "spam": "stopspam", "stopspam": "spam",
    "bl": "unbl", "unbl": "bl",
}

# ─── SETUP ────────────────────────────────────────────────────────────────────
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ─── HELPER EMBED ─────────────────────────────────────────────────────────────
async def send_embed(ctx, description: str, color: int = EMBED_COLOR):
    embed = discord.Embed(description=description, color=color)
    await ctx.send(embed=embed)

# ─── VARIABLES GLOBALES ───────────────────────────────────────────────────────
whitelist_full: set[int] = set(OWNER_IDS)
whitelist_cmd: dict[int, set[str]] = {}

leashed: dict[int, str] = {}
moving: set[int] = set()
randomnaming: set[int] = set()
vocallocked: dict[int, int] = {}
mutetoggling: set[int] = set()
spamming: set[int] = set()
blacklist: set[int] = set()

message_timestamps: dict[int, list] = {}

# Interrupteur global : si False, le bot ne répond plus à rien sauf /on (owner)
bot_enabled: bool = True


# ─── CHECK PERMISSION ─────────────────────────────────────────────────────────
def is_allowed(cmd_name: str = None):
    async def predicate(ctx):
        uid = ctx.author.id
        if uid in whitelist_full:
            return True
        if cmd_name and uid in whitelist_cmd and cmd_name in whitelist_cmd[uid]:
            return True
        await send_embed(ctx, "❌ Tu n'as pas la permission d'utiliser cette commande.")
        return False
    return commands.check(predicate)


@bot.event
async def on_command_error(ctx, error):
    # CommandNotFound : commande inexistante tapée avec le préfixe, on ignore
    if isinstance(error, commands.CommandNotFound):
        return
    # CheckFailure : déjà géré (message envoyé par is_allowed ou switch off silencieux)
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await send_embed(ctx, f"⚠️ Il manque un argument : `{error.param.name}`.")
        return
    if isinstance(error, commands.MemberNotFound):
        await send_embed(ctx, f"⚠️ Membre introuvable : `{error.argument}`.")
        return
    if isinstance(error, commands.BadArgument):
        await send_embed(ctx, f"⚠️ Argument invalide : {error}")
        return
    if isinstance(error, commands.CommandOnCooldown):
        await send_embed(ctx, f"⏳ Commande en cooldown, réessaie dans {error.retry_after:.1f}s.")
        return
    # Erreur non prévue : on informe l'utilisateur et on log côté serveur
    await send_embed(ctx, f"❌ Erreur lors de l'exécution de la commande : {error}")
    print(f"⚠️ Erreur non gérée dans une commande : {error}")


@bot.check
async def global_off_switch(ctx):
    # Quand le bot est off, seul /on (owner uniquement) passe
    if ctx.command and ctx.command.name == "on":
        return True
    if not bot_enabled:
        return False
    return True


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


# ─── BOUCLE ANTI-TIMEOUT OWNER (toutes les 1s) ────────────────────────────────
@tasks.loop(seconds=1)
async def check_owner_timeout():
    for guild in bot.guilds:
        for owner_id in OWNER_IDS:
            member = guild.get_member(owner_id)
            if member and member.timed_out_until:
                try:
                    await member.timeout(None)
                except (discord.Forbidden, discord.HTTPException):
                    pass


# ─── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    check_leashes.start()
    check_owner_timeout.start()
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commandes slash synchronisées.")
    except Exception as e:
        print(f"⚠️ Erreur de synchronisation des commandes slash : {e}")
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
async def on_member_ban(guild, user):
    if user.id in OWNER_IDS:
        try:
            await guild.unban(user, reason="Anti-ban owner")
        except (discord.Forbidden, discord.HTTPException):
            pass


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()
    content_lower = content.lower()

    if bot_enabled:
        if content_lower == "quoi" or content_lower.endswith("quoi") or content_lower.endswith("quoi?") or content_lower.endswith("quoi !") or content_lower.endswith("quoi!"):
            await message.channel.send("feur")

        letters = [c for c in content if c.isalpha()]
        if len(letters) >= 5 and all(c.isupper() for c in letters):
            if message.author.id == 1381361986260045965:
                await message.channel.send("wAllah zz j'en ai marre de te rep")
            else:
                await message.channel.send("cris pas fdp")

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

@bot.hybrid_command(name="ban", description="Bannir un membre du serveur")
@is_allowed("ban")
async def ban(ctx, utilisateur: discord.Member, *, raison: str = "Aucune raison"):
    try:
        await utilisateur.ban(reason=raison)
        await send_embed(ctx, f"🔨 **{utilisateur}** a été banni. Raison : {raison}")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de bannir **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du ban de **{utilisateur}**.")


@bot.hybrid_command(name="mute", description="Mute un membre en vocal")
@is_allowed("mute")
async def mute(ctx, utilisateur: discord.Member):
    if not utilisateur.voice:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas dans un salon vocal.")
        return
    try:
        await utilisateur.edit(mute=True)
        await send_embed(ctx, f"🔇 **{utilisateur}** a été mute en vocal.")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de mute **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du mute de **{utilisateur}**.")


@bot.hybrid_command(name="unmute", description="Unmute un membre en vocal")
@is_allowed("unmute")
async def unmute(ctx, utilisateur: discord.Member):
    if not utilisateur.voice:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas dans un salon vocal.")
        return
    try:
        await utilisateur.edit(mute=False)
        await send_embed(ctx, f"🔊 **{utilisateur}** a été unmute.")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission d'unmute **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors de l'unmute de **{utilisateur}**.")


@bot.hybrid_command(name="timeout", description="Mettre un membre en timeout")
@is_allowed("timeout")
async def timeout(ctx, utilisateur: discord.Member, minutes: int = 5):
    from datetime import timedelta
    try:
        duration = discord.utils.utcnow() + timedelta(minutes=minutes)
        await utilisateur.timeout(duration)
        await send_embed(ctx, f"⏱️ **{utilisateur}** a reçu un timeout de {minutes} minute(s).")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de timeout **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du timeout de **{utilisateur}**.")


@bot.hybrid_command(name="rename", description="Changer le pseudo d'un membre")
@is_allowed("rename")
async def rename(ctx, utilisateur: discord.Member, *, pseudo: str):
    try:
        await utilisateur.edit(nick=pseudo)
        await send_embed(ctx, f"✏️ Pseudo de **{utilisateur}** changé en **{pseudo}**.")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de renommer **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du renommage de **{utilisateur}**.")


@bot.hybrid_command(name="dog", description="Mettre un membre en laisse (pseudo forcé)")
@is_allowed("dog")
async def dog(ctx, utilisateur: discord.Member):
    base = utilisateur.display_name
    if utilisateur.id in leashed:
        base = leashed[utilisateur.id].split(" (🦮")[0]
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** est déjà dog, mise à jour du pseudo.")
    forced = f"{base} (🦮 de {ctx.author.display_name})"
    leashed[utilisateur.id] = forced
    try:
        await utilisateur.edit(nick=forced)
        await send_embed(ctx, f"🦮 **{utilisateur.display_name}** est maintenant en laisse !")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de renommer **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du dog de **{utilisateur}**.")


@bot.hybrid_command(name="undog", description="Retirer la laisse d'un membre")
@is_allowed("undog")
async def undog(ctx, utilisateur: discord.Member):
    if utilisateur.id in leashed:
        del leashed[utilisateur.id]
        try:
            await utilisateur.edit(nick=None)
        except (discord.Forbidden, discord.HTTPException):
            pass
        await send_embed(ctx, f"✅ **{utilisateur.display_name}** n'est plus dog.")
    else:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas dog.")


@bot.hybrid_command(name="move", description="Déplacer un membre en boucle dans des vocaux aléatoires")
@is_allowed("move")
async def move(ctx, utilisateur: discord.Member):
    voice_channels = [c for c in ctx.guild.channels if isinstance(c, discord.VoiceChannel)]
    if len(voice_channels) < 2:
        await send_embed(ctx, "⚠️ Pas assez de salons vocaux.")
        return
    if utilisateur.id in moving:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** est déjà en cours de déplacement.")
        return
    if not utilisateur.voice:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas dans un salon vocal.")
        return
    moving.add(utilisateur.id)
    await send_embed(ctx, f"🌀 **{utilisateur.display_name}** va être déplacé en boucle ! (`/stopmove` pour arrêter)")

    async def loop_move():
        while utilisateur.id in moving:
            if utilisateur.voice:
                channel = random.choice(voice_channels)
                try:
                    await utilisateur.move_to(channel)
                except (discord.Forbidden, discord.HTTPException):
                    pass
            await asyncio.sleep(0.5)

    bot.loop.create_task(loop_move())


@bot.hybrid_command(name="stopmove", description="Arrêter le déplacement en boucle d'un membre")
@is_allowed("stopmove")
async def stopmove(ctx, utilisateur: discord.Member):
    if utilisateur.id in moving:
        moving.discard(utilisateur.id)
        await send_embed(ctx, f"✅ Déplacement de **{utilisateur.display_name}** arrêté.")
    else:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas en cours de déplacement.")


@bot.hybrid_command(name="lock", description="Bloquer un membre dans un salon vocal")
@is_allowed("lock")
async def lock(ctx, utilisateur: discord.Member, id_salon: str):
    try:
        channel_id = int(id_salon)
    except ValueError:
        await send_embed(ctx, "⚠️ ID de salon vocal invalide.")
        return
    channel = ctx.guild.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.VoiceChannel):
        await send_embed(ctx, "⚠️ ID de salon vocal invalide.")
        return
    if utilisateur.id in vocallocked:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** est déjà lock, mise à jour du salon.")
    vocallocked[utilisateur.id] = channel.id
    try:
        await utilisateur.move_to(channel)
        await send_embed(ctx, f"🔒 **{utilisateur.display_name}** est attaché à **{channel.name}** !")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de déplacer **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du lock (peut-être pas en vocal).")


@bot.hybrid_command(name="unlock", description="Débloquer un membre d'un salon vocal")
@is_allowed("unlock")
async def unlock(ctx, utilisateur: discord.Member):
    if utilisateur.id in vocallocked:
        del vocallocked[utilisateur.id]
        await send_embed(ctx, f"🔓 **{utilisateur.display_name}** n'est plus attaché à un vocal.")
    else:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas lock.")


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


@bot.hybrid_command(name="name", description="Changer le pseudo d'un membre aléatoirement toutes les 3s")
@is_allowed("name")
async def name(ctx, utilisateur: discord.Member):
    if utilisateur.id in randomnaming:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** est déjà en name.")
        return
    randomnaming.add(utilisateur.id)
    await send_embed(ctx, f"🎭 **{utilisateur.display_name}** va changer de pseudo toutes les 3s ! (`/unname` pour arrêter)")

    async def loop_rename():
        while utilisateur.id in randomnaming:
            rname = random.choice(RANDOM_NAMES)
            try:
                await utilisateur.edit(nick=rname)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(3)

    bot.loop.create_task(loop_rename())


@bot.hybrid_command(name="unname", description="Arrêter le changement de pseudo aléatoire")
@is_allowed("unname")
async def unname(ctx, utilisateur: discord.Member):
    if utilisateur.id in randomnaming:
        randomnaming.discard(utilisateur.id)
        await send_embed(ctx, f"✅ Name de **{utilisateur.display_name}** arrêté.")
    else:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas en name.")


# ─── MUTESPAM ─────────────────────────────────────────────────────────────────
@bot.hybrid_command(name="mutespam", description="Mute/unmute un membre en boucle")
@is_allowed("mutespam")
async def mutespam(ctx, utilisateur: discord.Member):
    if utilisateur.id in mutetoggling:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** est déjà en mutespam.")
        return
    if not utilisateur.voice:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas dans un salon vocal.")
        return
    mutetoggling.add(utilisateur.id)
    await send_embed(ctx, f"🔇🔊 **{utilisateur.display_name}** va être mute/unmute en boucle ! (`/unmutespam` pour arrêter)")

    async def loop_mutetoggle():
        muted = False
        while utilisateur.id in mutetoggling:
            try:
                muted = not muted
                await utilisateur.edit(mute=muted)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(1)
        try:
            await utilisateur.edit(mute=False)
        except Exception:
            pass

    bot.loop.create_task(loop_mutetoggle())


@bot.hybrid_command(name="unmutespam", description="Arrêter le mutespam d'un membre")
@is_allowed("unmutespam")
async def unmutespam(ctx, utilisateur: discord.Member):
    if utilisateur.id in mutetoggling:
        mutetoggling.discard(utilisateur.id)
        await send_embed(ctx, f"✅ Mutespam de **{utilisateur.display_name}** arrêté.")
    else:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas en mutespam.")


# ─── SPAM MP ──────────────────────────────────────────────────────────────────
@bot.hybrid_command(name="spam", description="Spammer un membre en message privé")
@is_allowed("spam")
async def spam(ctx, utilisateur: discord.Member, *, message: str):
    if utilisateur.id in spamming:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** est déjà en spam MP.")
        return
    spamming.add(utilisateur.id)
    await send_embed(ctx, f"📩 Spam MP lancé sur **{utilisateur.display_name}** ! (`/stopspam` pour arrêter)")

    async def loop_spam():
        while utilisateur.id in spamming:
            try:
                await utilisateur.send(message)
            except (discord.Forbidden, discord.HTTPException):
                pass
            await asyncio.sleep(1)

    bot.loop.create_task(loop_spam())


@bot.hybrid_command(name="stopspam", description="Arrêter le spam MP d'un membre")
@is_allowed("stopspam")
async def stopspam(ctx, utilisateur: discord.Member):
    if utilisateur.id in spamming:
        spamming.discard(utilisateur.id)
        await send_embed(ctx, f"✅ Spam MP de **{utilisateur.display_name}** arrêté.")
    else:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'est pas en spam MP.")


# ─── BLACKLIST ────────────────────────────────────────────────────────────────
@bot.hybrid_command(name="bl", description="Blacklister et bannir définitivement un membre")
@is_allowed("bl")
async def bl(ctx, utilisateur: discord.Member, *, raison: str = "Blacklisté"):
    if utilisateur.id in blacklist:
        await send_embed(ctx, f"⚠️ **{utilisateur}** est déjà blacklisté.")
        return
    blacklist.add(utilisateur.id)
    try:
        await utilisateur.ban(reason=raison)
        await send_embed(ctx, f"⛔ **{utilisateur}** a été blacklisté et banni définitivement.")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de bannir **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du ban de **{utilisateur}**.")


@bot.hybrid_command(name="unbl", description="Retirer un utilisateur de la blacklist et le débannir")
@is_allowed("unbl")
async def unbl(ctx, id_utilisateur: str):
    try:
        user_id = int(id_utilisateur)
    except ValueError:
        await send_embed(ctx, "⚠️ ID invalide.")
        return
    if user_id in blacklist:
        blacklist.discard(user_id)
        try:
            await ctx.guild.unban(discord.Object(id=user_id))
            await send_embed(ctx, f"✅ **{user_id}** retiré de la blacklist et débanni.")
        except discord.Forbidden:
            await send_embed(ctx, f"❌ Je n'ai pas la permission de débannir **{user_id}**.")
        except discord.HTTPException:
            await send_embed(ctx, f"❌ Erreur lors du déban de **{user_id}**.")
    else:
        await send_embed(ctx, f"⚠️ L'utilisateur **{user_id}** n'est pas blacklisté.")


# ─── AVB ──────────────────────────────────────────────────────────────────────
AVB_ROLE_ID = 1524260172258607206

@bot.hybrid_command(name="avb", description="Donner le rôle AVB à un membre")
@is_allowed("avb")
async def avb(ctx, utilisateur: discord.Member):
    role = ctx.guild.get_role(AVB_ROLE_ID)
    if not role:
        await send_embed(ctx, "❌ Le rôle AVB est introuvable sur ce serveur.")
        return
    if role in utilisateur.roles:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** a déjà le rôle {role.name}.")
        return
    try:
        await utilisateur.add_roles(role)
        await send_embed(ctx, f"✅ **{utilisateur.display_name}** a reçu le rôle **{role.name}** !")
    except discord.Forbidden:
        await send_embed(ctx, "❌ Je n'ai pas la permission d'attribuer ce rôle.")
    except discord.HTTPException:
        await send_embed(ctx, "❌ Une erreur est survenue lors de l'attribution du rôle.")


@bot.hybrid_command(name="derank", description="Retirer tous les rôles d'un membre")
@is_allowed("derank")
async def derank(ctx, utilisateur: discord.Member):
    roles_to_remove = [r for r in utilisateur.roles if r != ctx.guild.default_role]
    if not roles_to_remove:
        await send_embed(ctx, f"⚠️ **{utilisateur.display_name}** n'a aucun rôle à retirer.")
        return
    try:
        await utilisateur.remove_roles(*roles_to_remove)
        await send_embed(ctx, f"✅ Tous les rôles de **{utilisateur.display_name}** ont été retirés.")
    except discord.Forbidden:
        await send_embed(ctx, f"❌ Je n'ai pas la permission de retirer les rôles de **{utilisateur}**.")
    except discord.HTTPException:
        await send_embed(ctx, f"❌ Erreur lors du retrait des rôles de **{utilisateur}**.")


# ─── HACK (troll) ─────────────────────────────────────────────────────────────
@bot.hybrid_command(name="hack", description="Faux hack pour troll un membre")
@is_allowed("hack")
async def hack(ctx, utilisateur: discord.Member):
    embed = discord.Embed(description=f"🖥️ Hacking **{utilisateur.display_name}**...", color=EMBED_COLOR)
    msg = await ctx.send(embed=embed)
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
        f"[~] HACK COMPLETE. {utilisateur.display_name} has been compromised.",
    ]
    for step in steps:
        lines_so_far.append(step)
        display = "\n".join(lines_so_far) + "\n```"
        new_embed = discord.Embed(description=display, color=EMBED_COLOR)
        await msg.edit(embed=new_embed)
        await asyncio.sleep(1.2)


# ─── OFF / ON ─────────────────────────────────────────────────────────────────
@bot.hybrid_command(name="off", description="Désactive le bot entièrement (sauf /on)")
@is_allowed("off")
async def off(ctx):
    global bot_enabled
    bot_enabled = False
    await send_embed(ctx, "🔴 Bot désactivé. Seul `/on` (owner) peut le réactiver.")


@bot.hybrid_command(name="on", description="Réactive le bot (owner uniquement)")
async def on(ctx):
    global bot_enabled
    if ctx.author.id not in OWNER_IDS:
        await send_embed(ctx, "❌ Seul le propriétaire peut réactiver le bot.")
        return
    bot_enabled = True
    await send_embed(ctx, "🟢 Bot réactivé.")


# ─── SAY ──────────────────────────────────────────────────────────────────────
@bot.hybrid_command(name="say", description="Le bot répète exactement le message donné")
@is_allowed("say")
async def say(ctx, *, message: str):
    if ctx.interaction:
        await ctx.interaction.response.send_message("✅ Envoyé.", ephemeral=True)
    await ctx.channel.send(message)


@bot.hybrid_command(name="reset", description="Réinitialise tous les états du bot (owner seulement)")
async def reset(ctx):
    global bot_enabled
    if ctx.author.id not in OWNER_IDS:
        await send_embed(ctx, "❌ Seul le propriétaire peut utiliser /reset.")
        return

    # Retire les pseudos forcés avant de vider la liste des laisses
    for user_id in list(leashed.keys()):
        member = ctx.guild.get_member(user_id)
        if member:
            try:
                await member.edit(nick=None)
            except (discord.Forbidden, discord.HTTPException):
                pass

    leashed.clear()
    moving.clear()
    randomnaming.clear()
    vocallocked.clear()
    mutetoggling.clear()
    spamming.clear()
    blacklist.clear()
    whitelist_cmd.clear()
    whitelist_full.clear()
    whitelist_full.update(OWNER_IDS)
    bot_enabled = True

    await send_embed(ctx, "♻️ Tout a été réinitialisé : laisses, blacklist, pseudos aléatoires, locks vocaux, mutespam, spam MP, whitelist (owners conservés), et le bot est réactivé.")


# ─── WHITELIST ────────────────────────────────────────────────────────────────
@bot.hybrid_command(name="wl", description="Donner un accès total à un membre (owner seulement)")
async def wl(ctx, utilisateur: discord.Member):
    if ctx.author.id not in OWNER_IDS:
        await send_embed(ctx, "❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if utilisateur.id in whitelist_full:
        await send_embed(ctx, f"⚠️ **{utilisateur}** a déjà un accès total.")
        return
    whitelist_full.add(utilisateur.id)
    whitelist_cmd.pop(utilisateur.id, None)
    await send_embed(ctx, f"✅ **{utilisateur}** a maintenant accès à toutes les commandes.")


@bot.hybrid_command(name="unwl", description="Retirer toutes les permissions d'un membre (owner seulement)")
async def unwl(ctx, utilisateur: discord.Member):
    if ctx.author.id not in OWNER_IDS:
        await send_embed(ctx, "❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if utilisateur.id in OWNER_IDS:
        await send_embed(ctx, "❌ Impossible de retirer le propriétaire.")
        return
    if utilisateur.id not in whitelist_full and utilisateur.id not in whitelist_cmd:
        await send_embed(ctx, f"⚠️ **{utilisateur}** n'a aucune permission.")
        return
    whitelist_full.discard(utilisateur.id)
    whitelist_cmd.pop(utilisateur.id, None)
    await send_embed(ctx, f"✅ Toutes les permissions de **{utilisateur}** ont été retirées.")


@bot.hybrid_command(name="wlcmd", description="Donner accès à des commandes précises (owner seulement)")
async def wlcmd(ctx, utilisateur: discord.Member, *, commandes: str):
    if ctx.author.id not in OWNER_IDS:
        await send_embed(ctx, "❌ Seul le propriétaire peut modifier la whitelist.")
        return
    if utilisateur.id in whitelist_full:
        await send_embed(ctx, f"⚠️ **{utilisateur}** a déjà un accès total, inutile de limiter.")
        return
    cmds = commandes.split()
    if not cmds:
        await send_embed(ctx, "⚠️ Précise au moins une commande. Ex: `/wlcmd utilisateur:@user commandes:ban mute`")
        return

    valides = [c for c in cmds if c in VALID_COMMANDS]
    invalides = [c for c in cmds if c not in VALID_COMMANDS]

    if not valides:
        liste_invalides = ", ".join(f"`{c}`" for c in invalides)
        await send_embed(ctx, f"❌ Aucune commande valide fournie. Introuvable(s) : {liste_invalides}")
        return

    if utilisateur.id not in whitelist_cmd:
        whitelist_cmd[utilisateur.id] = set()

    # Ajoute chaque commande valide + son inverse automatiquement (sauf exceptions)
    auto_ajoutees = set()
    for c in valides:
        whitelist_cmd[utilisateur.id].add(c)
        opposite = OPPOSITE_COMMANDS.get(c)
        if opposite and opposite not in whitelist_cmd[utilisateur.id]:
            whitelist_cmd[utilisateur.id].add(opposite)
            auto_ajoutees.add(opposite)

    liste = ", ".join(f"`/{c}`" for c in whitelist_cmd[utilisateur.id])
    description = f"✅ **{utilisateur}** peut maintenant utiliser : {liste}"
    if auto_ajoutees:
        liste_auto = ", ".join(f"`/{c}`" for c in auto_ajoutees)
        description += f"\n➕ Commande(s) inverse(s) ajoutée(s) automatiquement : {liste_auto}"
    if invalides:
        liste_invalides = ", ".join(f"`{c}`" for c in invalides)
        description += f"\n❌ Commande(s) introuvable(s), ignorée(s) : {liste_invalides}"

    await send_embed(ctx, description)


@bot.hybrid_command(name="unwlcmd", description="Retirer l'accès à des commandes précises (owner seulement)")
async def unwlcmd(ctx, utilisateur: discord.Member, *, commandes: str):
    if ctx.author.id not in OWNER_IDS:
        await send_embed(ctx, "❌ Seul le propriétaire peut modifier la whitelist.")
        return
    cmds = commandes.split()
    if not cmds:
        await send_embed(ctx, "⚠️ Précise au moins une commande. Ex: `/unwlcmd utilisateur:@user commandes:ban mute`")
        return

    invalides = [c for c in cmds if c not in VALID_COMMANDS]
    if invalides:
        liste_invalides = ", ".join(f"`{c}`" for c in invalides)
        await send_embed(ctx, f"❌ Commande(s) introuvable(s) : {liste_invalides}")
        return

    if utilisateur.id not in whitelist_cmd:
        await send_embed(ctx, f"⚠️ **{utilisateur}** n'a aucune permission limitée.")
        return
    for c in cmds:
        whitelist_cmd[utilisateur.id].discard(c)
    if not whitelist_cmd[utilisateur.id]:
        del whitelist_cmd[utilisateur.id]
        await send_embed(ctx, f"✅ Toutes les permissions limitées de **{utilisateur}** ont été retirées.")
    else:
        liste = ", ".join(f"`/{c}`" for c in whitelist_cmd[utilisateur.id])
        await send_embed(ctx, f"✅ Permissions mises à jour. **{utilisateur}** peut encore : {liste}")


@bot.hybrid_command(name="perms", description="Voir les permissions d'un utilisateur (owner seulement)")
async def perms(ctx, utilisateur: discord.Member):
    if ctx.author.id not in OWNER_IDS:
        await send_embed(ctx, "❌ Seul le propriétaire peut voir les permissions.")
        return
    if utilisateur.id in whitelist_full:
        await send_embed(ctx, f"🔓 **{utilisateur}** a un accès **total** à toutes les commandes.")
    elif utilisateur.id in whitelist_cmd:
        liste = ", ".join(f"`/{c}`" for c in whitelist_cmd[utilisateur.id])
        await send_embed(ctx, f"🔑 **{utilisateur}** a accès uniquement à : {liste}")
    else:
        await send_embed(ctx, f"⛔ **{utilisateur}** n'a aucune permission.")


# ─── HELP ─────────────────────────────────────────────────────────────────────
@bot.hybrid_command(name="help", description="Affiche la liste des commandes")
@is_allowed("help")
async def help_cmd(ctx):
    embed = discord.Embed(title="📋 Commandes du bot", color=EMBED_COLOR)

    embed.add_field(name="🔨 Modération", value="""
`/ban utilisateur raison` — Bannir un membre
`/mute utilisateur` — Mute vocal
`/unmute utilisateur` — Unmute vocal
`/timeout utilisateur minutes` — Timeout (défaut: 5 min)
`/hack utilisateur` — 👀
""", inline=False)

    embed.add_field(name="✏️ Pseudo / Laisse", value="""
`/rename utilisateur pseudo` — Changer le pseudo
`/dog utilisateur` — Mettre en laisse (pseudo forcé + 🦮)
`/undog utilisateur` — Retirer la laisse
`/name utilisateur` — Pseudo aléatoire toutes les 3s
`/unname utilisateur` — Arrêter le pseudo aléatoire
""", inline=False)

    embed.add_field(name="🌀 Vocal", value="""
`/move utilisateur` — Déplacer en boucle dans des vocaux aléatoires
`/stopmove utilisateur` — Arrêter les déplacements
`/lock utilisateur id_salon` — Bloquer dans un salon vocal
`/unlock utilisateur` — Débloquer du salon vocal
`/mutespam utilisateur` — Mute/unmute en boucle
`/unmutespam utilisateur` — Arrêter le mutespam
""", inline=False)

    embed.add_field(name="📩 Spam MP", value="""
`/spam utilisateur message` — Spammer un membre en MP
`/stopspam utilisateur` — Arrêter le spam MP
""", inline=False)

    embed.add_field(name="🎖️ Rôles", value="""
`/avb utilisateur` — Donner le rôle AVB à un membre
`/derank utilisateur` — Retirer tous les rôles d'un membre
""", inline=False)

    embed.add_field(name="💬 Divers", value="""
`/say message` — Le bot répète exactement le message
`/off` — Désactive le bot entièrement
`/on` — Réactive le bot (owner uniquement)
`/reset` — Réinitialise tous les états du bot (owner uniquement)
""", inline=False)

    embed.add_field(name="⛔ Blacklist", value="""
`/bl utilisateur raison` — Blacklister et bannir définitivement
`/unbl id_utilisateur` — Retirer de la blacklist et débannir
""", inline=False)

    embed.add_field(name="⚙️ Whitelist (owner seulement)", value="""
`/wl utilisateur` — Accès total à toutes les commandes
`/unwl utilisateur` — Retirer toutes les permissions
`/wlcmd utilisateur commandes` — Accès limité à des commandes précises
`/unwlcmd utilisateur commandes` — Retirer l'accès à des commandes précises
`/perms utilisateur` — Voir les permissions d'un utilisateur
""", inline=False)

    await ctx.send(embed=embed)


# ─── LANCEMENT ────────────────────────────────────────────────────────────────
keep_alive()
bot.run(TOKEN)
