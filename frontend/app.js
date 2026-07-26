// ═══════════════════════════════════════════════════════
//  STATE
// ═══════════════════════════════════════════════════════
// screens: landing, home, marketplace, chat, debate, play

let currentUser      = JSON.parse(localStorage.getItem('auth-user') || 'null');
let currentCharacter = null;
let allCharacters    = [];
let recorder, chunks, stream;
let selectedDebateCharacters = new Set();

// ═══════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════

async function request(path, options = {}) {
  const res = await fetch(path, options);
  const ct  = res.headers.get('content-type') || '';
  const payload = ct.includes('application/json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error(payload.detail || payload || 'Request failed');
  return payload;
}

function $id(id) { return document.getElementById(id); }

/** Show exactly one screen; hide everything else */
function showScreen(id) {
  // When leaving the play screen, restore the hub and hide the iframe.
  if (id !== 'screen-play') {
    const hub   = $id('play-hub');
    const frame = $id('play-detective-frame-wrap');
    if (hub)   hub.classList.remove('hidden');
    if (frame) frame.classList.add('hidden');
  }
  ['screen-landing', 'screen-home', 'screen-marketplace', 'screen-chat', 'screen-debate', 'screen-play']
    .forEach(s => {
      const el = $id(s);
      el.classList.toggle('hidden', s !== id);
      // screen-landing uses flex; ensure it shows correctly
      if (s === id) el.style.display = '';
    });
}

// ═══════════════════════════════════════════════════════
//  LANDING — Auth
// ═══════════════════════════════════════════════════════

$id('btn-show-login').onclick  = () => { $id('modal-login').classList.remove('hidden'); };
$id('btn-show-signup').onclick = () => { $id('modal-signup').classList.remove('hidden'); };
$id('close-login').onclick     = () => { $id('modal-login').classList.add('hidden'); };
$id('close-signup').onclick    = () => { $id('modal-signup').classList.add('hidden'); };

$id('switch-to-signup').onclick = () => {
  $id('modal-login').classList.add('hidden');
  $id('modal-signup').classList.remove('hidden');
};
$id('switch-to-login').onclick = () => {
  $id('modal-signup').classList.add('hidden');
  $id('modal-login').classList.remove('hidden');
};

// Close modals on backdrop click
['modal-login', 'modal-signup'].forEach(id => {
  $id(id).addEventListener('click', e => {
    if (e.target === $id(id)) $id(id).classList.add('hidden');
  });
});

$id('login-button').onclick = async () => {
  $id('login-error').textContent = '';
  try {
    currentUser = await request('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email:    $id('login-email').value,
        password: $id('login-password').value,
      }),
    });
    localStorage.setItem('auth-user', JSON.stringify(currentUser));
    $id('modal-login').classList.add('hidden');
    enterApp();
  } catch (err) {
    $id('login-error').textContent = err.message;
  }
};

$id('signup-button').onclick = async () => {
  $id('signup-error').textContent = '';
  try {
    currentUser = await request('/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name:     $id('signup-name').value,
        email:    $id('signup-email').value,
        password: $id('signup-password').value,
        gender:   $id('signup-gender').value,
        basics:   $id('signup-basics').value,
      }),
    });
    localStorage.setItem('auth-user', JSON.stringify(currentUser));
    $id('modal-signup').classList.add('hidden');
    enterApp();
  } catch (err) {
    $id('signup-error').textContent = err.message;
  }
};

// ═══════════════════════════════════════════════════════
//  APP ENTRY
// ═══════════════════════════════════════════════════════

async function enterApp() {
  // Sync username in navbars
  [$id('nav-username'), $id('nav-username2'), $id('nav-username3')].forEach(el => {
    if (el) el.textContent = currentUser.name || currentUser.email || '';
  });

  // Pre-fill profile fields
  $id('profile-name').value   = currentUser.name   || '';
  $id('profile-gender').value = currentUser.gender || '';
  $id('profile-basics').value = currentUser.basics || '';

  await loadCharacters();
  showScreen('screen-home');
}

// ═══════════════════════════════════════════════════════
//  LOAD CHARACTERS  (shared by home + debate + marketplace)
// ═══════════════════════════════════════════════════════

async function loadCharacters() {
  try {
    allCharacters = await request('/characters');
  } catch {
    allCharacters = [];
  }
  renderPosters();
  renderMarketplaceCards();
}

