"""
UKP Kickball Roster Manager - Flask Backend
"""
from flask import Flask, jsonify, request, send_from_directory, session
from functools import wraps
import sqlite3
import hashlib
import os
import io
import uuid
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import groupme as gm
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'ukp-kickball-secret-key-change-in-production')

# Database setup
if os.path.exists("/app"):
    os.makedirs("/app/data", exist_ok=True)
    os.makedirs("/app/data/logos", exist_ok=True)
    DB_NAME = "/app/data/kickball_roster.db"
    LOGO_FOLDER = "/app/data/logos"
else:
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/logos", exist_ok=True)
    DB_NAME = "data/kickball_roster.db"
    LOGO_FOLDER = "data/logos"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Positions definition
POSITIONS = [
    "Pitcher", "Catcher", "First Base", "Second Base", "Third Base",
    "Short Stop", "Left Field", "Left Center", "Center Field",
    "Right Center", "Right Field", "Out"
]

POSITION_ABBREVIATIONS = {
    "Pitcher": "P", "Catcher": "C", "First Base": "1st", "Second Base": "2nd",
    "Third Base": "3rd", "Short Stop": "SS", "Left Field": "LF",
    "Left Center": "LC", "Center Field": "CF", "Right Center": "RC",
    "Right Field": "RF", "Out": "Out"
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with required tables"""
    conn = get_db()
    c = conn.cursor()
    
    # Users table
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
            team_logo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Player status for games
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
        )
    ''')
    
    # Published lineup snapshot
    c.execute('''
        CREATE TABLE IF NOT EXISTS published_lineup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            inning INTEGER NOT NULL CHECK(inning BETWEEN 1 AND 7),
            position TEXT NOT NULL,
            player_name TEXT,
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    ''')
    
    # Published player order snapshot
    c.execute('''
        CREATE TABLE IF NOT EXISTS published_player_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            kicking_order INTEGER,
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    ''')
    
    # Settings table (key/value for GroupMe config etc.)
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # GroupMe event tracking (avoid duplicate posts)
    c.execute('''
        CREATE TABLE IF NOT EXISTS groupme_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            groupme_event_id TEXT,
            groupme_response TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES games(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    migrate_db()


def migrate_db():
    """Migrate database schema"""
    conn = get_db()
    c = conn.cursor()
    
    # Add kicking_order column if missing
    try:
        c.execute("PRAGMA table_info(game_player_status)")
        columns = [row[1] for row in c.fetchall()]
        if 'kicking_order' not in columns:
            c.execute('ALTER TABLE game_player_status ADD COLUMN kicking_order INTEGER')
            conn.commit()
    except:
        pass
    
    # Add is_female column to main_roster if missing
    try:
        c.execute("PRAGMA table_info(main_roster)")
        columns = [row[1] for row in c.fetchall()]
        if 'is_female' not in columns:
            c.execute('ALTER TABLE main_roster ADD COLUMN is_female BOOLEAN DEFAULT 0')
            conn.commit()
    except:
        pass
    
    # Add is_female column to substitutes if missing
    try:
        c.execute("PRAGMA table_info(substitutes)")
        columns = [row[1] for row in c.fetchall()]
        if 'is_female' not in columns:
            c.execute('ALTER TABLE substitutes ADD COLUMN is_female BOOLEAN DEFAULT 0')
            conn.commit()
    except:
        pass
    
    # Add team_logo column to games if missing
    try:
        c.execute("PRAGMA table_info(games)")
        columns = [row[1] for row in c.fetchall()]
        if 'team_logo' not in columns:
            c.execute('ALTER TABLE games ADD COLUMN team_logo TEXT')
            conn.commit()
    except:
        pass
    
    # Add is_published and published_at columns to games if missing
    try:
        c.execute("PRAGMA table_info(games)")
        columns = [row[1] for row in c.fetchall()]
        if 'is_published' not in columns:
            c.execute('ALTER TABLE games ADD COLUMN is_published BOOLEAN DEFAULT 0')
            conn.commit()
        if 'published_at' not in columns:
            c.execute('ALTER TABLE games ADD COLUMN published_at TIMESTAMP')
            conn.commit()
    except:
        pass
    
    # Add groupme_user_id column to main_roster and substitutes if missing
    for table in ('main_roster', 'substitutes'):
        try:
            c.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in c.fetchall()]
            if 'groupme_user_id' not in columns:
                c.execute(f'ALTER TABLE {table} ADD COLUMN groupme_user_id TEXT')
                conn.commit()
        except:
            pass
    
    # Add groupme_event_id column to groupme_events if missing
    try:
        c.execute("PRAGMA table_info(groupme_events)")
        columns = [row[1] for row in c.fetchall()]
        if 'groupme_event_id' not in columns:
            c.execute('ALTER TABLE groupme_events ADD COLUMN groupme_event_id TEXT')
            conn.commit()
    except:
        pass
    
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def get_next_thursday() -> datetime:
    today = datetime.now()
    days_until_thursday = (3 - today.weekday()) % 7
    if days_until_thursday == 0:
        days_until_thursday = 7
    return today + timedelta(days=days_until_thursday)


# Initialize database
init_db()


# ========== Static Routes ==========
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)


@app.route('/logos/<path:filename>')
def serve_logo(filename):
    return send_from_directory(LOGO_FOLDER, filename)


# ========== Auth Routes ==========
@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    if 'user_id' in session:
        return jsonify({'authenticated': True, 'username': session.get('username')})
    return jsonify({'authenticated': False})


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    conn.close()
    
    if user and user['password_hash'] == hash_password(password):
        session['user_id'] = user['id']
        session['username'] = username
        return jsonify({'success': True, 'username': username})
    
    return jsonify({'error': 'Invalid credentials'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Only allow registration if no users exist
    c.execute('SELECT COUNT(*) as cnt FROM users')
    if c.fetchone()['cnt'] > 0:
        conn.close()
        return jsonify({'error': 'Users already exist'}), 400
    
    try:
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                  (username, hash_password(password)))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 400


@app.route('/api/auth/has-users', methods=['GET'])
def has_users():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as cnt FROM users')
    count = c.fetchone()['cnt']
    conn.close()
    return jsonify({'hasUsers': count > 0})


@app.route('/api/auth/users', methods=['GET'])
@login_required
def get_users():
    """Get list of all users (admin only)"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, username FROM users ORDER BY username')
    users = [{'id': row['id'], 'username': row['username']} for row in c.fetchall()]
    conn.close()
    return jsonify(users)


@app.route('/api/auth/users', methods=['POST'])
@login_required
def create_user():
    """Create a new user (admin only)"""
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    try:
        c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                  (username, hash_password(password)))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 400


