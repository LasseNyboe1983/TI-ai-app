// Additional auth enforcement with tenant validation
(async function enforceAuth() {
  const ALLOWED_TENANT_ID = 'a157a1e5-2a04-45f5-9ca8-bd60db6bafd4';
  
  // Prevent redirect loops
  if (sessionStorage.getItem('authCheckInProgress') === 'true') {
    console.log('Auth check already in progress, skipping');
    return;
  }
  sessionStorage.setItem('authCheckInProgress', 'true');
  
  try {
    const res = await fetch('/.auth/me');
    const data = await res.json();
    
    if (!data.clientPrincipal || !data.clientPrincipal.userRoles.includes('authenticated')) {
      sessionStorage.removeItem('authCheckInProgress');
      window.location.replace('/');
      throw new Error('Not authenticated');
    }
    
    // Validate tenant ID and identity provider
    const userClaims = data.clientPrincipal.claims || [];
    const tidClaim = userClaims.find(c => c.typ === 'http://schemas.microsoft.com/identity/claims/tenantid');
    const userTenantId = tidClaim ? tidClaim.val : null;
    const identityProvider = data.clientPrincipal.identityProvider;
    const userId = data.clientPrincipal.userId;
    
    console.log('User Tenant ID:', userTenantId);
    console.log('Allowed Tenant ID:', ALLOWED_TENANT_ID);
    console.log('Identity Provider:', identityProvider);
    console.log('User ID:', userId);
    console.log('All claims:', userClaims);
    
    // Block personal Microsoft accounts (they don't have proper tenant IDs)
    if (!userTenantId || userTenantId === '9188040d-6c67-4c5b-b112-36a304b66dad') {
      console.warn('Personal account detected, redirecting to access-denied page');
      sessionStorage.removeItem('authCheckInProgress');
      await fetch('/.auth/logout');
      window.location.replace('/access-denied.html');
      throw new Error('Personal account detected');
    }
    
    // Verify user is from the allowed tenant
    if (userTenantId.toLowerCase() !== ALLOWED_TENANT_ID.toLowerCase()) {
      console.warn('Wrong tenant:', userTenantId, 'Expected:', ALLOWED_TENANT_ID);
      sessionStorage.removeItem('authCheckInProgress');
      await fetch('/.auth/logout');
      window.location.replace('/access-denied.html');
      throw new Error('Wrong tenant');
    }
    
    // Auth successful - clear the flag
    console.log('Auth check passed!');
    sessionStorage.removeItem('authCheckInProgress');
  } catch (err) {
    if (err.message !== 'Not authenticated' && err.message !== 'Wrong tenant') {
      window.location.replace('/');
      throw err;
    }
  }
})();

const form = document.getElementById('promptForm');
const chat = document.getElementById('chat');
const modelSelect = document.getElementById('modelSelect');
const input = document.getElementById('promptInput');
const userInfo = document.getElementById('userInfo');

// Conversation history
let conversationHistory = [];

// Fetch and display user info
async function loadUserInfo() {
  try {
    const res = await fetch('/.auth/me');
    const data = await res.json();
    if (data.clientPrincipal) {
      const name = data.clientPrincipal.userDetails || data.clientPrincipal.userId || 'User';
      userInfo.textContent = `Signed in as: ${name}`;
    }
  } catch (err) {
    console.warn('Failed to load user info', err);
  }
}

function addMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

loadUserInfo();

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;
  
  // Add user message to history and display
  conversationHistory.push({ role: 'user', content: prompt });
  addMessage(prompt, 'user');
  input.value = '';
  
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        prompt, 
        model: modelSelect.value,
        history: conversationHistory
      })
    });
    const data = await response.json();
    const answer = data.answer ?? 'No response';
    
    // Add assistant message to history and display
    conversationHistory.push({ role: 'assistant', content: answer });
    addMessage(answer, 'assistant');
  } catch {
    addMessage('Error contacting AI service.', 'assistant');
  } finally {
    button.disabled = false;
  }
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
