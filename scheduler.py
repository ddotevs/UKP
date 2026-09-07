"""
UKP Kickball Scheduler
Runs daily at 10am Eastern:
  Monday:    Post game event + announcement to GroupMe
  Tuesday:   Remind non-responders
  Wednesday: Remind non-responders again
  Thursday:  (Future: auto-build roster from schedule import)
"""
import sqlite3
import os
import time
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import groupme as gm
import requests as http_requests

TZ = ZoneInfo('America/New_York')
TARGET_HOUR = 10  # 10am Eastern

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


def get_gm_map():
    """Build player_name -> groupme_user_id map from both roster tables."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT player_name, groupme_user_id FROM main_roster WHERE groupme_user_id IS NOT NULL')
    gm_map = {row['player_name']: row['groupme_user_id'] for row in c.fetchall()}
    c.execute('SELECT player_name, groupme_user_id FROM substitutes WHERE groupme_user_id IS NOT NULL')
    gm_map.update({row['player_name']: row['groupme_user_id'] for row in c.fetchall()})
    conn.close()
    return gm_map


def ensure_next_game_exists():
    """Create the next game in the DB from the stored schedule if it doesn't exist yet."""
    schedule_json = get_setting('fall_26_schedule')
    if not schedule_json:
        return
    schedule = json.loads(schedule_json)
    today = datetime.now(TZ).strftime('%Y-%m-%d')
    conn = get_db()
    c = conn.cursor()
    for entry in schedule:
        game_date = entry['date']
        if game_date < today:
            continue
        # Check if this game already exists
        c.execute('SELECT id FROM games WHERE game_date = ?', (game_date,))
        if c.fetchone():
            continue
        # Create it
        c.execute('INSERT INTO games (game_date, team_name, opponent_name, game_time) VALUES (?, ?, ?, ?)',
                  (game_date, 'Unsolicited Kick Pics', entry['opponent'], entry['time']))
        conn.commit()
        print(f'Created game: {game_date} vs {entry["opponent"]} at {entry["time"]}')
        break  # Only create the next one
    conn.close()


def find_next_game():
    """Find the next upcoming game that hasn't been posted to GroupMe yet."""
    conn = get_db()
    c = conn.cursor()
    today = datetime.now(TZ).strftime('%Y-%m-%d')
    c.execute('''
        SELECT g.id, g.game_date, g.opponent_name, g.game_time 
        FROM games g
        WHERE g.game_date >= ?
        AND g.id NOT IN (SELECT game_id FROM groupme_events WHERE event_type = 'event')
        ORDER BY g.game_date ASC
        LIMIT 1
    ''', (today,))
    game = c.fetchone()
    conn.close()
    return game


def find_current_week_game():
    """Find the game for this week that has already been posted."""
    conn = get_db()
    c = conn.cursor()
    today = datetime.now(TZ)
    # Look for games within the next 7 days that have been posted
    week_end = (today + timedelta(days=7)).strftime('%Y-%m-%d')
    today_str = today.strftime('%Y-%m-%d')
    c.execute('''
        SELECT ge.game_id, ge.groupme_event_id, g.game_date, g.opponent_name
        FROM groupme_events ge
        JOIN games g ON g.id = ge.game_id
        WHERE ge.event_type = 'event'
        AND g.game_date >= ? AND g.game_date <= ?
        ORDER BY g.game_date ASC
        LIMIT 1
    ''', (today_str, week_end))
    row = c.fetchone()
    conn.close()
    return row


