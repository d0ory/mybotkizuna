import os
import asyncio
import random
import time
from datetime import timedelta
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

import http.server
import threading

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *args):
        pass

def start_server():
    port = int(os.environ.get("PORT", 10000))
    server = http.server.HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

threading.Thread(target=start_server, daemon=True).start()

load_dotenv()
TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])

# ---- CONFIG ----
WELCOME_CHANNEL_ID = 1561207036274806784
LOG_CHANNEL = "mod-log"
BANNED_WORDS = ["rape", "nigga", "rapist"]
MEMBERS_ROLE_ID = 1561174087823265913
RULES_EMOJI = "✅"
# --------------

ROLES_MESSAGES = {}
RULES_MESSAGES = {}  # guild_id -> message_id

# Anti-nuke tracking
BAN_TRACK = {}
KICK_TRACK = {}
CHANNEL_DELETE_TRACK = {}
ROLE_DELETE_TRACK = {}

# Gambling balances (in-memory, resets on restart)
BALANCES = {}
DAILY_CLAIMED = {}  # user_id -> last claim timestamp

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
        await self.tree.sync()

bot = MyBot()

# ---- HELPERS ----

async def log_action(guild, content, color=discord.Color.red()):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if not channel:
        return
    embed = discord.Embed(description=content, color=color)
    embed.set_footer(text="mod log")
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)

async def antinuke_alert(guild, content, color=discord.Color.red()):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if not channel:
        return
    embed = discord.Embed(description=content, color=color)
    embed.set_author(name="⚠️ ANTI-Nuke Alert")
    embed.set_footer(text=f"triggered by {guild.name} protection")
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed, content="<@&4>" if guild.roles else None)

def get_balance(user_id: int) -> int:
    if user_id not in BALANCES:
        BALANCES[user_id] = 100
    return BALANCES[user_id]

def add_balance(user_id: int, amount: int):
    BALANCES[user_id] = get_balance(user_id) + amount

# ---- EVENTS ----

