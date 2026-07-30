let ws = null;
let queueTimerInterval = null;
let secondsInQueue = 0;
let currentPlayerId = null;
let agentIcons = {};

async function fetchAgentIcons() {
    try {
        const response = await fetch('https://valorant-api.com/v1/agents?isPlayableCharacter=true');
        const data = await response.json();
        if (data.status === 200) {
            data.data.forEach(agent => {
                agentIcons[agent.displayName] = agent.displayIcon;
            });
        }
    } catch (e) {
        console.error("Failed to fetch agent icons", e);
    }
}

fetchAgentIcons();

// DOM Elements
const matchForm = document.getElementById('match-form');
const btnFindMatch = document.getElementById('btn-find-match');
const btnResetQueue = document.getElementById('btn-reset-queue');
const rosterContainer = document.getElementById('roster-container');
const rosterCount = document.getElementById('roster-count');
const timerEl = document.getElementById('queue-timer');
const mmrExpansionEl = document.getElementById('mmr-expansion');
const expansionProgress = document.getElementById('expansion-progress');
const engineLogs = document.getElementById('engine-logs');

// Modal Elements
const matchModal = document.getElementById('match-modal');
const modalMapName = document.getElementById('modal-map-name');
const attackersList = document.getElementById('attackers-list');
const defendersList = document.getElementById('defenders-list');
const attackersAvg = document.getElementById('attackers-avg');
const defendersAvg = document.getElementById('defenders-avg');
const btnCloseModal = document.getElementById('btn-close-modal');

function logToConsole(message) {
    const time = new Date().toLocaleTimeString();
    const div = document.createElement('div');
    div.className = 'log-line';
    div.textContent = `[${time}] ${message}`;
    engineLogs.appendChild(div);
    engineLogs.scrollTop = engineLogs.scrollHeight;
}

// Form Submission
matchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const gameName = document.getElementById('game_name').value.trim();
    const tagLine = document.getElementById('tag_line').value.trim();
    const agent = document.getElementById('agent_select').value;
    const userMMR = parseFloat(document.getElementById('user_mmr').value) || 0.0;

    if (!gameName || !tagLine) return;

    currentPlayerId = `${gameName}#${tagLine}`;

    logToConsole(`Searching for 5v5 match for ${currentPlayerId} (${userMMR} MMR)...`);
    btnFindMatch.disabled = true;
    btnFindMatch.style.opacity = '0.5';

    // Set initial "IN QUEUE" layout (1 / 10)
    renderInQueueState({
        player_id: currentPlayerId,
        game_name: gameName,
        tag_line: tagLine,
        agent: agent,
        mmr: userMMR
    });

    try {
        // 1. Connect WebSocket
        connectWebSocket(currentPlayerId);

        // 2. Call auto-match endpoint (Enqueues user immediately; background task populates 9 AI players after 7-15s)
        const response = await fetch('/api/v1/queue/auto-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                game_name: gameName,
                tag_line: tagLine,
                agent: agent,
                user_mmr: userMMR
            })
        });

        const data = await response.json();
        if (response.ok) {
            const source = data.user_payload.stats_source || 'simulated';
            logToConsole(`Enqueued in Redis ZSET [Telemetry: ${source}]. Searching for 9 agents (7-15s delay)...`);
            startQueueTimer();
        } else {
            logToConsole(`Error: ${data.detail}`);
            btnFindMatch.disabled = false;
            btnFindMatch.style.opacity = '1';
        }
    } catch (err) {
        logToConsole(`Network Error: ${err.message}`);
        btnFindMatch.disabled = false;
        btnFindMatch.style.opacity = '1';
    }
});