// ═══════════════════════════════════════════════════════
//  HOME — POSTER GRID
// ═══════════════════════════════════════════════════════

// Vivid per-character gradient colours for poster backgrounds
const POSTER_COLORS = [
  ['#2a0a1e', '#7a1545'],  // pink
  ['#0a1a2e', '#1a4568'],  // blue
  ['#0a2218', '#1a6040'],  // green
  ['#1c1408', '#6b4d0a'],  // amber
  ['#13061e', '#4a1570'],  // purple
];

function renderPosters() {
  const grid = $id('poster-grid');
  grid.innerHTML = '';
  allCharacters.forEach((char, i) => {
    const [bg1, bg2] = POSTER_COLORS[i % POSTER_COLORS.length];
    const card = document.createElement('div');
    card.className = 'poster-card';
    card.innerHTML = `
      <div class="poster-img-wrap" style="background: linear-gradient(160deg, ${bg1} 0%, ${bg2} 100%);">
        <img src="${char.avatar}" alt="${char.name}" onerror="this.style.display='none'">
      </div>
      <div class="poster-body">
        <p class="poster-creator">PocketX Original</p>
        <h3 class="poster-name">${char.name}</h3>
        <p class="poster-desc">${char.description}</p>
        <button class="poster-btn">Chat with ${char.name}</button>
      </div>
    `;
    card.querySelector('.poster-btn').onclick = (e) => {
      e.stopPropagation();
      openChat(char);
    };
    grid.appendChild(card);
  });
}

// ═══════════════════════════════════════════════════════
//  MARKETPLACE — CARDS
// ═══════════════════════════════════════════════════════

// Extra marketplace-only characters (community)
const MARKET_EXTRAS = [
  {
    id: '_mp_luna', name: 'Luna', category: 'Wellness',
    avatar: 'https://placehold.co/56x56/d1fae5/065f46?text=Luna',
    description: 'A soft-spoken empathy coach who listens first, judges never.',
    price: '$0.02 / msg', creator: 'nova_studio', rating: '4.8', chats: '3.2K',
  },
  {
    id: '_mp_rex', name: 'Rex', category: 'Fitness',
    avatar: 'https://placehold.co/56x56/fef3c7/92400e?text=Rex',
    description: 'Ex-army PT turned no-nonsense virtual trainer. Zero excuses.',
    price: '$4.99 / mo', creator: 'ironworks_ai', rating: '4.6', chats: '1.8K',
  },
  {
    id: '_mp_nova', name: 'Nova', category: 'Sci-Fi',
    avatar: 'https://placehold.co/56x56/dbeafe/1e3a8a?text=Nova',
    description: 'An AI from 2147 who is definitely not here to change the timeline.',
    price: 'Free', creator: 'timewarp_labs', rating: '4.9', chats: '7.1K',
  },
  {
    id: '_mp_chef', name: 'Chef Marco', category: 'Culinary',
    avatar: 'https://placehold.co/56x56/fee2e2/991b1b?text=Chef',
    description: 'Michelin-trained culinary AI who roasts bad recipes and bad technique equally.',
    price: '$2.99 / mo', creator: 'folio_kitchen', rating: '4.7', chats: '2.4K',
  },
];

function renderMarketplaceCards() {
  const grid = $id('mp-card-grid');
  grid.innerHTML = '';

  // Real API characters first
  allCharacters.forEach(char => {
    const card = makeMarketCard({
      id: char.id,
      name: char.name,
      category: 'Official',
      avatar: char.avatar,
      description: char.description,
      price: 'Free',
      creator: 'PocketX',
      rating: '5.0',
      chats: '10K+',
    }, true);
    grid.appendChild(card);
  });

  // Extra showcase cards
  MARKET_EXTRAS.forEach(m => {
    grid.appendChild(makeMarketCard(m, false));
  });
}

