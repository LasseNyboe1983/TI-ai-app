const statusEl = document.getElementById('status');
const form = document.getElementById('promptForm');
const promptEl = document.getElementById('prompt');
const chatEl = document.getElementById('chat');
const sendBtn = document.getElementById('sendBtn');
const modelEl = document.getElementById('model');

let conversationHistory = [];

function addMessage(role, text) {
  const node = document.createElement('div');
  node.className = `msg ${role}`;
  node.textContent = text;
  chatEl.appendChild(node);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function loadUser() {
  try {
    const res = await fetch('/.auth/me', { credentials: 'include' });
    if (!res.ok) {
      statusEl.textContent = 'Authentication session not available.';
      return;
    }

    const payload = await res.json();
    const principal = payload?.clientPrincipal;
    const username = principal?.userDetails || 'Authenticated user';
    statusEl.textContent = `Signed in as ${username}`;
  } catch {
    statusEl.textContent = 'Unable to read authentication session.';
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
      addMessage('system', data.error || 'Request failed.');
      return;
    }

    const reply = data.reply || '(No response)';
    addMessage('assistant', reply);

    conversationHistory = Array.isArray(data.conversationHistory)
      ? data.conversationHistory
      : [...conversationHistory, { role: 'user', content: prompt }, { role: 'assistant', content: reply }];
  } catch {
    addMessage('system', 'Network or server error.');
  } finally {
    sendBtn.disabled = false;
  }
});

loadUser();