@app.route('/api/auth/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    """Delete a user (cannot delete yourself)"""
    if session.get('user_id') == user_id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ========== Roster Routes ==========
@app.route('/api/roster', methods=['GET'])
def get_roster():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT player_name, is_female, groupme_user_id FROM main_roster ORDER BY player_name')
    roster = [{'name': row['player_name'], 'isFemale': bool(row['is_female']), 'groupmeUserId': row['groupme_user_id']} for row in c.fetchall()]
    conn.close()
    return jsonify(roster)


@app.route('/api/roster', methods=['POST'])
@login_required
def add_player():
    data = request.json
    name = data.get('name', '').strip()
    is_female = data.get('isFemale', False)
    
    if not name:
        return jsonify({'error': 'Player name required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO main_roster (player_name, is_female) VALUES (?, ?)',
                  (name, 1 if is_female else 0))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Player already exists'}), 400


@app.route('/api/roster/<name>', methods=['DELETE'])
@login_required
def delete_player(name):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM main_roster WHERE player_name = ?', (name,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/roster/<name>/gender', methods=['PUT'])
@login_required
def toggle_player_gender(name):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE main_roster SET is_female = NOT is_female WHERE player_name = ?', (name,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ========== Substitutes Routes ==========
@app.route('/api/substitutes', methods=['GET'])
def get_substitutes():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT player_name, is_female, groupme_user_id FROM substitutes ORDER BY player_name')
    subs = [{'name': row['player_name'], 'isFemale': bool(row['is_female']), 'groupmeUserId': row['groupme_user_id']} for row in c.fetchall()]
    conn.close()
    return jsonify(subs)


@app.route('/api/substitutes', methods=['POST'])
@login_required
def add_substitute():
    data = request.json
    name = data.get('name', '').strip()
    is_female = data.get('isFemale', False)
    
    if not name:
        return jsonify({'error': 'Substitute name required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO substitutes (player_name, is_female) VALUES (?, ?)',
                  (name, 1 if is_female else 0))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Substitute already exists'}), 400


@app.route('/api/substitutes/<name>', methods=['DELETE'])
@login_required
def delete_substitute(name):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM substitutes WHERE player_name = ?', (name,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/substitutes/<name>/gender', methods=['PUT'])
@login_required
def toggle_substitute_gender(name):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE substitutes SET is_female = NOT is_female WHERE player_name = ?', (name,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ========== Games Routes ==========
@app.route('/api/games', methods=['GET'])
def get_games():
    conn = get_db()
    c = conn.cursor()
    
    # Check if is_published column exists (for backward compatibility)
    c.execute("PRAGMA table_info(games)")
    columns = [row[1] for row in c.fetchall()]
    has_publish_columns = 'is_published' in columns
    
    if has_publish_columns:
        c.execute('SELECT id, game_date, team_name, opponent_name, team_logo, is_published, published_at FROM games ORDER BY game_date DESC')
    else:
        c.execute('SELECT id, game_date, team_name, opponent_name, team_logo FROM games ORDER BY game_date DESC')
    
    games = []
    for row in c.fetchall():
        game = dict(row)
        game['is_published'] = bool(game.get('is_published')) if has_publish_columns else False
        if not has_publish_columns:
            game['published_at'] = None
        games.append(game)
    conn.close()
    return jsonify(games)


@app.route('/api/games/current', methods=['GET'])
def get_current_game():
    """Get the game for the next Thursday (does NOT auto-create)"""
    conn = get_db()
    c = conn.cursor()
    
    # Check if is_published column exists
    c.execute("PRAGMA table_info(games)")
    columns = [row[1] for row in c.fetchall()]
    has_publish_columns = 'is_published' in columns
    
    next_thursday = get_next_thursday().date()
    
    if has_publish_columns:
        c.execute('SELECT id, game_date, team_name, opponent_name, team_logo, is_published, published_at FROM games WHERE game_date = ?',
                  (next_thursday,))
    else:
        c.execute('SELECT id, game_date, team_name, opponent_name, team_logo FROM games WHERE game_date = ?',
                  (next_thursday,))
    
    game = c.fetchone()
    
    if not game:
        # Return null to indicate no game exists (don't auto-create)
        conn.close()
        return jsonify({'exists': False, 'next_thursday': str(next_thursday)})
    
    game = dict(game)
    game['exists'] = True
    game['is_published'] = bool(game.get('is_published')) if has_publish_columns else False
    if not has_publish_columns:
        game['published_at'] = None
    
    conn.close()
    return jsonify(game)


@app.route('/api/games', methods=['POST'])
@login_required
def create_game():
    """Create a new game manually"""
    data = request.json
    game_date = data.get('game_date')
    team_name = data.get('team_name', '')
    opponent_name = data.get('opponent_name', '')
    
    if not game_date:
        return jsonify({'error': 'Game date is required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('INSERT INTO games (game_date, team_name, opponent_name, is_published) VALUES (?, ?, ?, 0)',
              (game_date, team_name, opponent_name))
    game_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'id': game_id,
        'game_date': game_date,
        'team_name': team_name,
        'opponent_name': opponent_name,
        'team_logo': None,
        'is_published': False,
        'published_at': None,
        'exists': True
    })