function makeMarketCard(char, isReal) {
  const card = document.createElement('div');
  card.className = 'mp-char-card';
  card.innerHTML = `
    <div class="mp-char-top">
      <img class="mp-char-avatar" src="${char.avatar}" alt="${char.name}" onerror="this.style.display='none'">
      <div class="mp-char-info">
        <div class="mp-char-name">${char.name}</div>
        <div class="mp-char-category">${char.category}</div>
      </div>
    </div>
    <p class="mp-char-desc">${char.description}</p>
    <div class="mp-char-meta">
      <span>⭐ ${char.rating} · 💬 ${char.chats}</span>
      <span class="mp-char-price">${char.price}</span>
    </div>
    <div class="mp-char-footer">
      <button class="mp-btn-chat">💬 Chat</button>
      <button class="mp-btn-license">📜 License</button>
    </div>
  `;
  card.querySelector('.mp-btn-chat').onclick = () => {
    if (isReal) {
      const realChar = allCharacters.find(c => c.id === char.id);
      if (realChar) openChat(realChar);
    } else {
      alert(`"${char.name}" is a community character — licensing coming soon!`);
    }
  };
  card.querySelector('.mp-btn-license').onclick = () => {
    alert(`License terms for "${char.name}" — coming soon!`);
  };
  return card;
}

// ═══════════════════════════════════════════════════════
//  CHAT SCREEN
// ═══════════════════════════════════════════════════════

// ── Orb speaking state (CSS-only, no Web Audio) ─────────
function _orbSetSpeaking(on) {
  const outer = $id('orb-ring-outer');
  const mid   = $id('orb-ring-mid');
  if (on) {
    outer.classList.add('orb-ring--speaking');
    mid.classList.add('orb-ring--speaking');
  } else {
    outer.classList.remove('orb-ring--speaking');
    mid.classList.remove('orb-ring--speaking');
  }
}

function openChat(character) {
  currentCharacter = character;
  // Sync hidden avatar (kept for any legacy references)
  $id('chat-avatar').src  = character.avatar;
  $id('chat-avatar').alt  = character.name;
  // Orb photo
  $id('orb-avatar').src = character.avatar;
  $id('orb-avatar').alt = character.name;
  $id('chat-char-name').textContent = character.name;
  $id('chat-char-desc').textContent = character.description;
  $id('status').textContent = `Ready to talk to ${character.name}.`;
  // Clear previous conversation
  const msgs = $id('chat-messages');
  msgs.innerHTML = `
    <div class="chat-welcome">
      <p>Start the conversation — press <strong>Record</strong> and speak.</p>
    </div>
  `;
  showScreen('screen-chat');
}

function appendChatBubble(text, isUser, label) {
  const msgs = $id('chat-messages');
  // Remove welcome placeholder if present
  const welcome = msgs.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  const div = document.createElement('div');
  div.className = 'chat-bubble' + (isUser ? ' chat-bubble--user' : '');
  div.innerHTML = `
    <div class="bubble-body">
      <div class="bubble-label">${label}</div>
      <div class="bubble-text">${text}</div>
    </div>
  `;
  msgs.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// Record / stop
$id('record-button').onclick = async () => {
  if (!currentUser || !currentCharacter) {
    $id('status').textContent = 'Login and choose a character first.';
    return;
  }
  stream   = await navigator.mediaDevices.getUserMedia({ audio: true });
  recorder = new MediaRecorder(stream);
  chunks   = [];
  recorder.ondataavailable = e => chunks.push(e.data);
  recorder.onstop = async () => {
    $id('status').textContent = `Sending to ${currentCharacter.name}…`;
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
    const form = new FormData();
    form.append('audio', blob, 'voice-note.webm');
    // Story characters (ids starting with _story_) use the Zep-backed endpoint
    const isStoryChar = currentCharacter.id.startsWith('_story_');
    const chatEndpoint = isStoryChar ? '/story-voice-chat' : '/voice-chat';
    const res = await fetch(
      `${chatEndpoint}?character_id=${encodeURIComponent(currentCharacter.id)}&user_id=${encodeURIComponent(currentUser.user_id)}`,
      { method: 'POST', body: form }
    );
    if (!res.ok) {
      $id('status').textContent = 'Request failed.';
      return;
    }
    const transcript = decodeURIComponent(res.headers.get('X-Transcript') || '');
    const reply      = decodeURIComponent(res.headers.get('X-Reply')      || '');
    appendChatBubble(transcript, true,  'You');
    appendChatBubble(reply,      false, currentCharacter.name);
    const audioBlob = await res.blob();
    const player = $id('player');
    player.src = URL.createObjectURL(audioBlob);
    player.load();

    // Animate orb while character speaks
    _orbSetSpeaking(true);
    player.addEventListener('ended', () => _orbSetSpeaking(false), { once: true });
    player.addEventListener('pause', () => _orbSetSpeaking(false), { once: true });

    player.play().catch(() => {});
    $id('status').textContent = `${currentCharacter.name} replied.`;
  };
  recorder.start();
  $id('record-button').disabled = true;
  $id('stop-button').disabled   = false;
  $id('status').textContent = 'Recording…';
};

$id('stop-button').onclick = () => {
  // Unlock the audio context synchronously inside this gesture handler so the
  // player.play() that fires after the async fetch is not blocked by autoplay policy.
  const player = $id('player');
  player.play().catch(() => {});
  player.pause();

  recorder.stop();
  stream.getTracks().forEach(t => t.stop());
  $id('record-button').disabled = false;
  $id('stop-button').disabled   = true;
};

// Save profile
$id('save-profile-button').onclick = async () => {
  try {
    const prev    = JSON.parse(localStorage.getItem('auth-user') || 'null');
    const updated = await request('/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUser.user_id,
        name:    $id('profile-name').value,
        gender:  $id('profile-gender').value,
        basics:  $id('profile-basics').value,
      }),
    });
    currentUser = { ...prev, ...updated };
    localStorage.setItem('auth-user', JSON.stringify(currentUser));
    [$id('nav-username'), $id('nav-username2')].forEach(el => {
      if (el) el.textContent = currentUser.name || '';
    });
    $id('status').textContent = 'Profile saved.';
  } catch (err) {
    $id('status').textContent = err.message;
  }
};

