"""
UKP Kickball Auto-Lineup Generator

Generates a 7-inning lineup based on:
- Player position abilities (0=can't, 1=pinch, 2=comfortable, 3=primary)
- Kicking role/order (leadoff, table_setter, contact, power, middle, back, unknown)
- Fair sit-out rotation across innings
- Gender rules (min 4 females, max 11 on field, max 6 males)
- Previous week's lineup as template when available
"""
import sqlite3
import os
from collections import defaultdict

if os.path.exists("/app"):
    DB_NAME = "/app/data/kickball_roster.db"
else:
    DB_NAME = "data/kickball_roster.db"

FIELD_POSITIONS = [
    "Pitcher", "Catcher", "First Base", "Second Base", "Third Base",
    "Short Stop", "Left Field", "Left Center", "Center Field",
    "Right Center", "Right Field"
]

KICKING_ROLE_ORDER = {
    'leadoff': 0, 'table_setter': 1, 'contact': 2, 'power': 3,
    'middle': 4, 'back': 5, 'unknown': 6
}

MAX_ON_FIELD = 11
MIN_FEMALES = 4
MAX_MALES = 6


def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def load_player_data(game_id):
    """Load all player data needed for lineup generation."""
    conn = get_db()
    c = conn.cursor()

    # Get players marked IN for this game
    c.execute('''SELECT gps.player_name, 
                        COALESCE(mr.is_female, s.is_female, 0) as is_female
                 FROM game_player_status gps
                 LEFT JOIN main_roster mr ON mr.player_name = gps.player_name
                 LEFT JOIN substitutes s ON s.player_name = gps.player_name
                 WHERE gps.game_id = ? AND gps.status = 'IN'
              ''', (game_id,))
    players_in = []
    for row in c.fetchall():
        players_in.append({
            'name': row['player_name'],
            'is_female': bool(row['is_female']),
        })

    # Get position abilities
    c.execute('SELECT player_name, position, ability FROM player_positions')
    abilities = defaultdict(dict)
    for row in c.fetchall():
        abilities[row['player_name']][row['position']] = row['ability']

    # Get kicking profiles
    c.execute('SELECT player_name, kicking_role, kicking_sub_rank FROM player_profiles')
    profiles = {}
    for row in c.fetchall():
        profiles[row['player_name']] = {
            'role': row['kicking_role'] or 'unknown',
            'sub_rank': row['kicking_sub_rank'] or 99,
        }

    # Get previous game's lineup for template
    c.execute('''SELECT id FROM games WHERE id < ? ORDER BY id DESC LIMIT 1''', (game_id,))
    prev_game = c.fetchone()
    prev_lineup = {}
    if prev_game:
        c.execute('SELECT inning, position, player_name FROM lineup_positions WHERE game_id = ?', (prev_game['id'],))
        for row in c.fetchall():
            inn = row['inning']
            if inn not in prev_lineup:
                prev_lineup[inn] = {}
            prev_lineup[inn][row['player_name']] = row['position']

    # Get cumulative sit-out counts across all games this season
    c.execute('''SELECT player_name, COUNT(*) as cnt FROM lineup_positions 
                 WHERE position = 'Out' GROUP BY player_name''')
    sit_out_history = {row['player_name']: row['cnt'] for row in c.fetchall()}

    conn.close()

    return players_in, abilities, profiles, prev_lineup, sit_out_history


def build_kicking_order(players_in, profiles):
    """Sort players into kicking order based on role and sub_rank."""
    def sort_key(player):
        name = player['name']
        prof = profiles.get(name, {'role': 'unknown', 'sub_rank': 99})
        role_order = KICKING_ROLE_ORDER.get(prof['role'], 6)
        return (role_order, prof['sub_rank'], name)

    return sorted(players_in, key=sort_key)


def plan_sit_outs(players, num_innings=7):
    """Determine who sits out each inning for fair rotation.
    
    Returns dict of {inning: [list of player names sitting out]}
    """
    num_players = len(players)
    if num_players <= MAX_ON_FIELD:
        return {i: [] for i in range(1, num_innings + 1)}

    num_sitting = num_players - MAX_ON_FIELD
    females = [p for p in players if p['is_female']]
    males = [p for p in players if not p['is_female']]
    num_females = len(females)

    # Build rotation: spread sit-outs evenly across innings
    # Prefer sitting males if we're near the 4-female minimum
    sit_schedule = {i: [] for i in range(1, num_innings + 1)}

    # Create a pool of sit-out slots
    # Each player should sit roughly (num_sitting * num_innings) / num_players times
    total_sit_slots = num_sitting * num_innings

    # Sort players by cumulative sit-outs (fewest first = they sit next)
    # But females can only sit if enough females remain on field
    player_sit_counts = {p['name']: 0 for p in players}

    for inning in range(1, num_innings + 1):
        # Who can sit this inning?
        available_to_sit = []
        for p in players:
            # Check if sitting this female would violate min females rule
            if p['is_female']:
                females_on_field = num_females - sum(
                    1 for s in sit_schedule[inning] 
                    if any(pl['is_female'] and pl['name'] == s for pl in players)
                )
                if females_on_field <= MIN_FEMALES:
                    continue
            # Check max males on field (if male sits, one fewer male on field — always OK)
            available_to_sit.append(p)

        # Sort by sit count (ascending) then by name for stability
        available_to_sit.sort(key=lambda p: (player_sit_counts[p['name']], p['name']))

        for i in range(min(num_sitting, len(available_to_sit))):
            p = available_to_sit[i]
            sit_schedule[inning].append(p['name'])
            player_sit_counts[p['name']] += 1

    return sit_schedule