@app.route('/api/games/<int:game_id>', methods=['DELETE'])
@login_required
def delete_game(game_id):
    """Delete a game and all associated data"""
    conn = get_db()
    c = conn.cursor()
    
    # Delete associated data
    c.execute('DELETE FROM lineup_positions WHERE game_id = ?', (game_id,))
    c.execute('DELETE FROM game_player_status WHERE game_id = ?', (game_id,))
    c.execute('DELETE FROM published_lineup WHERE game_id = ?', (game_id,))
    c.execute('DELETE FROM published_player_order WHERE game_id = ?', (game_id,))
    
    # Delete the game's logo file if exists
    c.execute('SELECT team_logo FROM games WHERE id = ?', (game_id,))
    logo_row = c.fetchone()
    if logo_row and logo_row['team_logo']:
        logo_path = os.path.join(LOGO_FOLDER, logo_row['team_logo'])
        if os.path.exists(logo_path):
            os.remove(logo_path)
    
    # Delete the game
    c.execute('DELETE FROM games WHERE id = ?', (game_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})


@app.route('/api/games/<int:game_id>', methods=['GET'])
def get_game(game_id):
    conn = get_db()
    c = conn.cursor()
    
    # Check if is_published column exists
    c.execute("PRAGMA table_info(games)")
    columns = [row[1] for row in c.fetchall()]
    has_publish_columns = 'is_published' in columns
    
    if has_publish_columns:
        c.execute('SELECT id, game_date, team_name, opponent_name, team_logo, is_published, published_at FROM games WHERE id = ?', (game_id,))
    else:
        c.execute('SELECT id, game_date, team_name, opponent_name, team_logo FROM games WHERE id = ?', (game_id,))
    
    game = c.fetchone()
    conn.close()
    
    if game:
        game_dict = dict(game)
        game_dict['is_published'] = bool(game_dict.get('is_published')) if has_publish_columns else False
        if not has_publish_columns:
            game_dict['published_at'] = None
        return jsonify(game_dict)
    return jsonify({'error': 'Game not found'}), 404


