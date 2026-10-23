import os
import asyncio
import random
from datetime import timedelta
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = int(os.environ["GUILD_ID"])

# ---- EDIT THESE ----
WELCOME_CHANNEL = "welcome"
LOG_CHANNEL = "mod-log"
BANNED_WORDS = ["rape", "nigga", "rapist"]
REACTION_ROLES = {
    "🎮": "Gamer",
    "🎨": "Art Fan",
    "🧑‍🎨": "Artist",
    "📺": "Show Watcher",
    "🛁": "Anime Watcher",
    "🎵": "Music Lover",
}
# --------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

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

# ---- EVENTS ----

@bot.event
async def on_ready():
    print(f"up and running as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL)
    if not channel:
        channel = member.guild.system_channel
    if not channel:
        return
    embed = discord.Embed(
        description=f"yo {member.mention}, welcome to **{member.guild.name}**.\nintroduce yourself and grab your roles below 👇",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"member #{member.guild.member_count}")
    await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel = discord.utils.get(member.guild.text_channels, name=LOG_CHANNEL)
    if not channel:
        return
    embed = discord.Embed(
        description=f"{member} ({member.id}) left the server",
        color=discord.Color.dark_grey()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await channel.send(embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    emoji_str = str(payload.emoji)
    if emoji_str not in REACTION_ROLES:
        return
    role_name = REACTION_ROLES[emoji_str]
    try:
        guild_obj = await bot.fetch_guild(payload.guild_id)
        member = await guild_obj.fetch_member(payload.user_id)
        role = discord.utils.get(guild_obj.roles, name=role_name)
        if role:
            await member.add_roles(role, reason=f"reaction role {emoji_str}")
    except (discord.Forbidden, discord.NotFound):
        pass

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return
    emoji_str = str(payload.emoji)
    if emoji_str not in REACTION_ROLES:
        return
    role_name = REACTION_ROLES[emoji_str]
    try:
        guild_obj = await bot.fetch_guild(payload.guild_id)
        member = await guild_obj.fetch_member(payload.user_id)
        role = discord.utils.get(guild_obj.roles, name=role_name)
        if role and role in member.roles:
            await member.remove_roles(role, reason=f"removed reaction role {emoji_str}")
    except (discord.Forbidden, discord.NotFound):
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

# ---- CORE ----

@bot.tree.command(name="ping", description="yep, i'm here")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"pong. {round(bot.latency * 1000)}ms")

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
    ]
    await interaction.response.send_message(random.choice(msgs))

@bot.tree.command(name="say", description="make me say something")
@app_commands.describe(text="what should i say?")
async def say(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

@bot.tree.command(name="rules", description="server rules, read them")
async def rules(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📜 rules",
        description="read these before you get nuked.",
        color=discord.Color.blurple()
    )
    if interaction.guild.icon:
        embed.set_author(name=interaction.guild.name, icon_url=interaction.guild.icon.url)
    embed.add_field(name="🤝 respect", value="no harassment, hate speech, or targeted bullying. be a decent human.", inline=False)
    embed.add_field(name="🔞 no nsfw", value="explicit content is not allowed in any channel. period.", inline=False)
    embed.add_field(name="🚫 no spam", value="no flooding, spam, or unsolicited dms. you'll get timed out.", inline=False)
    embed.add_field(name="📌 stay on topic", value="use the right channel for the right content. #memes is for memes, not for asking where the wifi password is.", inline=False)
    embed.add_field(name="📢 no self-promo", value="don't advertise your server, stream, or drop links without asking staff first.", inline=False)
    embed.add_field(name="🔒 privacy", value="no doxxing. no sharing someone's personal info. this is non-negotiable.", inline=False)
    embed.add_field(name="🇬🇧 english only", value="public channels are english. there's a #foreign for everything else.", inline=False)
    embed.add_field(name="⚖️ discord tos", value="discord's terms of service and community guidelines apply here too.", inline=False)
    embed.add_field(name="⚠️ what happens if you break them", value="**warning → timeout → kick/ban**\nrepeat offenses skip the warning. we don't do second chances twice.", inline=False)
    embed.add_field(name="💬 disagree with a mod?", value="open a ticket or dm staff. arguing in public just makes it worse for you.", inline=False)
    if interaction.guild.icon:
        embed.set_footer(text=f"thank you for keeping {interaction.guild.name} a good place 💜", icon_url=interaction.guild.icon.url)
    else:
        embed.set_footer(text="thank you for keeping this a good place 💜")
    embed.timestamp = discord.utils.utcnow()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="what can this bot do?")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="what i can do",
        description="pick a category or just scroll.",
        color=discord.Color.purple()
    )
    embed.add_field(name="📋 info", value="/avatar • /userinfo • /serverinfo • /rules • /ping", inline=False)
    embed.add_field(name="🎲 fun", value="/8ball • /coinflip • /roll • /say • /hello", inline=False)
    embed.add_field(name="🛠️ utility", value="/poll • /remind • /clear", inline=False)
    embed.add_field(name="👤 roles", value="/roles • /setup_roles (staff)", inline=False)
    embed.add_field(name="🛡️ moderation", value="/ban • /kick • /timeout (staff only)", inline=False)
    embed.set_footer(text=f"made for {interaction.guild.name}")
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

