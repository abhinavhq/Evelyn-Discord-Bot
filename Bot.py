# bot.py — ultimate full featured Discord bot
from dotenv import load_dotenv
load_dotenv()

import discord
import os
import json
import random
import threading
import time
import asyncio
import re
from pathlib import Path
import requests

# Music system requires: pip install PyNaCl yt-dlp
try:
    import yt_dlp
    MUSIC_ENABLED = True
except ImportError:
    MUSIC_ENABLED = False
    print("WARNING: yt-dlp not installed. Music disabled. Run: pip install yt-dlp PyNaCl")

print("DEBUG: bot.py starting")
print("DEBUG: TOKEN present?", bool(os.getenv("TOKEN")))


# ============================================================
# FILE DATABASE
# ============================================================
class FileDB:
    def init(self, path="replit_db.json"):
        self.path = Path(path)
        self.lock = threading.RLock()
        if not self.path.exists():
            self._write({})
        self._data = self._read()

    def _read(self):
        with self.lock:
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}

    def _write(self, data):
        tmp = self.path.with_suffix(".tmp")
        with self.lock:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(self.path)
            self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def update(self, d):
        new = dict(self._data)
        new.update(d)
        self._write(new)

    def clear(self):
        self._write({})


db = FileDB()
db.init()

# ensure default keys
for _k, _v in [
    ("responding", True),
    ("warnings", {}),
    ("economy", {}),
    ("afk", {}),
    ("marriages", {}),
    ("rep", {}),
    ("birthdays", {}),
    ("profiles", {}),
    ("streaks", {}),
    ("shop_items", {}),
    ("inventory", {}),
    ("custom_commands", {}),
    ("ticket_category", None),
    ("ticket_log", None),
    ("intro_channel", None),
    ("intro_data", {}),
    ("rss_feeds", {}),
    ("rss_last", {}),
    ("cat_channel", None),
    ("cat_active", False),
    ("cat_drop_min", 300),
    ("cat_drop_max", 900),
]:
    if _k not in db.keys():
        db.update({_k: _v})


# ============================================================
# HELPERS
# ============================================================
def add_encouragement(text):
    encs = db.get("encouragements", []) or []
    encs.append(text)
    db.update({"encouragements": encs})


def get_quote():
    try:
        r = requests.get("https://zenquotes.io/api/random", timeout=8)
        data = r.json()
        return data[0]["q"] + " — " + data[0]["a"]
    except Exception:
        return "Could not fetch a quote right now."


# ---------- Economy helpers ----------
DAILY_COINS = 100
DAILY_COOLDOWN = 86400

def get_balance(user_id):
    eco = db.get("economy", {}) or {}
    return eco.get(str(user_id), {}).get("coins", 0)

def set_balance(user_id, amount):
    eco = db.get("economy", {}) or {}
    uid = str(user_id)
    if uid not in eco:
        eco[uid] = {"coins": 0, "last_daily": 0}
    eco[uid]["coins"] = max(0, amount)
    db.update({"economy": eco})

def add_coins(user_id, amount):
    set_balance(user_id, get_balance(user_id) + amount)

def remove_coins(user_id, amount):
    set_balance(user_id, get_balance(user_id) - amount)

def get_last_daily(user_id):
    eco = db.get("economy", {}) or {}
    return eco.get(str(user_id), {}).get("last_daily", 0)

def set_last_daily(user_id, t):
    eco = db.get("economy", {}) or {}
    uid = str(user_id)
    if uid not in eco:
        eco[uid] = {"coins": 0, "last_daily": 0}
    eco[uid]["last_daily"] = t
    db.update({"economy": eco})


# ---------- Reminder helpers ----------
def parse_time(s):
    match = re.fullmatch(r"(\d+)([smhd])", s.strip().lower())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    return val * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


# ============================================================
# SOCIAL HELPERS
# ============================================================

def get_marriage(user_id):
    marriages = db.get("marriages", {}) or {}
    return marriages.get(str(user_id))

def set_marriage(user_id, partner_id):
    marriages = db.get("marriages", {}) or {}
    marriages[str(user_id)] = str(partner_id)
    marriages[str(partner_id)] = str(user_id)
    db.update({"marriages": marriages})

def remove_marriage(user_id):
    marriages = db.get("marriages", {}) or {}
    partner_id = marriages.pop(str(user_id), None)
    if partner_id:
        marriages.pop(str(partner_id), None)
    db.update({"marriages": marriages})

def get_rep(user_id):
    rep = db.get("rep", {}) or {}
    return rep.get(str(user_id), {"points": 0, "last_given": {}})

def give_rep(from_id, to_id):
    rep = db.get("rep", {}) or {}
    fid, tid = str(from_id), str(to_id)
    now = time.time()
    if fid not in rep:
        rep[fid] = {"points": 0, "last_given": {}}
    last = rep[fid]["last_given"].get(tid, 0)
    if now - last < 86400:
        remaining = 86400 - (now - last)
        hrs = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        return False, f"You can rep this user again in **{hrs}h {mins}m**."
    rep[fid]["last_given"][tid] = now
    if tid not in rep:
        rep[tid] = {"points": 0, "last_given": {}}
    rep[tid]["points"] += 1
    db.update({"rep": rep})
    return True, f"✅ Rep given! They now have **{rep[tid]['points']} rep**."

def get_profile(user_id):
    profiles = db.get("profiles", {}) or {}
    return profiles.get(str(user_id), {"bio": "No bio set.", "badge": ""})

def set_profile_bio(user_id, bio):
    profiles = db.get("profiles", {}) or {}
    uid = str(user_id)
    if uid not in profiles:
        profiles[uid] = {"bio": bio, "badge": ""}
    else:
        profiles[uid]["bio"] = bio
    db.update({"profiles": profiles})

def get_birthday(user_id):
    birthdays = db.get("birthdays", {}) or {}
    return birthdays.get(str(user_id))

def set_birthday(user_id, date_str):
    birthdays = db.get("birthdays", {}) or {}
    birthdays[str(user_id)] = date_str
    db.update({"birthdays": birthdays})



# ============================================================
# STREAK HELPERS
# ============================================================
STREAK_BONUS = 50
STREAK_MAX_BONUS = 500

def get_streak(user_id):
    streaks = db.get("streaks", {}) or {}
    return streaks.get(str(user_id), {"streak": 0, "last_day": ""})

def update_streak(user_id):
    import datetime
    streaks = db.get("streaks", {}) or {}
    uid = str(user_id)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    data = streaks.get(uid, {"streak": 0, "last_day": ""})
    if data["last_day"] == today:
        return data["streak"], 0
    if data["last_day"] == yesterday:
        data["streak"] += 1
    else:
        data["streak"] = 1
    data["last_day"] = today
    streaks[uid] = data
    db.update({"streaks": streaks})
    bonus = min(data["streak"] * STREAK_BONUS, STREAK_MAX_BONUS)
    return data["streak"], bonus


# ============================================================
# SHOP HELPERS
# ============================================================
DEFAULT_SHOP = {
    "vip_role":    {"name": "VIP Role",      "price": 500, "type": "role", "role_name": "VIP"},
    "lucky_charm": {"name": "Lucky Charm",   "price": 200, "type": "item", "desc": "Doubles your next fishing reward"},
    "xp_boost":    {"name": "XP Boost",      "price": 400, "type": "item", "desc": "Earn 2x XP for 1 hour"},
    "fishing_rod": {"name": "Golden Rod",    "price": 350, "type": "item", "desc": "+10% chance of rare fish"},
    "color_blue":  {"name": "Blue Name",     "price": 300, "type": "role", "role_name": "Blue"},
    "color_red":   {"name": "Red Name",      "price": 300, "type": "role", "role_name": "Red"},
}

def get_shop():
    items = db.get("shop_items", {}) or {}
    if not items:
        db.update({"shop_items": DEFAULT_SHOP})
        return DEFAULT_SHOP
    return items

def get_inventory(user_id):
    inv = db.get("inventory", {}) or {}
    return inv.get(str(user_id), {})

def add_to_inventory(user_id, item_key, item_name):
    inv = db.get("inventory", {}) or {}
    uid = str(user_id)
    if uid not in inv:
        inv[uid] = {}
    inv[uid][item_key] = inv[uid].get(item_key, 0) + 1
    db.update({"inventory": inv})

def remove_from_inventory(user_id, item_key):
    inv = db.get("inventory", {}) or {}
    uid = str(user_id)
    if uid in inv and item_key in inv[uid]:
        inv[uid][item_key] -= 1
        if inv[uid][item_key] <= 0:
            del inv[uid][item_key]
        db.update({"inventory": inv})
        return True
    return False

def has_item(user_id, item_key):
    return get_inventory(user_id).get(item_key, 0) > 0


# ============================================================
# CUSTOM COMMAND HELPERS
# ============================================================
def get_custom_commands():
    return db.get("custom_commands", {}) or {}

def add_custom_command(trigger, response):
    cmds = get_custom_commands()
    cmds[trigger.lower()] = response
    db.update({"custom_commands": cmds})

def remove_custom_command(trigger):
    cmds = get_custom_commands()
    removed = cmds.pop(trigger.lower(), None)
    db.update({"custom_commands": cmds})
    return removed is not None

# ============================================================
# CONSTANTS
# ============================================================
LEVEL_ROLES = {
    1:   "🆕 Newbie",
    5:   "🟢 Beginner",
    10:  "🔵 Regular",
    15:  "🟣 Active Member",
    20:  "⭐️ Elite",
    30:  "🔥 Veteran",
    40:  "💎 Pro",
    50:  "🏆 Legend",
    75:  "🌌 Mythic",
    100: "👑 Immortal",
}

XP_COOLDOWN_SECONDS = 60
XP_PER_MESSAGE = 5
xp_cooldown = {}

POLL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

SLOTS_SYMBOLS = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣", "🎰"]
SLOTS_MULTIPLIERS = {
    ("🍒", "🍒", "🍒"): 3,
    ("🍋", "🍋", "🍋"): 4,
    ("🍊", "🍊", "🍊"): 5,
    ("🍇", "🍇", "🍇"): 8,
    ("💎", "💎", "💎"): 20,
    ("7️⃣", "7️⃣", "7️⃣"): 50,
    ("🎰", "🎰", "🎰"): 100,
}

FISH_TABLE = [
    ("🐟 Common Fish",     "Common",    10,  0.45),
    ("🐠 Tropical Fish",   "Uncommon",  25,  0.25),
    ("🐡 Pufferfish",      "Uncommon",  30,  0.15),
    ("🦈 Shark",           "Rare",      75,  0.08),
    ("🐙 Octopus",         "Rare",      80,  0.04),
    ("🦑 Giant Squid",     "Epic",      150, 0.02),
    ("👑 Golden Fish",     "Legendary", 500, 0.01),
]