@app.route('/api/games/<int:game_id>', methods=['PUT'])
@login_required
def update_game(game_id):
    data = request.json
    conn = get_db()
    c = conn.cursor()
    c.execute('''UPDATE games SET game_date = ?, team_name = ?, opponent_name = ?, 
                updated_at = CURRENT_TIMESTAMP WHERE id = ?''',
              (data.get('game_date'), data.get('team_name'), data.get('opponent_name'), game_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/games/<int:game_id>/logo', methods=['POST'])
@login_required
def upload_logo(game_id):
    if 'logo' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['logo']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"game_{game_id}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(LOGO_FOLDER, filename)
        
        # Delete old logo if exists
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT team_logo FROM games WHERE id = ?', (game_id,))
        old_logo = c.fetchone()
        if old_logo and old_logo['team_logo']:
            old_path = os.path.join(LOGO_FOLDER, old_logo['team_logo'])
            if os.path.exists(old_path):
                os.remove(old_path)
        
        # Save new logo
        file.save(filepath)
        
        # Update database
        c.execute('UPDATE games SET team_logo = ? WHERE id = ?', (filename, game_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'logo': filename})
    
    return jsonify({'error': 'Invalid file type'}), 400


@app.route('/api/games/<int:game_id>/logo', methods=['DELETE'])
@login_required
def delete_logo(game_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT team_logo FROM games WHERE id = ?', (game_id,))
    result = c.fetchone()
    
    if result and result['team_logo']:
        filepath = os.path.join(LOGO_FOLDER, result['team_logo'])
        if os.path.exists(filepath):
            os.remove(filepath)
        
        c.execute('UPDATE games SET team_logo = NULL WHERE id = ?', (game_id,))
        conn.commit()
    
    conn.close()
    return jsonify({'success': True})


# ========== Player Status Routes ==========
@app.route('/api/games/<int:game_id>/status', methods=['GET'])
def get_game_status(game_id):
    conn = get_db()
    c = conn.cursor()
    
    # Get main roster
    c.execute('SELECT player_name, is_female FROM main_roster ORDER BY player_name')
    main_roster = [{'name': row['player_name'], 'isFemale': bool(row['is_female'])} for row in c.fetchall()]
    
    # Get substitutes
    c.execute('SELECT player_name, is_female FROM substitutes ORDER BY player_name')
    substitutes = [{'name': row['player_name'], 'isFemale': bool(row['is_female'])} for row in c.fetchall()]
    
    # Get existing statuses
    c.execute('''SELECT player_name, status, is_substitute, kicking_order 
                FROM game_player_status WHERE game_id = ?''', (game_id,))
    existing_statuses = {row['player_name']: {'status': row['status'], 'isSub': bool(row['is_substitute']),
                                               'kickingOrder': row['kicking_order']} for row in c.fetchall()}
    
    # Auto-initialize main roster players as IN if they don't have a status yet
    statuses = {}
    max_order = 0
    
    # Get current max kicking order
    c.execute('SELECT COALESCE(MAX(kicking_order), 0) FROM game_player_status WHERE game_id = ?', (game_id,))
    max_order = c.fetchone()[0] or 0
    
    for player in main_roster:
        name = player['name']
        if name in existing_statuses:
            statuses[name] = existing_statuses[name]
        else:
            # Auto-add main roster player as IN
            max_order += 1
            c.execute('''INSERT INTO game_player_status (game_id, player_name, status, is_substitute, kicking_order)
                        VALUES (?, ?, 'IN', 0, ?)''', (game_id, name, max_order))
            statuses[name] = {'status': 'IN', 'isSub': False, 'kickingOrder': max_order}
    
    # For substitutes, keep existing status or default to OUT (don't auto-add)
    for player in substitutes:
        name = player['name']
        if name in existing_statuses:
            statuses[name] = existing_statuses[name]
        else:
            # Substitutes default to OUT - don't insert, just return the default
            statuses[name] = {'status': 'OUT', 'isSub': True, 'kickingOrder': None}
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'mainRoster': main_roster,
        'substitutes': substitutes,
        'statuses': statuses
    })


@app.route('/api/games/<int:game_id>/status/<player_name>', methods=['PUT'])
@login_required
def toggle_player_status(game_id, player_name):
    conn = get_db()
    c = conn.cursor()
    
    # Check if substitute
    c.execute('SELECT COUNT(*) as cnt FROM substitutes WHERE player_name = ?', (player_name,))
    is_sub = c.fetchone()['cnt'] > 0
    
    # Get current status
    c.execute('SELECT status FROM game_player_status WHERE game_id = ? AND player_name = ?',
              (game_id, player_name))
    result = c.fetchone()
    current_status = result['status'] if result else ('OUT' if is_sub else 'IN')
    
    if current_status == 'IN':
        new_status = 'OUT'
        kicking_order = None
    else:
        new_status = 'IN'
        c.execute('SELECT COALESCE(MAX(kicking_order), 0) FROM game_player_status WHERE game_id = ? AND status = ?',
                  (game_id, 'IN'))
        max_order = c.fetchone()[0] or 0
        kicking_order = max_order + 1
    
    c.execute('''INSERT OR REPLACE INTO game_player_status 
               (game_id, player_name, status, is_substitute, kicking_order) VALUES (?, ?, ?, ?, ?)''',
              (game_id, player_name, new_status, 1 if is_sub else 0, kicking_order))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'newStatus': new_status})


