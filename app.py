import streamlit as st
import sqlite3
import hashlib
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Optional
import json

# Page configuration
st.set_page_config(
    page_title="UKP Kickball Roster",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database setup
DB_NAME = "kickball_roster.db"

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Users table for authentication
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Main roster table
    c.execute('''
        CREATE TABLE IF NOT EXISTS main_roster (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Substitute players table
    c.execute('''
        CREATE TABLE IF NOT EXISTS substitutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Games table
    c.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_date DATE NOT NULL,
            team_name TEXT NOT NULL,
            opponent_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Player status for games (IN/OUT)
    c.execute('''
        CREATE TABLE IF NOT EXISTS game_player_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('IN', 'OUT')),
            is_substitute BOOLEAN DEFAULT 0,
            FOREIGN KEY (game_id) REFERENCES games(id),
            UNIQUE(game_id, player_name)
        )
    ''')
    
    # Lineup positions for each inning
    c.execute('''
        CREATE TABLE IF NOT EXISTS lineup_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            inning INTEGER NOT NULL CHECK(inning BETWEEN 1 AND 7),
            position TEXT NOT NULL,
            player_name TEXT,
            FOREIGN KEY (game_id) REFERENCES games(id),
            UNIQUE(game_id, inning, position)
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    """Hash a password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    return hash_password(password) == password_hash

def is_authenticated() -> bool:
    """Check if user is authenticated"""
    return st.session_state.get('authenticated', False)

def login(username: str, password: str) -> bool:
    """Authenticate user"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Check if user exists
    c.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
    result = c.fetchone()
    conn.close()
    
    if result and verify_password(password, result[0]):
        st.session_state.authenticated = True
        st.session_state.username = username
        return True
    return False

def create_user(username: str, password: str) -> bool:
    """Create a new user (only if no users exist)"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Check if any users exist
    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] > 0:
        conn.close()
        return False
    
    # Create first user
    try:
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                 (username, hash_password(password)))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def get_next_thursday() -> datetime:
    """Get the next Thursday from today"""
    today = datetime.now()
    days_until_thursday = (3 - today.weekday()) % 7
    if days_until_thursday == 0:
        days_until_thursday = 7  # If today is Thursday, get next Thursday
    return today + timedelta(days=days_until_thursday)

# Initialize database
init_db()

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'current_game_id' not in st.session_state:
    st.session_state.current_game_id = None

# Authentication sidebar
with st.sidebar:
    st.title("⚾ UKP Kickball Roster")
    
    if not is_authenticated():
        st.subheader("Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                if login(username, password):
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        
        st.divider()
        st.subheader("Create First User")
        with st.form("create_user_form"):
            new_username = st.text_input("New Username", key="new_user")
            new_password = st.text_input("New Password", type="password", key="new_pass")
            create = st.form_submit_button("Create User")
            
            if create:
                if create_user(new_username, new_password):
                    st.success("User created! Please login.")
                else:
                    st.error("Users already exist or username taken.")
    else:
        st.success(f"Logged in as {st.session_state.get('username', 'User')}")
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.session_state.username = None
            st.rerun()

# Main app content
# Main navigation
st.title("⚾ UKP Kickball Roster Manager")

# Navigation tabs - different tabs for authenticated vs public
if is_authenticated():
    tabs = st.tabs(["Game Lineup", "Main Roster", "Substitutes", "View Lineup"])
else:
    st.info("👀 **View Mode**: You are viewing in read-only mode. Please login to edit.")
    tabs = st.tabs(["View Lineup"])

# Positions definition
POSITIONS = [
    "Pitcher", "Catcher", "First Base", "Second Base", "Third Base",
    "Short Stop", "Left Field", "Left Center", "Center Field",
    "Right Center", "Right Field", "Out"
]

# ========== GAME LINEUP TAB ==========
if is_authenticated() and len(tabs) > 0:
    with tabs[0]:
        st.header("Game Lineup Setup")
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Get or create current game
        next_thursday = get_next_thursday().date()
        
        # Check for existing game for next Thursday
        c.execute('SELECT id, game_date, team_name, opponent_name FROM games WHERE game_date = ?',
                 (next_thursday,))
        game = c.fetchone()
        
        if game:
            game_id, game_date, team_name, opponent_name = game
            st.session_state.current_game_id = game_id
        else:
            # Create new game
            c.execute('INSERT INTO games (game_date, team_name, opponent_name) VALUES (?, ?, ?)',
                     (next_thursday, "Unsolicited Kick Pics", ""))
            game_id = c.lastrowid
            conn.commit()
            st.session_state.current_game_id = game_id
            game_date = next_thursday
            team_name = "Unsolicited Kick Pics"
            opponent_name = ""
        
        # Game details
        col1, col2, col3 = st.columns(3)
        with col1:
            new_date = st.date_input("Game Date", value=game_date)
        with col2:
            new_team_name = st.text_input("Team Name", value=team_name)
        with col3:
            new_opponent = st.text_input("Opponent Name", value=opponent_name or "")
        
        if new_date != game_date or new_team_name != team_name or new_opponent != opponent_name:
            c.execute('''UPDATE games SET game_date = ?, team_name = ?, opponent_name = ?, 
                        updated_at = CURRENT_TIMESTAMP WHERE id = ?''',
                     (new_date, new_team_name, new_opponent, game_id))
            conn.commit()
        
        st.divider()
        
        # Get main roster and substitutes
        c.execute('SELECT player_name FROM main_roster ORDER BY player_name')
        main_roster = [row[0] for row in c.fetchall()]
        
        c.execute('SELECT player_name FROM substitutes ORDER BY player_name')
        substitutes = [row[0] for row in c.fetchall()]
        
        # Get current game player statuses
        c.execute('SELECT player_name, status, is_substitute FROM game_player_status WHERE game_id = ?',
                 (game_id,))
        statuses = {row[0]: {'status': row[1], 'is_sub': row[2]} for row in c.fetchall()}
        
        # Player status management
        st.subheader("Player Status")
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Main Roster")
            in_players = []
            out_players = []
            
            for player in main_roster:
                current_status = statuses.get(player, {}).get('status', 'IN')
                if current_status == 'IN':
                    in_players.append(player)
                else:
                    out_players.append(player)
            
            # IN column
            st.markdown("**IN (Available)**")
            for player in in_players:
                if st.button(f"➡️ {player}", key=f"main_in_{player}", use_container_width=True):
                    c.execute('''INSERT OR REPLACE INTO game_player_status 
                               (game_id, player_name, status, is_substitute) 
                               VALUES (?, ?, 'OUT', 0)''', (game_id, player))
                    conn.commit()
                    st.rerun()
            
            # OUT column
            st.markdown("**OUT (Not Available)**")
            for player in out_players:
                if st.button(f"⬅️ {player}", key=f"main_out_{player}", use_container_width=True):
                    c.execute('''INSERT OR REPLACE INTO game_player_status 
                               (game_id, player_name, status, is_substitute) 
                               VALUES (?, ?, 'IN', 0)''', (game_id, player))
                    conn.commit()
                    st.rerun()
        
        with col2:
            st.markdown("### Substitutes")
            if substitutes:
                for sub in substitutes:
                    sub_status = statuses.get(sub, {}).get('status', None)
                    if sub_status is None:
                        if st.button(f"➕ Add {sub} to Game", key=f"add_sub_{sub}", use_container_width=True):
                            c.execute('''INSERT INTO game_player_status 
                                       (game_id, player_name, status, is_substitute) 
                                       VALUES (?, ?, 'IN', 1)''', (game_id, sub))
                            conn.commit()
                            st.rerun()
                    elif sub_status == 'IN':
                        if st.button(f"➡️ {sub}", key=f"sub_in_{sub}", use_container_width=True):
                            c.execute('''UPDATE game_player_status SET status = 'OUT' 
                                       WHERE game_id = ? AND player_name = ?''', (game_id, sub))
                            conn.commit()
                            st.rerun()
                    else:
                        if st.button(f"⬅️ {sub}", key=f"sub_out_{sub}", use_container_width=True):
                            c.execute('''UPDATE game_player_status SET status = 'IN' 
                                       WHERE game_id = ? AND player_name = ?''', (game_id, sub))
                            conn.commit()
                            st.rerun()
            else:
                st.info("No substitutes available. Add them in the Substitutes tab.")
        
        st.divider()
        
        # Get available players (IN status)
        c.execute('''SELECT player_name FROM game_player_status 
                    WHERE game_id = ? AND status = 'IN' ORDER BY player_name''', (game_id,))
        available_players = [row[0] for row in c.fetchall()]
        
        # Get current lineup
        c.execute('''SELECT inning, position, player_name FROM lineup_positions 
                    WHERE game_id = ? ORDER BY inning, position''', (game_id,))
        current_lineup = {}
        for row in c.fetchall():
            inning, position, player = row
            if inning not in current_lineup:
                current_lineup[inning] = {}
            current_lineup[inning][position] = player
        
        # Track which players are in lineup
        players_in_lineup = set()
        for inning_data in current_lineup.values():
            players_in_lineup.update(inning_data.values())
        
        # Highlight players not in lineup
        unused_players = [p for p in available_players if p not in players_in_lineup]
        
        if unused_players:
            st.warning(f"⚠️ Players not yet in lineup: {', '.join(unused_players)}")
        
        # Lineup interface
        st.subheader("Lineup by Inning")
        
        # Statistics
        col1, col2 = st.columns(2)
        with col1:
            # Count innings with unused positions
            incomplete_innings = 0
            for inning in range(1, 8):
                if inning not in current_lineup:
                    incomplete_innings += 1
                else:
                    positions_filled = len([p for p in current_lineup[inning].values() if p])
                    if positions_filled < len(POSITIONS):
                        incomplete_innings += 1
            
            st.metric("Innings with Unused Positions", incomplete_innings)
        
        with col2:
            # Count players sitting out
            c.execute('''SELECT player_name, COUNT(*) as sit_count 
                        FROM lineup_positions 
                        WHERE game_id = ? AND position = 'Out' 
                        GROUP BY player_name''', (game_id,))
            sit_counts = {row[0]: row[1] for row in c.fetchall()}
            total_sits = sum(sit_counts.values())
            st.metric("Total Player Sit-Outs", total_sits)
        
        # Create lineup grid
        for inning in range(1, 8):
            with st.expander(f"Inning {inning}", expanded=(inning == 1)):
                cols = st.columns(4)
                
                for idx, position in enumerate(POSITIONS):
                    col_idx = idx % 4
                    
                    with cols[col_idx]:
                        current_player = current_lineup.get(inning, {}).get(position, "")
                        
                        # Create selectbox for each position
                        options = [""] + available_players
                        if current_player and current_player not in available_players:
                            options.append(current_player)
                        
                        # Style "Out" position differently
                        label = position
                        if position == "Out":
                            label = f"🔴 {position}"  # Red indicator for Out position
                        
                        selected = st.selectbox(
                            label,
                            options=options,
                            index=options.index(current_player) if current_player in options else 0,
                            key=f"inning_{inning}_pos_{position}"
                        )
                        
                        # Update database
                        if selected != current_player:
                            if selected:
                                c.execute('''INSERT OR REPLACE INTO lineup_positions 
                                           (game_id, inning, position, player_name) 
                                           VALUES (?, ?, ?, ?)''',
                                         (game_id, inning, position, selected))
                            else:
                                c.execute('''DELETE FROM lineup_positions 
                                           WHERE game_id = ? AND inning = ? AND position = ?''',
                                         (game_id, inning, position))
                            conn.commit()
        
        conn.close()
        st.success("Lineup saved!")

# ========== MAIN ROSTER TAB ==========
if is_authenticated() and len(tabs) > 1:
    with tabs[1]:
        st.header("Main Roster Management")
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Add new player
        with st.form("add_player_form"):
            new_player = st.text_input("Add New Player to Main Roster")
            submit = st.form_submit_button("Add Player")
            
            if submit and new_player:
                try:
                    c.execute('INSERT INTO main_roster (player_name) VALUES (?)', (new_player,))
                    conn.commit()
                    st.success(f"Added {new_player} to main roster!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"{new_player} is already in the roster.")
        
        # Display current roster
        c.execute('SELECT player_name FROM main_roster ORDER BY player_name')
        roster = [row[0] for row in c.fetchall()]
        
        if roster:
            st.subheader("Current Roster")
            for player in roster:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(player)
                with col2:
                    if st.button("Delete", key=f"del_{player}"):
                        c.execute('DELETE FROM main_roster WHERE player_name = ?', (player,))
                        conn.commit()
                        st.rerun()
        else:
            st.info("No players in main roster yet.")
        
        conn.close()

# ========== SUBSTITUTES TAB ==========
if is_authenticated() and len(tabs) > 2:
    with tabs[2]:
        st.header("Substitute Players Management")
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        # Add new substitute
        with st.form("add_substitute_form"):
            new_sub = st.text_input("Add New Substitute Player")
            submit = st.form_submit_button("Add Substitute")
            
            if submit and new_sub:
                try:
                    c.execute('INSERT INTO substitutes (player_name) VALUES (?)', (new_sub,))
                    conn.commit()
                    st.success(f"Added {new_sub} as substitute!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"{new_sub} is already in substitutes.")
        
        # Display current substitutes
        c.execute('SELECT player_name FROM substitutes ORDER BY player_name')
        subs = [row[0] for row in c.fetchall()]
        
        if subs:
            st.subheader("Current Substitutes")
            for sub in subs:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(sub)
                with col2:
                    if st.button("Delete", key=f"del_sub_{sub}"):
                        c.execute('DELETE FROM substitutes WHERE player_name = ?', (sub,))
                        conn.commit()
                        st.rerun()
        else:
            st.info("No substitutes added yet.")
        
        conn.close()

# ========== VIEW LINEUP TAB ==========
# View lineup is accessible to both authenticated and public users
view_tab_idx = 3 if is_authenticated() else 0
with tabs[view_tab_idx]:
    st.header("View Lineup")
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Select game to view
    c.execute('SELECT id, game_date, team_name, opponent_name FROM games ORDER BY game_date DESC')
    games = c.fetchall()
    
    if games:
        game_options = [f"{row[1]} - {row[2]} vs {row[3] or 'TBD'}" for row in games]
        selected_game_idx = st.selectbox("Select Game", range(len(game_options)), 
                                         format_func=lambda x: game_options[x])
        selected_game_id = games[selected_game_idx][0]
        
        # Get game details
        game_date, team_name, opponent_name = games[selected_game_idx][1:]
        st.markdown(f"### {team_name} vs {opponent_name or 'TBD'}")
        st.markdown(f"**Date:** {game_date}")
        
        # Get lineup
        c.execute('''SELECT inning, position, player_name FROM lineup_positions 
                    WHERE game_id = ? ORDER BY inning, position''', (selected_game_id,))
        lineup_data = c.fetchall()
        
        if lineup_data:
            # Organize by inning
            lineup_by_inning = {}
            for inning, position, player in lineup_data:
                if inning not in lineup_by_inning:
                    lineup_by_inning[inning] = {}
                lineup_by_inning[inning][position] = player
            
            # Display lineup table with styling
            display_data = []
            for inning in range(1, 8):
                row = {"Inning": inning}
                for position in POSITIONS:
                    player = lineup_by_inning.get(inning, {}).get(position, "")
                    # Style "Out" position differently
                    if position == "Out" and player:
                        row[position] = f"🔴 {player}"
                    else:
                        row[position] = player if player else "-"
                display_data.append(row)
            
            df = pd.DataFrame(display_data)
            
            # Apply styling to highlight "Out" column
            def highlight_out_column(val):
                if isinstance(val, str) and val.startswith("🔴"):
                    return 'background-color: #ffcccc'
                return ''
            
            styled_df = df.style.applymap(highlight_out_column, subset=[col for col in df.columns if col == "Out"])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
            # Statistics
            st.subheader("Statistics")
            col1, col2 = st.columns(2)
            
            with col1:
                # Player sit-out counts
                c.execute('''SELECT player_name, COUNT(*) as sit_count 
                            FROM lineup_positions 
                            WHERE game_id = ? AND position = 'Out' 
                            GROUP BY player_name 
                            ORDER BY sit_count DESC''', (selected_game_id,))
                sit_data = c.fetchall()
                if sit_data:
                    st.markdown("**Player Sit-Out Counts:**")
                    for player, count in sit_data:
                        st.write(f"{player}: {count} innings")
                else:
                    st.info("No players sat out.")
            
            with col2:
                # Incomplete innings
                incomplete = 0
                for inning in range(1, 8):
                    if inning not in lineup_by_inning:
                        incomplete += 1
                    else:
                        filled = len([p for p in lineup_by_inning[inning].values() if p])
                        if filled < len(POSITIONS):
                            incomplete += 1
                st.metric("Innings with Unused Positions", incomplete)
        else:
            st.info("No lineup set for this game yet.")
    else:
        st.info("No games created yet.")
    
    conn.close()

