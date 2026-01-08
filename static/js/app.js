/**
 * UKP Kickball Roster Manager - Frontend Application
 */

// ========================================
// State Management
// ========================================
const state = {
    authenticated: false,
    username: null,
    currentTab: 'gameLineup',
    currentGame: null,
    games: [],
    mainRoster: [],
    substitutes: [],
    playerStatuses: {},
    lineup: {},
    availablePlayers: [],
    genders: {},
    sitOutCounts: {},
    positions: [],
    abbreviations: {}
};

// ========================================
// API Helpers
// ========================================
async function api(endpoint, options = {}) {
    const response = await fetch(endpoint, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    });
    
    const data = await response.json();
    
    if (!response.ok) {
        throw new Error(data.error || 'API request failed');
    }
    
    return data;
}

// ========================================
// Auth Functions
// ========================================
async function checkAuthStatus() {
    try {
        const data = await api('/api/auth/status');
        state.authenticated = data.authenticated;
        state.username = data.username;
    } catch (error) {
        console.error('Auth check failed:', error);
        state.authenticated = false;
    }
    
    updateAuthUI();
    updateTabs();
}

async function checkHasUsers() {
    try {
        const data = await api('/api/auth/has-users');
        document.getElementById('registerSection').style.display = data.hasUsers ? 'none' : 'block';
    } catch (error) {
        console.error('Has users check failed:', error);
    }
}