# ========== Lineup Routes ==========
@app.route('/api/games/<int:game_id>/lineup', methods=['GET'])
def get_lineup(game_id):
    conn = get_db()
    c = conn.cursor()
    
    # Get available players in kicking order
    c.execute('''SELECT player_name, COALESCE(kicking_order, 999) as order_val 
                FROM game_player_status 
                WHERE game_id = ? AND status = 'IN' 
                ORDER BY order_val, player_name''', (game_id,))
    available_players = [row['player_name'] for row in c.fetchall()]
    
    # Get player genders
    c.execute('SELECT player_name, is_female FROM main_roster')
    genders = {row['player_name']: bool(row['is_female']) for row in c.fetchall()}
    c.execute('SELECT player_name, is_female FROM substitutes')
    for row in c.fetchall():
        genders[row['player_name']] = bool(row['is_female'])
    
    # Get lineup positions
    c.execute('''SELECT inning, position, player_name FROM lineup_positions 
                WHERE game_id = ? ORDER BY inning, position''', (game_id,))
    lineup = {}
    for row in c.fetchall():
        inning = row['inning']
        if inning not in lineup:
            lineup[inning] = {}
        lineup[inning][row['player_name']] = row['position']
    
    # Get sit-out counts
    c.execute('''SELECT player_name, COUNT(*) as cnt FROM lineup_positions 
                WHERE game_id = ? AND position = 'Out' GROUP BY player_name''', (game_id,))
    sitOutCounts = {row['player_name']: row['cnt'] for row in c.fetchall()}
    
    conn.close()
    return jsonify({
        'availablePlayers': available_players,
        'genders': genders,
        'lineup': lineup,
        'sitOutCounts': sitOutCounts,
        'positions': POSITIONS,
        'abbreviations': POSITION_ABBREVIATIONS
    })


@app.route('/api/games/<int:game_id>/lineup/<player_name>/<int:inning>', methods=['PUT'])
@login_required
def update_lineup_position(game_id, player_name, inning):
    data = request.json
    new_position = data.get('position', '')
    
    conn = get_db()
    c = conn.cursor()
    
    # Delete old position for this player in this inning
    c.execute('''DELETE FROM lineup_positions 
               WHERE game_id = ? AND inning = ? AND player_name = ?''',
              (game_id, inning, player_name))
    
    # Insert new position if not empty
    if new_position:
        c.execute('''INSERT INTO lineup_positions (game_id, inning, position, player_name) 
                    VALUES (?, ?, ?, ?)''', (game_id, inning, new_position, player_name))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/games/<int:game_id>/lineup/copy', methods=['POST'])
@login_required
def copy_inning(game_id):
    conn = get_db()
    c = conn.cursor()
    
    # Get inning 1 positions
    c.execute('SELECT position, player_name FROM lineup_positions WHERE game_id = ? AND inning = 1',
              (game_id,))
    first_inning = c.fetchall()
    
    # Copy to innings 2-7
    for inning_num in range(2, 8):
        c.execute('DELETE FROM lineup_positions WHERE game_id = ? AND inning = ?', (game_id, inning_num))
        for row in first_inning:
            if row['position']:
                c.execute('INSERT INTO lineup_positions (game_id, inning, position, player_name) VALUES (?, ?, ?, ?)',
                          (game_id, inning_num, row['position'], row['player_name']))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/games/<int:game_id>/lineup/reset', methods=['POST'])
@login_required
def reset_lineup(game_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM lineup_positions WHERE game_id = ?', (game_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/games/<int:game_id>/order/<player_name>', methods=['PUT'])
@login_required
def update_player_order(game_id, player_name):
    data = request.json
    direction = data.get('direction')  # 'up' or 'down'
    
    conn = get_db()
    c = conn.cursor()
    
    # Get current player's order
    c.execute('SELECT kicking_order FROM game_player_status WHERE game_id = ? AND player_name = ?',
              (game_id, player_name))
    current_order = c.fetchone()['kicking_order']
    
    if direction == 'up':
        # Find player above
        c.execute('''SELECT player_name, kicking_order FROM game_player_status 
                    WHERE game_id = ? AND status = 'IN' AND kicking_order < ?
                    ORDER BY kicking_order DESC LIMIT 1''', (game_id, current_order))
    else:
        # Find player below
        c.execute('''SELECT player_name, kicking_order FROM game_player_status 
                    WHERE game_id = ? AND status = 'IN' AND kicking_order > ?
                    ORDER BY kicking_order ASC LIMIT 1''', (game_id, current_order))
    
    swap_player = c.fetchone()
    if swap_player:
        # Swap orders
        c.execute('UPDATE game_player_status SET kicking_order = ? WHERE game_id = ? AND player_name = ?',
                  (swap_player['kicking_order'], game_id, player_name))
        c.execute('UPDATE game_player_status SET kicking_order = ? WHERE game_id = ? AND player_name = ?',
                  (current_order, game_id, swap_player['player_name']))
        conn.commit()
    
    conn.close()
    return jsonify({'success': True})


@app.route('/api/games/<int:game_id>/reorder', methods=['PUT'])
@login_required
def reorder_players(game_id):
    """Bulk reorder players. Expects {"order": ["Player A", "Player B", ...]}"""
    data = request.json
    order = data.get('order', [])
    
    conn = get_db()
    c = conn.cursor()
    for idx, player_name in enumerate(order):
        c.execute('UPDATE game_player_status SET kicking_order = ? WHERE game_id = ? AND player_name = ?',
                  (idx, game_id, player_name))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ========== Publish Routes ==========
