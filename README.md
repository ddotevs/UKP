# UKP Kickball Roster Manager

A Streamlit web application for managing kickball team rosters, lineups, and game planning.

## Features

- **Main Roster Management**: Add and manage your core team roster
- **Substitute Players**: Manage substitute players that can be added on a game-by-game basis
- **Game Lineup Setup**: 
  - 7 innings with 11 positions + "Out" position
  - Drag-and-drop style interface for setting lineups
  - Player status management (IN/OUT for each game)
- **Statistics Tracking**:
  - Count of innings with unused positions
  - Player sit-out counts per game
- **Game Details**:
  - Date picker (defaults to next Thursday)
  - Editable team name (default: "Unsolicited Kick Pics")
  - Editable opponent name
- **Authentication**: 
  - Public viewing of lineups
  - Login required for editing

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd UKP
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
streamlit run app.py
```

## Usage

### First Time Setup

1. When you first run the app, create a user account in the sidebar
2. Login with your credentials
3. Add players to your main roster in the "Main Roster" tab
4. Optionally add substitute players in the "Substitutes" tab

### Setting Up a Game

1. Go to the "Game Lineup" tab
2. Adjust the game date, team name, and opponent name as needed
3. Move players from main roster to IN (available) or OUT (not available)
4. Add substitute players to the game if needed
5. Set the lineup for each of the 7 innings by selecting players for each position
6. The app will highlight players who are available but not yet in the lineup

### Viewing Lineups

- Use the "View Lineup" tab to see lineups for any game
- View statistics including player sit-out counts and incomplete innings

## Positions

Each inning has 12 positions:
- Pitcher
- Catcher
- First Base
- Second Base
- Third Base
- Short Stop
- Left Field
- Left Center
- Center Field
- Right Center
- Right Field
- Out (for players sitting the inning)

## Database

The app uses SQLite for data storage. The database file (`kickball_roster.db`) is created automatically on first run.

## Deployment to AWS

This app can be deployed to AWS using various methods:

### Option 1: AWS App Runner
1. Create a Dockerfile (see below)
2. Push to a container registry (ECR)
3. Deploy via AWS App Runner

### Option 2: EC2 with Streamlit
1. Launch an EC2 instance
2. Install dependencies
3. Run Streamlit with public access
4. Configure security groups appropriately

### Option 3: ECS/Fargate
1. Containerize the application
2. Deploy to ECS or Fargate
3. Use Application Load Balancer for public access

## Dockerfile Example

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

## Security Notes

- Passwords are hashed using SHA256
- Only the first user can be created through the UI
- For production, consider:
  - Using stronger password hashing (bcrypt)
  - Implementing proper session management
  - Using environment variables for sensitive data
  - Setting up HTTPS
  - Using a more robust database (PostgreSQL)

## License

MIT License

