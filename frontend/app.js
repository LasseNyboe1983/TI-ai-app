const statusEl = document.getElementById('status');
const form = document.getElementById('promptForm');
const promptEl = document.getElementById('prompt');
const chatEl = document.getElementById('chat');
const sendBtn = document.getElementById('sendBtn');
const modelEl = document.getElementById('model');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');

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

async function loadUser() {
  try {
    const res = await fetch('/.auth/me', { credentials: 'include' });
    if (!res.ok) {
      statusEl.textContent = 'Authentication session not available.';
      return;
    }

    const payload = await res.json();
    const principal = payload?.clientPrincipal;
    if (!principal) {
      statusEl.textContent = 'Not signed in. Redirecting to Microsoft Entra login...';
      window.location.replace('/.auth/login/aad?post_login_redirect_uri=/');
      return;
    }

    const username = principal.userDetails || 'Authenticated user';
    const claims = principal?.claims || [];
    const provider = principal?.identityProvider || 'unknown';
    const tenant =
      getClaim(claims, ['tid', 'http://schemas.microsoft.com/identity/claims/tenantid', 'tenantid']) ||
      tenantFromIssuer(getClaim(claims, ['iss'])) ||
      'missing';

    statusEl.textContent = `Signed in as ${username} | provider=${provider} | tenant=${tenant}`;
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
      const details = [];
      if (data.expectedTenant) details.push(`expected=${data.expectedTenant}`);
      if (data.actualTenant) details.push(`actual=${data.actualTenant}`);
      const detailText = details.length ? ` (${details.join(', ')})` : '';
      addMessage('system', (data.error || 'Request failed.') + detailText);
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

if (clearHistoryBtn) {
  clearHistoryBtn.addEventListener('click', () => {
    conversationHistory = [];
    chatEl.innerHTML = '';
  });
}

loadUser();