@bot.tree.command(name="userinfo", description="info about a user")
@app_commands.describe(user="who? (default: you)")
async def userinfo(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user = interaction.user
    roles = [r.mention for r in sorted(user.roles, key=lambda r: r.position) if r.name != "@everyone"]
    embed = discord.Embed(
        title=user.display_name,
        color=discord.Color.random()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="id", value=f"`{user.id}`", inline=True)
    embed.add_field(name="joined server", value=user.joined_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name="account created", value=user.created_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name="roles", value=", ".join(roles) if roles else "none", inline=False)
    embed.set_footer(text=f"{user.display_name}#{user.discriminator}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="about this server")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    online = sum(1 for m in g.members if m.status != discord.Status.offline)
    embed = discord.Embed(
        title=g.name,
        color=discord.Color.blurple()
    )
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="members", value=f"{g.member_count} total • {online} online", inline=True)
    embed.add_field(name="channels", value=str(len(g.text_channels)), inline=True)
    embed.add_field(name="roles", value=str(len(g.roles) - 1), inline=True)
    embed.add_field(name="created", value=g.created_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name="boosts", value=str(g.premium_subscription_count), inline=True)
    embed.add_field(name="owner", value=g.owner.display_name if g.owner else "unknown", inline=True)
    embed.set_footer(text=f"server id: {g.id}")
    await interaction.response.send_message(embed=embed)

# ---- FUN ----

@bot.tree.command(name="8ball", description="ask the magic 8ball a question")
@app_commands.describe(question="your question")
async def eightball(interaction: discord.Interaction, question: str):
    answers = [
        "it's certain.",
        "without a doubt.",
        "yes, definitely.",
        "you may rely on it.",
        "as i see it, yes.",
        "outlook good.",
        "reply is vague, ask again later.",
        "can't predict right now.",
        "concentrate and ask again.",
        "don't count on it.",
        "my sources say no.",
        "outlook not so good.",
        "definitely not.",
        "very doubtful.",
        "the fog is too thick to see.",
        "better not tell you now.",
    ]
    await interaction.response.send_message(f"**{question}**\n\n🎱 {random.choice(answers)}")

@bot.tree.command(name="coinflip", description="flip a coin")
async def coinflip(interaction: discord.Interaction):
    result = random.choice(["heads", "tails"])
    emoji = "🪙" if result == "heads" else "🥚"
    await interaction.response.send_message(f"{emoji} **{result}**")

@bot.tree.command(name="roll", description="roll a die or dice")
@app_commands.describe(sides="how many sides? (default 6)")
@app_commands.describe(count="how many dice? (default 1)")
async def roll(interaction: discord.Interaction, sides: int = 6, count: int = 1):
    count = max(1, min(count, 20))
    sides = max(2, min(sides, 1000))
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls)
    if count == 1:
        msg = f"🎲 you rolled a **{rolls[0]}** on a d{sides}"
    else:
        msg = f"🎲 {', '.join(map(str, rolls))} on {count}d{sides} → **{total}**"
    await interaction.response.send_message(msg)

# ---- UTILITY ----