TRIVIA = [
    {"q": "🎮 What is the best-selling video game of all time?",       "options": ["Minecraft", "Tetris", "GTA V", "Wii Sports"],           "answer": 0},
    {"q": "🎮 In which game do you play as Master Chief?",              "options": ["Destiny", "Halo", "Call of Duty", "Gears of War"],       "answer": 1},
    {"q": "🎮 What year was the first Pokemon game released?",          "options": ["1994", "1996", "1998", "2000"],                          "answer": 1},
    {"q": "🎮 Which company made the Nintendo Switch?",                 "options": ["Sony", "Microsoft", "Nintendo", "Sega"],                 "answer": 2},
    {"q": "🎮 What is the currency in The Legend of Zelda?",            "options": ["Gold", "Coins", "Rupees", "Gems"],                       "answer": 2},
    {"q": "🎮 What game features a battle royale on Erangel?",          "options": ["Fortnite", "Warzone", "PUBG", "Apex Legends"],           "answer": 2},
    {"q": "🎮 In Among Us, what do Impostors do?",                      "options": ["Complete tasks", "Sabotage and kill", "Report bodies", "Call meetings"], "answer": 1},
    {"q": "🎮 What is the main character's name in God of War?",        "options": ["Kratos", "Zeus", "Ares", "Thor"],                        "answer": 0},
    {"q": "🎮 Which game has the phrase 'The cake is a lie'?",          "options": ["Half-Life", "Portal", "Bioshock", "Mirror's Edge"],       "answer": 1},
    {"q": "🎮 What color is Sonic the Hedgehog?",                       "options": ["Red", "Yellow", "Blue", "Green"],                        "answer": 2},
    {"q": "🍥 What is Naruto's signature jutsu?",                       "options": ["Chidori", "Rasengan", "Amaterasu", "Susanoo"],           "answer": 1},
    {"q": "🍥 When does Goku first go Super Saiyan in DBZ?",            "options": ["Against Frieza", "Against Cell", "Against Buu", "Against Vegeta"], "answer": 0},
    {"q": "🍥 What is the main character's name in Death Note?",        "options": ["L", "Light Yagami", "Ryuk", "Near"],                     "answer": 1},
    {"q": "🍥 Which anime features the Survey Corps fighting Titans?",  "options": ["Demon Slayer", "My Hero Academia", "Attack on Titan", "Tokyo Ghoul"], "answer": 2},
    {"q": "🍥 What is Luffy's devil fruit in One Piece?",               "options": ["Flame Flame Fruit", "Gum Gum Fruit", "Dark Dark Fruit", "Ice Ice Fruit"], "answer": 1},
    {"q": "🍥 What studio made Spirited Away?",                         "options": ["Toei Animation", "Madhouse", "Studio Ghibli", "Bones"],  "answer": 2},
    {"q": "🍥 What is Ichigo's zanpakuto called in Bleach?",            "options": ["Zangetsu", "Senbonzakura", "Ryujin Jakka", "Benihime"], "answer": 0},
    {"q": "🍥 Which anime has the 'Plus Ultra' motto?",                 "options": ["Naruto", "Demon Slayer", "My Hero Academia", "Black Clover"], "answer": 2},
    {"q": "🍥 Main character in Fullmetal Alchemist?",                  "options": ["Roy Mustang", "Edward Elric", "Alphonse Elric", "Winry Rockbell"], "answer": 1},
    {"q": "🍥 In SAO, what is the name of the first game?",             "options": ["ALfheim Online", "Gun Gale Online", "Sword Art Online", "Project Alicization"], "answer": 2},
]

active_trivia = {}

music_queues = {}
music_playing = {}
now_playing = {}

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

sad_words = [
    "sad", "depressed", "unhappy", "miserable", "depressing", "down", "blue",
    "lonely", "angry", "upset", "tired", "stress", "stressed", "anxious",
    "anxiety", "hurt", "pain", "cry", "crying", "mad", "depress", "frustrated",
    "frustration", "dejection", "despair", "gloom", "gloomy", "hopeless",
    "helpless", "downcast", "melancholy", "melancholic", "dispirited",
    "disheartened", "forlorn", "woeful",
]

starter_encouragements = [
    "Cheer up!", "Hang in there.", "You're a great person! You're doing great!",
    "Believe in yourself!", "Keep going — you're stronger than you think.",
    "You've got this!", "One step at a time.",
    "Don't give up now, you're almost there.",
    "You are capable of amazing things.", "Even the hardest days pass.",
    "You're doing better than you realise.",
    "Stay positive — brighter days are coming.", "Keep moving forward.",
    "Every challenge makes you stronger.", "You matter more than you know.",
    "Don't be afraid to start again.", "Your feelings are valid.",
    "It's okay to rest — just don't quit.", "I'm proud of you for trying.",
    "You're not alone.", "Your hard work will pay off.",
    "You deserve happiness.", "You can rise from anything.",
    "Progress is still progress, no matter how small.", "Today is a new chance.",
    "Stay hopeful — things get better.", "Trust your journey.",
    "You're braver than your fears.", "Mistakes help you grow.",
    "Keep believing in yourself.", "You're enough, just as you are.",
    "Better days are coming — keep going.",
    "You are stronger than your struggles.", "You're worthy of success.",
    "Take it slow, but take it.", "You can handle this.", "Never lose hope.",
    "You inspire others, even if you don't realise it.",
    "Don't underestimate yourself.", "You're doing your best — that's enough.",
    "You're growing every single day.", "You can overcome anything.",
    "Every storm runs out of rain.", "Your story isn't over yet.",
    "Believe in the person you're becoming.",
    "You have the power to change your life.", "Don't let doubt stop you.",
    "Keep your heart strong.", "You are loved and appreciated.",
    "What you're feeling is temporary.", "You'll make it through this.",
    "The world is better because you're in it.",
    "Hard times don't last — strong people do.",
    "You are not defined by your struggles.",
    "You have survived every bad day — you'll survive this too.",
    "Your potential is limitless.", "You are worthy of every good thing.",
    "Never forget how far you've come.",
    "Every day is a second chance.",
    "You are more powerful than your fears.",
    "Hope is still alive — hold on to it.",
    "You deserve peace and happiness.",
    "You have already overcome so much.",
    "Be gentle with yourself; you're trying your best.",
    "Something amazing is waiting for you — keep moving.",
    "You are worthy of love and respect.",
    "You are stronger, wiser, and braver every day.",
]

eight_ball_responses = [
    "Yes 👍", "No ❌", "Maybe 🤔", "Definitely 😎",
    "Ask again later ⏳", "I don't think so 😕",
    "Absolutely 💯", "Not sure 🤷",
]

gaming_anime_jokes = [
    "Why don't programmers like nature? 🌳 Too many bugs 🐛😂",
    "I told my computer I needed a break… it froze 🧊💻",
    "Why did Python cross the road? 🐍 To import the other side 😆",
    "Why do Java developers wear glasses? 👓 Because they don't C 👀😂",
    "My code works… I have no idea why 🤷‍♂️💀",
    "Why was the computer cold? 🥶 It left its Windows open 🪟😂",
    "Debugging: removing bugs 🐛 one at a time… and adding two more 😭",
    "Programmers don't panic 😎 they just Google faster 🔍⚡️",
    "Why did the developer go broke? 💸 Because he used up all his cache 🧠😂",
    "Why do programmers prefer dark mode? 🌙 Because light attracts bugs 🐛😂",
    "Why do gamers hate sunlight? ☀️🎮 Because it causes lag 😭",
    "I paused my game to do something important… then forgot what 😆🎮",
    "Gamers don't age ⏳🎮 they just level up 🔼😎",
    "My ping is so high 📶 that my bullets arrive tomorrow 😭🔫",
    "I don't rage quit 😌🎮 I strategically disconnect 😎",
    "'Just one more match' 🎮 turned into 3 AM 🌙😂",
    "Skill issue? ❌ Lag issue? ✅ 😎",
    "Anime taught me that shouting louder = more power 🔥🍥😂",
    "I'll start anime early tonight… 🌙🍥 watches till sunrise ☀️😭",
    "Anime logic: fall from space ☄️🍥 survive with bandage 🤕😂",
    "Gaming and anime taught me one thing 🎮🍥 sleep is optional 😴❌",
    "If life had save points 💾🎮 I'd be less stressed 😌",
    "NPCs in games: 'Be careful out there' 🎮🙂 me: jumps off cliff 💀😂",
    "Gamers + anime fans 🤝 understand pain and grind 😤🔥",
]


# ============================================================
# DISCORD CLIENT
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents)


# ============================================================
# MUSIC HELPERS
# ============================================================
async def play_next(guild, channel):
    gid = guild.id
    queue = music_queues.get(gid, [])
    if not queue:
        music_playing[gid] = False
        now_playing.pop(gid, None)
        vc = guild.voice_client
        if vc:
            await vc.disconnect()
        return

    entry = queue.pop(0)
    music_queues[gid] = queue

    try:
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(entry["url"], download=False)
            if "entries" in info:
                info = info["entries"][0]
            stream_url = info["url"]
            title = info.get("title", "Unknown")

        vc = guild.voice_client
        if not vc:
            return

        source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        music_playing[gid] = True
        now_playing[gid] = title

        def after_play(error):
            if error:
                print(f"Music error: {error}")
            asyncio.run_coroutine_threadsafe(play_next(guild, channel), client.loop)

        vc.play(source, after=after_play)
        await channel.send(f"🎵 Now playing: **{title}**")

    except Exception as e:
        await channel.send(f"❌ Error playing track: {e}")
        music_playing[gid] = False


# ============================================================
# BIRTHDAY BACKGROUND TASK
# ============================================================
async def birthday_check_loop():
    """Runs once per day, announces birthdays in #general."""
    await client.wait_until_ready()
    while not client.is_closed():
        import datetime
        today = datetime.datetime.now().strftime("%d/%m")
        birthdays = db.get("birthdays", {}) or {}
        for uid, bday in birthdays.items():
            if bday == today:
                for guild in client.guilds:
                    member = guild.get_member(int(uid))
                    if member:
                        channel = (
                            discord.utils.get(guild.text_channels, name="general")
                            or discord.utils.get(guild.text_channels, name="birthday")
                            or guild.system_channel
                        )
                        if channel:
                            embed = discord.Embed(
                                title="🎂 Happy Birthday!",
                                description=f"🎉 Everyone wish **{member.display_name}** a happy birthday! 🎈🎁",
                                color=discord.Color.gold()
                            )
                            embed.set_thumbnail(url=member.display_avatar.url)
                            await channel.send(embed=embed)
        # Sleep until next day (check every 24h)
        await asyncio.sleep(86400)


# ============================================================
# EVENTS
# ============================================================

# ============================================================
# INTRO HELPERS
# ============================================================
INTRO_QUESTIONS = [
    ("name",     "👤 What's your name / nickname?"),
    ("age",      "🎂 How old are you?"),
    ("location", "🌍 Where are you from?"),
    ("hobbies",  "🎮 What are your hobbies / interests?"),
    ("games",    "🕹️ Favourite games or anime?"),
    ("fact",     "✨ Share a fun fact about yourself!"),
]

pending_intros = {}   # user_id -> {answers, step}

async def send_intro_dm(member):
    try:
        embed = discord.Embed(
            title="👋 Welcome! Let's set up your intro.",
            description=(
                "I'll ask you a few quick questions.\n"
                "Your answers will be posted in the introductions channel.\n\n"
                "Type `skip` to skip any question."
            ),
            color=discord.Color.blurple()
        )
        await member.send(embed=embed)
        pending_intros[member.id] = {"answers": {}, "step": 0, "guild_id": member.guild.id}
        await ask_intro_question(member)
    except discord.Forbidden:
        pass   # DMs closed

async def ask_intro_question(member):
    step = pending_intros[member.id]["step"]
    if step >= len(INTRO_QUESTIONS):
        await finish_intro(member)
        return
    key, question = INTRO_QUESTIONS[step]
    await member.send(f"**Question {step+1}/{len(INTRO_QUESTIONS)}:** {question}")

async def finish_intro(member):
    data = pending_intros.pop(member.id, None)
    if not data:
        return
    answers = data["answers"]
    guild = client.get_guild(data["guild_id"])
    if not guild:
        return

    embed = discord.Embed(
        title=f"📋 Introduction — {member.display_name}",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    for key, question in INTRO_QUESTIONS:
        val = answers.get(key, "*Skipped*")
        label = question.split(" ", 1)[1]   # strip emoji
        embed.add_field(name=question.split()[0] + " " + label, value=val, inline=False)
    embed.set_footer(text=f"Member since {member.joined_at.strftime('%d %b %Y')}")

    # post to intro channel
    intro_ch_id = db.get("intro_channel")
    channel = None
    if intro_ch_id:
        channel = guild.get_channel(int(intro_ch_id))
    if not channel:
        channel = discord.utils.get(guild.text_channels, name="introductions")
    if channel:
        await channel.send(embed=embed)

    # save to db
    intro_data = db.get("intro_data", {}) or {}
    intro_data[str(member.id)] = {k: answers.get(k, "") for k, _ in INTRO_QUESTIONS}
    db.update({"intro_data": intro_data})

    await member.send("✅ Your introduction has been posted! Welcome to the server! 🎉")


# ============================================================
# RSS FEED HELPERS
# ============================================================
import xml.etree.ElementTree as ET
from datetime import timezone

def _fetch_rss_sync(url):
    r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    return r.content

async def fetch_rss(url):
    try:
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, _fetch_rss_sync, url)
        root = ET.fromstring(content)
        items = root.findall(".//item")
        results = []
        for item in items[:5]:
            title = item.findtext("title", "No title")
            link  = item.findtext("link", "")
            pub   = item.findtext("pubDate", "")
            results.append({"title": title, "link": link, "pub": pub})
        return results
    except Exception as e:
        return []