@app.route('/api/games/<int:game_id>/publish', methods=['POST'])
@login_required
def publish_lineup(game_id):
    """Publish the current lineup, making it visible to the public"""
    conn = get_db()
    c = conn.cursor()
    
    # Clear existing published data for this game
    c.execute('DELETE FROM published_lineup WHERE game_id = ?', (game_id,))
    c.execute('DELETE FROM published_player_order WHERE game_id = ?', (game_id,))
    
    # Copy current lineup to published
    c.execute('''INSERT INTO published_lineup (game_id, inning, position, player_name)
                SELECT game_id, inning, position, player_name FROM lineup_positions WHERE game_id = ?''',
              (game_id,))
    
    # Copy current player order to published
    c.execute('''INSERT INTO published_player_order (game_id, player_name, kicking_order)
                SELECT game_id, player_name, kicking_order FROM game_player_status 
                WHERE game_id = ? AND status = 'IN' ''', (game_id,))
    
    # Mark game as published
    c.execute('''UPDATE games SET is_published = 1, published_at = CURRENT_TIMESTAMP WHERE id = ?''',
              (game_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'published': True})


@app.route('/api/games/<int:game_id>/unpublish', methods=['POST'])
@login_required
def unpublish_lineup(game_id):
    """Unpublish the lineup, hiding it from public view"""
    conn = get_db()
    c = conn.cursor()
    
    # Clear published data
    c.execute('DELETE FROM published_lineup WHERE game_id = ?', (game_id,))
    c.execute('DELETE FROM published_player_order WHERE game_id = ?', (game_id,))
    
    # Mark game as unpublished
    c.execute('''UPDATE games SET is_published = 0, published_at = NULL WHERE id = ?''', (game_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'published': False})


@app.route('/api/games/<int:game_id>/lineup/published', methods=['GET'])
def get_published_lineup(game_id):
    """Get the published lineup for public viewing"""
    conn = get_db()
    c = conn.cursor()
    
    # Check if is_published column exists
    c.execute("PRAGMA table_info(games)")
    columns = [row[1] for row in c.fetchall()]
    has_publish_columns = 'is_published' in columns
    
    # Check if game is published
    is_published = False
    if has_publish_columns:
        c.execute('SELECT is_published FROM games WHERE id = ?', (game_id,))
        game = c.fetchone()
        is_published = game and bool(game['is_published'])
    
    if not is_published:
        conn.close()
        return jsonify({
            'published': False,
            'availablePlayers': [],
            'genders': {},
            'lineup': {},
            'sitOutCounts': {},
            'positions': POSITIONS,
            'abbreviations': POSITION_ABBREVIATIONS
        })
    
    # Get published player order
    c.execute('''SELECT player_name, kicking_order FROM published_player_order 
                WHERE game_id = ? ORDER BY kicking_order, player_name''', (game_id,))
    available_players = [row['player_name'] for row in c.fetchall()]
    
    # Get player genders
    c.execute('SELECT player_name, is_female FROM main_roster')
    genders = {row['player_name']: bool(row['is_female']) for row in c.fetchall()}
    c.execute('SELECT player_name, is_female FROM substitutes')
    for row in c.fetchall():
        genders[row['player_name']] = bool(row['is_female'])
    
    # Get published lineup positions
    c.execute('''SELECT inning, position, player_name FROM published_lineup 
                WHERE game_id = ? ORDER BY inning, position''', (game_id,))
    lineup = {}
    for row in c.fetchall():
        inning = row['inning']
        if inning not in lineup:
            lineup[inning] = {}
        lineup[inning][row['player_name']] = row['position']
    
    # Get sit-out counts from published lineup
    c.execute('''SELECT player_name, COUNT(*) as cnt FROM published_lineup 
                WHERE game_id = ? AND position = 'Out' GROUP BY player_name''', (game_id,))
    sitOutCounts = {row['player_name']: row['cnt'] for row in c.fetchall()}
    
    conn.close()
    return jsonify({
        'published': True,
        'availablePlayers': available_players,
        'genders': genders,
        'lineup': lineup,
        'sitOutCounts': sitOutCounts,
        'positions': POSITIONS,
        'abbreviations': POSITION_ABBREVIATIONS
    })