@bot.tree.command(name="poll", description="make a quick poll")
@app_commands.describe(question="the question")
@app_commands.describe(option_a="first option")
@app_commands.describe(option_b="second option")
async def poll(interaction: discord.Interaction, question: str, option_a: str, option_b: str):
    embed = discord.Embed(
        title=f"📊 {question}",
        color=discord.Color.orange()
    )
    embed.add_field(name=f"🅰️ {option_a}", value="👍", inline=True)
    embed.add_field(name=f"🅱️ {option_b}", value="👎", inline=True)
    embed.set_footer(text="react to vote")
    msg = await interaction.response.send_message(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.tree.command(name="remind", description="i'll remind you later")
@app_commands.describe(minutes="how many minutes from now?")
@app_commands.describe(what="what should i remind you about?")
async def remind(interaction: discord.Interaction, minutes: int, what: str):
    minutes = max(1, min(minutes, 1440))
    channel = interaction.channel
    user = interaction.user
    await interaction.response.send_message(f"ok, i'll ping you in **{minutes} min** about: {what}", ephemeral=True)
    await asyncio.sleep(minutes * 60)
    try:
        await channel.send(f"{user.mention} — reminder: **{what}**")
    except discord.Forbidden:
        pass

@bot.tree.command(name="clear", description="delete recent messages (staff)")
@app_commands.describe(amount="how many? (1-100)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int = 10):
    amount = max(1, min(amount, 100))
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🗑️ deleted {len(deleted)} messages", ephemeral=True)

# ---- ROLES ----

@bot.tree.command(name="roles", description="show available reaction roles")
async def roles(interaction: discord.Interaction):
    lines = []
    for emoji, role_name in REACTION_ROLES.items():
        lines.append(f"{emoji} **{role_name}**")
    embed = discord.Embed(
        title="👤 pick your roles",
        description="\n".join(lines),
        color=discord.Color.teal()
    )
    embed.set_footer(text="react to the roles message to add/remove roles")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setup_roles", description="post the reaction roles message (staff)")
@app_commands.checks.has_permissions(manage_roles=True)
async def setup_roles(interaction: discord.Interaction):
    lines = []
    for emoji, role_name in REACTION_ROLES.items():
        lines.append(f"{emoji} {role_name}")
    embed = discord.Embed(
        title="👤 pick your roles",
        description="react to get the role. react again to remove it.\n\n" + "\n".join(lines),
        color=discord.Color.teal()
    )
    embed.set_footer(text="managed by the bot")
    msg = await interaction.response.send_message(embed=embed)
    for emoji in REACTION_ROLES:
        await msg.add_reaction(emoji)
    await log_action(interaction.guild, f"**roles setup** — reaction roles posted by {interaction.user.mention}", discord.Color.green())

# ---- MODERATION ----

@bot.tree.command(name="ban", description="ban someone (staff)")
@app_commands.describe(user="who?")
@app_commands.describe(reason="why?")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str = "no reason given"):
    await interaction.guild.ban(user, reason=reason)
    embed = discord.Embed(description=f"🔨 banned **{user.display_name}**\nreason: {reason}", color=discord.Color.red())
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, f"**ban** — {user.mention} by {interaction.user.mention}\nreason: {reason}", discord.Color.red())

@bot.tree.command(name="kick", description="kick someone (staff)")
@app_commands.describe(user="who?")
@app_commands.describe(reason="why?")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str = "no reason given"):
    await interaction.guild.kick(user, reason=reason)
    embed = discord.Embed(description=f"👢 kicked **{user.display_name}**\nreason: {reason}", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, f"**kick** — {user.mention} by {interaction.user.mention}\nreason: {reason}", discord.Color.orange())

@bot.tree.command(name="timeout", description="timeout someone (staff)")
@app_commands.describe(user="who?")
@app_commands.describe(minutes="how long?")
@app_commands.describe(reason="why?")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, user: discord.Member, minutes: int = 10, reason: str = "no reason given"):
    minutes = max(1, min(minutes, 10080))
    await user.timeout(timedelta(minutes=minutes), reason=reason)
    embed = discord.Embed(description=f"⏰ timed out **{user.display_name}** for {minutes} min\nreason: {reason}", color=discord.Color.yellow())
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, f"**timeout** — {user.mention} by {interaction.user.mention} for {minutes}m\nreason: {reason}", discord.Color.yellow())

# ---- RUN ----

if __name__ == "__main__":
    bot.run(TOKEN)   