async def rss_check_loop():
    await client.wait_until_ready()
    while not client.is_closed():
        feeds = db.get("rss_feeds", {}) or {}
        last  = db.get("rss_last", {}) or {}
        for feed_name, feed_info in feeds.items():
            url     = feed_info.get("url")
            ch_id   = feed_info.get("channel_id")
            if not url or not ch_id:
                continue
            channel = client.get_channel(int(ch_id))
            if not channel:
                continue
            items = await fetch_rss(url)
            feed_last = last.get(feed_name, "")
            new_items = []
            for item in items:
                if item["link"] == feed_last:
                    break
                new_items.append(item)
            if new_items:
                last[feed_name] = new_items[0]["link"]
                db.update({"rss_last": last})
                for item in reversed(new_items):
                    embed = discord.Embed(
                        title=item["title"][:256],
                        url=item["link"],
                        color=discord.Color.orange()
                    )
                    embed.set_footer(text=f"📰 {feed_name} • {item['pub'][:32] if item['pub'] else ''}")
                    await channel.send(embed=embed)
        await asyncio.sleep(300)   # check every 5 minutes


# ============================================================
# CAT DROP HELPERS
# ============================================================
CAT_REWARD_MIN = 20
CAT_REWARD_MAX = 80
cat_active_catch = {}   # guild_id -> True/False

def _fetch_cat_url():
    try:
        r = requests.get("https://api.thecatapi.com/v1/images/search", timeout=8)
        return r.json()[0]["url"]
    except Exception:
        return None

async def cat_drop_loop():
    await client.wait_until_ready()
    # sleep on startup so bot is fully ready
    await asyncio.sleep(random.randint(60, 120))
    while not client.is_closed():
        drop_min = db.get("cat_drop_min", 300)
        drop_max = db.get("cat_drop_max", 900)
        await asyncio.sleep(random.randint(drop_min, drop_max))
        ch_id = db.get("cat_channel")
        if not ch_id:
            continue
        for guild in client.guilds:
            channel = guild.get_channel(int(ch_id))
            if not channel:
                continue
            # fetch cat image non-blocking
            loop = asyncio.get_event_loop()
            cat_url = await loop.run_in_executor(None, _fetch_cat_url)
            reward = random.randint(CAT_REWARD_MIN, CAT_REWARD_MAX)
            cat_active_catch[guild.id] = {"reward": reward}
            embed = discord.Embed(
                title="🐱 A wild cat appeared!",
                description=f"Type `$catch` to catch it and earn **🪙 {reward}** coins!\nYou have **30 seconds!**",

                color=discord.Color.from_rgb(255, 165, 0)
            )
            if cat_url:
                embed.set_image(url=cat_url)
            await channel.send(embed=embed)

            # expire after 30s
            await asyncio.sleep(30)
            if guild.id in cat_active_catch:
                del cat_active_catch[guild.id]
                await channel.send("🐱 The cat ran away... no one caught it!")


@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user}")
    client.loop.create_task(birthday_check_loop())
    client.loop.create_task(rss_check_loop())
    client.loop.create_task(cat_drop_loop())