# ========== Settings Routes ==========
def get_setting(key, default=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()


@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    return jsonify({
        'groupme_access_token': get_setting('groupme_access_token', ''),
        'groupme_group_id': get_setting('groupme_group_id', ''),
    })


@app.route('/api/settings', methods=['POST'])
@login_required
def update_settings():
    data = request.json
    for key in ('groupme_access_token', 'groupme_group_id'):
        if key in data:
            set_setting(key, data[key].strip())
    return jsonify({'success': True})


# ========== GroupMe Routes ==========
@app.route('/api/roster/<name>/groupme', methods=['PUT'])
@login_required
def set_player_groupme(name):
    data = request.json
    gm_id = data.get('groupmeUserId', '').strip()
    conn = get_db()
    c = conn.cursor()
    # Try main roster first, then substitutes
    c.execute('UPDATE main_roster SET groupme_user_id = ? WHERE player_name = ?', (gm_id or None, name))
    if c.rowcount == 0:
        c.execute('UPDATE substitutes SET groupme_user_id = ? WHERE player_name = ?', (gm_id or None, name))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/groupme/members', methods=['GET'])
@login_required
def groupme_members():
    token = get_setting('groupme_access_token')
    group_id = get_setting('groupme_group_id')
    if not token or not group_id:
        return jsonify({'error': 'GroupMe not configured. Set token and group ID in Settings.'}), 400
    try:
        members = gm.get_group_members(token, group_id)
        return jsonify(members)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/groupme/post-event/<int:game_id>', methods=['POST'])
@login_required
def post_groupme_event(game_id):
    token = get_setting('groupme_access_token')
    group_id = get_setting('groupme_group_id')
    if not token or not group_id:
        return jsonify({'error': 'GroupMe not configured'}), 400

    conn = get_db()
    c = conn.cursor()

    # Check if already posted
    c.execute('SELECT id FROM groupme_events WHERE game_id = ? AND event_type = ?', (game_id, 'event'))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'Event already posted for this game'}), 400

    # Get game info
    c.execute('SELECT game_date, opponent_name FROM games WHERE id = ?', (game_id,))
    game = c.fetchone()
    if not game:
        conn.close()
        return jsonify({'error': 'Game not found'}), 404

    # Get players marked IN
    c.execute("SELECT player_name FROM game_player_status WHERE game_id = ? AND status = 'IN'", (game_id,))
    players_in = [row['player_name'] for row in c.fetchall()]

    # Build groupme user map from both roster tables
    c.execute('SELECT player_name, groupme_user_id FROM main_roster WHERE groupme_user_id IS NOT NULL')
    gm_map = {row['player_name']: row['groupme_user_id'] for row in c.fetchall()}
    c.execute('SELECT player_name, groupme_user_id FROM substitutes WHERE groupme_user_id IS NOT NULL')
    gm_map.update({row['player_name']: row['groupme_user_id'] for row in c.fetchall()})

    game_date = game['game_date']
    opponent = game['opponent_name']

    results = {}
    gm_event_id = None

    # 1) Create calendar event
    try:
        event_name = f'Kickball vs. {opponent}' if opponent else 'Kickball Game'
        start_at = f'{game_date}T19:00:00-04:00'
        event_resp = gm.create_event(token, group_id, event_name, start_at=start_at)
        # Try to extract the event ID from the response
        resp_data = event_resp.get('response', {})
        if isinstance(resp_data, dict):
            gm_event_id = resp_data.get('event', {}).get('event_id') or resp_data.get('event_id')
        results['event'] = 'created'
    except Exception as e:
        results['event'] = f'failed: {e}'

    # 2) Post message with @mentions
    try:
        text, mentions = gm.build_game_message(game_date, opponent, players_in, gm_map)
        gm.post_message(token, group_id, text, mentions)
        results['message'] = 'sent'
    except Exception as e:
        results['message'] = f'failed: {e}'

    # Track it
    c.execute('INSERT INTO groupme_events (game_id, event_type, groupme_event_id, groupme_response) VALUES (?, ?, ?, ?)',
              (game_id, 'event', gm_event_id, str(results)))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'results': results})


