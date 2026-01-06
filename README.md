# UKP Kickball Roster Manager

A web application for managing kickball team rosters, lineups, and game planning. Built with Flask (Python) backend and vanilla HTML/CSS/JavaScript frontend.

## Features

- **Main Roster Management**: Add and manage your core team roster with gender tracking
- **Substitute Players**: Manage substitute players that can be added on a game-by-game basis
- **Game Lineup Setup**: 
  - 7 innings with 11 field positions + "Out" position
  - Spreadsheet-style interface for setting lineups
  - Player status management (IN/OUT for each game)
  - Kicking order management with up/down controls
- **Validation & Warnings**:
  - Female player count per inning (requires 4)
  - Duplicate position detection
  - Unused position tracking
  - Player sit-out counts per game
- **Game Details**:
  - Date picker (defaults to next Thursday)
  - Editable team name (default: "Unsolicited Kick Pics")
  - Editable opponent name
- **Authentication**: 
  - Public viewing of lineups (read-only)
  - Login required for editing
- **Modern UI**:
  - Dark theme with sports aesthetic
  - Mobile responsive design
  - Smooth animations

## Quick Start

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open http://localhost:8080 in your browser

### Docker

Build and run with Docker:

```bash
docker build -t ukp-kickball .
docker run -p 8080:8080 -v $(pwd)/data:/app/data ukp-kickball
```

Or use Docker Compose:

```bash
docker-compose up -d
```

## First Time Setup

1. Open the application in your browser
2. Click "Login" and create the first user account
3. Login with your credentials
4. Add players to your main roster in the "Roster" tab
5. Optionally add substitute players

## Setting Up a Game

1. Go to the "Game Lineup" tab
2. Adjust the game date, team name, and opponent name as needed
3. Toggle players IN (green) or OUT (gray) for the game
4. Expand "Substitutes" to add substitutes to the game
5. Use the spreadsheet view to set positions for each inning
6. Use ↑↓ buttons to reorder the kicking lineup
7. Click "Copy Inning 1 to All" to quickly fill all innings

## Viewing Lineups

- Use the "View Lineup" tab to see lineups for any game
- This view is accessible without login (read-only)
- Select different games from the dropdown

## Positions

Each inning has 12 positions:
- **P** - Pitcher
- **C** - Catcher
- **1st** - First Base
- **2nd** - Second Base
- **3rd** - Third Base
- **SS** - Short Stop
- **LF** - Left Field
- **LC** - Left Center
- **CF** - Center Field
- **RC** - Right Center
- **RF** - Right Field
- **Out** - Sitting out the inning

## Tech Stack

- **Backend**: Flask (Python)
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Database**: SQLite
- **Production Server**: Gunicorn

## Project Structure

```
UKP/
├── app.py              # Flask backend API
├── requirements.txt    # Python dependencies
├── Dockerfile         # Container configuration
├── docker-compose.yml # Docker Compose config
├── static/
│   ├── index.html     # Main HTML page
│   ├── css/
│   │   └── style.css  # Styles
│   ├── js/
│   │   └── app.js     # Frontend JavaScript
│   └── images/
│       └── logo.png   # Team logo
└── data/
    └── kickball_roster.db  # SQLite database (created automatically)
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret key | `ukp-kickball-secret-key-change-in-production` |
| `PORT` | Server port | `8080` |
| `FLASK_DEBUG` | Enable debug mode | `false` |

## Security Notes

- Passwords are hashed using SHA256
- Only the first user can be created through the UI
- For production, set a strong `SECRET_KEY` environment variable
- Consider using HTTPS (via reverse proxy like nginx)
- The SQLite database is stored in `/app/data` (Docker) or `./data` (local)

## License

MIT License