@bot.event
async def on_ready():
    print(f"up and running as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.channels, id=WELCOME_CHANNEL_ID)
    if not channel:
        channel = member.guild.system_channel
    if not channel:
        return

    embed = discord.Embed(
        color=discord.Color.green()
    )
    embed.set_author(name=f"🎉 Welcome to {member.guild.name}!", icon_url=member.guild.icon.url if member.guild.icon else None)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name=f"Hey {member.mention} 👋",
        value="You're now part of the community!\nHere's what to do next:",
        inline=False
    )
    embed.add_field(
        name="📋 Get Started",
        value="1️⃣ Read the **rules** with `/rules` and react ✅ to unlock your role\n"
              "2️⃣ Grab your roles in the reaction roles channel\n"
              "3️⃣ Say hi in the chat and introduce yourself!",
        inline=False
    )
    embed.add_field(
        name="🎮 Have Fun",
        value="Try `/slots`, `/coinflip_bet`, or `/blackjack` to win some coins!\n"
              "Type `/help` anytime to see everything I can do.",
        inline=False
    )
    embed.set_footer(text=f"Member #{member.guild.member_count} • Welcome aboard 💜", icon_url=member.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    now = time.time()
    guild_id = member.guild.id
    if guild_id not in KICK_TRACK:
        KICK_TRACK[guild_id] = []
    KICK_TRACK[guild_id] = [t for t in KICK_TRACK[guild_id] if now - t < 30]
    KICK_TRACK[guild_id].append(now)

    if len(KICK_TRACK[guild_id]) >= 5:
        count = len(KICK_TRACK[guild_id])
        KICK_TRACK[guild_id] = []
        await antinuke_alert(member.guild, f"🚨 **mass kick detected** — {count}+ members kicked in 30s\nlast: {member.mention} ({member.id})", discord.Color.red())
        return

    channel = discord.utils.get(member.guild.text_channels, name=LOG_CHANNEL)
    if not channel:
        return
    embed = discord.Embed(
        description=f"👋 {member} ({member.id}) left the server",
        color=discord.Color.dark_grey()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)

@bot.event
async def on_member_ban(member, guild):
    now = time.time()
    if guild.id not in BAN_TRACK:
        BAN_TRACK[guild.id] = []
    BAN_TRACK[guild.id] = [t for t in BAN_TRACK[guild.id] if now - t < 30]
    BAN_TRACK[guild.id].append(now)

    if len(BAN_TRACK[guild.id]) >= 5:
        count = len(BAN_TRACK[guild.id])
        BAN_TRACK[guild.id] = []
        await antinuke_alert(guild, f"🚨 **mass ban detected** — {count}+ members banned in 30s\nlast: {member.mention} ({member.id})\n**attempting to unban...**", discord.Color.red())
        try:
            await guild.unban(member, reason="anti-nuke auto-unban")
        except discord.Forbidden:
            pass
        return

    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if not channel:
        return
    embed = discord.Embed(
        description=f"🔨 **{member}** ({member.id}) was banned",
        color=discord.Color.red()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)

@bot.event
async def on_guild_channel_delete(channel):
    now = time.time()
    guild_id = channel.guild.id
    if guild_id not in CHANNEL_DELETE_TRACK:
        CHANNEL_DELETE_TRACK[guild_id] = []
    CHANNEL_DELETE_TRACK[guild_id] = [t for t in CHANNEL_DELETE_TRACK[guild_id] if now - t < 30]
    CHANNEL_DELETE_TRACK[guild_id].append(now)

    if len(CHANNEL_DELETE_TRACK[guild_id]) >= 3:
        count = len(CHANNEL_DELETE_TRACK[guild_id])
        CHANNEL_DELETE_TRACK[guild_id] = []
        await antinuke_alert(channel.guild, f"🚨 **mass channel delete detected** — {count}+ channels deleted in 30s\nlast: #{channel.name}", discord.Color.red())
        return

    log_ch = discord.utils.get(channel.guild.text_channels, name=LOG_CHANNEL)
    if not log_ch:
        return
    embed = discord.Embed(
        description=f"🗑️ channel **#{channel.name}** was deleted",
        color=discord.Color.orange()
    )
    embed.timestamp = discord.utils.utcnow()
    await log_ch.send(embed=embed)

@bot.event
async def on_guild_role_delete(role):
    now = time.time()
    guild_id = role.guild.id
    if guild_id not in ROLE_DELETE_TRACK:
        ROLE_DELETE_TRACK[guild_id] = []
    ROLE_DELETE_TRACK[guild_id] = [t for t in ROLE_DELETE_TRACK[guild_id] if now - t < 30]
    ROLE_DELETE_TRACK[guild_id].append(now)

    if len(ROLE_DELETE_TRACK[guild_id]) >= 3:
        count = len(ROLE_DELETE_TRACK[guild_id])
        ROLE_DELETE_TRACK[guild_id] = []
        await antinuke_alert(role.guild, f"🚨 **mass role delete detected** — {count}+ roles deleted in 30s\nlast: **{role.name}**", discord.Color.red())
        return

    log_ch = discord.utils.get(role.guild.text_channels, name=LOG_CHANNEL)
    if not log_ch:
        return
    embed = discord.Embed(
        description=f"🎭 role **{role.name}** was deleted",
        color=discord.Color.orange()
    )
    embed.timestamp = discord.utils.utcnow()
    await log_ch.send(embed=embed)

@bot.event
async def on_guild_update(before, after):
    changes = []
    if before.name != after.name:
        changes.append(f"**name:** {before.name} → {after.name}")
    if before.icon != after.icon:
        changes.append("**icon changed**")
    if before.owner_id != after.owner_id:
        changes.append(f"**owner:** {before.owner_id} → {after.owner_id}")
    if changes:
        await antinuke_alert(after, f"⚙️ **server settings changed**\n" + "\n".join(changes), discord.Color.yellow())

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    # --- Rules reaction → assign members role ---
    if payload.guild_id in RULES_MESSAGES:
        if payload.message_id == RULES_MESSAGES[payload.guild_id]:
            if str(payload.emoji) == RULES_EMOJI:
                try:
                    guild_obj = await bot.fetch_guild(payload.guild_id)
                    member = await guild_obj.fetch_member(payload.user_id)
                    role = discord.utils.get(guild_obj.roles, id=MEMBERS_ROLE_ID)
                    if role and role not in member.roles:
                        await member.add_roles(role, reason="accepted rules")
                except (discord.Forbidden, discord.NotFound):
                    pass
                return

    # --- Reaction roles ---
    if payload.guild_id not in ROLES_MESSAGES:
        return
    if payload.message_id != ROLES_MESSAGES[payload.guild_id]:
        return
    try:
        guild_obj = await bot.fetch_guild(payload.guild_id)
        ch = await guild_obj.fetch_channel(payload.channel_id)
        message = await ch.fetch_message(payload.message_id)
        if not message.embeds:
            return
        embed = message.embeds[0]
        for line in (embed.description or "").split("\n"):
            stripped = line.strip()
            if stripped.startswith("  "):
                parts = stripped.split("  ", 1)
                if len(parts) == 2:
                    emoji_str, role_name = parts[0].strip(), parts[1].strip()
                    if emoji_str == str(payload.emoji):
                        member = await guild_obj.fetch_member(payload.user_id)
                        role = discord.utils.get(guild_obj.roles, name=role_name)
                        if role:
                            await member.add_roles(role, reason=f"reaction role {emoji_str}")
    except (discord.Forbidden, discord.NotFound, IndexError):
        pass

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return
    if payload.guild_id not in ROLES_MESSAGES:
        return
    if payload.message_id != ROLES_MESSAGES[payload.guild_id]:
        return
    try:
        guild_obj = await bot.fetch_guild(payload.guild_id)
        ch = await guild_obj.fetch_channel(payload.channel_id)
        message = await ch.fetch_message(payload.message_id)
        if not message.embeds:
            return
        embed = message.embeds[0]
        for line in (embed.description or "").split("\n"):
            stripped = line.strip()
            if stripped.startswith("  "):
                parts = stripped.split("  ", 1)
                if len(parts) == 2:
                    emoji_str, role_name = parts[0].strip(), parts[1].strip()
                    if emoji_str == str(payload.emoji):
                        member = await guild_obj.fetch_member(payload.user_id)
                        role = discord.utils.get(guild_obj.roles, name=role_name)
                        if role and role in member.roles:
                            await member.remove_roles(role, reason=f"removed reaction role {emoji_str}")
    except (discord.Forbidden, discord.NotFound, IndexError):
        pass

@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return
    content = message.content.lower()
    for word in BANNED_WORDS:
        if word.lower() in content:
            try:
                await message.delete()
                await message.channel.send(f"hey {message.author.mention}, that word's banned here. keep it clean.", delete_after=5)
                await log_action(message.guild, f"**filtered message** — {message.author.mention} in #{message.channel.name}\ncontent: `{word}`", discord.Color.orange())
            except discord.Forbidden:
                pass
            return

# ---- ERROR HANDLER ----

@bot.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        embed = discord.Embed(description="you don't have permission for that. ask a mod if you think that's a mistake.", color=discord.Color.red())
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError):
        print(f"error in {interaction.command.name}: {error.original}")
        if not interaction.response.is_done():
            await interaction.response.send_message("something broke on my end, try again in a sec.", ephemeral=True)
    else:
        print(f"unhandled error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("something went wrong.", ephemeral=True)

# ---- MODALS ----

class SetupRolesModal(discord.ui.Modal, title="Create Reaction Roles"):
    channel = discord.ui.TextInput(label="Channel", placeholder="e.g. roles", style=discord.TextStyle.short, required=True)
    title = discord.ui.TextInput(label="Embed Title", placeholder="e.g. Pick Your Roles", style=discord.TextStyle.short, required=True)
    description = discord.ui.TextInput(label="Description", placeholder="e.g. React below to get your roles!", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        channel_name = self.channel.value.lstrip("#")
        channel = discord.utils.get(interaction.guild.text_channels, name=channel_name)
        if not channel:
            await interaction.response.send_message(f"channel **#{channel_name}** not found.", ephemeral=True)
            return

        desc = self.description.value or "react below to get your roles!"
        embed = discord.Embed(
            title=f"👤 {self.title.value}",
            description=f"{desc}\n\n**available roles:**\n\n  _none yet. use `/add_reaction` to add some._",
            color=discord.Color.teal()
        )
        embed.set_footer(text=f"managed by {interaction.guild.name} bot")
        embed.timestamp = discord.utils.utcnow()

        msg = await channel.send(embed=embed)
        ROLES_MESSAGES[interaction.guild.id] = msg.id

        confirm = discord.Embed(
            title="✅ reaction roles created",
            description=f"posted in **#{channel_name}**\n\nuse **`/add_reaction`** to add emoji + role pairs",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=confirm, ephemeral=True)
        await log_action(interaction.guild, f"**roles setup** — reaction roles embed created in #{channel_name} by {interaction.user.mention}", discord.Color.green())


class AddReactionModal(discord.ui.Modal, title="Add Reaction Role"):
    emoji = discord.ui.TextInput(label="Emoji", placeholder="paste the emoji here", style=discord.TextStyle.short, required=True)
    role_name = discord.ui.TextInput(label="Role Name", placeholder="e.g. Gamer", style=discord.TextStyle.short, required=True)
    channel_name = discord.ui.TextInput(label="Channel", placeholder="where the roles embed is posted", style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        channel_name = self.channel_name.value.lstrip("#")
        channel = discord.utils.get(interaction.guild.text_channels, name=channel_name)
        if not channel:
            await interaction.response.send_message(f"channel **#{channel_name}** not found.", ephemeral=True)
            return

        role = discord.utils.get(interaction.guild.roles, name=self.role_name.value)
        if not role:
            await interaction.response.send_message(f"role **{self.role_name.value}** not found. make sure it exists in server settings.", ephemeral=True)
            return

        if interaction.guild.id not in ROLES_MESSAGES:
            await interaction.response.send_message("no reaction roles embed found. run **`/setup_roles`** first.", ephemeral=True)
            return

        try:
            message = await channel.fetch_message(ROLES_MESSAGES[interaction.guild.id])
        except discord.NotFound:
            await interaction.response.send_message("the roles embed was deleted. run **`/setup_roles`** again.", ephemeral=True)
            return

        if not message.embeds:
            await interaction.response.send_message("the roles embed is broken. run **`/setup_roles`** again.", ephemeral=True)
            return

        embed = message.embeds[0]
        desc_lines = (embed.description or "").split("\n")
        desc_lines = [l for l in desc_lines if "_none yet" not in l]

        new_line = f"  {self.emoji.value}  {self.role_name.value}"
        desc_lines.append(new_line)

        embed.description = "\n".join(desc_lines)
        await message.edit(embed=embed)
        await message.add_reaction(self.emoji.value)

        confirm = discord.Embed(
            title="✅ reaction added",
            description=f"**{self.emoji.value}** → **{self.role_name.value}**\n\nposted in **#{channel_name}**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=confirm, ephemeral=True)
        await log_action(interaction.guild, f"**roles update** — {self.emoji.value} → {self.role_name.value} added by {interaction.user.mention}", discord.Color.green())


class RemoveReactionModal(discord.ui.Modal, title="Remove Reaction Role"):
    emoji = discord.ui.TextInput(label="Emoji", placeholder="the emoji to remove", style=discord.TextStyle.short, required=True)
    channel_name = discord.ui.TextInput(label="Channel", placeholder="where the roles embed is posted", style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        channel_name = self.channel_name.value.lstrip("#")
        channel = discord.utils.get(interaction.guild.text_channels, name=channel_name)
        if not channel:
            await interaction.response.send_message(f"channel **#{channel_name}** not found.", ephemeral=True)
            return

        if interaction.guild.id not in ROLES_MESSAGES:
            await interaction.response.send_message("no reaction roles embed found.", ephemeral=True)
            return

        try:
            message = await channel.fetch_message(ROLES_MESSAGES[interaction.guild.id])
        except discord.NotFound:
            await interaction.response.send_message("the roles embed was deleted.", ephemeral=True)
            return

        if not message.embeds:
            await interaction.response.send_message("the roles embed is broken.", ephemeral=True)
            return

        embed = message.embeds[0]
        desc_lines = (embed.description or "").split("\n")
        new_lines = []
        removed = False
        for line in desc_lines:
            stripped = line.strip()
            if stripped.startswith(self.emoji.value):
                removed = True
                continue
            new_lines.append(line)

        if not removed:
            await interaction.response.send_message(f"emoji **{self.emoji.value}** not found in the roles embed.", ephemeral=True)
            return

        role_lines = [l for l in new_lines if l.strip().startswith("  ") and "_none yet" not in l]
        if len(role_lines) == 0:
            new_lines.append("  _none yet. use `/add_reaction` to add some._")

        embed.description = "\n".join(new_lines)
        await message.edit(embed=embed)

        try:
            await message.clear_reaction(self.emoji.value)
        except Exception:
            pass

        confirm = discord.Embed(
            title="✅ reaction removed",
            description=f"**{self.emoji.value}** removed from **#{channel_name}**",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=confirm, ephemeral=True)


# ---- REACTION ROLES COMMANDS ----

@bot.tree.command(name="setup_roles", description="create a new reaction roles embed (staff)")
@app_commands.checks.has_permissions(manage_roles=True)
async def setup_roles(interaction: discord.Interaction):
    await interaction.response.send_modal(SetupRolesModal())

@bot.tree.command(name="add_reaction", description="add an emoji + role to the roles embed (staff)")
@app_commands.checks.has_permissions(manage_roles=True)
async def add_reaction(interaction: discord.Interaction):
    await interaction.response.send_modal(AddReactionModal())

@bot.tree.command(name="remove_reaction", description="remove an emoji + role from the roles embed (staff)")
@app_commands.checks.has_permissions(manage_roles=True)
async def remove_reaction(interaction: discord.Interaction):
    await interaction.response.send_modal(RemoveReactionModal())

# ---- ANTI-Nuke COMMAND ----

@bot.tree.command(name="antinuke_status", description="show anti-nuke protection status (staff)")
@app_commands.checks.has_permissions(manage_guild=True)
async def antinuke_status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ anti-nuke protection",
        description="all protections are **always active** and cannot be disabled.\n\n**what's protected:**\n\n"
                    "• 🚫 mass bans (5+ in 30s → alert + auto-unban)\n"
                    "• 🚫 mass kicks (5+ in 30s → alert)\n"
                    "• 🚫 mass channel deletes (3+ in 30s → alert)\n"
                    "• 🚫 mass role deletes (3+ in 30s → alert)\n"
                    "• ⚙️ server name/icon/owner changes → alert\n\n"
                    "all events are logged in **#" + LOG_CHANNEL + "**",
        color=discord.Color.green()
    )
    embed.set_footer(text="protection is automatic and cannot be turned off")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---- CORE ----

@bot.tree.command(name="ping", description="check bot latency")
async def ping(interaction: discord.Interaction):
    start = time.time()
    await interaction.response.send_message("🏓 pinging...")
    end = time.time()
    await interaction.edit_original_response(content=f"🏓 pong! `{round((end - start) * 1000)}ms`")

@bot.tree.command(name="hello", description="say hi to someone")
@app_commands.describe(user="who are we greeting?")
async def hello(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user = interaction.user
    msgs = [
        f"hey {user.mention}, what's good 👋",
        f"yo {user.mention}, welcome back!",
        f"heyyy {user.mention} ✨",
        f"sup {user.mention}, how you doing",
        f"yo yo {user.mention} 🔥",
        f"what's up {user.mention} 🤙",
    ]
    await interaction.response.send_message(random.choice(msgs))

@bot.tree.command(name="say", description="make the bot say something")
@app_commands.describe(text="what should i say?")
async def say(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

@bot.tree.command(name="rules", description="server rules — react ✅ to get your role")
async def rules(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 Server Rules",
        description="Read these carefully. Breaking them means consequences.",
        color=discord.Color.blurple()
    )
    if interaction.guild.icon:
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)

    embed.add_field(name="🤝 Respect Everyone", value="No harassment, hate speech, or targeted bullying. Be a decent human.", inline=False)
    embed.add_field(name="🔞 No NSFW", value="Explicit content is not allowed in any channel. Period.", inline=False)
    embed.add_field(name="🚫 No Spam", value="No flooding, spam, or unsolicited DMs. You'll get timed out.", inline=False)
    embed.add_field(name="📌 Stay On Topic", value="Use the right channel for the right content. #memes is for memes, not wifi password requests.", inline=False)
    embed.add_field(name="📢 No Self-Promo", value="Don't advertise your server, stream, or drop links without asking staff first.", inline=False)
    embed.add_field(name="🔒 Privacy", value="No doxxing. No sharing someone's personal info. Non-negotiable.", inline=False)
    embed.add_field(name="🇬🇧 English Only", value="Public channels are English. Use #foreign for everything else.", inline=False)
    embed.add_field(name="⚖️ Discord ToS", value="Discord's Terms of Service and Community Guidelines apply here too.", inline=False)
    embed.add_field(name="⚠️ Consequences", value="**Warning → Timeout → Kick/Ban**\nRepeat offenses skip the warning.", inline=False)
    embed.add_field(name="💬 Disagree with a mod?", value="Open a ticket or DM staff. Arguing in public makes it worse for you.", inline=False)

    embed.add_field(name=f"{RULES_EMOJI} Accept Rules", value=f"React with {RULES_EMOJI} below to confirm you've read the rules and get your **member role**.", inline=False)

    if interaction.guild.icon:
        embed.set_footer(text=f"Thank you for keeping {interaction.guild.name} a good place 💜", icon_url=interaction.guild.icon.url)
    else:
        embed.set_footer(text="Thank you for keeping this a good place 💜")
    embed.timestamp = discord.utils.utcnow()

    msg = await interaction.response.send_message(embed=embed)
    await msg.add_reaction(RULES_EMOJI)

    # Store the rules message ID for reaction tracking
    if interaction.guild.id not in RULES_MESSAGES:
        RULES_MESSAGES[interaction.guild.id] = msg.id

@bot.tree.command(name="help", description="full command guide")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Command Guide",
        description="Everything I can do, organized by category.\nClick a command name for details, or just type it!",
        color=discord.Color.purple()
    )
    if interaction.guild.icon:
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)

    embed.add_field(
        name="ℹ️ Info",
        value="`/ping` — check my latency\n"
              "`/avatar` — view someone's avatar\n"
              "`/userinfo` — detailed user info\n"
              "`/serverinfo` — server statistics\n"
              "`/rules` — read rules & get your role",
        inline=False
    )
    embed.add_field(
        name="🎰 Casino & Gambling",
        value="`/slots` — spin the slot machine\n"
              "`/coinflip_bet` — bet on heads or tails\n"
              "`/dice_bet` — bet high or low on a d6\n"
              "`/blackjack` — play a round of blackjack\n"
              "`/balance` — check your coin balance\n"
              "`/daily` — claim 50 free coins (once per day)",
        inline=False
    )
    embed.add_field(
        name="🎲 Fun",
        value="`/8ball` — ask the magic 8-ball\n"
              "`/coinflip` — flip a coin (no betting)\n"
              "`/roll` — roll dice (XdY format)\n"
              "`/hello` — say hi to someone\n"
              "`/say` — make me say anything",
        inline=False
    )
    embed.add_field(
        name="🛠️ Utility",
        value="`/poll` — create a quick A/B poll\n"
              "`/remind` — set a reminder (1-1440 min)\n"
              "`/clear` — delete recent messages (staff)",
        inline=False
    )
    embed.add_field(
        name="👤 Roles (Staff)",
        value="`/setup_roles` — create reaction roles embed\n"
              "`/add_reaction` — add an emoji+role pair\n"
              "`/remove_reaction` — remove an emoji+role pair",
        inline=False
    )
    embed.add_field(
        name="🛡️ Moderation (Staff)",
        value="`/ban` — ban a member\n"
              "`/kick` — kick a member\n"
              "`/timeout` — timeout a member\n"
              "`/antinuke_status` — view protection status",
        inline=False
    )
    embed.add_field(
        name="💡 Tips",
        value="• You start with **100 coins** — use `/daily` for more\n"
              "• Casino bets are risky — don't bet what you can't afford to lose!\n"
              "• Balances reset when the bot restarts\n"
              "• React ✅ on `/rules` to get your member role",
        inline=False
    )
    embed.set_footer(text=f"Made for {interaction.guild.name} • {len(bot.tree.get_commands())} commands available")
    await interaction.response.send_message(embed=embed)

# ---- INFO ----

@bot.tree.command(name="avatar", description="show someone's avatar")
@app_commands.describe(user="whose avatar? (default: you)")
async def avatar(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user = interaction.user
    embed = discord.Embed(
        title=f"{user.display_name}'s avatar",
        color=discord.Color.random()
    )
    embed.set_image(url=user.display_avatar.url)
    embed.set_footer(text="right click → copy image address to save it")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="detailed info about a user")
@app_commands.describe(user="who? (default: you)")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user = interaction.user
    roles = [r.mention for r in sorted(user.roles, key=lambda r: r.position) if r.name != "@everyone"]
    embed = discord.Embed(
        title=f"👤 {user.display_name}",
        color=discord.Color.random()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="Joined Server", value=user.joined_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name="Account Created", value=user.created_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name="Status", value=str(user.status).capitalize(), inline=True)
    embed.add_field(name="Roles", value=", ".join(roles) if roles else "none", inline=False)
    embed.add_field(name="Balance", value=f"🪙 {get_balance(user.id)} coins", inline=True)
    embed.set_footer(text=f"{user.display_name}#{user.discriminator}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="about this server")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    online = sum(1 for m in g.members if m.status != discord.Status.offline)
    embed = discord.Embed(
        title=f"🏠 {g.name}",
        color=discord.Color.blurple()
    )
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="👥 Members", value=f"{g.member_count} total • {online} online", inline=True)
    embed.add_field(name="💬 Channels", value=str(len(g.text_channels)), inline=True)
    embed.add_field(name="🎭 Roles", value=str(len(g.roles) - 1), inline=True)
    embed.add_field(name="📅 Created", value=g.created_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name="🚀 Boosts", value=str(g.premium_subscription_count), inline=True)
    embed.add_field(name="👑 Owner", value=g.owner.display_name if g.owner else "unknown", inline=True)
    embed.set_footer(text=f"server id: {g.id}")
    await interaction.response.send_message(embed=embed)

# ---- FUN ----

@bot.tree.command(name="8ball", description="ask the magic 8-ball a question")
@app_commands.describe(question="your question")
async def eightball(interaction: discord.Interaction, question: str):
    answers = [
        "🟢 it's certain.",
        "🟢 without a doubt.",
        "🟢 yes, definitely.",
        "🟢 you may rely on it.",
        "🟢 as I see it, yes.",
        "🟢 outlook good.",
        "🟡 reply hazy, ask again later.",
        "🟡 can't predict right now.",
        "🟡 concentrate and ask again.",
        "🔴 don't count on it.",
        "🔴 my sources say no.",
        "🔴 outlook not so good.",
        "🔴 definitely not.",
        "🔴 very doubtful.",
        "⚪ the fog is too thick to see.",
        "⚪ better not tell you now.",
    ]
    embed = discord.Embed(
        title="🎱 Magic 8-Ball",
        description=f"**Q:** {question}\n\n**A:** {random.choice(answers)}",
        color=discord.Color.dark_teal()
    )
    embed.set_footer(text="the 8-ball always knows... probably")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="coinflip", description="flip a coin (no betting)")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["heads", "tails"])
    emoji = "🪙" if result == "heads" else "🌙"
    embed = discord.Embed(
        title="🪙 Coin Flip",
        description=f"{emoji} **{result.title()}**!\n\n*the coin spins through the air...*",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roll", description="roll dice")
@app_commands.describe(sides="sides per die (2-1000, default 6)")
@app_commands.describe(count="number of dice (1-20, default 1)")
async def roll(interaction: discord.Interaction, sides: int = 6, count: int = 1):
    count = max(1, min(count, 20))
    sides = max(2, min(sides, 1000))
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    if count == 1:
        desc = f"🎲 You rolled a **{rolls[0]}** on a d{sides}"
    else:
        desc = f"🎲 {', '.join(map(str, rolls))} on {count}d{sides} → **{total}**"
    embed = discord.Embed(title="🎲 Dice Roll", description=desc, color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)

# ---- CASINO / GAMBLING ----

@bot.tree.command(name="balance", description="check your coin balance")
async def balance_cmd(interaction: discord.Interaction):
    bal = get_balance(interaction.user.id)
    embed = discord.Embed(
        title="🪙 Your Balance",
        description=f"{interaction.user.mention} has **{bal}** coins\n\n*use `/daily` to claim free coins!*",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="daily", description="claim your daily 50 coins")
async def daily(interaction: discord.Interaction):
    user_id = interaction.user.id
    now = time.time()
    if user_id in DAILY_CLAIMED:
        elapsed = now - DAILY_CLAIMED[user_id]
        if elapsed < 86400:
            remaining = int(86400 - elapsed)
            hours = remaining // 3600
            mins = (remaining % 3600) // 60
            await interaction.response.send_message(f"⏰ you already claimed today! come back in **{hours}h {mins}m**.", ephemeral=True)
            return
    add_balance(user_id, 50)
    DAILY_CLAIMED[user_id] = now
    embed = discord.Embed(
        title="🎁 Daily Reward!",
        description=f"+**50** coins added to your balance!\n\nNew balance: **{get_balance(user_id)}** 🪙",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="slots", description="spin the slot machine! 🎰")
@app_commands.describe(bet="how many coins to bet? (min 10)")
async def slots(interaction: discord.Interaction, bet: int = 10):
    bet = max(10, min(bet, get_balance(interaction.user.id)))
    bal = get_balance(interaction.user.id)
    if bal < bet:
        await interaction.response.send_message(f"❌ you only have **{bal}** coins! use `/daily` for more.", ephemeral=True)
        return

    await interaction.response.send_message("🎰 spinning...", ephemeral=True)
    await asyncio.sleep(1.5)

    symbols = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
    reel1 = random.choice(symbols)
    reel2 = random.choice(symbols)
    reel3 = random.choice(symbols)

    display = f"| {reel1} | {reel2} | {reel3} |"

    if reel1 == reel2 == reel3:
        if reel1 == "7️⃣":
            winnings = bet * 10
            msg = "🎉🎉 **JACKPOT!** 🎉🎉\n**7️⃣ 7️⃣ 7️⃣** — you won **10x** your bet!"
            color = discord.Color.gold()
        elif reel1 == "💎":
            winnings = bet * 5
            msg = "💎 **Diamonds!** 💎\nYou won **5x** your bet!"
            color = discord.Color.blue()
        else:
            winnings = bet * 3
            msg = f"✨ **Triple {reel1}!** ✨\nYou won **3x** your bet!"
            color = discord.Color.green()
        add_balance(interaction.user.id, winnings)
    elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
        winnings = bet
        msg = f"👀 **Pair!** You got your bet back."
        color = discord.Color.orange()
        add_balance(interaction.user.id, winnings)
    else:
        winnings = 0
        msg = "😔 No match... better luck next time!"
        color = discord.Color.red()

    add_balance(interaction.user.id, -bet)

    embed = discord.Embed(
        title="🎰 Slot Machine",
        description=f"{display}\n\n{msg}\n\n**Bet:** {bet} 🪙 → **Won:** {winnings} 🪙\n**New balance:** {get_balance(interaction.user.id)} 🪙",
        color=color
    )
    embed.set_footer(text="odds: 1/216 for jackpot • 1/36 for pair")
    await interaction.edit_original_response(content=None, embed=embed)

@bot.tree.command(name="coinflip_bet", description="bet coins on heads or tails")
@app_commands.describe(bet="how many coins to bet? (min 10)")
@app_commands.describe(side="heads or tails")
async def coinflip_bet(interaction: discord.Interaction, side: str, bet: int = 10):
    bet = max(10, min(bet, get_balance(interaction.user.id)))
    bal = get_balance(interaction.user.id)
    if bal < bet:
        await interaction.response.send_message(f"❌ you only have **{bal}** coins!", ephemeral=True)
        return
    side = side.lower()
    if side not in ("heads", "tails"):
        await interaction.response.send_message("❌ pick **heads** or **tails**.", ephemeral=True)
        return

    await interaction.response.send_message("🪙 flipping...", ephemeral=True)
    await asyncio.sleep(1)

    result = random.choice(["heads", "tails"])
    won = result == side

    add_balance(interaction.user.id, -bet)
    if won:
        add_balance(interaction.user.id, bet * 2)
        emoji = "🪙" if result == "heads" else "🌙"
        msg = f"{emoji} **{result.title()}!** You won **{bet * 2}** coins! 🎉"
        color = discord.Color.green()
    else:
        emoji = "🪙" if result == "heads" else "🌙"
        msg = f"{emoji} **{result.title()}!** You lost **{bet}** coins. 💀"
        color = discord.Color.red()

    embed = discord.Embed(
        title="🪙 Coin Flip Bet",
        description=f"You bet on **{side.title()}**\nResult: **{result.title()}**\n\n{msg}\n\n**New balance:** {get_balance(interaction.user.id)} 🪙",
        color=color
    )
    embed.set_footer(text="2x payout on win • 50/50 odds")
    await interaction.edit_original_response(content=None, embed=embed)

@bot.tree.command(name="dice_bet", description="bet high or low on a d6 roll")
@app_commands.describe(bet="how many coins to bet? (min 10)")
@app_commands.describe(guess="high (4-6) or low (1-3)")
async def dice_bet(interaction: discord.Interaction, guess: str, bet: int = 10):
    bet = max(10, min(bet, get_balance(interaction.user.id)))
    bal = get_balance(interaction.user.id)
    if bal < bet:
        await interaction.response.send_message(f"❌ you only have **{bal}** coins!", ephemeral=True)
        return
    guess = guess.lower()
    if guess not in ("high", "low"):
        await interaction.response.send_message("❌ pick **high** (4-6) or **low** (1-3).", ephemeral=True)
        return

    await interaction.response.send_message("🎲 rolling...", ephemeral=True)
    await asyncio.sleep(1)

    roll = random.randint(1, 6)
    dice_faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    is_high = roll >= 4
    won = (guess == "high" and is_high) or (guess == "low" and not is_high)

    add_balance(interaction.user.id, -bet)
    if won:
        add_balance(interaction.user.id, bet * 2)
        msg = f"🎉 You won **{bet * 2}** coins!"
        color = discord.Color.green()
    else:
        msg = f"💀 You lost **{bet}** coins."
        color = discord.Color.red()

    embed = discord.Embed(
        title="🎲 Dice Bet",
        description=f"You bet on **{guess.title()}**\nResult: {dice_faces[roll-1]} **{roll}** ({'High' if is_high else 'Low'})\n\n{msg}\n\n**New balance:** {get_balance(interaction.user.id)} 🪙",
        color=color
    )
    embed.set_footer(text="2x payout • 50/50 odds (1-3 low, 4-6 high)")
    await interaction.edit_original_response(content=None, embed=embed)

@bot.tree.command(name="blackjack", description="play a round of blackjack (bet min 10)")
@app_commands.describe(bet="how many coins to bet? (min 10)")
async def blackjack(interaction: discord.Interaction, bet: int = 10):
    bet = max(10, min(bet, get_balance(interaction.user.id)))
    bal = get_balance(interaction.user.id)
    if bal < bet:
        await interaction.response.send_message(f"❌ you only have **{bal}** coins!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # Simple blackjack: you get 2 cards, dealer gets 2 (one hidden)
    # You choose hit or stand via the result
    def draw_card():
        suits = ["♠️", "♥️", "♦️", "♣️"]
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        suit = random.choice(suits)
        rank = random.choice(ranks)
        value = 11 if rank == "A" else (10 if rank in ("J", "Q", "K") else int(rank))
        return f"{rank}{suit}", value

    player_hand = [draw_card() for _ in range(2)]
    dealer_hand = [draw_card() for _ in range(2)]

    def hand_value(hand):
        total = sum(v for _, v in hand)
        aces = sum(1 for _, v in hand if v == 11)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def format_hand(hand):
        return " ".join(f"{c}" for c, _ in hand)

    player_total = hand_value(player_hand)
    dealer_total = hand_value(dealer_hand)

    # Auto-play: if player has < 17, hit once (simplified)
    if player_total < 17:
        player_hand.append(draw_card())
        player_total = hand_value(player_hand)

    # Dealer hits until 17+
    while hand_value(dealer_hand) < 17:
        dealer_hand.append(draw_card())
    dealer_total = hand_value(dealer_hand)

    # Determine winner
    if player_total > 21:
        result = "bust"
        msg = f"💀 You **busted** with {player_total}! Dealer wins."
        color = discord.Color.red()
    elif dealer_total > 21:
        result = "dealer_bust"
        add_balance(interaction.user.id, bet * 2)
        msg = f"🎉 Dealer **busted** with {dealer_total}! You win **{bet * 2}** coins!"
        color = discord.Color.green()
    elif player_total > dealer_total:
        result = "win"
        add_balance(interaction.user.id, bet * 2)
        msg = f"🎉 You **win** {player_total} vs {dealer_total}! +**{bet * 2}** coins!"
        color = discord.Color.green()
    elif player_total == dealer_total:
        result = "push"
        add_balance(interaction.user.id, bet)
        msg = f"🤝 **Push!** Both have {player_total}. Bet returned."
        color = discord.Color.orange()
    else:
        result = "lose"
        msg = f"😔 Dealer wins {dealer_total} vs your {player_total}. -{bet} coins."
        color = discord.Color.red()

    if result not in ("win", "dealer_bust", "push"):
        add_balance(interaction.user.id, -bet)
    elif result == "push":
        pass  # already returned bet
    else:
        add_balance(interaction.user.id, -bet)

    embed = discord.Embed(
        title="🃏 Blackjack",
        description=f"**Your hand:** {format_hand(player_hand)} → **{player_total}**\n"
                    f"**Dealer:** {format_hand(dealer_hand)} → **{dealer_total}**\n\n"
                    f"{msg}\n\n**New balance:** {get_balance(interaction.user.id)} 🪙",
        color=color
    )
    embed.set_footer(text="Simplified: auto-hit under 17 • Dealer hits to 17 • 2x payout on win")
    await interaction.followup.send(embed=embed, ephemeral=True)

# ---- UTILITY ----

@bot.tree.command(name="poll", description="create a quick A/B poll")
@app_commands.describe(question="the question")
@app_commands.describe(option_a="first option")
@app_commands.describe(option_b="second option")
async def poll(interaction: discord.Interaction, question: str, option_a: str, option_b: str):
    embed = discord.Embed(
        title=f"📊 Poll: {question}",
        color=discord.Color.orange()
    )
    embed.add_field(name=f"🅰️ {option_a}", value="👍", inline=True)
    embed.add_field(name=f"🅱️ {option_b}", value="👎", inline=True)
    embed.set_footer(text="react to vote!")
    await interaction.response.send_message(embed=embed)
    # Add reactions after the message is sent
    await asyncio.sleep(0.5)
    msg = await interaction.original_response()
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.tree.command(name="remind", description="set a reminder")
@app_commands.describe(minutes="how many minutes from now? (1-1440)")
@app_commands.describe(what="what to remind you about")
async def remind(interaction: discord.Interaction, minutes: int, what: str):
    minutes = max(1, min(minutes, 1440))
    channel = interaction.channel
    user = interaction.user
    await interaction.response.send_message(f"⏰ ok, I'll ping you in **{minutes} min** about: {what}", ephemeral=True)
    await asyncio.sleep(minutes * 60)
    try:
        await channel.send(f"{user.mention} — ⏰ reminder: **{what}**")
    except discord.Forbidden:
        pass

@bot.tree.command(name="clear", description="delete recent messages (staff)")
@app_commands.describe(amount="how many? (1-100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int = 10):
    amount = max(1, min(amount, 100))
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🗑️ deleted **{len(deleted)}** messages", ephemeral=True)

# ---- MODERATION ----

@bot.tree.command(name="ban", description="ban a member (staff)")
@app_commands.describe(user="who?")
@app_commands.describe(reason="why?")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "no reason given"):
    await interaction.guild.ban(user, reason=reason)
    embed = discord.Embed(description=f"🔨 banned **{user.display_name}**\nreason: {reason}", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, f"**ban** — {user.mention} by {interaction.user.mention}\nreason: {reason}", discord.Color.red())

@bot.tree.command(name="kick", description="kick a member (staff)")
@app_commands.describe(user="who?")
@app_commands.describe(reason="why?")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "no reason given"):
    await interaction.guild.kick(user, reason=reason)
    embed = discord.Embed(description=f"👢 kicked **{user.display_name}**\nreason: {reason}", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, f"**kick** — {user.mention} by {interaction.user.mention}\nreason: {reason}", discord.Color.orange())

@bot.tree.command(name="timeout", description="timeout a member (staff)")
@app_commands.describe(user="who?")
@app_commands.describe(minutes="how long? (1-10080)")
@app_commands.describe(reason="why?")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, user: discord.Member, minutes: int = 10, reason: str = "no reason given"):
    minutes = max(1, min(minutes, 10080))
    await user.timeout(timedelta(minutes=minutes), reason=reason)
    embed = discord.Embed(description=f"⏰ timed out **{user.display_name}** for {minutes} min\nreason: {reason}", color=discord.Color.yellow())
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, f"**timeout** — {user.mention} by {interaction.user.mention}\nreason: {reason} for {minutes}m", discord.Color.yellow())

# ---- RUN ----

if __name__ == "__main__":
    bot.run(TOKEN)   