def assign_positions(players_on_field, abilities, prev_inning=None):
    """Assign field positions to players for one inning.
    
    Returns dict of {player_name: position}
    """
    assignments = {}
    unassigned = list(players_on_field)
    available_positions = list(FIELD_POSITIONS[:len(players_on_field)])

    # Phase 1: Assign players with primary (ability=3) positions
    for player in list(unassigned):
        name = player['name']
        player_abilities = abilities.get(name, {})
        primary = [pos for pos, ab in player_abilities.items() if ab == 3 and pos in available_positions]
        if primary:
            pos = primary[0]
            if prev_inning and prev_inning.get(name) in primary:
                pos = prev_inning[name]
            assignments[name] = pos
            available_positions.remove(pos)
            unassigned.remove(player)

    # Phase 2: Assign comfortable (ability=2) positions
    for player in list(unassigned):
        name = player['name']
        player_abilities = abilities.get(name, {})
        comfortable = [pos for pos, ab in player_abilities.items() if ab >= 2 and pos in available_positions]
        if comfortable:
            pos = comfortable[0]
            if prev_inning and prev_inning.get(name) in comfortable:
                pos = prev_inning[name]
            if pos in available_positions:
                assignments[name] = pos
                available_positions.remove(pos)
                unassigned.remove(player)

    # Phase 3: Assign pinch-able (ability=1) positions
    for player in list(unassigned):
        name = player['name']
        player_abilities = abilities.get(name, {})
        pinch = [pos for pos, ab in player_abilities.items() if ab >= 1 and pos in available_positions]
        if pinch:
            assignments[name] = pinch[0]
            available_positions.remove(pinch[0])
            unassigned.remove(player)

    # Phase 4: Fill remaining (no ability data = assign whatever's left, but respect "never")
    for player in list(unassigned):
        name = player['name']
        player_abilities = abilities.get(name, {})
        never_positions = {pos for pos, ab in player_abilities.items() if ab == -1}
        allowed = [pos for pos in available_positions if pos not in never_positions]
        if allowed:
            assignments[name] = allowed[0]
            available_positions.remove(allowed[0])
            unassigned.remove(player)
        elif available_positions:
            # Last resort: even if marked never, fill the slot
            assignments[name] = available_positions.pop(0)
            unassigned.remove(player)

    return assignments


def generate_lineup(game_id):
    """Generate a complete 7-inning lineup for a game.
    
    Returns dict of {inning: {player_name: position}} and kicking_order list.
    """
    players_in, abilities, profiles, prev_lineup, sit_history = load_player_data(game_id)

    if not players_in:
        return {}, []

    # Build kicking order
    kicking_order = build_kicking_order(players_in, profiles)

    # Plan sit-outs
    sit_schedule = plan_sit_outs(kicking_order)

    # Generate lineup for each inning
    lineup = {}
    prev_inning = prev_lineup.get(1, {})

    for inning in range(1, 8):
        sitting = set(sit_schedule.get(inning, []))
        on_field = [p for p in kicking_order if p['name'] not in sitting]

        # Assign positions
        assignments = assign_positions(on_field, abilities, prev_inning)

        # Mark sitting players as Out
        inning_lineup = {}
        for p in kicking_order:
            if p['name'] in sitting:
                inning_lineup[p['name']] = 'Out'
            else:
                inning_lineup[p['name']] = assignments.get(p['name'], '')

        lineup[inning] = inning_lineup
        prev_inning = assignments  # Use this inning as reference for next

    return lineup, [p['name'] for p in kicking_order]


def save_generated_lineup(game_id, lineup, kicking_order):
    """Save a generated lineup to the database."""
    conn = get_db()
    c = conn.cursor()

    # Clear existing lineup
    c.execute('DELETE FROM lineup_positions WHERE game_id = ?', (game_id,))

    # Save positions
    for inning, assignments in lineup.items():
        for player_name, position in assignments.items():
            if position:
                c.execute('INSERT INTO lineup_positions (game_id, inning, position, player_name) VALUES (?, ?, ?, ?)',
                          (game_id, inning, position, player_name))

    # Update kicking order
    for idx, name in enumerate(kicking_order):
        c.execute('UPDATE game_player_status SET kicking_order = ? WHERE game_id = ? AND player_name = ?',
                  (idx, game_id, name))

    conn.commit()
    conn.close()
