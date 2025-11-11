const form = document.getElementById('promptForm');
const chat = document.getElementById('chat');
const modelSelect = document.getElementById('modelSelect');
const input = document.getElementById('promptInput');

function addMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;
  addMessage(prompt, 'user');
  input.value = '';
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, model: modelSelect.value })
    });
    const data = await response.json();
    addMessage(data.answer ?? 'No response', 'assistant');
  } catch {
    addMessage('Error contacting AI service.', 'assistant');
  } finally {
    button.disabled = false;
  }
});
