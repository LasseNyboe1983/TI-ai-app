const userInfoEl = document.getElementById('userInfo');
const form = document.getElementById('promptForm');
const promptEl = document.getElementById('prompt');
const chatEl = document.getElementById('chat');
const sendBtn = document.getElementById('sendBtn');
const modelEl = document.getElementById('model');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const signOutBtn = document.getElementById('signOutBtn');

let conversationHistory = [];

function getClaim(claims, keys) {
  if (!Array.isArray(claims)) return null;
  for (const key of keys) {
    const match = claims.find((c) => c?.typ === key && c?.val);
    if (match?.val) return match.val;
  }
  return null;
}

function tenantFromIssuer(issuer) {
  if (!issuer || typeof issuer !== 'string') return null;
  const marker = 'login.microsoftonline.com/';
  if (!issuer.includes(marker)) return null;
  return issuer.split(marker)[1]?.split('/')[0] || null;
}

function addMessage(role, text) {
  const node = document.createElement('div');
  node.className = `msg ${role}`;
  node.textContent = text;
  chatEl.appendChild(node);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function addImageMessage(role, imageUrl) {
  const node = document.createElement('div');
  node.className = `msg ${role}`;

  const image = document.createElement('img');
  image.className = 'msg-image';
  image.src = imageUrl;
  image.alt = 'Generated image';

  node.appendChild(image);
  chatEl.appendChild(node);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function loadModels() {
  try {
    const response = await fetch('/api/models', { credentials: 'include' });
    const data = await response.json();
    const models = Array.isArray(data?.models) ? data.models : [];

    modelEl.innerHTML = '';
    for (const model of models) {
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = model.label || model.id;
      modelEl.appendChild(option);
    }

    if (!modelEl.options.length) {
      const fallback = document.createElement('option');
      fallback.value = 'gpt-35-turbo';
      fallback.textContent = 'gpt-35-turbo';
      modelEl.appendChild(fallback);
    }
  } catch {
    modelEl.innerHTML = '';
    const fallback = document.createElement('option');
    fallback.value = 'gpt-35-turbo';
    fallback.textContent = 'gpt-35-turbo';
    modelEl.appendChild(fallback);
  }
}

async function loadUser() {
  try {
    const res = await fetch('/.auth/me', { credentials: 'include' });
    if (!res.ok) {
      if (userInfoEl) userInfoEl.textContent = '';
      return;
    }

    const payload = await res.json();
    const principal = payload?.clientPrincipal;
    if (!principal) {
      if (userInfoEl) userInfoEl.textContent = '';
      window.location.replace('/.auth/login/aad?post_login_redirect_uri=/');
      return;
    }

    const username = principal.userDetails || '';
    if (userInfoEl) userInfoEl.textContent = username;
  } catch {
    if (userInfoEl) userInfoEl.textContent = '';
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = promptEl.value.trim();
  if (!prompt) return;

  addMessage('user', prompt);
  promptEl.value = '';
  sendBtn.disabled = true;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        prompt,
        model: modelEl.value,
        conversationHistory,
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const details = [];
      if (data.expectedTenant) details.push(`expected=${data.expectedTenant}`);
      if (data.actualTenant) details.push(`actual=${data.actualTenant}`);
      const detailText = details.length ? ` (${details.join(', ')})` : '';
      addMessage('system', (data.error || 'Request failed.') + detailText);
      return;
    }

    const replyType = data.replyType || 'text';
    const reply = data.reply || '';
    const imageUrl = data.imageUrl || '';

    if (replyType === 'image' && imageUrl) {
      addImageMessage('assistant', imageUrl);
    } else {
      addMessage('assistant', reply || '(No response)');
    }

    conversationHistory = Array.isArray(data.conversationHistory)
      ? data.conversationHistory
      : [...conversationHistory, { role: 'user', content: prompt }, { role: 'assistant', content: reply || '[image generated]' }];
  } catch {
    addMessage('system', 'Network or server error.');
  } finally {
    sendBtn.disabled = false;
  }
});

if (clearHistoryBtn) {
  clearHistoryBtn.addEventListener('click', () => {
    conversationHistory = [];
    chatEl.innerHTML = '';
  });
}

if (signOutBtn) {
  signOutBtn.addEventListener('click', () => {
    window.location.assign('/.auth/logout?post_logout_redirect_uri=%2Fsigned-out-full.html');
  });
}

loadUser();
loadModels();
