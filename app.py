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
            kicking_order INTEGER,
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
                    # Get max kicking order to add at end
                    c.execute('''SELECT COALESCE(MAX(kicking_order), 0) 
                                FROM game_player_status 
                                WHERE game_id = ? AND status = 'IN' ''', (game_id,))
                    max_order = c.fetchone()[0] or 0
                    c.execute('''INSERT OR REPLACE INTO game_player_status 
                               (game_id, player_name, status, is_substitute, kicking_order) 
                               VALUES (?, ?, 'OUT', 0, NULL)''', (game_id, player))
                    conn.commit()
                    st.rerun()
            
            # OUT column
            st.markdown("**OUT (Not Available)**")
            for player in out_players:
                if st.button(f"⬅️ {player}", key=f"main_out_{player}", use_container_width=True):
                    # Get max kicking order to add at end
                    c.execute('''SELECT COALESCE(MAX(kicking_order), 0) 
                                FROM game_player_status 
                                WHERE game_id = ? AND status = 'IN' ''', (game_id,))
                    max_order = c.fetchone()[0] or 0
                    c.execute('''INSERT OR REPLACE INTO game_player_status 
                               (game_id, player_name, status, is_substitute, kicking_order) 
                               VALUES (?, ?, 'IN', 0, ?)''', (game_id, player, max_order + 1))
                    conn.commit()
                    st.rerun()
        
        with col2:
            st.markdown("### Substitutes")
            if substitutes:
                for sub in substitutes:
                    sub_status = statuses.get(sub, {}).get('status', None)
                    if sub_status is None:
                        if st.button(f"➕ Add {sub} to Game", key=f"add_sub_{sub}", use_container_width=True):
                            # Get max kicking order to add at end
                            c.execute('''SELECT COALESCE(MAX(kicking_order), 0) 
                                        FROM game_player_status 
                                        WHERE game_id = ? AND status = 'IN' ''', (game_id,))
                            max_order = c.fetchone()[0] or 0
                            c.execute('''INSERT INTO game_player_status 
                                       (game_id, player_name, status, is_substitute, kicking_order) 
                                       VALUES (?, ?, 'IN', 1, ?)''', (game_id, sub, max_order + 1))
                            conn.commit()
                            st.rerun()
                    elif sub_status == 'IN':
                        if st.button(f"➡️ {sub}", key=f"sub_in_{sub}", use_container_width=True):
                            c.execute('''UPDATE game_player_status SET status = 'OUT', kicking_order = NULL 
                                       WHERE game_id = ? AND player_name = ?''', (game_id, sub))
                            conn.commit()
                            st.rerun()
                    else:
                        if st.button(f"⬅️ {sub}", key=f"sub_out_{sub}", use_container_width=True):
                            # Get max kicking order to add at end
                            c.execute('''SELECT COALESCE(MAX(kicking_order), 0) 
                                        FROM game_player_status 
                                        WHERE game_id = ? AND status = 'IN' ''', (game_id,))
                            max_order = c.fetchone()[0] or 0
                            c.execute('''UPDATE game_player_status SET status = 'IN', kicking_order = ? 
                                       WHERE game_id = ? AND player_name = ?''', (max_order + 1, game_id, sub))
                            conn.commit()
                            st.rerun()
            else:
                st.info("No substitutes available. Add them in the Substitutes tab.")
        
        st.divider()
        
        # Get available players (IN status) with kicking order
        c.execute('''SELECT player_name, COALESCE(kicking_order, 999) as order_val 
                    FROM game_player_status 
                    WHERE game_id = ? AND status = 'IN' 
                    ORDER BY order_val, player_name''', (game_id,))
        available_players_data = c.fetchall()
        
        # Initialize kicking order if not set
        if available_players_data:
            needs_order_init = any(row[1] == 999 for row in available_players_data)
            if needs_order_init:
                # Set initial kicking order based on current order
                for idx, (player_name, _) in enumerate(available_players_data, 1):
                    c.execute('''UPDATE game_player_status 
                                SET kicking_order = ? 
                                WHERE game_id = ? AND player_name = ?''',
                             (idx, game_id, player_name))
                conn.commit()
                # Re-fetch with updated order
                c.execute('''SELECT player_name, kicking_order 
                            FROM game_player_status 
                            WHERE game_id = ? AND status = 'IN' 
                            ORDER BY kicking_order, player_name''', (game_id,))
                available_players_data = c.fetchall()
        
        available_players = [row[0] for row in available_players_data]
        
        # Get current lineup (position -> player mapping for each inning)
        c.execute('''SELECT inning, position, player_name FROM lineup_positions 
                    WHERE game_id = ? ORDER BY inning, position''', (game_id,))
        current_lineup = {}
        for row in c.fetchall():
            inning, position, player = row
            if inning not in current_lineup:
                current_lineup[inning] = {}
            current_lineup[inning][position] = player
        
        # Get player -> position mapping for each inning (reverse lookup)
        player_positions_by_inning = {}
        for inning in range(1, 8):
            player_positions_by_inning[inning] = {}
            for position, player in current_lineup.get(inning, {}).items():
                if player:
                    player_positions_by_inning[inning][player] = position
        
        # Kicking Order Management
        st.subheader("Kicking Order")
        st.caption("Drag players to reorder, or use the buttons below")
        
        # Display current order with reorder buttons
        if available_players:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown("**Current Kicking Order:**")
            
            # Create reorder interface
            for idx, player in enumerate(available_players):
                col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
                with col1:
                    st.write(f"{idx + 1}. {player}")
                with col2:
                    if idx > 0:
                        if st.button("↑", key=f"move_up_{player}", help="Move up"):
                            # Swap with player above
                            prev_player = available_players[idx - 1]
                            # Get current orders
                            c.execute('''SELECT kicking_order FROM game_player_status 
                                        WHERE game_id = ? AND player_name = ?''', (game_id, player))
                            current_order = c.fetchone()[0]
                            c.execute('''SELECT kicking_order FROM game_player_status 
                                        WHERE game_id = ? AND player_name = ?''', (game_id, prev_player))
                            prev_order = c.fetchone()[0]
                            # Swap orders
                            c.execute('''UPDATE game_player_status SET kicking_order = ? 
                                        WHERE game_id = ? AND player_name = ?''',
                                     (prev_order, game_id, player))
                            c.execute('''UPDATE game_player_status SET kicking_order = ? 
                                        WHERE game_id = ? AND player_name = ?''',
                                     (current_order, game_id, prev_player))
                            conn.commit()
                            st.rerun()
                with col3:
                    if idx < len(available_players) - 1:
                        if st.button("↓", key=f"move_down_{player}", help="Move down"):
                            # Swap with player below
                            next_player = available_players[idx + 1]
                            # Get current orders
                            c.execute('''SELECT kicking_order FROM game_player_status 
                                        WHERE game_id = ? AND player_name = ?''', (game_id, player))
                            current_order = c.fetchone()[0]
                            c.execute('''SELECT kicking_order FROM game_player_status 
                                        WHERE game_id = ? AND player_name = ?''', (game_id, next_player))
                            next_order = c.fetchone()[0]
                            # Swap orders
                            c.execute('''UPDATE game_player_status SET kicking_order = ? 
                                        WHERE game_id = ? AND player_name = ?''',
                                     (next_order, game_id, player))
                            c.execute('''UPDATE game_player_status SET kicking_order = ? 
                                        WHERE game_id = ? AND player_name = ?''',
                                     (current_order, game_id, next_player))
                            conn.commit()
                            st.rerun()
        else:
            st.info("No players available. Add players to IN status above.")
        
        st.divider()
        
        # Lineup interface - Spreadsheet style
        st.subheader("Lineup by Inning (Spreadsheet View)")
        
        if available_players:
            # Create position options (including "Out")
            position_options = [""] + POSITIONS
            
            # Create dataframe-style interface
            # Header row
            header_cols = st.columns([2] + [1] * 7)  # Player name + 7 innings
            with header_cols[0]:
                st.markdown("**Player**")
            for i, col in enumerate(header_cols[1:], 1):
                with col:
                    st.markdown(f"**Inning {i}**")
            
            # Player rows with position dropdowns
            lineup_changed = False
            for player_idx, player in enumerate(available_players):
                row_cols = st.columns([2] + [1] * 7)
                
                with row_cols[0]:
                    st.write(f"{player_idx + 1}. {player}")
                
                for inning in range(1, 8):
                    with row_cols[inning]:
                        # Get current position for this player in this inning
                        current_position = player_positions_by_inning[inning].get(player, "")
                        
                        # Create dropdown
                        selected_position = st.selectbox(
                            "",
                            options=position_options,
                            index=position_options.index(current_position) if current_position in position_options else 0,
                            key=f"lineup_{player}_{inning}",
                            label_visibility="collapsed"
                        )
                        
                        # Update database if changed
                        if selected_position != current_position:
                            lineup_changed = True
                            # Remove old position assignment
                            if current_position:
                                c.execute('''DELETE FROM lineup_positions 
                                           WHERE game_id = ? AND inning = ? AND position = ?''',
                                         (game_id, inning, current_position))
                            
                            # Add new position assignment
                            if selected_position:
                                # Check if position is already taken by another player
                                c.execute('''SELECT player_name FROM lineup_positions 
                                            WHERE game_id = ? AND inning = ? AND position = ?''',
                                         (game_id, inning, selected_position))
                                existing = c.fetchone()
                                if existing and existing[0] != player:
                                    # Remove old player from this position
                                    c.execute('''DELETE FROM lineup_positions 
                                               WHERE game_id = ? AND inning = ? AND position = ?''',
                                             (game_id, inning, selected_position))
                                
                                # Assign player to position
                                c.execute('''INSERT OR REPLACE INTO lineup_positions 
                                           (game_id, inning, position, player_name) 
                                           VALUES (?, ?, ?, ?)''',
                                         (game_id, inning, selected_position, player))
            
            if lineup_changed:
                conn.commit()
                st.success("Lineup updated!")
            
            # Statistics
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                # Count innings with unused positions (should have 11 playing positions filled)
                incomplete_innings = 0
                playing_positions = [p for p in POSITIONS if p != "Out"]
                for inning in range(1, 8):
                    inning_positions = current_lineup.get(inning, {})
                    positions_filled = len([p for pos, p in inning_positions.items() 
                                          if p and pos in playing_positions])
                    if positions_filled < 11:
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
        else:
            st.info("No players available. Add players to IN status above.")
        
        conn.close()

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
        
        # Get available players in kicking order
        c.execute('''SELECT player_name, COALESCE(kicking_order, 999) as order_val 
                    FROM game_player_status 
                    WHERE game_id = ? AND status = 'IN' 
                    ORDER BY order_val, player_name''', (selected_game_id,))
        available_players_data = c.fetchall()
        available_players = [row[0] for row in available_players_data]
        
        # Get lineup
        c.execute('''SELECT inning, position, player_name FROM lineup_positions 
                    WHERE game_id = ? ORDER BY inning, position''', (selected_game_id,))
        lineup_data = c.fetchall()
        
        if lineup_data or available_players:
            # Organize by player -> inning -> position
            player_positions_by_inning = {}
            for inning in range(1, 8):
                player_positions_by_inning[inning] = {}
            
            for inning, position, player in lineup_data:
                if player:
                    player_positions_by_inning[inning][player] = position
            
            # Display spreadsheet-style view
            if available_players:
                # Create dataframe for display
                display_data = []
                for player_idx, player in enumerate(available_players):
                    row = {"Kick Order": player_idx + 1, "Player": player}
                    for inning in range(1, 8):
                        position = player_positions_by_inning[inning].get(player, "")
                        if position == "Out":
                            row[f"Inning {inning}"] = f"🔴 {position}"
                        else:
                            row[f"Inning {inning}"] = position if position else "-"
                    display_data.append(row)
                
                df = pd.DataFrame(display_data)
                df = df.set_index(["Kick Order", "Player"])
                
                # Apply styling to highlight "Out" positions
                def highlight_out(val):
                    if isinstance(val, str) and val.startswith("🔴"):
                        return 'background-color: #ffcccc'
                    return ''
                
                styled_df = df.style.applymap(highlight_out)
                st.dataframe(styled_df, use_container_width=True)
            else:
                st.info("No players were available for this game.")
            
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
                # Incomplete innings (should have 11 playing positions filled)
                incomplete = 0
                playing_positions = [p for p in POSITIONS if p != "Out"]
                for inning in range(1, 8):
                    inning_positions = player_positions_by_inning.get(inning, {})
                    positions_filled = len([pos for pos in inning_positions.values() 
                                          if pos and pos in playing_positions])
                    if positions_filled < 11:
                        incomplete += 1
                st.metric("Innings with Unused Positions", incomplete)
        else:
            st.info("No lineup set for this game yet.")
    else:
        st.info("No games created yet.")
    
    conn.close()