// Render "IN QUEUE" state while searching
function renderInQueueState(userPlayer) {
    rosterCount.textContent = '1';
    rosterContainer.innerHTML = `
        <div class="empty-state">
            <div class="radar-ping"></div>
            <h4 style="color: var(--val-red); font-family: var(--font-heading); font-size: 1.8rem; margin-bottom: 0.5rem;">IN QUEUE // SEARCHING FOR AGENTS...</h4>
            <p>Your Agent <strong>${userPlayer.game_name}#${userPlayer.tag_line}</strong> (${userPlayer.agent} - ${userPlayer.mmr} MMR) is queued in Redis ZSET.</p>
            <p style="font-size: 0.8rem; color: var(--val-text-muted); margin-top: 0.5rem;">Expanding MMR tolerance range... Match will pop in 7-15 seconds.</p>
        </div>
    `;
}

// Leave Queue Button
btnResetQueue.addEventListener('click', async () => {
    if (!currentPlayerId) return;

    try {
        await fetch('/api/v1/queue/leave', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_id: currentPlayerId })
        });
        logToConsole(`Player ${currentPlayerId} left queue.`);
    } catch (e) {}

    resetState();
});

// Reset State
function resetState() {
    stopQueueTimer();
    secondsInQueue = 0;
    timerEl.textContent = '00:00';
    if (ws) {
        ws.close();
        ws = null;
    }
    currentPlayerId = null;
    rosterContainer.innerHTML = `
        <div class="empty-state">
            <div class="radar-ping"></div>
            <p>No agents in queue. Click <strong>FIND 5V5 MATCH</strong> to generate 10 agents across Attackers and Defenders!</p>
        </div>
    `;
    rosterCount.textContent = '0';
    btnFindMatch.disabled = false;
    btnFindMatch.style.opacity = '1';
    mmrExpansionEl.textContent = '±150 MMR';
    expansionProgress.style.width = '0%';
}

