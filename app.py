import streamlit as st
import sqlite3
import hashlib
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Optional
import json
from urllib.parse import quote, unquote

# Page configuration - will be updated based on auth status
# Try to use logo, fallback to emoji if not found
try:
    st.set_page_config(
        page_title="UKP Kickball Roster",
        page_icon="static/images/logo.png",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except:
    st.set_page_config(
        page_title="UKP Kickball Roster",
        page_icon="⚾",
        layout="wide",
        initial_sidebar_state="expanded"
    )

# Mobile responsiveness CSS
st.markdown("""
    <style>
    /* Mobile responsiveness */
    @media (max-width: 768px) {
        /* Make columns stack on mobile */
        div[data-testid="column"] {
            width: 100% !important;
            margin-bottom: 0.5rem;
        }
        /* Reduce padding on mobile */
        .main .block-container {
            padding: 1rem !important;
        }
        /* Make buttons more touch-friendly */
        button {
            min-height: 44px !important;
            padding: 0.5rem !important;
        }
        /* Make selectboxes more touch-friendly */
        div[data-testid="stSelectbox"] {
            min-height: 44px !important;
        }
        /* Stack player status buttons vertically on mobile */
        div[data-testid="column"]:has(button[key*="toggle_"]) {
            flex: 0 0 50% !important;
            max-width: 50% !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# Database setup
import os
# Use /app/data directory if we're in Docker, otherwise current directory
if os.path.exists("/app"):
    # We're in Docker, use /app/data
    os.makedirs("/app/data", exist_ok=True)
    DB_NAME = "/app/data/kickball_roster.db"
else:
    # Local development, use data directory
    os.makedirs("data", exist_ok=True)
    DB_NAME = "data/kickball_roster.db"

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    
    # Migrate: Remove UNIQUE constraint from lineup_positions if it exists
    try:
        # SQLite doesn't support DROP CONSTRAINT directly, so we need to recreate the table
        c.execute('''SELECT name FROM sqlite_master WHERE type='table' AND name='lineup_positions' ''')
        if c.fetchone():
            # Check if unique constraint exists by trying to insert a duplicate
            # If it fails, we need to recreate the table
            c.execute('''PRAGMA table_info(lineup_positions)''')
            columns = c.fetchall()
            # Check if we need to migrate
            c.execute('''SELECT sql FROM sqlite_master WHERE type='table' AND name='lineup_positions' ''')
            table_sql = c.fetchone()
            if table_sql and 'UNIQUE(game_id, inning, position)' in table_sql[0]:
                # Recreate table without unique constraint
                c.execute('''CREATE TABLE IF NOT EXISTS lineup_positions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    inning INTEGER NOT NULL,
                    position TEXT NOT NULL,
                    player_name TEXT NOT NULL,
                    FOREIGN KEY (game_id) REFERENCES games(id)
                )''')
                c.execute('''INSERT INTO lineup_positions_new SELECT * FROM lineup_positions''')
                c.execute('''DROP TABLE lineup_positions''')
                c.execute('''ALTER TABLE lineup_positions_new RENAME TO lineup_positions''')
                conn.commit()
    except Exception as e:
        # If migration fails, continue - table might not exist yet or constraint might not exist
        pass
    
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
            is_female BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Substitute players table
    c.execute('''
        CREATE TABLE IF NOT EXISTS substitutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT UNIQUE NOT NULL,
            is_female BOOLEAN DEFAULT 0,
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
            FOREIGN KEY (game_id) REFERENCES games(id)
            -- Removed UNIQUE constraint to allow duplicate positions
            -- Multiple players can have the same position (for validation/testing)
            -- Out position can have multiple players
        )
    ''')
    
    conn.commit()
    conn.close()
    
    # Migrate existing databases to add kicking_order column if it doesn't exist
    migrate_db()

def migrate_db():
    """Migrate database schema for new columns"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Check if kicking_order column exists in game_player_status table
    try:
        c.execute("PRAGMA table_info(game_player_status)")
        columns = [row[1] for row in c.fetchall()]
        if 'kicking_order' not in columns:
            # Add kicking_order column
            c.execute('ALTER TABLE game_player_status ADD COLUMN kicking_order INTEGER')
            conn.commit()
    except Exception as e:
        # Table might not exist yet, which is fine
        pass
    
    # Check if is_female column exists in main_roster table
    try:
        c.execute("PRAGMA table_info(main_roster)")
        columns = [row[1] for row in c.fetchall()]
        if 'is_female' not in columns:
            # Add is_female column
            c.execute('ALTER TABLE main_roster ADD COLUMN is_female BOOLEAN DEFAULT 0')
            conn.commit()
    except Exception as e:
        pass
    
    # Check if is_female column exists in substitutes table
    try:
        c.execute("PRAGMA table_info(substitutes)")
        columns = [row[1] for row in c.fetchall()]
        if 'is_female' not in columns:
            # Add is_female column
            c.execute('ALTER TABLE substitutes ADD COLUMN is_female BOOLEAN DEFAULT 0')
            conn.commit()
    except Exception as e:
        pass
    
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
try:
    init_db()
except Exception as e:
    st.error(f"Database initialization error: {e}")
    import traceback
    st.code(traceback.format_exc())
    # Don't stop - allow the app to continue with a warning
    st.warning("App is running in limited mode. Some features may not work.")

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'current_game_id' not in st.session_state:
    st.session_state.current_game_id = None
if 'sidebar_collapsed' not in st.session_state:
    st.session_state.sidebar_collapsed = False

# Collapse sidebar if authenticated - using Streamlit's built-in method
if is_authenticated():
    # Hide sidebar using CSS
    st.markdown("""
        <style>
        section[data-testid="stSidebar"] {
            display: none;
        }
        section[data-testid="stSidebar"] ~ div {
            margin-left: 0rem;
        }
        </style>
    """, unsafe_allow_html=True)

# Authentication sidebar
with st.sidebar:
    # Display logo in title
    try:
        col_logo, col_title = st.columns([0.15, 0.85])
        with col_logo:
            st.image("static/images/logo.png", width=60)
        with col_title:
            st.title("UKP Kickball Roster")
    except:
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
# Display logo instead of emoji in title
try:
    col_logo, col_title = st.columns([0.15, 0.85])
    with col_logo:
        st.image("static/images/logo.png", width=60)
    with col_title:
        st.title("UKP Kickball Roster Manager")
except:
    st.title("⚾ UKP Kickball Roster Manager")

# Navigation tabs - different tabs for authenticated vs public
if is_authenticated():
    tabs = st.tabs(["Game Lineup", "Roster", "View Lineup"])
    # Default to Game Lineup tab (index 0) for logged in users
    # Streamlit tabs default to first tab, so this is already correct
else:
    st.info("👀 **View Mode**: You are viewing in read-only mode. Please login to edit.")
    tabs = st.tabs(["View Lineup"])

# Positions definition
POSITIONS = [
    "Pitcher", "Catcher", "First Base", "Second Base", "Third Base",
    "Short Stop", "Left Field", "Left Center", "Center Field",
    "Right Center", "Right Field", "Out"
]

# Position abbreviations for display
POSITION_ABBREVIATIONS = {
    "Pitcher": "P",
    "Catcher": "C",
    "First Base": "1st",
    "Second Base": "2nd",
    "Third Base": "3rd",
    "Short Stop": "SS",
    "Left Field": "LF",
    "Left Center": "LC",
    "Center Field": "CF",
    "Right Center": "RC",
    "Right Field": "RF",
    "Out": "Out"
}

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
        
        # Player status management - Compact grid view
        st.subheader("Player Status")
        
        # Compact grid view for main roster - 12 columns with minimal padding
        st.markdown("**Main Roster**")
        
        # Check for player toggle from session state FIRST (before building roster list)
        # This ensures status is updated before we render buttons
        if 'toggle_player' in st.session_state and st.session_state.toggle_player:
            player_to_toggle = st.session_state.toggle_player
            # Check if this is a substitute or main roster player
            is_sub = player_to_toggle in substitutes
            # Get current status from database
            c.execute('''SELECT status FROM game_player_status 
                       WHERE game_id = ? AND player_name = ?''', (game_id, player_to_toggle))
            result = c.fetchone()
            # Default status: 'IN' for main roster, 'OUT' for substitutes
            current_status = result[0] if result else ('OUT' if is_sub else 'IN')
            
            # If player doesn't exist in game_player_status yet, initialize them
            if not result:
                c.execute('''INSERT OR IGNORE INTO game_player_status 
                           (game_id, player_name, status, is_substitute, kicking_order) 
                           VALUES (?, ?, ?, ?, NULL)''', 
                         (game_id, player_to_toggle, current_status, 1 if is_sub else 0))
                conn.commit()
            
            if current_status == 'IN':
                c.execute('''INSERT OR REPLACE INTO game_player_status 
                           (game_id, player_name, status, is_substitute, kicking_order) 
                           VALUES (?, ?, 'OUT', ?, NULL)''', (game_id, player_to_toggle, 1 if is_sub else 0))
                conn.commit()
            else:
                c.execute('''SELECT COALESCE(MAX(kicking_order), 0) 
                            FROM game_player_status 
                            WHERE game_id = ? AND status = 'IN' ''', (game_id,))
                max_order = c.fetchone()[0] or 0
                c.execute('''INSERT OR REPLACE INTO game_player_status 
                           (game_id, player_name, status, is_substitute, kicking_order) 
                           VALUES (?, ?, 'IN', ?, ?)''', (game_id, player_to_toggle, 1 if is_sub else 0, max_order + 1))
                conn.commit()
            # Clear the toggle flag and rerun
            st.session_state.toggle_player = None
            st.rerun()
        
        # Create grid with 12 columns for very compact display
        num_cols = 12
        roster_list = []
        for player in main_roster:
            current_status = statuses.get(player, {}).get('status', 'IN')
            roster_list.append((player, current_status))
        
        # Display buttons with compact sizing (primary color handled by config.toml)
        roster_buttons_id = f"roster-buttons-{game_id}"
        st.markdown(f"""
            <style>
            /* Compact sizing for roster buttons - primary color comes from config.toml */
            #{roster_buttons_id} ~ * button[data-testid="baseButton-primary"],
            #{roster_buttons_id} ~ * button[data-testid="baseButton-secondary"] {{
                padding: 2px 6px !important;
                font-size: 0.7rem !important;
                min-height: 24px !important;
                height: 24px !important;
                font-weight: 500 !important;
            }}
            /* OUT buttons (secondary) need red border styling */
            #{roster_buttons_id} ~ * button[data-testid="baseButton-secondary"] {{
                background-color: transparent !important;
                border-color: #dc3545 !important;
                border: 2px solid #dc3545 !important;
                color: #dc3545 !important;
            }}
            #{roster_buttons_id} ~ * button[data-testid="baseButton-secondary"]:hover {{
                background-color: rgba(220, 53, 69, 0.1) !important;
            }}
            </style>
            <div id="{roster_buttons_id}"></div>
        """, unsafe_allow_html=True)
        
        # Create buttons in a grid using Streamlit buttons
        for i in range(0, len(roster_list), num_cols):
            cols = st.columns(num_cols)
            for j, col in enumerate(cols):
                if i + j < len(roster_list):
                    player, status = roster_list[i + j]
                    with col:
                        if status == 'IN':
                            # Green button for IN status
                            button_key = f"roster_toggle_in_{player}_{game_id}"
                            if st.button(player, key=button_key, type="primary", use_container_width=True):
                                st.session_state.toggle_player = player
                                st.rerun()
                        else:
                            # Red border button for OUT status
                            button_key = f"roster_toggle_out_{player}_{game_id}"
                            if st.button(player, key=button_key, type="secondary", use_container_width=True):
                                st.session_state.toggle_player = player
                                st.rerun()
        
        # Substitutes section - collapsible, default to collapsed
        with st.expander("**Substitutes**", expanded=False):
            if substitutes:
                # Get current game player statuses for substitutes
                # Initialize substitutes in game_player_status if they don't exist yet
                sub_statuses = {}
                for sub in substitutes:
                    c.execute('SELECT status FROM game_player_status WHERE game_id = ? AND player_name = ?',
                             (game_id, sub))
                    result = c.fetchone()
                    if result:
                        sub_statuses[sub] = result[0]
                    else:
                        # Initialize substitute as OUT if not in game_player_status yet
                        sub_statuses[sub] = 'OUT'
                        c.execute('''INSERT OR IGNORE INTO game_player_status 
                                   (game_id, player_name, status, is_substitute, kicking_order) 
                                   VALUES (?, ?, 'OUT', 1, NULL)''', (game_id, sub))
                        conn.commit()
                
                # Create grid with 12 columns for substitutes
                sub_list = []
                for sub in substitutes:
                    current_status = sub_statuses.get(sub, 'OUT')
                    sub_list.append((sub, current_status))
                
                # Compact sizing for substitutes (primary color handled by config.toml)
                sub_buttons_id = f"sub-buttons-{game_id}"
                st.markdown(f"""
                    <style>
                    /* Compact sizing for substitute buttons - primary color comes from config.toml */
                    #{sub_buttons_id} ~ * button[data-testid="baseButton-primary"],
                    #{sub_buttons_id} ~ * button[data-testid="baseButton-secondary"] {{
                        padding: 2px 6px !important;
                        font-size: 0.7rem !important;
                        min-height: 24px !important;
                        height: 24px !important;
                        font-weight: 500 !important;
                    }}
                    /* OUT buttons (secondary) need red border styling */
                    #{sub_buttons_id} ~ * button[data-testid="baseButton-secondary"] {{
                        background-color: transparent !important;
                        border-color: #dc3545 !important;
                        border: 2px solid #dc3545 !important;
                        color: #dc3545 !important;
                    }}
                    #{sub_buttons_id} ~ * button[data-testid="baseButton-secondary"]:hover {{
                        background-color: rgba(220, 53, 69, 0.1) !important;
                    }}
                    </style>
                    <div id="{sub_buttons_id}"></div>
                """, unsafe_allow_html=True)
                
                # Create buttons in a grid using Streamlit buttons
                for i in range(0, len(sub_list), num_cols):
                    cols = st.columns(num_cols)
                    for j, col in enumerate(cols):
                        if i + j < len(sub_list):
                            sub_player, sub_status = sub_list[i + j]
                            with col:
                                if sub_status == 'IN':
                                    # Green button for IN status
                                    button_key = f"sub_toggle_in_{sub_player}_{game_id}"
                                    if st.button(sub_player, key=button_key, type="primary", use_container_width=True):
                                        st.session_state.toggle_player = sub_player
                                        st.rerun()
                                else:
                                    # Red border button for OUT status
                                    button_key = f"sub_toggle_out_{sub_player}_{game_id}"
                                    if st.button(sub_player, key=button_key, type="secondary", use_container_width=True):
                                        st.session_state.toggle_player = sub_player
                                        st.rerun()
            else:
                st.info("No substitutes available. Add them in the Roster tab.")
        
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
        
        # Get player gender information
        c.execute('''SELECT player_name, is_female FROM main_roster''')
        main_roster_genders = {row[0]: bool(row[1]) for row in c.fetchall()}
        c.execute('''SELECT player_name, is_female FROM substitutes''')
        sub_genders = {row[0]: bool(row[1]) for row in c.fetchall()}
        player_genders = {**main_roster_genders, **sub_genders}
        
        # Lineup interface - Spreadsheet style
        st.subheader("Lineup by Inning (Spreadsheet View)")
        
        if available_players:
            # Create position options (including "Out") - use abbreviations for display
            # Move blank option to bottom
            position_options = POSITIONS + [""]
            playing_positions = [p for p in POSITIONS if p != "Out"]
            
            # Function to check female count for an inning
            def check_female_count(inning_num):
                c.execute('''SELECT COUNT(DISTINCT lp.player_name)
                            FROM lineup_positions lp
                            LEFT JOIN main_roster mr ON lp.player_name = mr.player_name
                            LEFT JOIN substitutes s ON lp.player_name = s.player_name
                            WHERE lp.game_id = ? AND lp.inning = ? 
                            AND lp.position != 'Out' AND lp.position != ''
                            AND (COALESCE(mr.is_female, 0) = 1 OR COALESCE(s.is_female, 0) = 1)''',
                         (game_id, inning_num))
                return c.fetchone()[0]
            
            # Function to get unused positions for an inning
            def get_unused_positions(inning_num):
                c.execute('''SELECT position FROM lineup_positions 
                            WHERE game_id = ? AND inning = ? AND position != 'Out' AND position != '' ''',
                         (game_id, inning_num))
                filled_positions = {row[0] for row in c.fetchall()}
                playing_positions = {p for p in POSITIONS if p != "Out"}
                unused = playing_positions - filled_positions
                return unused
            
            # Function to get duplicate positions for an inning
            def get_duplicate_positions(inning_num):
                c.execute('''SELECT position, COUNT(*) as cnt 
                            FROM lineup_positions 
                            WHERE game_id = ? AND inning = ? AND position != 'Out' AND position != '' 
                            GROUP BY position 
                            HAVING cnt > 1''',
                         (game_id, inning_num))
                duplicates = [row[0] for row in c.fetchall()]
                return duplicates
            
            # Function to get which players have duplicate positions in an inning
            def get_duplicate_players_by_position(inning_num):
                """Returns dict mapping position -> list of players who have that position"""
                c.execute('''SELECT position, player_name 
                            FROM lineup_positions 
                            WHERE game_id = ? AND inning = ? AND position != 'Out' AND position != '' ''',
                         (game_id, inning_num))
                position_players = {}
                for position, player in c.fetchall():
                    if position not in position_players:
                        position_players[position] = []
                    position_players[position].append(player)
                # Filter to only duplicates
                return {pos: players for pos, players in position_players.items() if len(players) > 1}
            
            # Check all warnings for all innings and track duplicate positions
            # This must be done AFTER all database updates to get current state
            inning_warnings = {}
            duplicate_positions_by_inning = {}  # inning -> set of duplicate positions
            duplicate_players_by_inning = {}   # inning -> dict of position -> list of players
            
            # Refresh lineup data from database before checking warnings
            c.execute('''SELECT inning, position, player_name FROM lineup_positions 
                        WHERE game_id = ? ORDER BY inning, position''', (game_id,))
            current_lineup_refreshed = {}
            for row in c.fetchall():
                inning, position, player = row
                if inning not in current_lineup_refreshed:
                    current_lineup_refreshed[inning] = {}
                current_lineup_refreshed[inning][position] = player
            
            for i in range(1, 8):
                warnings = []
                female_count = check_female_count(i)
                if female_count < 4:
                    warnings.append(f"Only {female_count} females on field (need 4)")
                
                duplicates = get_duplicate_positions(i)
                if duplicates:
                    dup_abbrevs = [POSITION_ABBREVIATIONS.get(d, d) for d in duplicates]
                    warnings.append(f"Duplicate positions: {', '.join(dup_abbrevs)}")
                    duplicate_positions_by_inning[i] = set(duplicates)
                    duplicate_players_by_inning[i] = get_duplicate_players_by_position(i)
                else:
                    duplicate_positions_by_inning[i] = set()
                    duplicate_players_by_inning[i] = {}
                
                unused = get_unused_positions(i)
                if unused:
                    unused_abbrevs = [POSITION_ABBREVIATIONS.get(u, u) for u in unused]
                    warnings.append(f"Unused positions: {', '.join(unused_abbrevs)}")
                
                if warnings:
                    inning_warnings[i] = warnings
            
            # Create dataframe-style interface
            # Header row - with up/down buttons and sit-out count
            header_cols = st.columns([2, 0.5, 0.5] + [1] * 7 + [0.6])  # Player + up/down + 7 innings + sit-out count
            with header_cols[0]:
                st.markdown("**Player**")
            with header_cols[1]:
                st.markdown("**↑**")
            with header_cols[2]:
                st.markdown("**↓**")
            
            # Copy and Reset buttons
            col_copy, col_reset = st.columns([1, 1])
            with col_copy:
                if st.button("Copy Inning 1 to All", key="copy_all_innings", help="Copy lineup from Inning 1 to innings 2-7"):
                    # Get all positions from inning 1
                    c.execute('''SELECT position, player_name FROM lineup_positions 
                                WHERE game_id = ? AND inning = 1''', (game_id,))
                    first_inning = c.fetchall()
                    
                    # Copy to innings 2-7
                    for inning_num in range(2, 8):
                        # Clear current inning
                        c.execute('''DELETE FROM lineup_positions 
                                   WHERE game_id = ? AND inning = ?''', (game_id, inning_num))
                        
                        # Copy positions
                        for position, player in first_inning:
                            if position:  # Only copy non-empty positions
                                c.execute('''INSERT INTO lineup_positions 
                                           (game_id, inning, position, player_name) 
                                           VALUES (?, ?, ?, ?)''',
                                         (game_id, inning_num, position, player))
                    conn.commit()
                    st.rerun()
            
            with col_reset:
                if st.button("Reset Lineup", key="reset_lineup", help="Clear all position assignments"):
                    # Clear all lineup positions for this game
                    c.execute('''DELETE FROM lineup_positions 
                               WHERE game_id = ?''', (game_id,))
                    conn.commit()
                    st.rerun()
            
            for i, col in enumerate(header_cols[3:10], 1):
                with col:
                    inning_num = i
                    warning_icon = ""
                    if inning_num in inning_warnings:
                        warnings_text = " | ".join(inning_warnings[inning_num])
                        warning_icon = f'<span title="{warnings_text}" style="color: #ffa500; font-size: 1.2em;">⚠️</span>'
                    
                    st.markdown(f"**Inning {i}** {warning_icon}", unsafe_allow_html=True)
            
            # Sit-out count header
            with header_cols[10]:
                st.markdown("**Out**")
            
            # Get current order from database
            player_orders = {}
            for player in available_players:
                c.execute('''SELECT kicking_order FROM game_player_status 
                            WHERE game_id = ? AND player_name = ?''', (game_id, player))
                order = c.fetchone()[0]
                if order:
                    player_orders[player] = order
            
            # Sort available_players by their order
            available_players_sorted = sorted(available_players, 
                                            key=lambda p: player_orders.get(p, 999))
            
            # Get sit-out counts for each player
            c.execute('''SELECT player_name, COUNT(*) as sit_count 
                        FROM lineup_positions 
                        WHERE game_id = ? AND position = 'Out' 
                        GROUP BY player_name''', (game_id,))
            sit_out_counts = {row[0]: row[1] for row in c.fetchall()}
            
            # Player rows with position dropdowns and reorder buttons
            lineup_changed = False
            order_changed = False
            
            for player_idx, player in enumerate(available_players_sorted):
                row_cols = st.columns([2, 0.5, 0.5] + [1] * 7 + [0.6])
                
                with row_cols[0]:
                    is_female = player_genders.get(player, False)
                    gender_indicator = "♀" if is_female else ""
                    st.write(f"{player_idx + 1}. {player} {gender_indicator}")
                
                # Up button for reordering
                with row_cols[1]:
                    if player_idx > 0:
                        if st.button("↑", key=f"move_up_{player}", help="Move up"):
                            # Swap with player above
                            prev_player = available_players_sorted[player_idx - 1]
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
                            order_changed = True
                            st.rerun()
                
                # Down button for reordering
                with row_cols[2]:
                    if player_idx < len(available_players_sorted) - 1:
                        if st.button("↓", key=f"move_down_{player}", help="Move down"):
                            # Swap with player below
                            next_player = available_players_sorted[player_idx + 1]
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
                            order_changed = True
                            st.rerun()
                
                for inning in range(1, 8):
                    with row_cols[inning + 2]:  # +2 because of player name (0), up (1), down (2), innings start at index 3
                        # Get current position for this player in this inning - refresh from database
                        c.execute('''SELECT position FROM lineup_positions 
                                    WHERE game_id = ? AND inning = ? AND player_name = ?''',
                                 (game_id, inning, player))
                        result = c.fetchone()
                        current_position = result[0] if result else ""
                        
                        # Check if this position is a duplicate
                        is_duplicate = current_position in duplicate_positions_by_inning.get(inning, set())
                        
                        # Create dropdown with abbreviations for display
                        # Map full position names to abbreviations for display, blank at bottom
                        display_options = [POSITION_ABBREVIATIONS.get(pos, pos) for pos in POSITIONS] + [""]
                        current_abbrev = POSITION_ABBREVIATIONS.get(current_position, current_position) if current_position else ""
                        
                        # Find index for current selection (blank is at the end)
                        if current_abbrev in display_options:
                            current_index = display_options.index(current_abbrev)
                        else:
                            current_index = len(display_options) - 1  # Default to blank at bottom
                        
                        # Add help text if duplicate
                        help_text = ""
                        if is_duplicate and current_position:
                            dup_players = duplicate_players_by_inning.get(inning, {}).get(current_position, [])
                            dup_players_str = ", ".join([p for p in dup_players if p != player])
                            help_text = f"⚠️ DUPLICATE: {POSITION_ABBREVIATIONS.get(current_position, current_position)} also assigned to: {dup_players_str}"
                        
                        selectbox_key = f"lineup_{player}_{inning}"
                        
                        selected_abbrev = st.selectbox(
                            "",
                            options=display_options,
                            index=current_index,
                            key=selectbox_key,
                            label_visibility="collapsed",
                            help=help_text if help_text else None
                        )
                        
                        # Note: Visual highlighting removed - duplicate errors shown in hover tooltip only
                        
                        # Convert abbreviation back to full position name
                        abbrev_to_full = {v: k for k, v in POSITION_ABBREVIATIONS.items()}
                        selected_position = abbrev_to_full.get(selected_abbrev, selected_abbrev) if selected_abbrev else ""
                        
                        # Update database if changed
                        if selected_position != current_position:
                            lineup_changed = True
                            
                            # Remove old position assignment for this player only
                            if current_position:
                                c.execute('''DELETE FROM lineup_positions 
                                           WHERE game_id = ? AND inning = ? AND position = ? AND player_name = ?''',
                                         (game_id, inning, current_position, player))
                            
                            # Add new position assignment (allow duplicates - don't remove other players)
                            if selected_position:
                                # Check if this player already has this position (shouldn't happen, but be safe)
                                c.execute('''SELECT COUNT(*) FROM lineup_positions 
                                            WHERE game_id = ? AND inning = ? AND position = ? AND player_name = ?''',
                                         (game_id, inning, selected_position, player))
                                exists = c.fetchone()[0] > 0
                                
                                if not exists:
                                    # Add new position assignment (duplicates are allowed - multiple players can have same position)
                                    c.execute('''INSERT INTO lineup_positions 
                                               (game_id, inning, position, player_name) 
                                               VALUES (?, ?, ?, ?)''',
                                             (game_id, inning, selected_position, player))
                                conn.commit()
                            else:
                                conn.commit()
                            
                            # Force rerun to refresh all data
                            st.rerun()
                
                # Sit-out count column
                with row_cols[10]:
                    sit_count = sit_out_counts.get(player, 0)
                    if sit_count > 0:
                        st.markdown(f"<div style='text-align: center; color: #ff6b6b; font-weight: bold;'>{sit_count}</div>", 
                                  unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='text-align: center;'>0</div>", unsafe_allow_html=True)
            
            if lineup_changed and not order_changed:
                # Only show success if lineup changed but order didn't (to avoid double messages)
                pass
            
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
            is_female = st.checkbox("Female", key="new_player_female")
            submit = st.form_submit_button("Add Player")
            
            if submit and new_player:
                try:
                    c.execute('INSERT INTO main_roster (player_name, is_female) VALUES (?, ?)', 
                             (new_player, 1 if is_female else 0))
                    conn.commit()
                    st.success(f"Added {new_player} to main roster!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"{new_player} is already in the roster.")
        
        # Display current roster
        c.execute('SELECT player_name, is_female FROM main_roster ORDER BY player_name')
        roster = c.fetchall()
        
        if roster:
            st.subheader("Current Roster")
            for player_name, is_female in roster:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    gender_indicator = "♀" if is_female else ""
                    st.write(f"{player_name} {gender_indicator}")
                with col2:
                    gender_text = "♀" if is_female else "♂"
                    if st.button(gender_text, key=f"toggle_{player_name}", help="Toggle gender"):
                        # Toggle gender
                        new_gender = 0 if is_female else 1
                        c.execute('UPDATE main_roster SET is_female = ? WHERE player_name = ?',
                                 (new_gender, player_name))
                        conn.commit()
                        st.rerun()
                with col3:
                    if st.button("Delete", key=f"del_{player_name}"):
                        c.execute('DELETE FROM main_roster WHERE player_name = ?', (player_name,))
                        conn.commit()
                        st.rerun()
        else:
            st.info("No players in main roster yet.")
        
        st.divider()
        
        # Add/Edit Substitutes
        st.markdown("**Manage Substitutes**")
        conn_sub = sqlite3.connect(DB_NAME)
        c_sub = conn_sub.cursor()
        
        # Get substitutes from database
        c_sub.execute('SELECT player_name, is_female FROM substitutes ORDER BY player_name')
        substitutes_list = c_sub.fetchall()
        
        with st.form("add_substitute_form"):
            new_sub_name = st.text_input("Substitute Name")
            is_female_sub = st.checkbox("Female", key="new_sub_female")
            submit_sub = st.form_submit_button("Add Substitute")
            
            if submit_sub and new_sub_name:
                if new_sub_name.strip():
                    try:
                        c_sub.execute('INSERT INTO substitutes (player_name, is_female) VALUES (?, ?)',
                                 (new_sub_name.strip(), 1 if is_female_sub else 0))
                        conn_sub.commit()
                        st.success(f"Added {new_sub_name} to substitutes")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Substitute already exists")
        
        # List and manage existing substitutes
        if substitutes_list:
            st.markdown("**Edit Substitutes**")
            for sub_name, is_female in substitutes_list:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    gender_indicator = "♀" if is_female else ""
                    st.write(f"{sub_name} {gender_indicator}")
                with col2:
                    gender_text = "♀" if is_female else "♂"
                    if st.button(gender_text, key=f"toggle_sub_{sub_name}", help="Toggle gender"):
                        # Toggle gender
                        new_gender = 0 if is_female else 1
                        c_sub.execute('UPDATE substitutes SET is_female = ? WHERE player_name = ?',
                                 (new_gender, sub_name))
                        conn_sub.commit()
                        st.rerun()
                with col3:
                    if st.button("Delete", key=f"del_sub_{sub_name}"):
                        c_sub.execute('DELETE FROM substitutes WHERE player_name = ?', (sub_name,))
                        conn_sub.commit()
                        st.rerun()
        
        conn_sub.close()
        conn.close()

# ========== VIEW LINEUP TAB ==========
# View lineup is accessible to both authenticated and public users
view_tab_idx = 2 if is_authenticated() else 0
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
                        if position:
                            # Use abbreviation for display
                            abbrev = POSITION_ABBREVIATIONS.get(position, position)
                            row[f"Inning {inning}"] = abbrev
                        else:
                            row[f"Inning {inning}"] = "-"
                    display_data.append(row)
                
                df = pd.DataFrame(display_data)
                df = df.set_index(["Kick Order", "Player"])
                
                # Apply styling to highlight "Out" positions with slightly transparent red
                def highlight_out(val):
                    if isinstance(val, str) and val == "Out":
                        return 'background-color: rgba(220, 53, 69, 0.2)'
                    return ''
                
                styled_df = df.style.applymap(highlight_out)
                st.dataframe(styled_df, use_container_width=True)
            else:
                st.info("No players were available for this game.")
        else:
            st.info("No lineup set for this game yet.")
    else:
        st.info("No games created yet.")
    
    conn.close()

