// Validate access by checking the backend
(async function validateAccess() {
  try {
    const testRes = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: 'test', model: 'gpt-35-turbo', history: [] })
    });
    
    if (testRes.status === 403) {
      // User is not authorized - redirect to access denied
      await fetch('/.auth/logout');
      window.location.replace('/access-denied.html');
      throw new Error('Access denied');
    }
  } catch (err) {
    if (err.message === 'Access denied') throw err;
    console.error('Access validation failed:', err);
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