// WebSocket Manager
function connectWebSocket(playerId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/queue/${encodeURIComponent(playerId)}`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        logToConsole(`WebSocket connected for ${playerId}`);
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'MATCH_FOUND') {
            logToConsole(`🎉 MATCH FOUND! Map: ${msg.data.map} | Lobby ID: ${msg.data.lobby_id}`);
            stopQueueTimer();
            
            // 1. Render full 5v5 layout on main dashboard
            const all10 = [...msg.data.attackers, ...msg.data.defenders];
            render5v5Roster(all10);

            // 2. Display Match Found Modal
            displayMatchModal(msg.data);
        }
    };

    ws.onclose = () => {
        logToConsole(`WebSocket disconnected.`);
    };
}

// Timer & Expansion Animation
function startQueueTimer() {
    secondsInQueue = 0;
    timerEl.textContent = '00:00';
    
    if (queueTimerInterval) clearInterval(queueTimerInterval);

    queueTimerInterval = setInterval(() => {
        secondsInQueue++;
        const mins = String(Math.floor(secondsInQueue / 60)).padStart(2, '0');
        const secs = String(secondsInQueue % 60).padStart(2, '0');
        timerEl.textContent = `${mins}:${secs}`;

        // Dynamic MMR Expansion calculation (+25 MMR every 5 seconds)
        const multiplier = Math.floor(secondsInQueue / 5);
        const currentTolerance = 150 + (multiplier * 25);
        mmrExpansionEl.textContent = `±${currentTolerance} MMR`;
        
        const progressPct = Math.min(100, ((secondsInQueue % 5) / 5) * 100);
        expansionProgress.style.width = `${progressPct}%`;
    }, 1000);
}

function stopQueueTimer() {
    if (queueTimerInterval) {
        clearInterval(queueTimerInterval);
        queueTimerInterval = null;
    }
}

// Render 5v5 Roster Layout directly on Dashboard
function render5v5Roster(players) {
    rosterContainer.innerHTML = '';
    rosterCount.textContent = players.length;

    // Split 10 players into Attackers (5) and Defenders (5)
    const sorted = [...players].sort((a, b) => b.mmr - a.mmr);
    const attackers = sorted.filter((_, idx) => idx % 2 === 0);
    const defenders = sorted.filter((_, idx) => idx % 2 !== 0);

    const layout = document.createElement('div');
    layout.className = 'five-vs-five-layout';

    // Attackers Column
    const atkCol = document.createElement('div');
    atkCol.className = 'team-column attackers';
    const atkAvg = Math.round(sumMMR(attackers) / (attackers.length || 1));
    atkCol.innerHTML = `<div class="team-column-header"><span>ATTACKERS (5)</span> <span>AVG ${atkAvg} MMR</span></div>`;
    attackers.forEach(p => atkCol.appendChild(createPlayerItem(p)));

    // VS Center Badge
    const vsDiv = document.createElement('div');
    vsDiv.className = 'vs-badge-center';
    vsDiv.textContent = 'VS';

    // Defenders Column
    const defCol = document.createElement('div');
    defCol.className = 'team-column defenders';
    const defAvg = Math.round(sumMMR(defenders) / (defenders.length || 1));
    defCol.innerHTML = `<div class="team-column-header"><span>DEFENDERS (5)</span> <span>AVG ${defAvg} MMR</span></div>`;
    defenders.forEach(p => defCol.appendChild(createPlayerItem(p)));

    layout.appendChild(atkCol);
    layout.appendChild(vsDiv);
    layout.appendChild(defCol);

    rosterContainer.appendChild(layout);
}

function createPlayerItem(p) {
    const item = document.createElement('div');
    item.className = `player-item ${p.player_id === currentPlayerId ? 'is-user' : ''}`;
    const agentName = p.agent || 'Jett';
    const iconUrl = agentIcons[agentName] || 'https://media.valorant-api.com/agents/add6443a-41bd-e414-f6ad-e58d267f4e95/displayicon.png';
    
    item.innerHTML = `
        <div class="player-info">
            <img src="${iconUrl}" class="agent-icon-img" alt="${agentName}">
            <div class="agent-details-column">
                <span class="agent-badge">${agentName}</span>
                <div>
                    <span class="player-name">${p.game_name}</span>
                    <span class="player-tag">#${p.tag_line}</span>
                </div>
            </div>
        </div>
        <div class="player-stats">
            <div class="stat-box">
                <span class="stat-label">RANK / MMR</span>
                <span class="rank-text">${p.rank || 'Immortal'} (${Math.round(p.mmr)})</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">ACS / KDA</span>
                <span>${p.acs || 240} | ${p.kda || 1.4}</span>
            </div>
        </div>
    `;
    return item;
}

function sumMMR(team) {
    return team.reduce((acc, p) => acc + p.mmr, 0);
}

// Match Found Modal Display
function displayMatchModal(matchData) {
    modalMapName.textContent = matchData.map || 'HAVEN';
    attackersAvg.textContent = Math.round(sumMMR(matchData.attackers) / matchData.attackers.length);
    defendersAvg.textContent = Math.round(sumMMR(matchData.defenders) / matchData.defenders.length);

    renderTeamList(attackersList, matchData.attackers);
    renderTeamList(defendersList, matchData.defenders);

    matchModal.classList.remove('hidden');
}

function renderTeamList(container, team) {
    container.innerHTML = '';
    team.forEach(p => {
        const agentName = p.agent || 'Agent';
        const iconUrl = agentIcons[agentName] || 'https://media.valorant-api.com/agents/add6443a-41bd-e414-f6ad-e58d267f4e95/displayicon.png';
        const div = document.createElement('div');
        div.className = 'player-item';
        div.innerHTML = `
            <div class="player-info">
                <img src="${iconUrl}" class="agent-icon-img" alt="${agentName}">
                <div class="agent-details-column">
                    <span class="agent-badge">${agentName}</span>
                    <span class="player-name">${p.game_name}#${p.tag_line}</span>
                </div>
            </div>
            <div class="player-stats">
                <span class="rank-text">${Math.round(p.mmr)} MMR</span>
            </div>
        `;
        container.appendChild(div);
    });
}

btnCloseModal.addEventListener('click', () => {
    matchModal.classList.add('hidden');
    btnFindMatch.disabled = false;
    btnFindMatch.style.opacity = '1';
});