@client.event
async def on_member_join(member):
    guild = member.guild
    channel = (
        discord.utils.get(guild.text_channels, name="general")
        or discord.utils.get(guild.text_channels, name="welcome")
        or guild.system_channel
    )
    if channel:
        embed = discord.Embed(
            title=f"👋 Welcome to {guild.name}!",
            description=(
                f"Hey {member.mention}, we're glad you're here! 🎉\n\n"
                f"You are member **#{guild.member_count}**.\n"
                f"Check out the rules and have fun! 😊"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Joined: {member.joined_at.strftime('%d %b %Y')}")
        await channel.send(embed=embed)
    # Send intro DM
    await send_intro_dm(member)


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.strip()
    content_lower = content.lower()
    guild = message.guild

    # ===== DM INTRO HANDLER =====
    if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
        uid = message.author.id
        if uid in pending_intros:
            step = pending_intros[uid]["step"]
            answer = content.strip() if content.lower() != "skip" else "*Skipped*"
            key = INTRO_QUESTIONS[step][0]
            pending_intros[uid]["answers"][key] = answer
            pending_intros[uid]["step"] += 1
            await ask_intro_question(message.author)
        return   # don't process DMs as server commands


    # ===== AFK CHECK =====
    if message.mentions:
        afk_data = db.get("afk", {}) or {}
        for mentioned in message.mentions:
            uid = str(mentioned.id)
            if uid in afk_data:
                reason = afk_data[uid]["reason"]
                since = afk_data[uid]["since"]
                await message.channel.send(
                    f"💤 **{mentioned.display_name}** is AFK: *{reason}* (since {since})"
                )

    afk_data = db.get("afk", {}) or {}
    uid = str(message.author.id)
    if uid in afk_data and not content_lower.startswith("$afk"):
        del afk_data[uid]
        db.update({"afk": afk_data})
        await message.channel.send(
            f"✅ Welcome back {message.author.mention}! Your AFK has been removed."
        )

    # ===== XP SYSTEM =====
    if not message.author.bot:
        user_id = str(message.author.id)
        now = time.time()
        xp_data = db.get("xp", {}) or {}

        if user_id not in xp_data:
            xp_data[user_id] = {"xp": 0, "level": 0}

        last_time = xp_cooldown.get(user_id, 0)
        if now - last_time >= XP_COOLDOWN_SECONDS:
            xp_data[user_id]["xp"] += XP_PER_MESSAGE
            xp_cooldown[user_id] = now

            current_xp = xp_data[user_id]["xp"]
            current_level = xp_data[user_id]["level"]

            if current_xp >= (current_level + 1) * 100:
                xp_data[user_id]["level"] += 1
                new_level = xp_data[user_id]["level"]
                await message.channel.send(
                    f"🎉 {message.author.mention} reached **Level {new_level}**!"
                )
                for r in message.author.roles:
                    if r.name in LEVEL_ROLES.values():
                        await message.author.remove_roles(r)
                if new_level in LEVEL_ROLES:
                    role = discord.utils.get(guild.roles, name=LEVEL_ROLES[new_level])
                    if role:
                        await message.author.add_roles(role)
                        await message.channel.send(
                            f"🏅 {message.author.mention} earned **{LEVEL_ROLES[new_level]}**!"
                        )

        db.update({"xp": xp_data})

    # ===== TRIVIA ANSWER CHECK =====
    cid = message.channel.id
    if cid in active_trivia and not active_trivia[cid]["answered"]:
        trivia = active_trivia[cid]
        if content.strip() == POLL_EMOJIS[trivia["answer"]]:
            active_trivia[cid]["answered"] = True
            correct = trivia["options"][trivia["answer"]]
            await message.channel.send(
                f"🎉 {message.author.mention} got it right! "
                f"The answer was **{POLL_EMOJIS[trivia['answer']]} {correct}**!"
            )
            del active_trivia[cid]
            return

    # ============================================================
    # COMMANDS
    # ============================================================

    # --- $ping ---
    if content_lower == "$ping":
        latency = round(client.latency * 1000)
        await message.channel.send(f"🏓 Pong! Latency: **{latency}ms**")
        return

    # --- $help ---
    if content_lower == "$help":
        await message.channel.send(
            "**🤖 Bot Commands — Page 1/2**\n\n"
            "**General:**\n"
            "• `$ping` → Latency check\n"
            "• `$inspire` → Motivational quote\n"
            "• `$avatar` / `$avatar @user` → Show avatar\n\n"
            "**Encouragement:**\n"
            "• `$new <msg>` → Add encouragement\n"
            "• `$list` → List encouragements\n"
            "• `$del <index>` / `$del all confirm` → Delete\n"
            "• `$responding on/off` → Toggle auto-response\n\n"
            "**Info:**\n"
            "• `$userinfo` / `$userinfo @user`\n"
            "• `$serverinfo`\n\n"
            "**XP System:**\n"
            "• `$rank` → Your XP & level\n"
            "• `$leaderboard` → Top 5 by XP\n\n"
            "**💰 Economy:**\n"
            "• `$balance` / `$bal` → Check coins\n"
            "• `$daily` → Claim daily 100 coins\n"
            "• `$pay @user <amount>` → Send coins\n"
            "• `$richlist` → Top 5 richest users\n\n"
            "**🎰 Minigames:**\n"
            "• `$slots <bet>` → Slot machine\n"
            "• `$fish` → Fishing (costs 10 coins)\n"
            "• `$blackjack <bet>` / `$bj <bet>` → Blackjack\n\n"
            "**🗳️ Poll:**\n"
            "• `$poll <question> | <opt1> | <opt2> ...`\n\n"
            "**🧠 Trivia:** `$trivia`\n"
            "**⏰ Reminder:** `$remind <time> <msg>` (e.g. `$remind 10m check oven`)\n"
            "**💤 AFK:** `$afk <reason>`\n\n"
            "**📋 Intro:** `$intro` → Set up your introduction\n"
            "• `$viewintro @user` → View someone's intro\n"
            "• `$setintrochannel #ch` → Set intro channel *(Admin)*\n\n"
            "**📰 RSS:** `$addrss <n> #ch <url>` / `$removerss` / `$listrss` / `$rss <n>`\n\n"
            "**🐱 Cat Drops:** `$catch` → Catch dropped cats for coins\n"
            "• `$setcat #ch` → Set drop channel *(Admin)*\n"
            "• `$dropcat` → Force a drop *(Admin)*"
        )
        await message.channel.send(
            "**🤖 Bot Commands — Page 2/2**\n\n"
            "**🛡️ Moderation:**\n"
            "• `$warn @user <reason>` / `$warnings @user` / `$clearwarnings @user`\n"
            "• `$kick @user` / `$ban @user` / `$mute @user <dur>` / `$unmute @user`\n"
            "• `$purge <amount>` / `$announce #channel <msg>`\n\n"
            "**💕 Social:**\n"
            "• `$profile` / `$setbio <text>` / `$marry @user` / `$divorce`\n"
            "• `$rep @user` / `$repboard` / `$birthday set DD/MM`\n\n"
            "**🎫 Tickets:**\n"
            "• `$ticket` → Open support ticket\n"
            "• `$closeticket` → Close ticket channel\n\n"
            "**🏪 Shop & Inventory:**\n"
            "• `$shop` → Browse items\n"
            "• `$buy <item_id>` → Purchase item\n"
            "• `$inventory` / `$inv` → Your items\n\n"
            "**🎭 Custom Commands** *(Mod only)*:\n"
            "• `$addcmd <trigger> <response>` / `$removecmd <trigger>` / `$listcmds`\n\n"
            "**📨 Embed Messages** *(Mod only)*:\n"
            "• `$embed #ch | Title | Description | #Color`\n"
            "• `$embedimage #ch | Title | Desc | ImageURL | #Color`\n\n"
            "**🎵 Music:** `$play` `$skip` `$pause` `$resume` `$stop` `$queue` `$nowplaying`\n\n"
            "**🎮 Fun:** `$8ball` • `$roll` • `$coinflip` • `$joke` • `$meme` • `$guess`\n\n"
            "💙 Stay positive & enjoy the server!"
        )
        return

    # --- $avatar ---
    if content_lower.startswith("$avatar"):
        user = message.mentions[0] if message.mentions else message.author
        embed = discord.Embed(
            title=f"🖼️ {user.display_name}'s Avatar",
            color=discord.Color.blurple()
        )
        embed.set_image(url=user.display_avatar.url)
        embed.set_footer(text=f"Requested by {message.author.display_name}")
        await message.channel.send(embed=embed)
        return

    # --- $rank ---
    if content_lower == "$rank":
        user_id = str(message.author.id)
        xp_data = db.get("xp", {}) or {}
        xp = xp_data.get(user_id, {}).get("xp", 0)
        level = xp_data.get(user_id, {}).get("level", 0)
        next_level_xp = (level + 1) * 100
        embed = discord.Embed(title="🏆 Rank Card", color=discord.Color.gold())
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.add_field(name="User", value=message.author.mention, inline=False)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=f"{xp} / {next_level_xp}", inline=True)
        await message.channel.send(embed=embed)
        return

    # --- $leaderboard ---
    if content_lower == "$leaderboard":
        xp_data = db.get("xp", {}) or {}
        if not xp_data:
            await message.channel.send("No XP data yet.")
            return
        sorted_users = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)
        msg = "🏆 **XP Leaderboard**\n"
        for i, (uid, data) in enumerate(sorted_users[:5], start=1):
            u = guild.get_member(int(uid))
            if u:
                msg += f"{i}. {u.name} — Level {data['level']} ({data['xp']} XP)\n"
        await message.channel.send(msg)
        return

    # --- $userinfo ---
    if content_lower.startswith("$userinfo"):
        user = message.mentions[0] if message.mentions else message.author
        roles = [r.name for r in user.roles if r.name != "@everyone"]
        embed = discord.Embed(title="👤 User Info", color=discord.Color.blue())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Username", value=str(user), inline=True)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Joined Server", value=user.joined_at.strftime("%d %b %Y"), inline=False)
        embed.add_field(name="Account Created", value=user.created_at.strftime("%d %b %Y"), inline=False)
        embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
        await message.channel.send(embed=embed)
        return

    # --- $serverinfo ---
    if content_lower == "$serverinfo":
        embed = discord.Embed(title="🏠 Server Info", color=discord.Color.green())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Server Name", value=guild.name, inline=True)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=str(guild.owner), inline=False)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Created On", value=guild.created_at.strftime("%d %b %Y"), inline=False)
        await message.channel.send(embed=embed)
        return

    # --- $inspire ---
    if content_lower.startswith("$inspire"):
        loop = asyncio.get_event_loop()
        quote = await loop.run_in_executor(None, get_quote)
        await message.channel.send(quote)
        return

    # --- $list ---
    if content_lower == "$list":
        encs = db.get("encouragements", []) or []
        if not encs:
            await message.channel.send("No saved encouragements yet.")
            return
        header = "Saved encouragements:\n"
        lines = [f"{i}: {e}" for i, e in enumerate(encs)]
        max_len = 1900
        current = header
        for line in lines:
            if len(current) + len(line) + 1 > max_len:
                await message.channel.send(current.rstrip())
                current = ""
            current += line + "\n"
        if current:
            await message.channel.send(current.rstrip())
        return

    # --- $new ---
    if content_lower.startswith("$new "):
        text = content.split("$new ", 1)[1].strip()
        if text:
            add_encouragement(text)
            await message.channel.send("✅ New encouraging message added.")
        else:
            await message.channel.send("❗ Please provide a message after $new.")
        return

    # --- $del ---
    if content_lower.startswith("$del"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❗ Usage: `$del <index>` or `$del all confirm`")
            return
        key = parts[1].lower()
        if key == "all":
            if len(parts) >= 3 and parts[2].lower() == "confirm":
                db.update({"encouragements": []})
                await message.channel.send("✅ All encouragements deleted.")
            else:
                await message.channel.send("⚠️ Use: `$del all confirm`")
            return
        try:
            index = int(key)
        except ValueError:
            await message.channel.send("❗ Please provide a valid integer index.")
            return
        encs = db.get("encouragements", []) or []
        if not encs:
            await message.channel.send("ℹ️ No saved encouragements to delete.")
            return
        if index < 0:
            index = len(encs) + index
        if index < 0 or index >= len(encs):
            await message.channel.send(f"❗ Index out of range. Valid: 0 to {len(encs) - 1}.")
            return
        removed = encs.pop(index)
        db.update({"encouragements": encs})
        await message.channel.send(f"✅ Deleted encouragement #{index}: {removed}")
        return

    # --- $responding ---
    if content_lower.startswith("$responding "):
        arg = content_lower.split("$responding ", 1)[1].strip()
        if arg in ("true", "on", "1"):
            db.update({"responding": True})
            await message.channel.send("Responding is now ON.")
        elif arg in ("false", "off", "0"):
            db.update({"responding": False})
            await message.channel.send("Responding is now OFF.")
        else:
            await message.channel.send("Use `$responding on` or `$responding off`.")
        return

    # ============================================================
    # ECONOMY
    # ============================================================

    if content_lower in ("$balance", "$bal") or content_lower.startswith("$balance ") or content_lower.startswith("$bal "):
        user = message.mentions[0] if message.mentions else message.author
        coins = get_balance(user.id)
        embed = discord.Embed(title="💰 Balance", color=discord.Color.gold())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=user.mention, inline=False)
        embed.add_field(name="Coins", value=f"🪙 **{coins:,}**", inline=True)
        await message.channel.send(embed=embed)
        return

    # $daily handled in STREAK section below

    if content_lower.startswith("$pay"):
        if not message.mentions:
            await message.channel.send("❗ Usage: `$pay @user <amount>`")
            return
        target = message.mentions[0]
        parts = content.split()
        if len(parts) < 3:
            await message.channel.send("❗ Usage: `$pay @user <amount>`")
            return
        try:
            amount = int(parts[-1])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.channel.send("❗ Please provide a valid positive amount.")
            return
        if target.id == message.author.id:
            await message.channel.send("❗ You can't pay yourself!")
            return
        bal = get_balance(message.author.id)
        if bal < amount:
            await message.channel.send(f"❌ You only have **🪙 {bal:,}** coins.")
            return
        remove_coins(message.author.id, amount)
        add_coins(target.id, amount)
        await message.channel.send(
            f"✅ {message.author.mention} paid **🪙 {amount:,}** to {target.mention}!"
        )
        return

    if content_lower == "$richlist":
        eco = db.get("economy", {}) or {}
        if not eco:
            await message.channel.send("No economy data yet.")
            return
        sorted_eco = sorted(eco.items(), key=lambda x: x[1].get("coins", 0), reverse=True)
        msg = "💰 **Richest Users**\n"
        count = 0
        for uid, data in sorted_eco:
            u = guild.get_member(int(uid))
            if u and count < 5:
                msg += f"{count+1}. {u.name} — 🪙 {data.get('coins', 0):,}\n"
                count += 1
        await message.channel.send(msg)
        return

    # ============================================================
    # MINIGAMES
    # ============================================================

    if content_lower.startswith("$slots"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❗ Usage: `$slots <bet>`")
            return
        try:
            bet = int(parts[1])
            if bet <= 0:
                raise ValueError
        except ValueError:
            await message.channel.send("❗ Please provide a valid bet amount.")
            return
        bal = get_balance(message.author.id)
        if bal < bet:
            await message.channel.send(f"❌ Not enough coins! You have **🪙 {bal:,}**.")
            return
        reels = [random.choice(SLOTS_SYMBOLS) for _ in range(3)]
        result = tuple(reels)
        display = " | ".join(reels)
        multiplier = SLOTS_MULTIPLIERS.get(result, 0)
        if multiplier == 0 and len(set(reels)) == 2:
            multiplier = 1.5
        if multiplier >= 1:
            winnings = int(bet * multiplier) - bet
            add_coins(message.author.id, winnings)
            new_bal = get_balance(message.author.id)
            if multiplier >= 10:
                result_text = f"🎉 **JACKPOT!** You won **🪙 {int(bet * multiplier):,}**!"
            else:
                result_text = f"✅ You won **🪙 {int(bet * multiplier):,}**! (×{multiplier})"
        else:
            remove_coins(message.author.id, bet)
            new_bal = get_balance(message.author.id)
            result_text = f"❌ You lost **🪙 {bet:,}**."
        embed = discord.Embed(title="🎰 Slot Machine", color=discord.Color.gold())
        embed.add_field(name="Result", value=f"[ {display} ]", inline=False)
        embed.add_field(name="Outcome", value=result_text, inline=False)
        embed.add_field(name="New Balance", value=f"🪙 {new_bal:,}", inline=True)
        await message.channel.send(embed=embed)
        return

    if content_lower == "$fish":
        FISH_COST = 10
        bal = get_balance(message.author.id)
        if bal < FISH_COST:
            await message.channel.send(f"❌ Fishing costs **🪙 {FISH_COST}** coins. You have **🪙 {bal:,}**.")
            return
        remove_coins(message.author.id, FISH_COST)
        await message.channel.send(f"🎣 {message.author.mention} is fishing...")
        await asyncio.sleep(2)
        roll = random.random()
        cumulative = 0
        caught = None
        for fish in FISH_TABLE:
            cumulative += fish[3]
            if roll < cumulative:
                caught = fish
                break
        if not caught:
            caught = FISH_TABLE[0]
        name, rarity, value, _ = caught
        add_coins(message.author.id, value)
        new_bal = get_balance(message.author.id)
        rarity_colors = {
            "Common": discord.Color.light_grey(),
            "Uncommon": discord.Color.green(),
            "Rare": discord.Color.blue(),
            "Epic": discord.Color.purple(),
            "Legendary": discord.Color.gold(),
        }
        embed = discord.Embed(title="🎣 You caught something!", color=rarity_colors.get(rarity, discord.Color.blue()))
        embed.add_field(name="Fish", value=name, inline=True)
        embed.add_field(name="Rarity", value=rarity, inline=True)
        embed.add_field(name="Value", value=f"🪙 {value}", inline=True)
        embed.add_field(name="New Balance", value=f"🪙 {new_bal:,}", inline=False)
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$blackjack") or content_lower.startswith("$bj"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❗ Usage: `$blackjack <bet>`")
            return
        try:
            bet = int(parts[1])
            if bet <= 0:
                raise ValueError
        except ValueError:
            await message.channel.send("❗ Please provide a valid bet amount.")
            return
        bal = get_balance(message.author.id)
        if bal < bet:
            await message.channel.send(f"❌ Not enough coins! You have **🪙 {bal:,}**.")
            return

        def make_deck():
            suits = ["♠", "♥", "♦", "♣"]
            ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
            return [r + s for s in suits for r in ranks]

        def card_value(card):
            rank = card[:-1]
            if rank in ("J", "Q", "K"): return 10
            if rank == "A": return 11
            return int(rank)

        def hand_value(hand):
            total = sum(card_value(c) for c in hand)
            aces = sum(1 for c in hand if c[:-1] == "A")
            while total > 21 and aces:
                total -= 10
                aces -= 1
            return total

        def fmt_hand(hand):
            return " ".join(hand)

        deck = make_deck()
        random.shuffle(deck)
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        pval = hand_value(player_hand)
        dval = hand_value(dealer_hand)

        if pval == 21:
            winnings = int(bet * 1.5)
            add_coins(message.author.id, winnings)
            embed = discord.Embed(title="🃏 Blackjack — BLACKJACK!", color=discord.Color.gold())
            embed.add_field(name="Your Hand", value=f"{fmt_hand(player_hand)} = **{pval}**", inline=False)
            embed.add_field(name="Dealer Hand", value=f"{fmt_hand(dealer_hand)} = **{dval}**", inline=False)
            embed.add_field(name="Result", value=f"🎉 Blackjack! You win **🪙 {winnings:,}**!", inline=False)
            await message.channel.send(embed=embed)
            return

        embed = discord.Embed(
            title="🃏 Blackjack",
            description=f"Bet: 🪙 {bet:,}\nType `hit` to draw or `stand` to hold. You have **20 seconds**.",
            color=discord.Color.dark_green()
        )
        embed.add_field(name="Your Hand", value=f"{fmt_hand(player_hand)} = **{pval}**", inline=False)
        embed.add_field(name="Dealer Shows", value=f"{dealer_hand[0]} + ❓", inline=False)
        await message.channel.send(embed=embed)

        def check(m):
            return (
                m.author == message.author
                and m.channel == message.channel
                and m.content.lower() in ("hit", "stand")
            )

        while True:
            try:
                resp = await client.wait_for("message", check=check, timeout=20)
            except asyncio.TimeoutError:
                await message.channel.send(f"⏰ {message.author.mention} timed out — you stand automatically.")
                break
            if resp.content.lower() == "hit":
                player_hand.append(deck.pop())
                pval = hand_value(player_hand)
                if pval > 21:
                    remove_coins(message.author.id, bet)
                    new_bal = get_balance(message.author.id)
                    embed = discord.Embed(title="🃏 Blackjack — BUST!", color=discord.Color.red())
                    embed.add_field(name="Your Hand", value=f"{fmt_hand(player_hand)} = **{pval}**", inline=False)
                    embed.add_field(name="Result", value=f"💥 Bust! You lost **🪙 {bet:,}**.", inline=False)
                    embed.add_field(name="New Balance", value=f"🪙 {new_bal:,}", inline=True)
                    await message.channel.send(embed=embed)
                    return
                await message.channel.send(f"🃏 Your hand: {fmt_hand(player_hand)} = **{pval}**\nType `hit` or `stand`.")
            else:
                break

        while hand_value(dealer_hand) < 17:
            dealer_hand.append(deck.pop())
        dval = hand_value(dealer_hand)

        if dval > 21 or pval > dval:
            add_coins(message.author.id, bet)
            result_text = f"🎉 You win **🪙 {bet:,}**!"
            color = discord.Color.green()
        elif pval == dval:
            result_text = "🤝 It's a tie — bet returned."
            color = discord.Color.light_grey()
        else:
            remove_coins(message.author.id, bet)
            result_text = f"❌ Dealer wins. You lost **🪙 {bet:,}**."
            color = discord.Color.red()

        new_bal = get_balance(message.author.id)
        embed = discord.Embed(title="🃏 Blackjack — Result", color=color)
        embed.add_field(name="Your Hand", value=f"{fmt_hand(player_hand)} = **{pval}**", inline=False)
        embed.add_field(name="Dealer Hand", value=f"{fmt_hand(dealer_hand)} = **{dval}**", inline=False)
        embed.add_field(name="Result", value=result_text, inline=False)
        embed.add_field(name="New Balance", value=f"🪙 {new_bal:,}", inline=True)
        await message.channel.send(embed=embed)
        return

    # ============================================================
    # POLL
    # ============================================================
    if content_lower.startswith("$poll"):
        raw = content[5:].strip()
        if not raw or "|" not in raw:
            await message.channel.send(
                "❗ Usage: `$poll <question> | <opt1> | <opt2> ...`\n"
                "Example: `$poll Favourite game? | Minecraft | Fortnite | Valorant`"
            )
            return
        parts = [p.strip() for p in raw.split("|")]
        question = parts[0]
        options = parts[1:]
        if len(options) < 2:
            await message.channel.send("❗ Please provide at least 2 options.")
            return
        if len(options) > 10:
            await message.channel.send("❗ Maximum 10 options allowed.")
            return
        description = "\n".join(f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title=f"🗳️ {question}", description=description, color=discord.Color.blurple())
        embed.set_footer(text=f"Poll by {message.author.display_name}")
        poll_msg = await message.channel.send(embed=embed)
        for i in range(len(options)):
            await poll_msg.add_reaction(POLL_EMOJIS[i])
        return

    # ============================================================
    # MODERATION
    # ============================================================

    if content_lower.startswith("$warn"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$warn @user <reason>`")
            return
        target = message.mentions[0]
        parts = content.split(maxsplit=2)
        reason = parts[2] if len(parts) >= 3 else "No reason provided"
        warnings = db.get("warnings", {}) or {}
        uid = str(target.id)
        if uid not in warnings:
            warnings[uid] = []
        warnings[uid].append({"reason": reason, "by": str(message.author), "time": time.strftime("%d %b %Y %H:%M")})
        db.update({"warnings": warnings})
        embed = discord.Embed(title="⚠️ Warning Issued", color=discord.Color.yellow())
        embed.add_field(name="User", value=target.mention, inline=True)
        embed.add_field(name="Warned by", value=message.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=str(len(warnings[uid])), inline=True)
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$warnings"):
        if not message.mentions:
            await message.channel.send("❗ Usage: `$warnings @user`")
            return
        target = message.mentions[0]
        warnings = db.get("warnings", {}) or {}
        user_warns = warnings.get(str(target.id), [])
        if not user_warns:
            await message.channel.send(f"✅ {target.mention} has no warnings.")
            return
        embed = discord.Embed(title=f"⚠️ Warnings for {target.display_name}", color=discord.Color.orange())
        for i, w in enumerate(user_warns, 1):
            embed.add_field(name=f"Warning #{i} — {w['time']}", value=f"**Reason:** {w['reason']}\n**By:** {w['by']}", inline=False)
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$clearwarnings"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$clearwarnings @user`")
            return
        target = message.mentions[0]
        warnings = db.get("warnings", {}) or {}
        warnings[str(target.id)] = []
        db.update({"warnings": warnings})
        await message.channel.send(f"✅ Cleared all warnings for {target.mention}.")
        return

    if content_lower.startswith("$kick"):
        if not message.author.guild_permissions.kick_members:
            await message.channel.send("❌ You need Kick Members permission.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$kick @user <reason>`")
            return
        target = message.mentions[0]
        parts = content.split(maxsplit=2)
        reason = parts[2] if len(parts) >= 3 else "No reason provided"
        try:
            await target.kick(reason=reason)
            await message.channel.send(f"👢 **{target}** has been kicked. Reason: {reason}")
        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to kick that user.")
        return

    if content_lower.startswith("$ban"):
        if not message.author.guild_permissions.ban_members:
            await message.channel.send("❌ You need Ban Members permission.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$ban @user <reason>`")
            return
        target = message.mentions[0]
        parts = content.split(maxsplit=2)
        reason = parts[2] if len(parts) >= 3 else "No reason provided"
        try:
            await target.ban(reason=reason)
            await message.channel.send(f"🔨 **{target}** has been banned. Reason: {reason}")
        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to ban that user.")
        return

    if content_lower.startswith("$mute"):
        if not message.author.guild_permissions.moderate_members:
            await message.channel.send("❌ You need Moderate Members permission.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$mute @user <duration> <reason>`\nDuration examples: `10m`, `2h`, `1d`")
            return
        target = message.mentions[0]
        parts = content.split()
        if len(parts) < 3:
            await message.channel.send("❗ Usage: `$mute @user <duration> <reason>`")
            return
        duration_str = parts[2]
        reason = " ".join(parts[3:]) if len(parts) > 3 else "No reason provided"
        seconds = parse_time(duration_str)
        if not seconds:
            await message.channel.send("❗ Invalid duration. Use: `10s`, `5m`, `2h`, `1d`")
            return
        try:
            until = discord.utils.utcnow() + discord.utils.datetime.timedelta(seconds=seconds)
            await target.timeout(until, reason=reason)
            await message.channel.send(f"🔇 **{target.display_name}** has been muted for **{duration_str}**. Reason: {reason}")
        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to mute that user.")
        except Exception as e:
            await message.channel.send(f"❌ Error: {e}")
        return

    if content_lower.startswith("$unmute"):
        if not message.author.guild_permissions.moderate_members:
            await message.channel.send("❌ You need Moderate Members permission.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$unmute @user`")
            return
        target = message.mentions[0]
        try:
            await target.timeout(None)
            await message.channel.send(f"🔊 **{target.display_name}** has been unmuted.")
        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to unmute that user.")
        return

    if content_lower.startswith("$purge"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❗ Usage: `$purge <amount>` (max 100)")
            return
        try:
            amount = int(parts[1])
            if amount < 1 or amount > 100:
                raise ValueError
        except ValueError:
            await message.channel.send("❗ Please provide a number between 1 and 100.")
            return
        deleted = await message.channel.purge(limit=amount + 1)
        msg = await message.channel.send(f"🗑️ Deleted **{len(deleted) - 1}** messages.")
        await asyncio.sleep(3)
        await msg.delete()
        return

    if content_lower.startswith("$announce"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        parts = content.split(maxsplit=2)
        if len(parts) < 3 or not message.channel_mentions:
            await message.channel.send("❗ Usage: `$announce #channel <message>`")
            return
        target_channel = message.channel_mentions[0]
        announcement_text = parts[2].replace(target_channel.mention, "").strip()
        if not announcement_text:
            await message.channel.send("❗ Please provide an announcement message.")
            return
        embed = discord.Embed(title="📢 Announcement", description=announcement_text, color=discord.Color.red())
        embed.set_footer(text=f"Posted by {message.author.display_name} • {time.strftime('%d %b %Y %H:%M')}")
        await target_channel.send(embed=embed)
        await message.channel.send(f"✅ Announcement posted in {target_channel.mention}.")
        return

    # ============================================================
    # TRIVIA
    # ============================================================
    if content_lower == "$trivia":
        question = random.choice(TRIVIA)
        active_trivia[message.channel.id] = {
            "answer": question["answer"],
            "options": question["options"],
            "answered": False,
        }
        description = "\n".join(f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(question["options"]))
        embed = discord.Embed(
            title="🧠 Trivia Time!",
            description=f"**{question['q']}**\n\n{description}\n\nReply with the correct number emoji!",
            color=discord.Color.purple()
        )
        embed.set_footer(text="You have 30 seconds!")
        await message.channel.send(embed=embed)

        async def expire_trivia():
            await asyncio.sleep(30)
            if message.channel.id in active_trivia and not active_trivia[message.channel.id]["answered"]:
                correct = question["options"][question["answer"]]
                await message.channel.send(
                    f"⏰ Time's up! The correct answer was **{POLL_EMOJIS[question['answer']]} {correct}**."
                )
                del active_trivia[message.channel.id]

        asyncio.create_task(expire_trivia())
        return

    # ============================================================
    # REMINDERS
    # ============================================================
    if content_lower.startswith("$remind"):
        parts = content.split(maxsplit=2)
        if len(parts) < 3:
            await message.channel.send(
                "❗ Usage: `$remind <time> <message>`\n"
                "Examples: `$remind 10m check oven` | `$remind 2h study break`"
            )
            return
        seconds = parse_time(parts[1])
        if not seconds:
            await message.channel.send("❗ Invalid time format. Use: `30s`, `10m`, `2h`, `1d`")
            return
        if seconds > 604800:
            await message.channel.send("❗ Maximum reminder time is 7 days.")
            return
        reminder_text = parts[2]
        await message.channel.send(f"⏰ Got it! I'll remind you about **{reminder_text}** in **{parts[1]}**.")

        async def send_reminder():
            await asyncio.sleep(seconds)
            await message.channel.send(f"⏰ {message.author.mention} — Reminder: **{reminder_text}**")

        asyncio.create_task(send_reminder())
        return

    # ============================================================
    # AFK
    # ============================================================
    if content_lower.startswith("$afk"):
        parts = content.split(maxsplit=1)
        reason = parts[1] if len(parts) > 1 else "AFK"
        afk_data = db.get("afk", {}) or {}
        afk_data[str(message.author.id)] = {"reason": reason, "since": time.strftime("%H:%M")}
        db.update({"afk": afk_data})
        await message.channel.send(f"💤 **{message.author.display_name}** is now AFK: *{reason}*")
        return

    # ============================================================
    # 💕 SOCIAL — MARRIAGE
    # ============================================================

    if content_lower.startswith("$marry"):
        if not message.mentions:
            await message.channel.send("❗ Usage: `$marry @user`")
            return
        target = message.mentions[0]
        if target.id == message.author.id:
            await message.channel.send("❗ You can't marry yourself!")
            return
        if target.bot:
            await message.channel.send("❗ You can't marry a bot!")
            return
        if get_marriage(message.author.id):
            partner_id = get_marriage(message.author.id)
            partner = guild.get_member(int(partner_id))
            pname = partner.display_name if partner else "someone"
            await message.channel.send(f"💍 You're already married to **{pname}**! Divorce first with `$divorce`.")
            return
        if get_marriage(target.id):
            await message.channel.send(f"💔 **{target.display_name}** is already married!")
            return

        await message.channel.send(
            f"💍 {target.mention}, **{message.author.display_name}** has proposed to you!\n"
            f"Type `yes` to accept or `no` to decline. *(30 seconds)*"
        )

        def marry_check(m):
            return m.author == target and m.channel == message.channel and m.content.lower() in ("yes", "no")

        try:
            resp = await client.wait_for("message", check=marry_check, timeout=30)
        except asyncio.TimeoutError:
            await message.channel.send(f"💔 **{target.display_name}** didn't respond — proposal expired.")
            return

        if resp.content.lower() == "yes":
            set_marriage(message.author.id, target.id)
            embed = discord.Embed(
                title="💍 Just Married!",
                description=f"🎉 {message.author.mention} and {target.mention} are now married!",
                color=discord.Color.from_rgb(255, 182, 193)
            )
            embed.set_footer(text="Congratulations! 💕")
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(f"💔 **{target.display_name}** declined the proposal.")
        return

    if content_lower == "$divorce":
        partner_id = get_marriage(message.author.id)
        if not partner_id:
            await message.channel.send("❗ You're not married!")
            return
        partner = guild.get_member(int(partner_id))
        pname = partner.display_name if partner else "your partner"
        remove_marriage(message.author.id)
        await message.channel.send(f"💔 **{message.author.display_name}** and **{pname}** are now divorced.")
        return

    if content_lower.startswith("$spouse"):
        user = message.mentions[0] if message.mentions else message.author
        partner_id = get_marriage(user.id)
        if not partner_id:
            await message.channel.send(f"💔 **{user.display_name}** is not married.")
            return
        partner = guild.get_member(int(partner_id))
        pname = partner.mention if partner else f"<@{partner_id}>"
        await message.channel.send(f"💍 **{user.display_name}** is married to {pname}!")
        return

    # ============================================================
    # 💕 SOCIAL — PROFILE
    # ============================================================

    if content_lower.startswith("$profile"):
        user = message.mentions[0] if message.mentions else message.author
        uid = str(user.id)
        xp_data = db.get("xp", {}) or {}
        xp = xp_data.get(uid, {}).get("xp", 0)
        level = xp_data.get(uid, {}).get("level", 0)
        coins = get_balance(user.id)
        rep_points = get_rep(user.id).get("points", 0)
        profile = get_profile(user.id)
        bio = profile.get("bio", "No bio set.")
        partner_id = get_marriage(user.id)
        partner = guild.get_member(int(partner_id)) if partner_id else None
        birthday = get_birthday(user.id)

        embed = discord.Embed(
            title=f"👤 {user.display_name}'s Profile",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="📝 Bio", value=bio, inline=False)
        embed.add_field(name="⭐ Level", value=str(level), inline=True)
        embed.add_field(name="✨ XP", value=str(xp), inline=True)
        embed.add_field(name="🪙 Coins", value=f"{coins:,}", inline=True)
        embed.add_field(name="👍 Rep", value=str(rep_points), inline=True)
        embed.add_field(name="💍 Spouse", value=partner.mention if partner else "Single 💔", inline=True)
        embed.add_field(name="🎂 Birthday", value=birthday if birthday else "Not set", inline=True)
        embed.set_footer(text=f"Member since {user.joined_at.strftime('%d %b %Y')}")
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$setbio"):
        parts = content.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.channel.send("❗ Usage: `$setbio <your bio here>` e.g. `$setbio Hi I love gaming!")

            return
        bio = parts[1].strip()
        if len(bio) > 150:
            await message.channel.send(f"❗ Bio must be 150 characters or less. Yours is **{len(bio)}** characters.")
            return
        set_profile_bio(message.author.id, bio)
        await message.channel.send(f"✅ Bio updated to: *{bio}*")
        return

    # ============================================================
    # 💕 SOCIAL — REP
    # ============================================================

    if content_lower.startswith("$rep") and not content_lower.startswith("$repboard"):
        if not message.mentions:
            await message.channel.send("❗ Usage: `$rep @user`")
            return
        target = message.mentions[0]
        if target.id == message.author.id:
            await message.channel.send("❗ You can't rep yourself!")
            return
        if target.bot:
            await message.channel.send("❗ You can't rep a bot!")
            return
        success, msg = give_rep(message.author.id, target.id)
        if success:
            await message.channel.send(f"👍 {message.author.mention} gave rep to {target.mention}! {msg}")
        else:
            await message.channel.send(f"⏳ {msg}")
        return

    if content_lower == "$repboard":
        rep = db.get("rep", {}) or {}
        if not rep:
            await message.channel.send("No rep data yet.")
            return
        sorted_rep = sorted(rep.items(), key=lambda x: x[1].get("points", 0), reverse=True)
        msg = "👍 **Rep Leaderboard**\n"
        count = 0
        for uid, data in sorted_rep:
            u = guild.get_member(int(uid))
            if u and count < 5:
                msg += f"{count+1}. {u.name} — 👍 {data.get('points', 0)}\n"
                count += 1
        await message.channel.send(msg)
        return

    # ============================================================
    # 💕 SOCIAL — BIRTHDAY
    # ============================================================

    if content_lower.startswith("$birthday set "):
        import datetime
        date_str = content.split("$birthday set ", 1)[1].strip()
        try:
            datetime.datetime.strptime(date_str, "%d/%m")
        except ValueError:
            await message.channel.send("❗ Use format: `$birthday set DD/MM` e.g. `$birthday set 25/12`")
            return
        set_birthday(message.author.id, date_str)
        await message.channel.send(f"🎂 Your birthday has been set to **{date_str}**!")
        return

    if content_lower.startswith("$birthday"):
        user = message.mentions[0] if message.mentions else message.author
        bday = get_birthday(user.id)
        if bday:
            await message.channel.send(f"🎂 **{user.display_name}**'s birthday is **{bday}**!")
        else:
            await message.channel.send(
                f"❓ **{user.display_name}** hasn't set a birthday yet.\n"
                f"Use `$birthday set DD/MM` to set yours!"
            )
        return

    # ============================================================
    # 🎫 TICKET SYSTEM
    # ============================================================

    if content_lower == "$ticket":
        guild = message.guild
        author = message.author
        # find or create ticket category
        cat_name = "Tickets"
        category = discord.utils.get(guild.categories, name=cat_name)
        if not category:
            try:
                category = await guild.create_category(cat_name)
            except discord.Forbidden:
                category = None
        # check if user already has open ticket
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{author.name.lower()}")
        if existing:
            await message.channel.send(f"❗ You already have an open ticket: {existing.mention}")
            return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        # give mods access too
        for role in guild.roles:
            if role.permissions.manage_messages:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        try:
            ticket_channel = await guild.create_text_channel(
                f"ticket-{author.name.lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"Support ticket for {author}"
            )
        except discord.Forbidden:
            await message.channel.send(
                "❌ I don't have **Manage Channels** permission.\n"
                "Please go to **Server Settings → Roles → Evelyn** and enable it."
            )
            return
        embed = discord.Embed(
            title="🎫 Support Ticket",
            description=(
                f"Welcome {author.mention}! Support staff will be with you shortly.\n\n"
                "Please describe your issue clearly.\n"
                "Use `$closeticket` to close this ticket when resolved."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Ticket by {author} • {time.strftime('%d %b %Y %H:%M')}")
        await ticket_channel.send(embed=embed)
        await message.channel.send(f"✅ Your ticket has been created: {ticket_channel.mention}")
        return

    if content_lower == "$closeticket":
        if not message.channel.name.startswith("ticket-"):
            await message.channel.send("❗ This command can only be used inside a ticket channel.")
            return
        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"Ticket closed by {message.author.mention}. This channel will be deleted in 5 seconds.",
            color=discord.Color.red()
        )
        await message.channel.send(embed=embed)
        await asyncio.sleep(5)
        await message.channel.delete()
        return

    if content_lower.startswith("$addticketmod"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$addticketmod @role_or_user`")
            return
        target = message.mentions[0]
        if message.channel.name.startswith("ticket-"):
            await message.channel.set_permissions(target, read_messages=True, send_messages=True)
            await message.channel.send(f"✅ {target.mention} can now access this ticket.")
        return

    # ============================================================
    # 🔥 DAILY STREAKS (upgraded $daily — replaces old one)
    # ============================================================

    if content_lower == "$daily":
        uid = message.author.id
        last = get_last_daily(uid)
        now = time.time()
        remaining = DAILY_COOLDOWN - (now - last)
        if remaining > 0:
            hrs = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            streak_data = get_streak(uid)
            await message.channel.send(
                f"⏳ You already claimed your daily! Come back in **{hrs}h {mins}m**.\n"
                f"🔥 Current streak: **{streak_data['streak']} days**"
            )
            return
        streak, bonus = update_streak(uid)
        total = DAILY_COINS + bonus
        add_coins(uid, total)
        set_last_daily(uid, now)
        bal = get_balance(uid)
        embed = discord.Embed(
            title="💰 Daily Reward Claimed!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.add_field(name="Base Reward", value=f"🪙 {DAILY_COINS}", inline=True)
        embed.add_field(name="Streak Bonus", value=f"🪙 +{bonus}", inline=True)
        embed.add_field(name="Total Received", value=f"🪙 **{total}**", inline=True)
        embed.add_field(name="🔥 Streak", value=f"**{streak} day{'s' if streak != 1 else ''}**", inline=True)
        embed.add_field(name="New Balance", value=f"🪙 {bal:,}", inline=True)
        if streak >= 7:
            embed.set_footer(text="🔥 Amazing streak! Keep it going!")
        elif streak >= 3:
            embed.set_footer(text="⚡ You're on a roll!")
        else:
            embed.set_footer(text="Come back tomorrow for a streak bonus!")
        await message.channel.send(embed=embed)
        return

    # ============================================================
    # 🏪 SHOP + INVENTORY
    # ============================================================

    if content_lower == "$shop":
        shop = get_shop()
        embed = discord.Embed(
            title="🏪 Server Shop",
            description="Use `$buy <item_id>` to purchase an item!",
            color=discord.Color.gold()
        )
        for key, item in shop.items():
            item_type = "🎭 Role" if item["type"] == "role" else "🎒 Item"
            desc = item.get("desc", item.get("role_name", ""))
            embed.add_field(
                name=f"{item['name']} — 🪙 {item['price']:,}",
                value=f"{item_type} • `{key}` • {desc}",
                inline=False
            )
        bal = get_balance(message.author.id)
        embed.set_footer(text=f"Your balance: 🪙 {bal:,}")
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$buy "):
        item_key = content.split("$buy ", 1)[1].strip().lower()
        shop = get_shop()
        if item_key not in shop:
            await message.channel.send(f"❗ Item `{item_key}` not found. Use `$shop` to see available items.")
            return
        item = shop[item_key]
        price = item["price"]
        bal = get_balance(message.author.id)
        if bal < price:
            await message.channel.send(f"❌ Not enough coins! You need **🪙 {price:,}** but have **🪙 {bal:,}**.")
            return
        remove_coins(message.author.id, price)
        if item["type"] == "role":
            role_name = item["role_name"]
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                try:
                    role = await guild.create_role(name=role_name, reason="Shop purchase")
                except discord.Forbidden:
                    add_coins(message.author.id, price)
                    await message.channel.send("❌ I don't have permission to create roles.")
                    return
            try:
                await message.author.add_roles(role)
                await message.channel.send(
                    f"✅ You purchased {item['name']} for {price:,} coins! 🎭 The {role_name} role has been added."
                    f"✅ You purchased {item['name']} for {price:,} coins! 🎭 The {role_name} role has been added."
                )
            except discord.Forbidden:
                add_coins(message.author.id, price)
                await message.channel.send("❌ I don't have permission to assign roles.")


        else:
            add_to_inventory(message.author.id, item_key, item["name"])
            await message.channel.send(
                f"✅ You purchased {item['name']} for {price:,} coins!\n🎒 Check your inventory with `$inventory`."
            )
        return


    if content_lower in ("$inventory", "$inv"):
        inv = get_inventory(message.author.id)
        shop = get_shop()
        embed = discord.Embed(
            title=f"🎒 {message.author.display_name}'s Inventory",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        if not inv:
            embed.description = "Your inventory is empty! Visit `$shop` to buy items."
        else:
            for key, qty in inv.items():
                item_info = shop.get(key, {})
                name = item_info.get("name", key)
                desc = item_info.get("desc", "")
                embed.add_field(name=f"{name} x{qty}", value=desc or "Special item", inline=False)
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$addshop") and message.author.guild_permissions.administrator:
        # $addshop <key> <price> <type:role|item> <name...>
        parts = content.split(maxsplit=4)
        if len(parts) < 5:
            await message.channel.send("❗ Usage: `$addshop <key> <price> <role|item> <name>`")
            return
        try:
            key, price_str, itype, name = parts[1], parts[2], parts[3], parts[4]
            price = int(price_str)
            if itype not in ("role", "item"):
                raise ValueError
        except ValueError:
            await message.channel.send("❗ Invalid format. Example: `$addshop cool_role 500 role Cool Role`")
            return
        shop = get_shop()
        shop[key.lower()] = {"name": name, "price": price, "type": itype,
                              "role_name": name if itype == "role" else "",
                              "desc": name if itype == "item" else ""}
        db.update({"shop_items": shop})
        await message.channel.send(f"✅ Added **{name}** to the shop for 🪙 {price:,}.")
        return

    if content_lower.startswith("$removeshop") and message.author.guild_permissions.administrator:
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❗ Usage: `$removeshop <key>`")
            return
        key = parts[1].lower()
        shop = get_shop()
        if key not in shop:
            await message.channel.send(f"❗ Item `{key}` not found in shop.")
            return
        del shop[key]
        db.update({"shop_items": shop})
        await message.channel.send(f"✅ Removed `{key}` from the shop.")
        return

    # ============================================================
    # 🎭 CUSTOM COMMANDS
    # ============================================================

    if content_lower.startswith("$addcmd"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        parts = content.split(maxsplit=2)
        if len(parts) < 3:
            await message.channel.send("❗ Usage: `$addcmd <trigger> <response>`\nExample: `$addcmd hello Hi there! Welcome!`")
            return
        trigger, response = parts[1].lower(), parts[2]
        if trigger.startswith("$") and len(trigger) < 15:
            # don't allow overriding real commands
            reserved = ["ping","help","rank","daily","balance","bal","marry","divorce",
                        "profile","rep","birthday","shop","buy","inventory","inv","ticket",
                        "warn","kick","ban","mute","purge","play","skip","trivia","addcmd",
                        "removecmd","listcmds","addshop","removeshop","closeticket"]
            if trigger[1:] in reserved:
                await message.channel.send(f"❗ `{trigger}` is a reserved command and cannot be overridden.")
                return
        add_custom_command(trigger, response)
        await message.channel.send(f"✅ Custom command `{trigger}` created!")
        return

    if content_lower.startswith("$removecmd"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❗ Usage: `$removecmd <trigger>`")
            return
        trigger = parts[1].lower()
        if remove_custom_command(trigger):
            await message.channel.send(f"✅ Custom command `{trigger}` removed.")
        else:
            await message.channel.send(f"❗ No custom command found for `{trigger}`.")
        return

    if content_lower == "$listcmds":
        cmds = get_custom_commands()
        if not cmds:
            await message.channel.send("No custom commands set yet. Use `$addcmd` to create one!")
            return
        lines = [f"• `{trigger}` → {resp[:60]}{'...' if len(resp)>60 else ''}" for trigger, resp in cmds.items()]
        # chunk to avoid 2000 char limit
        chunk, chunks = "", []
        for line in lines:
            if len(chunk) + len(line) + 1 > 1800:
                chunks.append(chunk)
                chunk = ""
            chunk += line + "\n"

        if chunk:
            chunks.append(chunk)
        for i, c in enumerate(chunks):
            header = (f"🎭 **Custom Commands** ({i+1}/{len(chunks)})" if len(chunks) > 1 else "🎭 **Custom Commands**") + "\n"


            await message.channel.send(header + c)
        return

    # check custom commands
    cmds = get_custom_commands()
    if content_lower in cmds:
        await message.channel.send(cmds[content_lower])
        return

    # ============================================================
    # MUSIC
    # ============================================================
    if content_lower.startswith("$play"):
        if not MUSIC_ENABLED:
            await message.channel.send("❌ Music disabled. Install with: `pip install yt-dlp PyNaCl`\nAlso make sure **ffmpeg** is installed.")
            return
        if not message.author.voice:
            await message.channel.send("❗ Join a voice channel first!")
            return
        query = content[5:].strip()
        if not query:
            await message.channel.send("❗ Usage: `$play <song name or URL>`")
            return
        vc = guild.voice_client
        if not vc:
            vc = await message.author.voice.channel.connect()
        elif vc.channel != message.author.voice.channel:
            await vc.move_to(message.author.voice.channel)
        gid = guild.id
        if gid not in music_queues:
            music_queues[gid] = []
        await message.channel.send(f"🔍 Searching for **{query}**...")
        try:
            search_query = f"ytsearch:{query}" if not query.startswith("http") else query
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                info = ydl.extract_info(search_query, download=False)
                if "entries" in info:
                    info = info["entries"][0]
                title = info.get("title", "Unknown")
                url = info.get("webpage_url", query)
            music_queues[gid].append({"url": url, "title": title})
            if not music_playing.get(gid):
                await play_next(guild, message.channel)
            else:
                await message.channel.send(f"➕ Added to queue: **{title}**")
        except Exception as e:
            await message.channel.send(f"❌ Could not find that song: {e}")
        return

    if content_lower == "$nowplaying":
        gid = guild.id
        title = now_playing.get(gid)
        vc = guild.voice_client
        if vc and vc.is_playing() and title:
            await message.channel.send(f"🎵 Now playing: **{title}**")
        else:
            await message.channel.send("❗ Nothing is playing right now.")
        return

    if content_lower == "$skip":
        vc = guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await message.channel.send("⏭️ Skipped!")
        else:
            await message.channel.send("❗ Nothing is playing right now.")
        return

    if content_lower == "$pause":
        vc = guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await message.channel.send("⏸️ Paused.")
        else:
            await message.channel.send("❗ Nothing is playing right now.")
        return

    if content_lower == "$resume":
        vc = guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await message.channel.send("▶️ Resumed!")
        else:
            await message.channel.send("❗ Nothing is paused right now.")
        return

    if content_lower == "$stop":
        vc = guild.voice_client
        if vc:
            music_queues[guild.id] = []
            music_playing[guild.id] = False
            now_playing.pop(guild.id, None)
            await vc.disconnect()
            await message.channel.send("⏹️ Stopped and left the voice channel.")
        else:
            await message.channel.send("❗ I'm not in a voice channel.")
        return

    if content_lower == "$queue":
        gid = guild.id
        queue = music_queues.get(gid, [])
        vc = guild.voice_client
        if not queue and not (vc and vc.is_playing()):
            await message.channel.send("📭 The queue is empty.")
            return
        msg = "🎶 **Music Queue:**\n"
        if now_playing.get(gid):
            msg += f"▶️ **Now:** {now_playing[gid]}\n"
        for i, entry in enumerate(queue, 1):
            msg += f"{i}. {entry['title']}\n"
        await message.channel.send(msg)
        return

    # ============================================================
    # FUN COMMANDS
    # ============================================================

    if content_lower.startswith("$8ball"):
        parts = content.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.channel.send("🎱 Ask a full question! e.g. `$8ball Will I win?`")
            return
        await message.channel.send(f"🎱 **Answer:** {random.choice(eight_ball_responses)}")
        return

    if content_lower.startswith("$roll"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("Usage: `$roll <number>`")
            return
        try:
            number = int(parts[1])
            result = random.randint(1, number)
            await message.channel.send(f"🎲 You rolled: **{result}**")
        except ValueError:
            await message.channel.send("Usage: `$roll <number>`")
        return

    if content_lower == "$coinflip":
        await message.channel.send(f"🪙 **{random.choice(['Heads', 'Tails'])}**")
        return

    if content_lower.startswith("$joke"):
        await message.channel.send(random.choice(gaming_anime_jokes))
        return

    if content_lower.startswith("$guess"):
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("Usage: `$guess <number 1-10>`")
            return
        try:
            user_guess = int(parts[1])
            bot_number = random.randint(1, 10)
            if user_guess == bot_number:
                await message.channel.send("🎉 Correct! You guessed it!")
            else:
                await message.channel.send(f"❌ Wrong! I chose **{bot_number}**")
        except ValueError:
            await message.channel.send("Usage: `$guess <number 1-10>`")
        return

    if content_lower.startswith("$meme"):
        try:
            response = requests.get("https://meme-api.com/gimme", timeout=8)
            data = response.json()
            embed = discord.Embed(title=data["title"], color=discord.Color.random())
            embed.set_image(url=data["url"])
            await message.channel.send(embed=embed)
        except Exception as e:
            await message.channel.send("❌ Could not fetch meme right now.")
            print(e)
        return

    # ============================================================
    # 📋 ADVANCED INTRO SYSTEM
    # ============================================================

    if content_lower == "$intro":
        await message.channel.send(
            f"📬 {message.author.mention} Check your DMs! I've sent you the introduction form."
        )
        await send_intro_dm(message.author)
        return

    if content_lower.startswith("$setintrochannel"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        if not message.channel_mentions:
            await message.channel.send("❗ Usage: `$setintrochannel #channel`")
            return
        ch = message.channel_mentions[0]
        db.update({"intro_channel": str(ch.id)})
        await message.channel.send(f"✅ Intro channel set to {ch.mention}.")
        return

    if content_lower.startswith("$viewintro"):
        user = message.mentions[0] if message.mentions else message.author
        intro_data = db.get("intro_data", {}) or {}
        data = intro_data.get(str(user.id))
        if not data:
            await message.channel.send(f"❓ **{user.display_name}** hasn't submitted an intro yet. Use `$intro` to create one!")
            return
        embed = discord.Embed(
            title=f"📋 {user.display_name}'s Introduction",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        for key, question in INTRO_QUESTIONS:
            val = data.get(key, "*Not answered*")
            embed.add_field(name=question, value=val or "*Skipped*", inline=False)
        await message.channel.send(embed=embed)
        return

    # ============================================================
    # 📰 RSS FEEDS
    # ============================================================

    if content_lower.startswith("$addrss"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        parts = content.split(maxsplit=3)
        if len(parts) < 4 or not message.channel_mentions:
            await message.channel.send("❗ Usage: `$addrss <name> #channel <url>`")
            return
        name    = parts[1]
        channel_mention = message.channel_mentions[0]
        url     = parts[3] if not parts[3].startswith("<") else parts[-1]
        # extract URL (last non-mention word)
        words = content.split()
        url = [w for w in words if w.startswith("http")][-1] if any(w.startswith("http") for w in words) else ""
        if not url:
            await message.channel.send("❗ Please include a valid RSS URL starting with http.")
            return
        feeds = db.get("rss_feeds", {}) or {}
        feeds[name] = {"url": url, "channel_id": str(channel_mention.id)}
        db.update({"rss_feeds": feeds})
        await message.channel.send(f"✅ RSS feed **{name}** added! Posts will appear in {channel_mention.mention}.")
        return

    if content_lower.startswith("$removerss"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        parts = content.split()
        if len(parts) < 2:
            await message.channel.send("❗ Usage: `$removerss <name>`")
            return
        name = parts[1]
        feeds = db.get("rss_feeds", {}) or {}
        if name not in feeds:
            await message.channel.send(f"❗ No feed named `{name}` found.")
            return
        del feeds[name]
        db.update({"rss_feeds": feeds})
        await message.channel.send(f"✅ RSS feed **{name}** removed.")
        return

    if content_lower == "$listrss":
        feeds = db.get("rss_feeds", {}) or {}
        if not feeds:
            await message.channel.send("No RSS feeds set up. Use `$addrss <name> #channel <url>` to add one.")
            return
        embed = discord.Embed(title="📰 RSS Feeds", color=discord.Color.orange())
        for name, info in feeds.items():
            ch = guild.get_channel(int(info["channel_id"])) if info.get("channel_id") else None
            embed.add_field(
                name=name,
                value="Channel: " + (ch.mention if ch else "Unknown") + "\nURL: " + info["url"][:60] + "...",

                inline=False
            )
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$rss "):
        # Manual fetch: $rss <name>
        parts = content.split(maxsplit=1)
        name = parts[1].strip()
        feeds = db.get("rss_feeds", {}) or {}
        if name not in feeds:
            await message.channel.send(f"❗ No feed named `{name}`. Use `$listrss` to see all feeds.")
            return
        await message.channel.send(f"🔄 Fetching **{name}**...")
        items = await fetch_rss(feeds[name]["url"])
        if not items:
            await message.channel.send("❌ Could not fetch feed or feed is empty.")
            return
        embed = discord.Embed(title=f"📰 Latest from {name}", color=discord.Color.orange())
        for item in items[:5]:
            embed.add_field(
                name=item["title"][:100],
                value=f"[Read more]({item['link']})" if item["link"] else "No link",
                inline=False
            )
        await message.channel.send(embed=embed)
        return

    # ============================================================
    # 🎫 ADVANCED TICKET SYSTEM (replaces old one)
    # ============================================================

    if content_lower.startswith("$ticket"):
        parts = content.split(maxsplit=1)
        ticket_type = parts[1].strip().lower() if len(parts) > 1 else "support"
        valid_types = {"support": "🟢 Support", "report": "🔴 Report", "appeal": "🟡 Appeal", "other": "⚪ Other"}
        if ticket_type not in valid_types:
            type_list = " | ".join(f"`{t}`" for t in valid_types)
            await message.channel.send(f"❗ Usage: `$ticket <type>`\nTypes: {type_list}")

            return

        cat_name = "Tickets"
        category = discord.utils.get(guild.categories, name=cat_name)
        if not category:
            try:
                category = await guild.create_category(cat_name)
            except discord.Forbidden:
                category = None  # bot lacks permission, ticket will be created without category

        existing = discord.utils.get(
            guild.text_channels,
            name=f"ticket-{message.author.name.lower()}"
        )
        if existing:
            await message.channel.send(f"❗ You already have an open ticket: {existing.mention}")
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            message.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        for role in guild.roles:
            if role.permissions.manage_messages:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ticket_channel = await guild.create_text_channel(
                f"ticket-{message.author.name.lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"{valid_types[ticket_type]} ticket for {message.author} | Type: {ticket_type}"
            )
        except discord.Forbidden:
            await message.channel.send(
                "❌ I don't have **Manage Channels** permission.\n"
                "Please go to **Server Settings → Roles → Evelyn** and enable it."
            )
            return

        embed = discord.Embed(
            title=f"{valid_types[ticket_type]} Ticket",
            color=discord.Color.green()
        )
        embed.add_field(name="Opened by", value=message.author.mention, inline=True)
        embed.add_field(name="Type", value=valid_types[ticket_type], inline=True)
        embed.add_field(
            name="Instructions",
            value=(

                "Please describe your issue in detail.\n"
                "Staff will be with you shortly.\n\n"
                "`$assignticket @staff` — assign to a staff member\n"
                "`$addnote <text>` — add a note to this ticket\n"
                "`$closeticket` — close and save transcript"
            ),
            inline=False
        )




        embed.set_footer(text=f"Ticket opened: {time.strftime('%d %b %Y %H:%M')}")
        await ticket_channel.send(embed=embed)
        await message.channel.send(f"✅ Ticket opened: {ticket_channel.mention}")
        return

    if content_lower == "$closeticket":
        if not message.channel.name.startswith("ticket-"):
            await message.channel.send("❗ Use this inside a ticket channel.")
            return

        # Build transcript
        transcript_lines = [f"# Ticket Transcript — {message.channel.name}",
                            f"Closed by: {message.author} on {time.strftime('%d %b %Y %H:%M')}", ""]
        async for msg in message.channel.history(limit=200, oldest_first=True):
            transcript_lines.append(f"[{msg.created_at.strftime('%H:%M')}] {msg.author}: {msg.content}")

        transcript = "\n".join(transcript_lines)


        # Try to send transcript to log channel or ticket opener
        log_ch_id = db.get("ticket_log")
        log_channel = guild.get_channel(int(log_ch_id)) if log_ch_id else None

        # Save as file
        import io
        transcript_file = discord.File(
            fp=io.BytesIO(transcript.encode()),
            filename=f"transcript-{message.channel.name}.txt"
        )

        close_embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=f"Closed by {message.author.mention}. Transcript saved.",
            color=discord.Color.red()
        )
        await message.channel.send(embed=close_embed)

        if log_channel:
            await log_channel.send(
                f"📁 Transcript for `{message.channel.name}`",
                file=transcript_file
            )

        await asyncio.sleep(5)
        await message.channel.delete()
        return

    if content_lower.startswith("$assignticket"):
        if not message.channel.name.startswith("ticket-"):
            await message.channel.send("❗ Use this inside a ticket channel.")
            return
        if not message.mentions:
            await message.channel.send("❗ Usage: `$assignticket @staff`")
            return
        staff = message.mentions[0]
        await message.channel.set_permissions(staff, read_messages=True, send_messages=True)
        embed = discord.Embed(
            title="👤 Ticket Assigned",
            description=f"This ticket has been assigned to {staff.mention}.",
            color=discord.Color.blue()
        )
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$addnote "):
        if not message.channel.name.startswith("ticket-"):
            await message.channel.send("❗ Use this inside a ticket channel.")
            return
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ Only staff can add notes.")
            return
        note = content.split("$addnote ", 1)[1].strip()
        embed = discord.Embed(
            title="📝 Staff Note",
            description=note,
            color=discord.Color.yellow()
        )
        embed.set_footer(text=f"Note by {message.author.display_name} • {time.strftime('%d %b %Y %H:%M')}")
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$setticketlog"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        if not message.channel_mentions:
            await message.channel.send("❗ Usage: `$setticketlog #channel`")
            return
        ch = message.channel_mentions[0]
        db.update({"ticket_log": str(ch.id)})
        await message.channel.send(f"✅ Ticket transcripts will be saved to {ch.mention}.")
        return

    # ============================================================
    # 🐱 CAT DROPS
    # ============================================================

    if content_lower == "$catch":
        gid = guild.id
        if gid not in cat_active_catch:
            await message.channel.send("🐱 There's no cat to catch right now! Wait for one to appear.")
            return
        reward = cat_active_catch.pop(gid)["reward"]
        add_coins(message.author.id, reward)
        bal = get_balance(message.author.id)
        embed = discord.Embed(
            title="🎉 You caught the cat!",
            description=f"{message.author.mention} caught the cat and earned **🪙 {reward}** coins!",
            color=discord.Color.green()
        )
        embed.add_field(name="New Balance", value=f"🪙 {bal:,}", inline=True)
        embed.set_footer(text="Meow! 🐱")
        await message.channel.send(embed=embed)
        return

    if content_lower.startswith("$setcat"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        if not message.channel_mentions:
            await message.channel.send("❗ Usage: `$setcat #channel`")
            return
        ch = message.channel_mentions[0]
        db.update({"cat_channel": str(ch.id)})
        await message.channel.send(f"✅ Cat drops will appear in {ch.mention}!")
        return

    if content_lower.startswith("$catinterval"):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        parts = content.split()
        if len(parts) < 3:
            await message.channel.send("❗ Usage: `$catinterval <min_seconds> <max_seconds>`")
            return
        try:
            mn, mx = int(parts[1]), int(parts[2])
            if mn < 60 or mx < mn:
                raise ValueError
        except ValueError:
            await message.channel.send("❗ Min must be ≥ 60 and max must be ≥ min.")
            return
        db.update({"cat_drop_min": mn, "cat_drop_max": mx})
        await message.channel.send(f"✅ Cats will drop every **{mn}–{mx} seconds**.")
        return

    if content_lower == "$dropcat":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need Administrator permission.")
            return
        ch_id = db.get("cat_channel")
        channel = guild.get_channel(int(ch_id)) if ch_id else message.channel
        loop = asyncio.get_event_loop()
        cat_url = await loop.run_in_executor(None, _fetch_cat_url)
        reward = random.randint(CAT_REWARD_MIN, CAT_REWARD_MAX)
        cat_active_catch[guild.id] = {"reward": reward}
        embed = discord.Embed(
            title="🐱 A wild cat appeared!",
            description=f"Type `$catch` to catch it and earn **🪙 {reward}** coins!\nYou have **30 seconds!**",
            color=discord.Color.from_rgb(255, 165, 0)
        )
        if cat_url:
            embed.set_image(url=cat_url)
        await channel.send(embed=embed)

        async def expire_cat():
            await asyncio.sleep(30)
            if guild.id in cat_active_catch:
                del cat_active_catch[guild.id]
                await channel.send("🐱 The cat ran away... no one caught it!")

        asyncio.create_task(expire_cat())
        return

    # ============================================================
    # 📨 EMBED MESSAGES
    # ============================================================

    if content_lower.startswith("$embed"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        # Format: $embed #channel | Title | Description | Color(optional)
        raw = content[6:].strip()
        if "|" not in raw:
            await message.channel.send(
                "❗ Usage: `$embed #channel | Title | Description | #HexColor`\n"
                "Example: `$embed #general | Hello! | Welcome to the server! | #ff0000`\n"
                "Color is optional."
            )
            return
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 3:
            await message.channel.send("❗ Need at least: `$embed #channel | Title | Description`")
            return

        target_ch = message.channel_mentions[0] if message.channel_mentions else message.channel
        title = parts[1] if len(parts) > 1 else "Announcement"
        description = parts[2] if len(parts) > 2 else ""
        color = discord.Color.blurple()
        if len(parts) > 3 and parts[3].startswith("#"):
            try:
                hex_color = int(parts[3].lstrip("#"), 16)
                color = discord.Color(hex_color)
            except ValueError:
                pass

        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"Posted by {message.author.display_name} • {time.strftime('%d %b %Y %H:%M')}")
        await target_ch.send(embed=embed)
        if target_ch != message.channel:
            await message.channel.send(f"✅ Embed posted in {target_ch.mention}!")
        return

    if content_lower.startswith("$embedimage"):
        if not message.author.guild_permissions.manage_messages:
            await message.channel.send("❌ You need Manage Messages permission.")
            return
        # Format: $embedimage #channel | Title | Description | ImageURL | Color
        raw = content[11:].strip()
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 4:
            await message.channel.send(
                "❗ Usage: `$embedimage #channel | Title | Description | ImageURL | #Color`"
            )
            return
        target_ch = message.channel_mentions[0] if message.channel_mentions else message.channel
        title = parts[1]
        description = parts[2]
        image_url = parts[3]
        color = discord.Color.blurple()
        if len(parts) > 4 and parts[4].startswith("#"):
            try:
                color = discord.Color(int(parts[4].lstrip("#"), 16))
            except ValueError:
                pass
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_image(url=image_url)
        embed.set_footer(text=f"Posted by {message.author.display_name}")
        await target_ch.send(embed=embed)
        if target_ch != message.channel:
            await message.channel.send(f"✅ Embed posted in {target_ch.mention}!")
        return

    # ============================================================
    # AUTO-ENCOURAGEMENT
    # ============================================================
    if db.get("responding", True):
        if any(word in content_lower for word in sad_words):
            options = list(starter_encouragements)
            options += db.get("encouragements", []) or []
            await message.channel.send(random.choice(options))


# ============================================================
# RUN
# ============================================================
token = os.getenv("TOKEN")
if not token:
    print("ERROR: TOKEN not found in environment variables.")
else:
    client.run(token)