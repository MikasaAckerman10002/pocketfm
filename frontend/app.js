const loginScreen = document.getElementById('login-screen');
const appScreen = document.getElementById('app-screen');
const authError = document.getElementById('auth-error');
const username = document.getElementById('username');
const characterList = document.getElementById('character-list');
const characterName = document.getElementById('character-name');
const characterDescription = document.getElementById('character-description');
const profileName = document.getElementById('profile-name');
const profileGender = document.getElementById('profile-gender');
const profileBasics = document.getElementById('profile-basics');
const saveProfileButton = document.getElementById('save-profile-button');
const recordButton = document.getElementById('record-button');
const stopButton = document.getElementById('stop-button');
const statusText = document.getElementById('status');
const player = document.getElementById('player');
const conversation = document.getElementById('conversation');

let currentUser = JSON.parse(localStorage.getItem('auth-user') || 'null');
let currentCharacter = null;
let recorder;
let chunks = [];
let stream;

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    throw new Error(payload.detail || payload || 'Request failed');
  }
  return payload;
}

async function loadCharacters() {
  const characters = await request('/characters');
  characterList.innerHTML = '';
  characters.forEach((character, index) => {
    const button = document.createElement('button');
    button.className = 'character-item secondary';
    button.textContent = character.name;
    button.onclick = () => selectCharacter(character, button);
    characterList.appendChild(button);
    if (index === 0) {
      selectCharacter(character, button);
    }
  });
}

function selectCharacter(character, button) {
  currentCharacter = character;
  characterName.textContent = character.name;
  characterDescription.textContent = character.description;
  document.querySelectorAll('.character-item').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  conversation.textContent = '';
  statusText.textContent = `Ready to talk to ${character.name}.`;
}

function renderAuthenticatedApp() {
  loginScreen.classList.add('hidden');
  appScreen.classList.remove('hidden');
  username.textContent = currentUser.name;
  profileName.value = currentUser.name || '';
  profileGender.value = currentUser.gender || '';
  profileBasics.value = currentUser.basics || '';
  loadCharacters();
}

async function handleSignup() {
  try {
    currentUser = await request('/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('signup-name').value,
        email: document.getElementById('signup-email').value,
        password: document.getElementById('signup-password').value,
        gender: document.getElementById('signup-gender').value,
        basics: document.getElementById('signup-basics').value,
      }),
    });
    localStorage.setItem('auth-user', JSON.stringify(currentUser));
    renderAuthenticatedApp();
  } catch (error) {
    authError.textContent = error.message;
  }
}

async function handleLogin() {
  try {
    currentUser = await request('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: document.getElementById('login-email').value,
        password: document.getElementById('login-password').value,
      }),
    });
    localStorage.setItem('auth-user', JSON.stringify(currentUser));
    renderAuthenticatedApp();
  } catch (error) {
    authError.textContent = error.message;
  }
}

async function saveProfile() {
  try {
    const previousUser = JSON.parse(localStorage.getItem('auth-user') || 'null');
    const updated = await request('/profiles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUser.user_id,
        name: profileName.value,
        gender: profileGender.value,
        basics: profileBasics.value,
      }),
    });
    currentUser = { ...previousUser, ...updated };
    localStorage.setItem('auth-user', JSON.stringify(currentUser));
    username.textContent = currentUser.name;
    statusText.textContent = 'Profile saved.';
  } catch (error) {
    statusText.textContent = error.message;
  }
}

recordButton.onclick = async () => {
  if (!currentUser || !currentCharacter) {
    statusText.textContent = 'Login and choose a character first.';
    return;
  }
  stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  recorder = new MediaRecorder(stream);
  chunks = [];
  recorder.ondataavailable = (event) => chunks.push(event.data);
  recorder.onstop = async () => {
    statusText.textContent = `Sending your voice note to ${currentCharacter.name}...`;
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
    const form = new FormData();
    form.append('audio', blob, 'voice-note.webm');
    const response = await fetch(`/voice-chat?character_id=${encodeURIComponent(currentCharacter.id)}&user_id=${encodeURIComponent(currentUser.user_id)}`, {
      method: 'POST',
      body: form,
    });
    if (!response.ok) {
      conversation.textContent = await response.text();
      statusText.textContent = 'Request failed.';
      return;
    }
    const audioBlob = await response.blob();
    player.src = URL.createObjectURL(audioBlob);
    player.play();
    conversation.textContent = `Transcript: ${decodeURIComponent(response.headers.get('X-Transcript') || '')}\n\nReply: ${decodeURIComponent(response.headers.get('X-Reply') || '')}`;
    statusText.textContent = `${currentCharacter.name} replied.`;
  };
  recorder.start();
  recordButton.disabled = true;
  stopButton.disabled = false;
  statusText.textContent = 'Recording...';
};

stopButton.onclick = () => {
  recorder.stop();
  stream.getTracks().forEach((track) => track.stop());
  recordButton.disabled = false;
  stopButton.disabled = true;
};

document.getElementById('signup-button').onclick = handleSignup;
document.getElementById('login-button').onclick = handleLogin;
document.getElementById('logout-button').onclick = () => {
  localStorage.removeItem('auth-user');
  location.reload();
};
saveProfileButton.onclick = saveProfile;

if (currentUser) {
  renderAuthenticatedApp();
}