def already_reminded_today(game_id):
    """Check if we already sent a reminder for this game today."""
    conn = get_db()
    c = conn.cursor()
    today_str = datetime.now(TZ).strftime('%Y-%m-%d')
    c.execute('''
        SELECT id FROM groupme_events 
        WHERE game_id = ? AND event_type = 'reminder' AND date(posted_at) = ?
    ''', (game_id, today_str))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def get_main_roster():
    """Get main roster player names only (not subs)."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT player_name FROM main_roster ORDER BY player_name')
    names = [row['player_name'] for row in c.fetchall()]
    conn.close()
    return names


def get_players_in(game_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT player_name FROM game_player_status WHERE game_id = ? AND status = 'IN'", (game_id,))
    players = [row['player_name'] for row in c.fetchall()]
    conn.close()
    return players


def get_game_day_forecast(game_date, game_time=None):
    """Fetch weather forecast for game day. Returns a one-line string or None."""
    weather_key = get_setting('weather_api_key')
    if not weather_key:
        return None
    try:
        resp = http_requests.get('https://api.openweathermap.org/data/2.5/forecast', params={
            'q': 'Sandy Springs,GA,US',
            'appid': weather_key,
            'units': 'imperial',
        }, timeout=5)
        resp.raise_for_status()
        forecasts = resp.json().get('list', [])
        # Target game time (default 7pm)
        gd = datetime.strptime(game_date, '%Y-%m-%d')
        target_hour = 19
        if game_time and 'PM' in game_time.upper():
            h = int(game_time.split(':')[0])
            if h != 12:
                target_hour = h + 12
        target = gd.replace(hour=target_hour)
        best = None
        for fc in forecasts:
            fc_dt = datetime.strptime(fc['dt_txt'], '%Y-%m-%d %H:%M:%S')
            if best is None or abs((fc_dt - target).total_seconds()) < abs((best[0] - target).total_seconds()):
                best = (fc_dt, fc)
        if best:
            fc = best[1]
            temp = round(fc['main']['temp'])
            desc = fc['weather'][0]['description']
            pop = round(fc.get('pop', 0) * 100)
            return f'Forecast: {temp}F, {desc}, {pop}% chance of rain'
    except Exception as e:
        print(f'Weather fetch failed: {e}')
    return None


def monday_post():
    """Post game event + announcement for the next unposted game."""
    # Ensure the next game exists in the DB from the stored schedule
    ensure_next_game_exists()

    token = get_setting('groupme_access_token')
    group_id = get_setting('groupme_group_id')
    if not token or not group_id:
        print('GroupMe not configured, skipping')
        return

    game = find_next_game()
    if not game:
        print('No unposted upcoming games')
        return

    game_id = game['id']
    game_date = game['game_date']
    opponent = game['opponent_name']
    game_time = game['game_time']
    main_roster = get_main_roster()
    gm_map = get_gm_map()
    weather = get_game_day_forecast(game_date, game_time)

    results = {}
    gm_event_id = None

    # Create calendar event
    try:
        import re as _re
        hour, minute = 19, 0
        if game_time:
            m = _re.match(r'(\d+):(\d+)\s*(AM|PM)', game_time, _re.IGNORECASE)
            if m:
                hour = int(m.group(1))
                minute = int(m.group(2))
                if m.group(3).upper() == 'PM' and hour != 12:
                    hour += 12
        start_at = f'{game_date}T{hour:02d}:{minute:02d}:00-04:00'
        end_at = f'{game_date}T{hour+1:02d}:{minute:02d}:00-04:00'

        # Game number from schedule
        schedule_json = get_setting('fall_26_schedule')
        game_num = ''
        if schedule_json:
            schedule = json.loads(schedule_json)
            for i, entry in enumerate(schedule):
                if entry['date'] == game_date:
                    game_num = f'Game {i+1} - '
                    break

        event_name = f'{game_num}{opponent}' if opponent else 'Kickball Game'
        event_resp = gm.create_event(token, group_id, event_name, start_at=start_at, end_at=end_at)
        resp_data = event_resp.get('response', {})
        if isinstance(resp_data, dict):
            gm_event_id = resp_data.get('event', {}).get('event_id') or resp_data.get('event_id')
        results['event'] = 'created'
    except Exception as e:
        results['event'] = f'failed: {e}'

    # Post message with @mentions
    try:
        text, mentions = gm.build_game_message(game_date, opponent, main_roster, gm_map, game_time=game_time, weather_line=weather)
        gm.post_message(token, group_id, text, mentions)
        results['message'] = 'sent'
    except Exception as e:
        results['message'] = f'failed: {e}'

    # Track it
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO groupme_events (game_id, event_type, groupme_event_id, groupme_response) VALUES (?, ?, ?, ?)',
              (game_id, 'event', gm_event_id, json.dumps(results)))
    conn.commit()
    conn.close()

    print(f'Monday post for game {game_id} ({game_date}): {results}')


def reminder_post():
    """Tag members who haven't responded to the current week's event."""
    token = get_setting('groupme_access_token')
    group_id = get_setting('groupme_group_id')
    if not token or not group_id:
        print('GroupMe not configured, skipping')
        return

    game_row = find_current_week_game()
    if not game_row:
        print('No posted game this week to remind about')
        return

    game_id = game_row['game_id']
    gm_event_id = game_row['groupme_event_id']

    if already_reminded_today(game_id):
        print(f'Already reminded today for game {game_id}')
        return

    gm_map = get_gm_map()
    # Invert: groupme_user_id -> player_name (main roster only)
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT player_name, groupme_user_id FROM main_roster WHERE groupme_user_id IS NOT NULL')
    id_to_player = {row['groupme_user_id']: row['player_name'] for row in c.fetchall()}
    conn.close()

    # Get categorized responses
    responses = {'going': set(), 'not_going': set(), 'maybe': set()}
    if gm_event_id:
        responses = gm.get_event_respondents(token, group_id, gm_event_id)

    # Definitive = going or not_going. Tag everyone else (maybe + no response).
    definitive = responses['going'] | responses['not_going']
    non_responders = [name for uid, name in id_to_player.items() if uid not in definitive]

    if not non_responders:
        print('Everyone has responded!')
        return

    # Post reminder
    try:
        # Build event link
        event_url = None
        if gm_event_id:
            share_token = get_setting('groupme_share_token', '')
            if share_token:
                event_url = f'https://groupme.com/join_event/{group_id}/{gm_event_id}/{share_token}'
        text, mentions = gm.build_reminder_message(non_responders, gm_map, event_url=event_url)
        gm.post_message(token, group_id, text, mentions)
        print(f'Reminder sent, tagged {len(non_responders)} non-responders')
    except Exception as e:
        print(f'Reminder failed: {e}')

    # Track it
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO groupme_events (game_id, event_type, groupme_response) VALUES (?, ?, ?)',
              (game_id, 'reminder', json.dumps({'tagged': non_responders})))
    conn.commit()
    conn.close()


def seconds_until_next_10am():
    """Calculate seconds until the next 10am Eastern."""
    now = datetime.now(TZ)
    target = now.replace(hour=TARGET_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main():
    print('UKP Scheduler started')
    while True:
        wait = seconds_until_next_10am()
        print(f'Sleeping {wait/3600:.1f} hours until next 10am Eastern...')
        time.sleep(wait)

        now = datetime.now(TZ)
        day = now.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu
        print(f'Woke up: {now.strftime("%A %Y-%m-%d %H:%M %Z")}')

        try:
            if day == 0:  # Monday
                monday_post()
            elif day in (1, 2):  # Tuesday, Wednesday
                reminder_post()
            elif day == 3:  # Thursday
                print('Thursday: roster auto-build not yet implemented (waiting on schedule import)')
            else:
                print(f'{now.strftime("%A")}: no scheduled action')
        except Exception as e:
            print(f'Scheduler error: {e}')

        # Sleep 1 hour to avoid re-triggering at 10am
        time.sleep(3600)


if __name__ == '__main__':
    main()