@app.route('/api/groupme/status/<int:game_id>', methods=['GET'])
@login_required
def groupme_status(game_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT event_type, posted_at, groupme_response FROM groupme_events WHERE game_id = ? ORDER BY posted_at DESC', (game_id,))
    events = [{'type': row['event_type'], 'postedAt': row['posted_at'], 'response': row['groupme_response']} for row in c.fetchall()]
    conn.close()
    return jsonify(events)


def render_lineup_image(game_id):
    """Render the lineup as a PNG image using Pillow. Returns bytes."""
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT game_date, team_name, opponent_name FROM games WHERE id = ?', (game_id,))
    game = c.fetchone()
    if not game:
        conn.close()
        return None

    # Get published lineup if available, otherwise current lineup
    c.execute("PRAGMA table_info(games)")
    cols = [row[1] for row in c.fetchall()]
    is_published = False
    if 'is_published' in cols:
        c.execute('SELECT is_published FROM games WHERE id = ?', (game_id,))
        is_published = bool(c.fetchone()['is_published'])

    if is_published:
        c.execute('''SELECT player_name, kicking_order FROM published_player_order 
                    WHERE game_id = ? ORDER BY kicking_order, player_name''', (game_id,))
        players = [row['player_name'] for row in c.fetchall()]
        c.execute('SELECT inning, position, player_name FROM published_lineup WHERE game_id = ?', (game_id,))
    else:
        c.execute('''SELECT player_name, kicking_order FROM game_player_status 
                    WHERE game_id = ? AND status = 'IN' ORDER BY kicking_order, player_name''', (game_id,))
        players = [row['player_name'] for row in c.fetchall()]
        c.execute('SELECT inning, position, player_name FROM lineup_positions WHERE game_id = ?', (game_id,))

    lineup = {}
    for row in c.fetchall():
        inn = row['inning']
        if inn not in lineup:
            lineup[inn] = {}
        lineup[inn][row['player_name']] = row['position']

    conn.close()

    if not players:
        return None

    # Image dimensions
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_hdr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except (OSError, IOError):
        font = ImageFont.load_default()
        font_sm = font
        font_hdr = font

    col_widths = [30, 140] + [50] * 7  # #, Name, Inn1-7
    row_height = 26
    header_height = 50
    padding = 10
    table_width = sum(col_widths) + padding * 2
    table_height = header_height + row_height + (len(players) * row_height) + padding * 2

    img = Image.new('RGB', (table_width, table_height), '#1C2128')
    draw = ImageDraw.Draw(img)

    # Title
    title = f"{game['team_name']} vs {game['opponent_name'] or 'TBD'}  —  {game['game_date']}"
    draw.text((padding, padding), title, fill='#FFFFFF', font=font_hdr)

    # Table header
    y = header_height
    x = padding
    header_labels = ['#', 'Player'] + [f'Inn {i}' for i in range(1, 8)]
    draw.rectangle([padding, y, table_width - padding, y + row_height], fill='#2C3E50')
    for i, label in enumerate(header_labels):
        draw.text((x + 4, y + 5), label, fill='#FFFFFF', font=font)
        x += col_widths[i]

    # Player rows
    for idx, player in enumerate(players):
        y = header_height + row_height + (idx * row_height)
        bg = '#21262D' if idx % 2 == 0 else '#1C2128'
        draw.rectangle([padding, y, table_width - padding, y + row_height], fill=bg)

        x = padding
        draw.text((x + 4, y + 5), str(idx + 1), fill='#8B949E', font=font_sm)
        x += col_widths[0]
        draw.text((x + 4, y + 5), player[:16], fill='#E6EDF3', font=font_sm)
        x += col_widths[1]

        for inn in range(1, 8):
            pos = lineup.get(inn, {}).get(player, '-')
            abbrev = POSITION_ABBREVIATIONS.get(pos, pos) if pos != '-' else '-'
            color = '#95A5A6' if pos == 'Out' else '#27AE60' if pos != '-' else '#484F58'
            draw.text((x + 4, y + 5), abbrev, fill=color, font=font_sm)
            x += col_widths[2]

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


@app.route('/api/games/<int:game_id>/lineup-image', methods=['GET'])
@login_required
def get_lineup_image(game_id):
    """Generate and return the lineup as a PNG image."""
    img_bytes = render_lineup_image(game_id)
    if not img_bytes:
        return jsonify({'error': 'No lineup to render'}), 404
    return img_bytes, 200, {'Content-Type': 'image/png'}


@app.route('/api/groupme/post-lineup-image/<int:game_id>', methods=['POST'])
@login_required
def post_lineup_image_to_groupme(game_id):
    """Render the lineup as an image and post it to GroupMe.
    On re-publish, deletes the old message first, then posts + pins the new one.
    """
    token = get_setting('groupme_access_token')
    group_id = get_setting('groupme_group_id')
    if not token or not group_id:
        return jsonify({'error': 'GroupMe not configured'}), 400

    img_bytes = render_lineup_image(game_id)
    if not img_bytes:
        return jsonify({'error': 'No lineup to render'}), 404

    try:
        conn = get_db()
        c = conn.cursor()

        # Check for a previous lineup image message to delete
        c.execute('''SELECT groupme_event_id FROM groupme_events 
                    WHERE game_id = ? AND event_type = 'lineup_image' 
                    ORDER BY posted_at DESC LIMIT 1''', (game_id,))
        prev = c.fetchone()
        if prev and prev['groupme_event_id']:
            try:
                gm.delete_message(token, group_id, prev['groupme_event_id'])
            except Exception:
                pass  # old message may already be gone

        # Upload new image and post
        image_url = gm.upload_image(token, img_bytes)
        c.execute('SELECT game_date, opponent_name FROM games WHERE id = ?', (game_id,))
        game = c.fetchone()

        caption = f'Lineup: {game["game_date"]} vs {game["opponent_name"] or "TBD"}'
        resp = gm.post_image_message(token, group_id, caption, image_url)

        # Extract the message_id from the response
        msg_id = None
        msg_data = resp.get('response', {}).get('message', {})
        if isinstance(msg_data, dict):
            msg_id = msg_data.get('id')

        # Pin the new message
        if msg_id:
            try:
                gm.pin_message(token, group_id, msg_id)
            except Exception:
                pass  # pinning is best-effort

        # Track it (store message_id in groupme_event_id for future delete/replace)
        c.execute('INSERT INTO groupme_events (game_id, event_type, groupme_event_id, groupme_response) VALUES (?, ?, ?, ?)',
                  (game_id, 'lineup_image', msg_id, f'image_url={image_url}'))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'image_url': image_url, 'message_id': msg_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
