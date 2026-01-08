"""
UKP Kickball Roster Manager - Flask Backend
"""
from flask import Flask, jsonify, request, send_from_directory, session
from functools import wraps
import sqlite3
import hashlib
import os
import uuid
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

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
    c.execute('SELECT player_name, is_female FROM main_roster ORDER BY player_name')
    roster = [{'name': row['player_name'], 'isFemale': bool(row['is_female'])} for row in c.fetchall()]
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
    c.execute('SELECT player_name, is_female FROM substitutes ORDER BY player_name')
    subs = [{'name': row['player_name'], 'isFemale': bool(row['is_female'])} for row in c.fetchall()]
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
    
    # Check if game already exists for this date
    c.execute('SELECT id FROM games WHERE game_date = ?', (game_date,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'A game already exists for this date'}), 400
    
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
