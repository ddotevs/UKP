"""
UKP Kickball Chatbot - GroupMe bot auto-responses
Parses incoming messages and generates responses for the bot.
"""
import random
import re
import sqlite3
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import groupme as gm
import requests as http_requests

TZ = ZoneInfo('America/New_York')

if os.path.exists("/app"):
    DB_NAME = "/app/data/kickball_roster.db"
else:
    DB_NAME = "data/kickball_roster.db"


def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting(key, default=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row['value'] if row else default


# ========================================
# Command Registry
# ========================================
COMMANDS = {}


def command(*triggers):
    """Decorator to register a command with one or more trigger phrases."""
    def decorator(func):
        for t in triggers:
            COMMANDS[t.lower()] = func
        return func
    return decorator


def match_command(text):
    """Find the best matching command for the given text."""
    text_lower = text.lower().strip()
    # Exact match first
    if text_lower in COMMANDS:
        return COMMANDS[text_lower], text_lower
    # Prefix/contains match
    for trigger, func in sorted(COMMANDS.items(), key=lambda x: -len(x[0])):
        if trigger in text_lower:
            return func, trigger
    return None, None


# ========================================
# Game Info Commands
# ========================================
def get_next_game():
    conn = get_db()
    c = conn.cursor()
    today = datetime.now(TZ).strftime('%Y-%m-%d')
    c.execute('SELECT id, game_date, team_name, opponent_name, game_time FROM games WHERE game_date >= ? ORDER BY game_date ASC LIMIT 1', (today,))
    game = c.fetchone()
    conn.close()
    return game


@command('when do we play', 'when is the game', 'what time is the game', 'game time', 'next game')
def cmd_game_time(text):
    game = get_next_game()
    if not game:
        return "No upcoming games on the schedule."
    date = datetime.strptime(game['game_date'], '%Y-%m-%d')
    day_str = date.strftime('%A, %B %-d')
    game_time = game['game_time'] or get_setting('default_game_time', '7:00 PM')
    return f"Next game: {day_str} at {game_time}"


@command('who are we playing', 'who do we play', 'opponent', 'matchup')
def cmd_opponent(text):
    game = get_next_game()
    if not game:
        return "No upcoming games on the schedule."
    opp = game['opponent_name'] or 'TBD'
    date = datetime.strptime(game['game_date'], '%Y-%m-%d')
    return f"We're playing {opp} on {date.strftime('%A, %B %-d')}"


@command("who's in", "whos in", "who is in", "who is playing", "who's playing", "whos playing", "roster")
def cmd_whos_in(text):
    game = get_next_game()
    if not game:
        return "No upcoming games on the schedule."
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT player_name FROM game_player_status WHERE game_id = ? AND status = 'IN' ORDER BY kicking_order, player_name", (game['id'],))
    players = [row['player_name'] for row in c.fetchall()]
    conn.close()
    if not players:
        return "Nobody has been marked IN yet for this game."
    return f"Playing this week ({len(players)}):\n" + '\n'.join(f"  {i+1}. {p}" for i, p in enumerate(players))


@command('countdown', 'how many days', 'days until')
def cmd_countdown(text):
    game = get_next_game()
    if not game:
        return "No upcoming games on the schedule."
    game_date = datetime.strptime(game['game_date'], '%Y-%m-%d').replace(tzinfo=TZ)
    now = datetime.now(TZ)
    delta = (game_date - now).days
    if delta == 0:
        return "GAME DAY! Let's gooooo!"
    elif delta == 1:
        return "Tomorrow is game day! Get your kicks ready!"
    else:
        return f"{delta} days until game day ({game_date.strftime('%A, %B %-d')})"


@command("who hasn't responded", "who hasnt responded", 'no response', 'non responders')
def cmd_non_responders(text):
    token = get_setting('groupme_access_token')
    group_id = get_setting('groupme_group_id')
    if not token or not group_id:
        return "GroupMe not configured."
    game = get_next_game()
    if not game:
        return "No upcoming games."
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT groupme_event_id FROM groupme_events WHERE game_id = ? AND event_type = 'event' LIMIT 1", (game['id'],))
    row = c.fetchone()
    if not row or not row['groupme_event_id']:
        conn.close()
        return "No event posted for this game yet."
    event_id = row['groupme_event_id']
    # Get all players with GroupMe IDs
    c.execute('SELECT player_name, groupme_user_id FROM main_roster WHERE groupme_user_id IS NOT NULL')
    gm_map = {row['groupme_user_id']: row['player_name'] for row in c.fetchall()}
    c.execute('SELECT player_name, groupme_user_id FROM substitutes WHERE groupme_user_id IS NOT NULL')
    gm_map.update({row['groupme_user_id']: row['player_name'] for row in c.fetchall()})
    conn.close()
    responded = gm.get_event_respondents(token, group_id, event_id)
    non_resp = [name for uid, name in gm_map.items() if uid not in responded]
    if not non_resp:
        return "Everyone has responded! We're locked in."
    return f"Still waiting on ({len(non_resp)}):\n" + '\n'.join(f"  - {p}" for p in sorted(non_resp))


# ========================================
# Sub Needed
# ========================================
@command('sub needed', 'need a sub', 'need sub', 'sub request')
def cmd_sub_needed(text):
    game = get_next_game()
    if not game:
        return "No upcoming games."
    sub_group_id = get_setting('groupme_sub_group_id')
    bot_id = get_setting('groupme_bot_id')
    if not sub_group_id:
        return "Sub group not configured. Set 'groupme_sub_group_id' in settings."
    date = datetime.strptime(game['game_date'], '%Y-%m-%d')
    game_time = get_setting('default_game_time', '7:00 PM')
    park = get_setting('park_name', 'the field')
    msg = f"SUB NEEDED!\n\nWe need a sub for {date.strftime('%A, %B %-d')} at {game_time} @ {park}.\n\nReply here or DM if you can make it!"
    # Post to the sub group using the access token (bot can't post to other groups)
    token = get_setting('groupme_access_token')
    if token:
        try:
            gm.post_message(token, sub_group_id, msg)
            return "Sub request posted to the subs group!"
        except Exception as e:
            return f"Failed to post to subs group: {e}"
    return "Access token not configured."


# ========================================
# Location / Directions / Weather
# ========================================
@command('where do we play', 'directions', 'where is the game', 'park', 'field', 'address')
def cmd_directions(text):
    park_name = get_setting('park_name')
    park_address = get_setting('park_address')
    if not park_name and not park_address:
        return "Park location not configured yet."
    parts = []
    if park_name:
        parts.append(park_name)
    if park_address:
        parts.append(park_address)
        maps_query = park_address.replace(' ', '+')
        parts.append(f"https://maps.google.com/?q={maps_query}")
    return '\n'.join(parts)


@command('weather', 'rain', 'forecast', 'is it going to rain')
def cmd_weather(text):
    weather_key = get_setting('weather_api_key')
    if not weather_key:
        return "Weather API not configured yet."

    # Get next game date to show game-day forecast
    game = get_next_game()
    game_date = None
    if game:
        game_date = datetime.strptime(game['game_date'], '%Y-%m-%d')

    try:
        # Current weather
        resp = http_requests.get('https://api.openweathermap.org/data/2.5/weather', params={
            'q': 'Sandy Springs,GA,US',
            'appid': weather_key,
            'units': 'imperial',
        }, timeout=5)
        resp.raise_for_status()
        current = resp.json()
        temp = round(current['main']['temp'])
        desc = current['weather'][0]['description']
        humidity = current['main']['humidity']
        result = f"Right now in Sandy Springs: {temp}°F, {desc}, {humidity}% humidity"

        # If game is within 5 days, get forecast for game day
        if game_date:
            days_out = (game_date - datetime.now()).days
            if 0 <= days_out <= 5:
                fc_resp = http_requests.get('https://api.openweathermap.org/data/2.5/forecast', params={
                    'q': 'Sandy Springs,GA,US',
                    'appid': weather_key,
                    'units': 'imperial',
                }, timeout=5)
                fc_resp.raise_for_status()
                forecasts = fc_resp.json().get('list', [])
                # Find forecast closest to game time (7pm on game day)
                game_target = game_date.replace(hour=19)
                best = None
                for fc in forecasts:
                    fc_dt = datetime.strptime(fc['dt_txt'], '%Y-%m-%d %H:%M:%S')
                    if best is None or abs((fc_dt - game_target).total_seconds()) < abs((best[0] - game_target).total_seconds()):
                        best = (fc_dt, fc)
                if best:
                    fc_data = best[1]
                    fc_temp = round(fc_data['main']['temp'])
                    fc_desc = fc_data['weather'][0]['description']
                    fc_pop = round(fc_data.get('pop', 0) * 100)
                    result += f"\n\nGame day forecast ({game_date.strftime('%A')} ~7pm): {fc_temp}°F, {fc_desc}, {fc_pop}% chance of rain"
        return result
    except Exception as e:
        return f"Couldn't fetch weather: {e}"


# ========================================
# Fun Commands
# ========================================
HYPE_MESSAGES = [
    "LET'S GOOOOO! Time to kick some balls!",
    "We didn't come to play... wait, yes we did. AND WE CAME TO WIN.",
    "Kickball is 90% mental. The other half is physical.",
    "They don't want this smoke. WE ARE THAT TEAM.",
    "Cleats laced. Vibes immaculate. Victory inevitable.",
    "If kickball was easy, they'd call it soccer.",
    "Remember: it's not about winning or losing. JK, it's about winning.",
    "The ball is round. The field is green. The beer is cold. Let's ride.",
    "We're not here for participation trophies. We're here for GLORY.",
    "Somewhere out there, the other team is sleeping. We are NOT sleeping.",
    "Fun fact: undefeated teams have a 100% win rate. Let's keep that energy.",
    "Kick. Ball. Win. Repeat.",
    "The only thing getting kicked harder than that ball is their confidence.",
]

EXCUSES = [
    "My dog ate my cleats.",
    "I have a very important meeting with my couch.",
    "My horoscope said to avoid red rubber balls today.",
    "I'm on a strict 'no exercise' diet.",
    "I pulled a muscle reaching for the remote.",
    "My car only drives to bars, not parks.",
    "I have to wash my hair. All of it. Individually.",
    "My therapist said I should avoid competitive situations... just kidding, she said I need to touch grass.",
    "I'm allergic to losing, and I don't trust us today.",
    "I threw out my back carrying this team last week.",
    "I'm protesting until we get better snacks.",
    "Mercury is in retrograde and I can't kick under those conditions.",
    "My Uber only goes to brunch.",
    "I left my legs at home.",
]

DAD_JOKES = [
    "Why did the kickball player bring a ladder? To reach the high kicks!",
    "What's a kickball player's favorite type of music? Sole music.",
    "I used to hate kickball... but then it grew on me. Like a bruise.",
    "Why don't kickball players ever get lost? They always follow the base path.",
    "What did the kickball say to the foot? 'You're my sole mate.'",
    "Why was the kickball team so good at math? They knew all the angles.",
    "I told my wife I was going to kickball. She said 'Have a ball!' I said 'That's the plan.'",
    "What's the difference between kickball and dating? In kickball, it's okay to kick and run.",
    "Why did the kickball cross the road? It was kicked there.",
    "I'm reading a book about kickball. It's got a great kick-start.",
]


@command('hype', 'hype me up', "let's go", 'lets go', 'pump me up', 'motivate me', 'lfg')
def cmd_hype(text):
    return random.choice(HYPE_MESSAGES)


@command('excuse', 'excuses', 'give me an excuse', "i can't make it", "cant make it")
def cmd_excuse(text):
    return f"Try this one:\n\n\"{random.choice(EXCUSES)}\""


@command('dad joke', 'joke', 'tell me a joke', 'make me laugh')
def cmd_dad_joke(text):
    return random.choice(DAD_JOKES)


@command('flip a coin', 'coin flip', 'heads or tails')
def cmd_coin_flip(text):
    result = random.choice(['Heads', 'Tails'])
    return f"🪙 {result}!"


@command('pick a number', 'random number')
def cmd_random_number(text):
    # Try to parse a range from the message
    match = re.search(r'(\d+)\s*(?:to|-)\s*(\d+)', text)
    if match:
        lo, hi = int(match.group(1)), int(match.group(2))
        return f"🎲 {random.randint(lo, hi)}"
    return f"🎲 {random.randint(1, 100)}"


@command('rule', 'rules', 'rule check', 'is that legal', 'can you')
def cmd_rules(text):
    rules = get_setting('kickball_rules')
    if not rules:
        return "Rules haven't been loaded yet. Ask your captain to add them!"
    # Try to find a relevant section based on keywords
    text_lower = text.lower()
    keywords = [w for w in text_lower.split() if w not in ('rule', 'rules', 'check', 'what', 'is', 'the', 'a', 'an', 'can', 'you', 'about')]
    if keywords:
        lines = rules.split('\n')
        relevant = []
        for i, line in enumerate(lines):
            if any(kw in line.lower() for kw in keywords):
                # Grab this line and a few around it for context
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                relevant.extend(lines[start:end])
                relevant.append('')
        if relevant:
            result = '\n'.join(relevant[:20])  # cap at 20 lines
            return f"Here's what I found:\n\n{result}"
    return "I have the rules but couldn't find a specific match. Try being more specific (e.g., 'rule check foul ball')"


# ========================================
# Help / Command List
# ========================================
HELP_TEXT = """UKP Bot Commands:

GAME INFO
  "next game" - When and where we play
  "who are we playing" - This week's opponent
  "who's in" - Players marked IN
  "countdown" - Days until game day
  "who hasn't responded" - Event non-responders

LOCATION
  "directions" - Park name, address, Google Maps link
  "weather" - Game day forecast

TEAM
  "sub needed" - Post sub request to the subs group
  "standings" - League standings (coming soon)

FUN
  "hype me up" - Get pumped
  "excuse" - Auto-excuse generator
  "dad joke" - You're welcome
  "flip a coin" - Heads or tails
  "pick a number 1 to 10" - Random number
  "rule check [topic]" - Look up a kickball rule

  "help" - This list"""


@command('help', 'commands', 'what can you do', 'menu')
def cmd_help(text):
    return HELP_TEXT


# ========================================
# Main Handler
# ========================================
def handle_message(data):
    """Process an incoming GroupMe callback message.
    Returns a response string, or None to stay silent.
    """
    # Ignore messages from bots (avoid infinite loops)
    if data.get('sender_type') == 'bot':
        return None

    text = data.get('text', '')
    if not text:
        return None

    # Check if the bot was mentioned by name
    bot_name = get_setting('groupme_bot_name', 'UKP Bot')
    mentioned = bot_name.lower() in text.lower()

    # Strip the bot name from the text for command matching
    clean_text = re.sub(re.escape(bot_name), '', text, flags=re.IGNORECASE).strip()
    # Also strip leading @, punctuation
    clean_text = re.sub(r'^[@,\s]+', '', clean_text).strip()

    if not mentioned and not clean_text.startswith('!'):
        return None

    # Strip leading ! for command prefix style
    if clean_text.startswith('!'):
        clean_text = clean_text[1:].strip()

    func, trigger = match_command(clean_text)
    if func:
        try:
            return func(clean_text)
        except Exception as e:
            return f"Oops, something broke: {e}"

    return f"I didn't understand that. Say \"help\" to see what I can do!"