// ═══════════════════════════════════════════════════════
//  DEBATE ARENA
// ═══════════════════════════════════════════════════════

function openDebate() {
  selectedDebateCharacters = new Set();
  renderDebateCharacters();
  $id('debate-setup').classList.remove('hidden');
  $id('debate-arena').classList.add('hidden');
  $id('debate-status').textContent   = '';
  $id('start-debate-button').disabled = false;
  showScreen('screen-debate');
}

function renderDebateCharacters() {
  const list = $id('debate-character-list');
  list.innerHTML = '';
  allCharacters.forEach(char => {
    const card = document.createElement('div');
    card.className = 'debate-char-card' + (selectedDebateCharacters.has(char.id) ? ' selected' : '');
    card.innerHTML = `
      <img src="${char.avatar}" alt="${char.name}">
      <span class="debate-char-name">${char.name}</span>
    `;
    card.onclick = () => {
      if (selectedDebateCharacters.has(char.id)) {
        selectedDebateCharacters.delete(char.id);
        card.classList.remove('selected');
      } else {
        if (selectedDebateCharacters.size >= 5) {
          $id('debate-status').textContent = 'Maximum 5 characters allowed.';
          return;
        }
        selectedDebateCharacters.add(char.id);
        card.classList.add('selected');
      }
      $id('debate-status').textContent = '';
    };
    list.appendChild(card);
  });
}

let _debateAbort  = null;   // AbortController for the fetch
let _debateStopped = false;  // flag read by consumeDebateStream

function _stopDebate() {
  _debateStopped = true;
  if (_debateAbort) { _debateAbort.abort(); _debateAbort = null; }
  // Silence any currently playing audio immediately
  const player = $id('debate-player');
  player.pause();
  player.src = '';
  $id('arena-typing').classList.add('hidden');
  $id('arena-stop-btn').classList.add('hidden');
  addModeratorBubble('Debate stopped.', 'summary');
  $id('start-debate-button').disabled = false;
}

$id('arena-stop-btn').onclick = _stopDebate;