async function login(username, password) {
    try {
        const data = await api('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        
        state.authenticated = true;
        state.username = data.username;
        closeModal('loginModal');
        updateAuthUI();
        updateTabs();
        loadCurrentTab();
        
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

async function logout() {
    try {
        await api('/api/auth/logout', { method: 'POST' });
    } catch (error) {
        console.error('Logout failed:', error);
    }
    
    state.authenticated = false;
    state.username = null;
    updateAuthUI();
    updateTabs();
    loadCurrentTab();
}

async function register(username, password) {
    try {
        await api('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        
        return { success: true };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

// ========================================
// UI Update Functions
// ========================================
function updateAuthUI() {
    const authSection = document.getElementById('authSection');
    
    if (state.authenticated) {
        authSection.innerHTML = `
            <div class="user-info">
                <div class="user-avatar">${state.username.charAt(0).toUpperCase()}</div>
                <span>${state.username}</span>
            </div>
            <button class="btn btn-ghost" onclick="logout()">Logout</button>
        `;
    } else {
        authSection.innerHTML = `
            <button class="btn btn-primary" onclick="openModal('loginModal')">Login</button>
        `;
    }
    
    // Show/hide view banner - hide if authenticated OR if there are published lineups
    updateViewBanner();
}

function updateViewBanner() {
    const viewBanner = document.getElementById('viewBanner');
    if (state.authenticated) {
        // Always hide for authenticated users
        viewBanner.style.display = 'none';
    } else {
        // For unauthenticated users, hide if there are published games
        const hasPublishedGames = state.games && state.games.some(g => g.is_published);
        viewBanner.style.display = hasPublishedGames ? 'none' : 'flex';
    }
}

function updateTabs() {
    const tabNav = document.getElementById('tabNav');
    
    if (state.authenticated) {
        tabNav.innerHTML = `
            <button class="tab-btn ${state.currentTab === 'gameLineup' ? 'active' : ''}" 
                    onclick="switchTab('gameLineup')">Game Lineup</button>
            <button class="tab-btn ${state.currentTab === 'roster' ? 'active' : ''}" 
                    onclick="switchTab('roster')">Roster</button>
            <button class="tab-btn ${state.currentTab === 'viewLineup' ? 'active' : ''}" 
                    onclick="switchTab('viewLineup')">View Lineup</button>
        `;
    } else {
        tabNav.innerHTML = `
            <button class="tab-btn active" onclick="switchTab('viewLineup')">View Lineup</button>
        `;
        state.currentTab = 'viewLineup';
    }
}

function switchTab(tab) {
    state.currentTab = tab;
    
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.textContent.toLowerCase().includes(tab.toLowerCase().replace(/([A-Z])/g, ' $1').trim().toLowerCase()));
    });
    
    // Show/hide panels
    document.getElementById('gameLineupPanel').style.display = tab === 'gameLineup' ? 'block' : 'none';
    document.getElementById('rosterPanel').style.display = tab === 'roster' ? 'block' : 'none';
    document.getElementById('viewLineupPanel').style.display = tab === 'viewLineup' ? 'block' : 'none';
    
    // Update active state properly
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    const tabs = { gameLineup: 0, roster: 1, viewLineup: state.authenticated ? 2 : 0 };
    const activeIndex = tabs[tab];
    const buttons = document.querySelectorAll('.tab-btn');
    if (buttons[activeIndex]) {
        buttons[activeIndex].classList.add('active');
    }
    
    loadCurrentTab();
}

async function loadCurrentTab() {
    switch (state.currentTab) {
        case 'gameLineup':
            await loadGameLineup();
            break;
        case 'roster':
            await loadRoster();
            break;
        case 'viewLineup':
            await loadViewLineup();
            break;
    }
}

// ========================================
// Game Lineup Functions
// ========================================
async function loadGameLineup() {
    if (!state.authenticated) return;
    
    const panel = document.getElementById('gameLineupPanel');
    panel.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    
    try {
        // Load current game (no longer auto-creates)
        const gameResponse = await api('/api/games/current');
        
        // Check if a game exists
        if (!gameResponse.exists) {
            // No game for this week - show create game UI
            state.currentGame = null;
            state.nextThursday = gameResponse.next_thursday;
            renderNoGameUI();
            return;
        }
        
        state.currentGame = gameResponse;
        
        // Load game status (players and their IN/OUT status)
        const statusData = await api(`/api/games/${state.currentGame.id}/status`);
        state.mainRoster = statusData.mainRoster;
        state.substitutes = statusData.substitutes;
        state.playerStatuses = statusData.statuses;
        
        // Load lineup
        const lineupData = await api(`/api/games/${state.currentGame.id}/lineup`);
        state.availablePlayers = lineupData.availablePlayers;
        state.genders = lineupData.genders;
        state.lineup = lineupData.lineup;
        state.sitOutCounts = lineupData.sitOutCounts;
        state.positions = lineupData.positions;
        state.abbreviations = lineupData.abbreviations;
        
        renderGameLineup();
    } catch (error) {
        console.error('Failed to load game lineup:', error);
        panel.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>Failed to load game lineup</p></div>`;
    }
}

function renderNoGameUI() {
    const panel = document.getElementById('gameLineupPanel');
    
    panel.innerHTML = `
        <div class="card">
            <div class="empty-state">
                <div class="empty-state-icon">📅</div>
                <h3>No Game Scheduled</h3>
                <p>No game exists for ${state.nextThursday}</p>
                <form class="create-game-form" onsubmit="createNewGame(event)">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="newGameDate">Game Date</label>
                            <input type="date" id="newGameDate" class="form-input" value="${state.nextThursday}" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="newTeamName">Team Name</label>
                            <input type="text" id="newTeamName" class="form-input" placeholder="Your team name">
                        </div>
                        <div class="form-group">
                            <label for="newOpponentName">Opponent</label>
                            <input type="text" id="newOpponentName" class="form-input" placeholder="Opponent name">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-primary">Create Game</button>
                </form>
            </div>
        </div>
    `;
}

async function createNewGame(event) {
    event.preventDefault();
    
    const gameDate = document.getElementById('newGameDate').value;
    const teamName = document.getElementById('newTeamName').value.trim();
    const opponentName = document.getElementById('newOpponentName').value.trim();
    
    try {
        const game = await api('/api/games', {
            method: 'POST',
            body: JSON.stringify({
                game_date: gameDate,
                team_name: teamName,
                opponent_name: opponentName
            })
        });
        
        state.currentGame = game;
        await loadGameLineup();
    } catch (error) {
        alert('Failed to create game: ' + error.message);
    }
}

function renderGameLineup() {
    const panel = document.getElementById('gameLineupPanel');
    
    // Build player status grid
    const mainRosterHtml = state.mainRoster.map(player => {
        const status = state.playerStatuses[player.name]?.status || 'IN';
        return `
            <button class="player-toggle status-${status.toLowerCase()}" 
                    onclick="togglePlayerStatus('${escapeHtml(player.name)}')">
                ${escapeHtml(player.name)}${player.isFemale ? ' ♀' : ''}
            </button>
        `;
    }).join('');
    
    const substitutesHtml = state.substitutes.map(player => {
        const status = state.playerStatuses[player.name]?.status || 'OUT';
        return `
            <button class="player-toggle status-${status.toLowerCase()}" 
                    onclick="togglePlayerStatus('${escapeHtml(player.name)}')">
                ${escapeHtml(player.name)}${player.isFemale ? ' ♀' : ''}
            </button>
        `;
    }).join('');
    
    // Build lineup table
    const lineupTableHtml = buildLineupTable();
    
    // Build logo section HTML
    const currentLogo = state.currentGame.team_logo;
    const logoPreviewHtml = currentLogo 
        ? `<img src="/logos/${currentLogo}" alt="Team Logo">`
        : '<span class="text-muted">No logo uploaded</span>';
    
    // Build publish status section
    const isPublished = state.currentGame.is_published;
    const publishedAt = state.currentGame.published_at;
    const publishStatusHtml = isPublished
        ? `<div class="publish-status published">
             <span class="publish-status-icon">✓</span>
             <span>Published${publishedAt ? ` on ${new Date(publishedAt).toLocaleString()}` : ''}</span>
           </div>`
        : `<div class="publish-status unpublished">
             <span class="publish-status-icon">○</span>
             <span>Not Published - Lineup is not visible to the public</span>
           </div>`;
    
    const publishButtonHtml = isPublished
        ? `<button class="btn btn-secondary" onclick="unpublishLineup()">
             Unpublish Lineup
           </button>
           <button class="btn btn-success" onclick="publishLineup()">
             Update Published Lineup
           </button>`
        : `<button class="btn btn-success" onclick="publishLineup()">
             Publish Lineup
           </button>`;
    
    panel.innerHTML = `
        <div class="card publish-card">
            <div class="publish-section">
                ${publishStatusHtml}
                <div class="publish-actions">
                    ${publishButtonHtml}
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Game Details</h3>
                <button class="btn btn-danger btn-sm" onclick="deleteGame()">Delete Game</button>
            </div>
            <div class="game-details">
                <div class="form-group">
                    <label>Game Date</label>
                    <input type="date" class="form-input" id="gameDate" 
                           value="${state.currentGame.game_date}" onchange="updateGameDetails()">
                </div>
                <div class="form-group">
                    <label>Team Name</label>
                    <input type="text" class="form-input" id="teamName" 
                           value="${escapeHtml(state.currentGame.team_name)}" onchange="updateGameDetails()">
                </div>
                <div class="form-group">
                    <label>Opponent</label>
                    <input type="text" class="form-input" id="opponentName" 
                           value="${escapeHtml(state.currentGame.opponent_name || '')}" 
                           placeholder="TBD" onchange="updateGameDetails()">
                </div>
            </div>
            
            <div class="logo-upload-section">
                <h4>Team Logo (displayed on public View Lineup)</h4>
                <div class="logo-preview">
                    ${logoPreviewHtml}
                </div>
                <div class="logo-upload-actions">
                    <div class="file-input-wrapper">
                        <button class="btn btn-secondary btn-sm">Upload Logo</button>
                        <input type="file" id="logoUpload" accept="image/*" onchange="uploadLogo(this)">
                    </div>
                    ${currentLogo ? '<button class="btn btn-ghost btn-sm" onclick="deleteLogo()">Remove Logo</button>' : ''}
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">Player Status</h3>
            </div>
            
            <div class="player-section">
                <div class="player-section-title">Main Roster</div>
                <div class="player-grid">
                    ${mainRosterHtml || '<p class="text-muted">No players in roster</p>'}
                </div>
            </div>
            
            <div class="player-section">
                <div class="collapsible-header" onclick="toggleCollapsible(this)">
                    <span class="collapsible-icon">▶</span>
                    <span class="player-section-title">Substitutes</span>
                </div>
                <div class="collapsible-content">
                    <div class="player-grid">
                        ${substitutesHtml || '<p class="text-muted">No substitutes</p>'}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="lineup-header">
                <h3 class="card-title">Lineup by Inning</h3>
                <div class="lineup-actions">
                    <button class="btn btn-secondary btn-sm" onclick="copyInning()">
                        Copy Inning 1 to All
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="resetLineup()">
                        Reset Lineup
                    </button>
                </div>
            </div>
            
            <div class="lineup-table-wrapper">
                ${lineupTableHtml}
            </div>
        </div>
    `;
}

function buildLineupTable() {
    if (state.availablePlayers.length === 0) {
        return `<div class="empty-state">
            <div class="empty-state-icon">👥</div>
            <p>No players available. Mark players as IN above.</p>
        </div>`;
    }
    
    // Build header with inning warnings
    let headerHtml = `
        <thead>
            <tr>
                <th style="min-width: 180px;">Player</th>
                <th style="width: 60px;">↑↓</th>
    `;
    
    for (let i = 1; i <= 7; i++) {
        const warnings = getInningWarnings(i);
        const warningIcon = warnings.length > 0 
            ? `<span class="inning-warning" title="${escapeHtml(warnings.join(' | '))}">⚠️</span>` 
            : '';
        headerHtml += `<th>Inn ${i} ${warningIcon}</th>`;
    }
    
    headerHtml += `<th>Out</th></tr></thead>`;
    
    // Build body
    let bodyHtml = '<tbody>';
    
    state.availablePlayers.forEach((player, index) => {
        const isFemale = state.genders[player] || false;
        const sitOutCount = state.sitOutCounts[player] || 0;
        
        bodyHtml += `
            <tr>
                <td>
                    <div class="player-name-cell">
                        <span class="player-order">${index + 1}.</span>
                        <span class="player-name">${escapeHtml(player)}</span>
                        ${isFemale ? '<span class="gender-indicator">♀</span>' : ''}
                    </div>
                </td>
                <td>
                    <div class="order-buttons">
                        <button class="order-btn" onclick="movePlayer('${escapeHtml(player)}', 'up')" 
                                ${index === 0 ? 'disabled' : ''}>↑</button>
                        <button class="order-btn" onclick="movePlayer('${escapeHtml(player)}', 'down')" 
                                ${index === state.availablePlayers.length - 1 ? 'disabled' : ''}>↓</button>
                    </div>
                </td>
        `;
        
        for (let inning = 1; inning <= 7; inning++) {
            const position = state.lineup[inning]?.[player] || '';
            const abbrev = position ? state.abbreviations[position] || position : '';
            const isOut = position === 'Out';
            const isDuplicate = checkDuplicatePosition(inning, position, player);
            
            bodyHtml += `
                <td>
                    <select class="position-select ${isOut ? 'position-out' : ''} ${isDuplicate ? 'has-duplicate' : ''}"
                            onchange="updatePosition('${escapeHtml(player)}', ${inning}, this.value)"
                            ${isDuplicate ? `title="Duplicate position!"` : ''}>
                        <option value="">-</option>
                        ${state.positions.map(pos => `
                            <option value="${pos}" ${position === pos ? 'selected' : ''}>
                                ${state.abbreviations[pos] || pos}
                            </option>
                        `).join('')}
                    </select>
                </td>
            `;
        }
        
        bodyHtml += `
                <td class="${sitOutCount > 0 ? 'sit-out-count' : 'sit-out-count zero'}">${sitOutCount}</td>
            </tr>
        `;
    });
    
    bodyHtml += '</tbody>';
    
    return `<table class="lineup-table">${headerHtml}${bodyHtml}</table>`;
}

function getInningWarnings(inning) {
    const warnings = [];
    
    // Count females on field
    let femaleCount = 0;
    const positionsUsed = new Set();
    const duplicates = new Set();
    
    for (const player of state.availablePlayers) {
        const position = state.lineup[inning]?.[player];
        if (position && position !== 'Out') {
            if (state.genders[player]) {
                femaleCount++;
            }
            if (positionsUsed.has(position)) {
                duplicates.add(position);
            }
            positionsUsed.add(position);
        }
    }
    
    if (femaleCount < 4 && positionsUsed.size > 0) {
        warnings.push(`Only ${femaleCount} females on field (need 4)`);
    }
    
    if (duplicates.size > 0) {
        const dupAbbrevs = Array.from(duplicates).map(p => state.abbreviations[p] || p);
        warnings.push(`Duplicate: ${dupAbbrevs.join(', ')}`);
    }
    
    // Check for unused positions
    const playingPositions = state.positions.filter(p => p !== 'Out');
    const unused = playingPositions.filter(p => !positionsUsed.has(p));
    if (unused.length > 0 && positionsUsed.size > 0) {
        const unusedAbbrevs = unused.slice(0, 3).map(p => state.abbreviations[p] || p);
        if (unused.length > 3) {
            unusedAbbrevs.push(`+${unused.length - 3} more`);
        }
        warnings.push(`Unused: ${unusedAbbrevs.join(', ')}`);
    }
    
    return warnings;
}

function checkDuplicatePosition(inning, position, currentPlayer) {
    if (!position || position === 'Out' || position === '') return false;
    
    for (const player of state.availablePlayers) {
        if (player !== currentPlayer && state.lineup[inning]?.[player] === position) {
            return true;
        }
    }
    
    return false;
}

async function togglePlayerStatus(playerName) {
    try {
        const result = await api(`/api/games/${state.currentGame.id}/status/${encodeURIComponent(playerName)}`, {
            method: 'PUT'
        });
        
        // Update local state
        if (!state.playerStatuses[playerName]) {
            state.playerStatuses[playerName] = {};
        }
        state.playerStatuses[playerName].status = result.newStatus;
        
        // Update just the button that was clicked (no full page refresh)
        const buttons = document.querySelectorAll('.player-toggle');
        buttons.forEach(btn => {
            if (btn.textContent.trim().replace(' ♀', '') === playerName) {
                btn.classList.remove('status-in', 'status-out');
                btn.classList.add(`status-${result.newStatus.toLowerCase()}`);
            }
        });
        
        // Reload just the lineup data (available players list may have changed)
        const lineupData = await api(`/api/games/${state.currentGame.id}/lineup`);
        state.availablePlayers = lineupData.availablePlayers;
        state.genders = lineupData.genders;
        state.lineup = lineupData.lineup;
        state.sitOutCounts = lineupData.sitOutCounts;
        
        // Re-render just the lineup table
        updateLineupTable();
    } catch (error) {
        console.error('Failed to toggle player status:', error);
    }
}

function updateLineupTable() {
    // Save scroll position before re-render
    const scrollY = window.scrollY;
    const tableWrapper = document.querySelector('.lineup-table-wrapper');
    const wrapperScrollLeft = tableWrapper ? tableWrapper.scrollLeft : 0;
    
    if (tableWrapper) {
        tableWrapper.innerHTML = buildLineupTable();
        // Restore horizontal scroll position for the table
        tableWrapper.scrollLeft = wrapperScrollLeft;
    }
    
    // Restore page scroll position
    window.scrollTo(0, scrollY);
}

async function updateGameDetails() {
    try {
        await api(`/api/games/${state.currentGame.id}`, {
            method: 'PUT',
            body: JSON.stringify({
                game_date: document.getElementById('gameDate').value,
                team_name: document.getElementById('teamName').value,
                opponent_name: document.getElementById('opponentName').value
            })
        });
    } catch (error) {
        console.error('Failed to update game details:', error);
    }
}

async function deleteGame() {
    const gameName = `${state.currentGame.team_name} vs ${state.currentGame.opponent_name || 'TBD'} (${state.currentGame.game_date})`;
    
    if (!confirm(`Are you sure you want to delete this game?\n\n${gameName}\n\nThis will delete all lineup data for this game and cannot be undone.`)) {
        return;
    }
    
    try {
        await api(`/api/games/${state.currentGame.id}`, { method: 'DELETE' });
        
        // Reload the game lineup (will show create game UI if no game exists)
        await loadGameLineup();
    } catch (error) {
        console.error('Failed to delete game:', error);
        alert('Failed to delete game: ' + error.message);
    }
}

async function updatePosition(player, inning, position) {
    try {
        // Store the old position to calculate sit-out count change
        const oldPosition = state.lineup[inning]?.[player] || '';
        
        await api(`/api/games/${state.currentGame.id}/lineup/${encodeURIComponent(player)}/${inning}`, {
            method: 'PUT',
            body: JSON.stringify({ position })
        });
        
        // Update local state
        if (!state.lineup[inning]) {
            state.lineup[inning] = {};
        }
        
        if (position) {
            state.lineup[inning][player] = position;
        } else {
            delete state.lineup[inning][player];
        }
        
        // Update sit-out counts properly
        // Decrement if moving FROM "Out"
        if (oldPosition === 'Out' && position !== 'Out') {
            state.sitOutCounts[player] = Math.max(0, (state.sitOutCounts[player] || 0) - 1);
        }
        // Increment if moving TO "Out"
        if (position === 'Out' && oldPosition !== 'Out') {
            state.sitOutCounts[player] = (state.sitOutCounts[player] || 0) + 1;
        }
        
        // Re-render just the lineup table to update warnings and counts
        updateLineupTable();
    } catch (error) {
        console.error('Failed to update position:', error);
    }
}

async function movePlayer(player, direction) {
    try {
        await api(`/api/games/${state.currentGame.id}/order/${encodeURIComponent(player)}`, {
            method: 'PUT',
            body: JSON.stringify({ direction })
        });
        
        // Reload just the lineup data (not the entire page)
        const lineupData = await api(`/api/games/${state.currentGame.id}/lineup`);
        state.availablePlayers = lineupData.availablePlayers;
        state.genders = lineupData.genders;
        state.lineup = lineupData.lineup;
        state.sitOutCounts = lineupData.sitOutCounts;
        
        // Re-render just the lineup table
        updateLineupTable();
    } catch (error) {
        console.error('Failed to move player:', error);
    }
}

async function copyInning() {
    try {
        await api(`/api/games/${state.currentGame.id}/lineup/copy`, { method: 'POST' });
        
        // Reload just the lineup data (not the entire page)
        const lineupData = await api(`/api/games/${state.currentGame.id}/lineup`);
        state.availablePlayers = lineupData.availablePlayers;
        state.genders = lineupData.genders;
        state.lineup = lineupData.lineup;
        state.sitOutCounts = lineupData.sitOutCounts;
        
        // Re-render just the lineup table
        updateLineupTable();
    } catch (error) {
        console.error('Failed to copy inning:', error);
    }
}

async function resetLineup() {
    if (!confirm('Are you sure you want to reset all lineup positions?')) return;
    
    try {
        await api(`/api/games/${state.currentGame.id}/lineup/reset`, { method: 'POST' });
        
        // Reload just the lineup data (not the entire page)
        const lineupData = await api(`/api/games/${state.currentGame.id}/lineup`);
        state.availablePlayers = lineupData.availablePlayers;
        state.genders = lineupData.genders;
        state.lineup = lineupData.lineup;
        state.sitOutCounts = lineupData.sitOutCounts;
        
        // Re-render just the lineup table
        updateLineupTable();
    } catch (error) {
        console.error('Failed to reset lineup:', error);
    }
}

async function uploadLogo(input) {
    const file = input.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('logo', file);
    
    try {
        const response = await fetch(`/api/games/${state.currentGame.id}/logo`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Upload failed');
        }
        
        // Update state and re-render
        state.currentGame.team_logo = data.logo;
        renderGameLineup();
    } catch (error) {
        console.error('Failed to upload logo:', error);
        alert('Failed to upload logo: ' + error.message);
    }
}

async function deleteLogo() {
    if (!confirm('Remove the team logo?')) return;
    
    try {
        await api(`/api/games/${state.currentGame.id}/logo`, { method: 'DELETE' });
        
        // Update state and re-render
        state.currentGame.team_logo = null;
        renderGameLineup();
    } catch (error) {
        console.error('Failed to delete logo:', error);
        alert('Failed to delete logo: ' + error.message);
    }
}

function toggleCollapsible(header) {
    header.classList.toggle('expanded');
    const content = header.nextElementSibling;
    content.classList.toggle('expanded');
}

async function publishLineup() {
    try {
        await api(`/api/games/${state.currentGame.id}/publish`, { method: 'POST' });
        
        // Update local state
        state.currentGame.is_published = true;
        state.currentGame.published_at = new Date().toISOString();
        
        // Re-render to show updated status
        renderGameLineup();
    } catch (error) {
        console.error('Failed to publish lineup:', error);
        alert('Failed to publish lineup: ' + error.message);
    }
}

async function unpublishLineup() {
    if (!confirm('Unpublish this lineup? It will no longer be visible to the public.')) return;
    
    try {
        await api(`/api/games/${state.currentGame.id}/unpublish`, { method: 'POST' });
        
        // Update local state
        state.currentGame.is_published = false;
        state.currentGame.published_at = null;
        
        // Re-render to show updated status
        renderGameLineup();
    } catch (error) {
        console.error('Failed to unpublish lineup:', error);
        alert('Failed to unpublish lineup: ' + error.message);
    }
}

// ========================================
// Roster Management Functions
// ========================================
async function loadRoster() {
    if (!state.authenticated) return;
    
    const panel = document.getElementById('rosterPanel');
    panel.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    
    try {
        const roster = await api('/api/roster');
        const substitutes = await api('/api/substitutes');
        const users = await api('/api/auth/users');
        
        renderRoster(roster, substitutes, users);
    } catch (error) {
        console.error('Failed to load roster:', error);
        panel.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>Failed to load roster</p></div>`;
    }
}

// Refresh roster data without showing loading spinner and preserve scroll position
async function refreshRosterData() {
    if (!state.authenticated) return;
    
    // Save scroll position before re-render
    const scrollY = window.scrollY;
    const panel = document.getElementById('rosterPanel');
    const panelScrollTop = panel ? panel.scrollTop : 0;
    
    try {
        const roster = await api('/api/roster');
        const substitutes = await api('/api/substitutes');
        const users = await api('/api/auth/users');
        
        renderRoster(roster, substitutes, users);
        
        // Restore scroll position after re-render
        window.scrollTo(0, scrollY);
        if (panel) panel.scrollTop = panelScrollTop;
    } catch (error) {
        console.error('Failed to refresh roster:', error);
    }
}

function renderRoster(roster, substitutes, users = []) {
    const panel = document.getElementById('rosterPanel');
    
    const rosterListHtml = roster.map(player => `
        <div class="roster-item">
            <div class="roster-item-name">
                <span>${escapeHtml(player.name)}</span>
                ${player.isFemale ? '<span class="gender-indicator">♀</span>' : ''}
            </div>
            <div class="roster-item-actions">
                <button class="gender-btn ${player.isFemale ? 'female' : 'male'}" 
                        onclick="toggleRosterGender('${escapeHtml(player.name)}')"
                        title="Toggle gender">
                    ${player.isFemale ? '♀' : '♂'}
                </button>
                <button class="btn btn-ghost btn-sm" 
                        onclick="deleteRosterPlayer('${escapeHtml(player.name)}')">
                    Delete
                </button>
            </div>
        </div>
    `).join('');
    
    const subsListHtml = substitutes.map(player => `
        <div class="roster-item">
            <div class="roster-item-name">
                <span>${escapeHtml(player.name)}</span>
                ${player.isFemale ? '<span class="gender-indicator">♀</span>' : ''}
            </div>
            <div class="roster-item-actions">
                <button class="gender-btn ${player.isFemale ? 'female' : 'male'}" 
                        onclick="toggleSubGender('${escapeHtml(player.name)}')"
                        title="Toggle gender">
                    ${player.isFemale ? '♀' : '♂'}
                </button>
                <button class="btn btn-ghost btn-sm" 
                        onclick="deleteSubstitute('${escapeHtml(player.name)}')">
                    Delete
                </button>
            </div>
        </div>
    `).join('');
    
    const usersListHtml = users.map(user => `
        <div class="roster-item">
            <div class="roster-item-name">
                <span>${escapeHtml(user.username)}</span>
                ${user.username === state.username ? '<span class="text-muted">(you)</span>' : ''}
            </div>
            <div class="roster-item-actions">
                ${user.username !== state.username ? `
                    <button class="btn btn-ghost btn-sm" 
                            onclick="deleteUser(${user.id}, '${escapeHtml(user.username)}')">
                        Delete
                    </button>
                ` : ''}
            </div>
        </div>
    `).join('');
    
    panel.innerHTML = `
        <div class="card roster-section">
            <div class="card-header">
                <h3 class="card-title">Main Roster</h3>
            </div>
            
            <form class="form-inline mb-lg" onsubmit="addPlayer(event)">
                <div class="form-group">
                    <label>Add New Player</label>
                    <input type="text" class="form-input" id="newPlayerName" 
                           placeholder="Player name" required>
                </div>
                <label class="form-checkbox">
                    <input type="checkbox" id="newPlayerFemale">
                    <span>Female</span>
                </label>
                <button type="submit" class="btn btn-primary">Add</button>
            </form>
            
            <div class="roster-list">
                ${rosterListHtml || '<p class="text-muted">No players yet</p>'}
            </div>
        </div>
        
        <div class="card roster-section">
            <div class="card-header">
                <h3 class="card-title">Substitutes</h3>
            </div>
            
            <form class="form-inline mb-lg" onsubmit="addSubstitute(event)">
                <div class="form-group">
                    <label>Add Substitute</label>
                    <input type="text" class="form-input" id="newSubName" 
                           placeholder="Substitute name" required>
                </div>
                <label class="form-checkbox">
                    <input type="checkbox" id="newSubFemale">
                    <span>Female</span>
                </label>
                <button type="submit" class="btn btn-primary">Add</button>
            </form>
            
            <div class="roster-list">
                ${subsListHtml || '<p class="text-muted">No substitutes yet</p>'}
            </div>
        </div>
        
        <div class="card roster-section">
            <div class="card-header">
                <h3 class="card-title">User Management</h3>
            </div>
            
            <form class="form-inline mb-lg" onsubmit="addUser(event)">
                <div class="form-group">
                    <label>Add New User</label>
                    <input type="text" class="form-input" id="newUsername" 
                           placeholder="Username" required>
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" class="form-input" id="newUserPassword" 
                           placeholder="Password" required minlength="4">
                </div>
                <button type="submit" class="btn btn-primary">Add User</button>
            </form>
            
            <div class="roster-list">
                ${usersListHtml || '<p class="text-muted">No users</p>'}
            </div>
        </div>
    `;
}

async function addPlayer(event) {
    event.preventDefault();
    
    const nameInput = document.getElementById('newPlayerName');
    const name = nameInput.value.trim();
    const isFemale = document.getElementById('newPlayerFemale').checked;
    
    if (!name) return;
    
    try {
        await api('/api/roster', {
            method: 'POST',
            body: JSON.stringify({ name, isFemale })
        });
        
        nameInput.value = '';
        document.getElementById('newPlayerFemale').checked = false;
        
        // Reload data without showing loading spinner (no flash)
        await refreshRosterData();
        
        // Auto-focus back to name input for quick entry
        setTimeout(() => {
            const newInput = document.getElementById('newPlayerName');
            if (newInput) newInput.focus();
        }, 100);
    } catch (error) {
        alert(error.message);
    }
}

async function deleteRosterPlayer(name) {
    if (!confirm(`Delete ${name} from roster?`)) return;
    
    try {
        await api(`/api/roster/${encodeURIComponent(name)}`, { method: 'DELETE' });
        await refreshRosterData();
    } catch (error) {
        alert(error.message);
    }
}

async function toggleRosterGender(name) {
    try {
        await api(`/api/roster/${encodeURIComponent(name)}/gender`, { method: 'PUT' });
        await refreshRosterData();
    } catch (error) {
        alert(error.message);
    }
}

async function addSubstitute(event) {
    event.preventDefault();
    
    const nameInput = document.getElementById('newSubName');
    const name = nameInput.value.trim();
    const isFemale = document.getElementById('newSubFemale').checked;
    
    if (!name) return;
    
    try {
        await api('/api/substitutes', {
            method: 'POST',
            body: JSON.stringify({ name, isFemale })
        });
        
        nameInput.value = '';
        document.getElementById('newSubFemale').checked = false;
        
        // Reload data without showing loading spinner (no flash)
        await refreshRosterData();
        
        // Auto-focus back to name input for quick entry
        setTimeout(() => {
            const newInput = document.getElementById('newSubName');
            if (newInput) newInput.focus();
        }, 100);
    } catch (error) {
        alert(error.message);
    }
}

async function deleteSubstitute(name) {
    if (!confirm(`Delete ${name} from substitutes?`)) return;
    
    try {
        await api(`/api/substitutes/${encodeURIComponent(name)}`, { method: 'DELETE' });
        await refreshRosterData();
    } catch (error) {
        alert(error.message);
    }
}

async function toggleSubGender(name) {
    try {
        await api(`/api/substitutes/${encodeURIComponent(name)}/gender`, { method: 'PUT' });
        await refreshRosterData();
    } catch (error) {
        alert(error.message);
    }
}

async function addUser(event) {
    event.preventDefault();
    
    const usernameInput = document.getElementById('newUsername');
    const passwordInput = document.getElementById('newUserPassword');
    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    
    if (!username || !password) return;
    
    try {
        await api('/api/auth/users', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        
        usernameInput.value = '';
        passwordInput.value = '';
        
        await refreshRosterData();
    } catch (error) {
        alert(error.message);
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    
    try {
        await api(`/api/auth/users/${userId}`, { method: 'DELETE' });
        await refreshRosterData();
    } catch (error) {
        alert(error.message);
    }
}

// ========================================
// View Lineup Functions
// ========================================
async function loadViewLineup() {
    const panel = document.getElementById('viewLineupPanel');
    panel.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    
    try {
        const games = await api('/api/games');
        state.games = games;
        
        // Update view banner based on published games
        updateViewBanner();
        
        if (games.length === 0) {
            panel.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📅</div><p>No games created yet</p></div>`;
            return;
        }
        
        renderViewLineup(games[0].id);
    } catch (error) {
        console.error('Failed to load games:', error);
        panel.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><p>Failed to load games</p></div>`;
    }
}

async function renderViewLineup(gameId, selectedPlayer = null) {
    const panel = document.getElementById('viewLineupPanel');
    
    // Find the game
    const game = state.games.find(g => g.id === gameId);
    if (!game) return;
    
    // Get published lineup data (for public view) or regular lineup (for authenticated users)
    let lineupData;
    if (state.authenticated) {
        // Authenticated users can see unpublished lineups
        lineupData = await api(`/api/games/${gameId}/lineup`);
        lineupData.published = true; // Mark as viewable
    } else {
        // Public view only shows published lineups
        lineupData = await api(`/api/games/${gameId}/lineup/published`);
    }
    
    // Store for player filter
    state.currentViewLineup = lineupData;
    state.currentViewGameId = gameId;
    
    // Build game selector - show publish status for authenticated users
    const gameSelectorHtml = `
        <div class="game-selector">
            <label class="form-group">
                <span>Select Game</span>
                <select class="form-select" onchange="changeViewGame(this.value)">
                    ${state.games.map(g => {
                        const publishIndicator = g.is_published ? '✓' : '○';
                        return `
                            <option value="${g.id}" ${g.id === gameId ? 'selected' : ''}>
                                ${state.authenticated ? publishIndicator + ' ' : ''}${g.game_date} - ${g.team_name} vs ${g.opponent_name || 'TBD'}
                            </option>
                        `;
                    }).join('')}
                </select>
            </label>
        </div>
    `;
    
    // Build team logo HTML
    const logoHtml = game.team_logo 
        ? `<div class="team-logo-display"><img src="/logos/${game.team_logo}" alt="${escapeHtml(game.team_name)} Logo"></div>`
        : '';
    
    // Build content
    let contentHtml = '';
    
    // Check if lineup is published (for public view)
    if (!lineupData.published) {
        contentHtml = `<div class="empty-state">
            <div class="empty-state-icon">🔒</div>
            <p>Lineup not yet published</p>
            <p class="text-muted">Check back later for the lineup.</p>
        </div>`;
    } else if (lineupData.availablePlayers.length === 0) {
        contentHtml = `<div class="empty-state"><div class="empty-state-icon">👥</div><p>No lineup set for this game</p></div>`;
    } else {
        // Player filter dropdown
        const playerFilterHtml = `
            <div class="player-filter">
                <label class="form-group">
                    <span>Filter by Player</span>
                    <select class="form-select" id="playerFilter" onchange="filterByPlayer(this.value)">
                        <option value="">All Players</option>
                        ${lineupData.availablePlayers.map((p, idx) => `
                            <option value="${escapeHtml(p)}" ${selectedPlayer === p ? 'selected' : ''}>
                                ${idx + 1}. ${escapeHtml(p)}
                            </option>
                        `).join('')}
                    </select>
                </label>
            </div>
        `;
        
        // If a player is selected, show mobile-friendly card view
        if (selectedPlayer) {
            const playerIndex = lineupData.availablePlayers.indexOf(selectedPlayer) + 1;
            const isFemale = lineupData.genders[selectedPlayer];
            
            let inningsHtml = '';
            for (let inning = 1; inning <= 7; inning++) {
                const position = lineupData.lineup[inning]?.[selectedPlayer] || '-';
                const abbrev = position !== '-' ? (lineupData.abbreviations[position] || position) : '-';
                const fullName = position !== '-' ? position : 'Not assigned';
                const isOut = position === 'Out';
                
                inningsHtml += `
                    <div class="player-inning-card ${isOut ? 'is-out' : ''}">
                        <div class="inning-number">Inning ${inning}</div>
                        <div class="inning-position">${abbrev}</div>
                        <div class="inning-position-full">${fullName}</div>
                    </div>
                `;
            }
            
            contentHtml = `
                ${playerFilterHtml}
                <div class="player-detail-view">
                    <div class="player-detail-header">
                        <div class="player-detail-number">#${playerIndex}</div>
                        <div class="player-detail-name">
                            ${escapeHtml(selectedPlayer)}
                            ${isFemale ? '<span class="gender-indicator">♀</span>' : ''}
                        </div>
                    </div>
                    <div class="player-innings-grid">
                        ${inningsHtml}
                    </div>
                </div>
            `;
        } else {
            // Show full table (desktop) + mobile cards
            let headerRow = '<tr><th>#</th><th>Player</th>';
            for (let i = 1; i <= 7; i++) {
                headerRow += `<th>Inn ${i}</th>`;
            }
            headerRow += '</tr>';
            
            let bodyRows = '';
            let mobileCardsHtml = '';
            
            lineupData.availablePlayers.forEach((player, index) => {
                const isFemale = lineupData.genders[player];
                
                // Desktop table row
                bodyRows += `<tr onclick="filterByPlayer('${escapeHtml(player)}')" class="clickable-row">
                    <td>${index + 1}</td>
                    <td>${escapeHtml(player)}${isFemale ? ' ♀' : ''}</td>`;
                
                // Mobile card
                let positionsHtml = '';
                for (let inning = 1; inning <= 7; inning++) {
                    const position = lineupData.lineup[inning]?.[player] || '-';
                    const abbrev = position !== '-' ? (lineupData.abbreviations[position] || position) : '-';
                    const isOut = position === 'Out';
                    
                    bodyRows += `<td class="${isOut ? 'out-position' : ''}">${abbrev}</td>`;
                    positionsHtml += `<span class="mobile-pos ${isOut ? 'out' : ''}">${abbrev}</span>`;
                }
                
                bodyRows += '</tr>';
                
                // Mobile card for this player
                mobileCardsHtml += `
                    <div class="mobile-player-card" onclick="filterByPlayer('${escapeHtml(player)}')">
                        <div class="mobile-player-info">
                            <span class="mobile-player-number">#${index + 1}</span>
                            <span class="mobile-player-name">${escapeHtml(player)}${isFemale ? ' ♀' : ''}</span>
                        </div>
                        <div class="mobile-positions">
                            ${positionsHtml}
                        </div>
                        <div class="mobile-tap-hint">Tap to view details</div>
                    </div>
                `;
            });
            
            contentHtml = `
                ${playerFilterHtml}
                
                <div class="desktop-table">
                    <div class="lineup-table-wrapper">
                        <table class="view-table">
                            <thead>${headerRow}</thead>
                            <tbody>${bodyRows}</tbody>
                        </table>
                    </div>
                </div>
                
                <div class="mobile-cards">
                    ${mobileCardsHtml}
                </div>
            `;
        }
    }
    
    // Show publish status banner for authenticated users viewing unpublished game
    const unpublishedBanner = state.authenticated && !game.is_published
        ? `<div class="unpublished-banner">
             <span>⚠️ This lineup is not published - only you can see it</span>
           </div>`
        : '';
    
    panel.innerHTML = `
        ${gameSelectorHtml}
        
        <div class="view-header">
            <div class="game-info">
                <h2>${escapeHtml(game.team_name)} vs ${escapeHtml(game.opponent_name || 'TBD')}</h2>
                <p class="game-date">📅 ${game.game_date}</p>
            </div>
            ${logoHtml}
        </div>
        
        ${unpublishedBanner}
        
        <div class="card">
            ${contentHtml}
        </div>
    `;
}

async function changeViewGame(gameId) {
    await renderViewLineup(parseInt(gameId));
}

function filterByPlayer(playerName) {
    if (state.currentViewGameId) {
        renderViewLineup(state.currentViewGameId, playerName || null);
    }
}

// ========================================
// Modal Functions
// ========================================
function openModal(modalId) {
    document.getElementById(modalId).style.display = 'flex';
    
    if (modalId === 'loginModal') {
        checkHasUsers();
    }
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
    
    // Clear forms
    if (modalId === 'loginModal') {
        document.getElementById('loginForm').reset();
        document.getElementById('registerForm').reset();
        document.getElementById('loginError').textContent = '';
        document.getElementById('registerError').textContent = '';
    }
}

// ========================================
// Utility Functions
// ========================================
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ========================================
// Event Listeners
// ========================================
document.addEventListener('DOMContentLoaded', async () => {
    // Check auth status and initialize
    await checkAuthStatus();
    
    // Show the correct panel based on auth status
    // (updateTabs already set state.currentTab appropriately)
    document.getElementById('gameLineupPanel').style.display = state.currentTab === 'gameLineup' ? 'block' : 'none';
    document.getElementById('rosterPanel').style.display = state.currentTab === 'roster' ? 'block' : 'none';
    document.getElementById('viewLineupPanel').style.display = state.currentTab === 'viewLineup' ? 'block' : 'none';
    
    await loadCurrentTab();
    
    // Login form
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('loginUsername').value;
        const password = document.getElementById('loginPassword').value;
        
        const result = await login(username, password);
        if (!result.success) {
            document.getElementById('loginError').textContent = result.error;
        }
    });
    
    // Register form
    document.getElementById('registerForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('regUsername').value;
        const password = document.getElementById('regPassword').value;
        
        const result = await register(username, password);
        if (result.success) {
            document.getElementById('registerError').textContent = '';
            alert('User created! Please login.');
            document.getElementById('registerForm').reset();
            document.getElementById('registerSection').style.display = 'none';
        } else {
            document.getElementById('registerError').textContent = result.error;
        }
    });
    
    // Close modal on overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeModal(overlay.id);
            }
        });
    });
    
    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay').forEach(overlay => {
                if (overlay.style.display !== 'none') {
                    closeModal(overlay.id);
                }
            });
        }
    });
});