$id('start-debate-button').onclick = async () => {
  if (selectedDebateCharacters.size < 2) {
    $id('debate-status').textContent = 'Please select at least 2 characters.';
    return;
  }
  const topic = $id('debate-topic').value.trim();
  if (!topic) {
    $id('debate-status').textContent = 'Please enter a debate topic.';
    return;
  }
  const rounds = parseInt($id('debate-rounds').value, 10);
  $id('debate-status').textContent = '⏳ Starting debate…';
  $id('start-debate-button').disabled = true;

  $id('debate-setup').classList.add('hidden');
  $id('debate-arena').classList.remove('hidden');
  $id('arena-topic-text').textContent = topic;
  $id('arena-feed').innerHTML = '';
  $id('arena-typing').classList.add('hidden');
  $id('arena-stop-btn').classList.remove('hidden');
  $id('debate-player').style.display = 'block';

  _debateStopped = false;
  _debateAbort   = new AbortController();

  try {
    const res = await fetch('/debate/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, character_ids: Array.from(selectedDebateCharacters), rounds }),
      signal: _debateAbort.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Stream failed' }));
      $id('debate-status').textContent = `Error: ${err.detail}`;
      $id('debate-setup').classList.remove('hidden');
      $id('debate-arena').classList.add('hidden');
      $id('arena-stop-btn').classList.add('hidden');
      $id('start-debate-button').disabled = false;
      return;
    }
    await consumeDebateStream(res.body);
  } catch (err) {
    if (!_debateStopped) {
      $id('debate-status').textContent = `Error: ${err.message}`;
      $id('debate-setup').classList.remove('hidden');
      $id('debate-arena').classList.add('hidden');
    }
  }
  $id('arena-stop-btn').classList.add('hidden');
  $id('start-debate-button').disabled = false;
};

$id('arena-reset-btn').onclick = () => {
  _stopDebate();
  $id('debate-arena').classList.add('hidden');
  $id('debate-setup').classList.remove('hidden');
  $id('debate-status').textContent = '';
};

// ── SSE stream helpers ──────────────────────────────

function playBase64Audio(b64) {
  return new Promise(resolve => {
    const player = $id('debate-player');
    const done = () => {
      player.onended = null; player.onerror = null;
      player.oncanplay = null; player.oncanplaythrough = null;
      resolve();
    };
    const tryPlay = () => {
      player.oncanplay = null; player.oncanplaythrough = null;
      player.play().catch(done);
    };
    player.onended  = done;
    player.onerror  = done;
    player.oncanplay = tryPlay;
    player.oncanplaythrough = tryPlay;
    player.src = `data:audio/mpeg;base64,${b64}`;
    player.load();
  });
}

function addRoundLabel(round) {
  const sep = document.createElement('div');
  sep.className = 'arena-round-label';
  sep.textContent = `Round ${round}`;
  $id('arena-feed').appendChild(sep);
}

function addTurnBubble(turn) {
  const div = document.createElement('div');
  div.className = 'arena-turn';
  div.innerHTML = `
    <img class="arena-turn-avatar" src="${turn.avatar}" alt="${turn.character_name}">
    <div class="arena-turn-body">
      <div class="arena-turn-name">${turn.character_name}</div>
      <div class="arena-turn-text">${turn.argument}</div>
    </div>
  `;
  $id('arena-feed').appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function addModeratorBubble(text, kind) {
  const div = document.createElement('div');
  div.className = `arena-moderator arena-moderator--${kind}`;
  div.innerHTML = `
    <div class="arena-moderator-label">⚖️ Alex — Moderator</div>
    <div class="arena-moderator-text">${text}</div>
  `;
  $id('arena-feed').appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

async function consumeDebateStream(body) {
  const reader  = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', lastRound = 0;

  while (true) {
    if (_debateStopped) { reader.cancel(); return; }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop();

    for (const raw of events) {
      if (_debateStopped) { reader.cancel(); return; }
      const lines = raw.trim().split('\n');
      let eventType = 'message', dataStr = '';
      for (const line of lines) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim();
        if (line.startsWith('data:'))  dataStr  = line.slice(5).trim();
      }
      if (!dataStr) continue;
      let data;
      try { data = JSON.parse(dataStr); } catch { continue; }

      if (eventType === 'error')           { $id('debate-status').textContent = `Error: ${data.detail}`; return; }
      if (eventType === 'round')           continue;
      if (eventType === 'moderator_intro') {
        addModeratorBubble(data.text, 'intro');
        if (data.audio_b64) await playBase64Audio(data.audio_b64);
        if (_debateStopped) return;
        await new Promise(r => setTimeout(r, 300));
      }
      if (eventType === 'turn') {
        if (data.round !== lastRound) { addRoundLabel(data.round); lastRound = data.round; }
        $id('typing-name').textContent = `${data.character_name} is speaking…`;
        $id('arena-typing').classList.remove('hidden');
        $id('arena-typing').scrollIntoView({ behavior: 'smooth', block: 'end' });
        await new Promise(r => setTimeout(r, 300));
        $id('arena-typing').classList.add('hidden');
        addTurnBubble(data);
        if (data.audio_b64) await playBase64Audio(data.audio_b64);
        if (_debateStopped) return;
        await new Promise(r => setTimeout(r, 400));
      }
      if (eventType === 'moderator_summary') {
        addModeratorBubble(data.text, 'summary');
        if (data.audio_b64) await playBase64Audio(data.audio_b64);
        if (_debateStopped) return;
        await new Promise(r => setTimeout(r, 600));
      }
      if (eventType === 'done') { $id('arena-typing').classList.add('hidden'); return; }
    }
  }
}

// ═══════════════════════════════════════════════════════
//  NAVIGATION WIRING
// ═══════════════════════════════════════════════════════

// Home screen nav
$id('nav-home-link').onclick        = () => showScreen('screen-home');
$id('nav-marketplace-link').onclick = () => showScreen('screen-marketplace');
$id('nav-debate-link').onclick      = openDebate;
$id('nav-play-link').onclick        = () => showScreen('screen-play');
$id('logout-button').onclick        = doLogout;

// Marketplace screen nav
$id('nav-home-link2').onclick        = () => showScreen('screen-home');
$id('nav-marketplace-link2').onclick = () => showScreen('screen-marketplace');
$id('nav-debate-link2').onclick      = openDebate;
$id('nav-play-link2').onclick        = () => showScreen('screen-play');
$id('logout-button2').onclick        = doLogout;

// Chat screen nav
$id('chat-back-btn').onclick          = () => showScreen('screen-home');
$id('nav-marketplace-link3').onclick  = () => showScreen('screen-marketplace');
$id('nav-debate-link3').onclick       = openDebate;
$id('nav-play-link3').onclick         = () => showScreen('screen-play');

// Debate screen nav
$id('debate-back-btn').onclick        = () => showScreen('screen-home');
$id('nav-home-link3').onclick         = () => showScreen('screen-home');
$id('nav-marketplace-link4').onclick  = () => showScreen('screen-marketplace');
$id('nav-play-link4').onclick         = () => showScreen('screen-play');

// Play screen nav
$id('nav-home-link4').onclick         = () => showScreen('screen-home');
$id('nav-marketplace-link5').onclick  = () => showScreen('screen-marketplace');
$id('nav-debate-link5').onclick       = openDebate;
$id('logout-button3').onclick         = doLogout;

// ── Detective game launch / back ──────────────────────────────────────────
$id('play-launch-detective').onclick = () => {
  const iframe = $id('play-detective-iframe');
  // Load the game on first launch; subsequent opens reuse the same session.
  if (!iframe.src || iframe.src === window.location.href) {
    iframe.src = '/detective/';
  }
  $id('play-hub').classList.add('hidden');
  $id('play-detective-frame-wrap').classList.remove('hidden');
};

$id('play-frame-back-btn').onclick = () => {
  $id('play-detective-frame-wrap').classList.add('hidden');
  $id('play-hub').classList.remove('hidden');
};

// Marketplace "create" button
$id('mp-create-btn').onclick = () => alert('Character Studio — coming soon!');

// Story poster "Chat with X" buttons
const STORY_CHARACTERS = {
  nova: {
    id: '_story_nova',
    name: 'Nova',
    description: 'An AI from 2147 crash-lands in the present day — carrying secrets that could rewrite history.',
    avatar: '/posters/media_08e3c3ab0b233157777531f44d7282189f110dc6.webp',
    voice_id: null,
  },
  princess: {
    id: '_story_princess',
    name: 'Princess',
    description: 'Exiled from her kingdom, she must choose between her crown and her conscience.',
    avatar: '/posters/media_a14409abc875067850659bd5107518d2a6df72c3.webp',
    voice_id: null,
  },
  yodha: {
    id: '_story_yodha',
    name: 'Yodha',
    description: 'The last warrior of a dying empire battles not just enemies — but the ghost of who he was.',
    avatar: '/posters/media_c5368aaf32b04d92e3a0f535be66acab7d4038d7.webp',
    voice_id: null,
  },
};

document.querySelectorAll('.story-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const key = btn.dataset.story;
    const storyChar = STORY_CHARACTERS[key];
    if (storyChar) openChat(storyChar);
  });
});

function doLogout() {
  localStorage.removeItem('auth-user');
  location.reload();
}

// ═══════════════════════════════════════════════════════
//  BOOT
// ═══════════════════════════════════════════════════════

if (currentUser) {
  enterApp();
} else {
  showScreen('screen-landing');
}
