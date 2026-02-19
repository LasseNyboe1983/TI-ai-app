const userInfoEl = document.getElementById('userInfo');
const form = document.getElementById('promptForm');
const promptEl = document.getElementById('prompt');
const chatEl = document.getElementById('chat');
const sendBtn = document.getElementById('sendBtn');
const modelEl = document.getElementById('model');
const modelToggleBtn = document.getElementById('modelToggleBtn');
const modelMenuEl = document.getElementById('modelMenu');
const modelDescriptionEl = document.getElementById('modelDescription');
const modelNameEl = document.getElementById('modelName');
const attachDocBtn = document.getElementById('attachDocBtn');
const docFileInput = document.getElementById('docFileInput');
const docStatusEl = document.getElementById('docStatus');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const signOutBtn = document.getElementById('signOutBtn');

let conversationHistory = [];
let attachedDocument = null;

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const MAX_CONTEXT_CHUNKS = 4;

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

function formatModelType(type) {
  const rawType = String(type || '').trim().toLowerCase();
  if (!rawType) return 'Model';
  if (rawType === 'image') return 'Picture';
  return rawType.charAt(0).toUpperCase() + rawType.slice(1);
}

function setDocumentStatus(text, isError = false) {
  if (!docStatusEl) return;
  docStatusEl.textContent = text || '';
  docStatusEl.style.color = isError ? '#b91c1c' : '#64748b';
}

function clearAttachedDocument() {
  attachedDocument = null;
  setDocumentStatus('');
}

function buildWordSet(value) {
  const words = String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter((word) => word.length > 2);
  return new Set(words);
}

function pickRelevantChunks(prompt, chunks) {
  const promptWords = buildWordSet(prompt);
  if (!promptWords.size) return chunks.slice(0, MAX_CONTEXT_CHUNKS);

  const scored = chunks.map((chunk, index) => {
    const chunkWords = buildWordSet(chunk);
    let overlap = 0;
    for (const word of promptWords) {
      if (chunkWords.has(word)) overlap += 1;
    }
    return { chunk, index, score: overlap };
  });

  return scored
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.index - b.index;
    })
    .slice(0, MAX_CONTEXT_CHUNKS)
    .filter((item) => item.score > 0)
    .map((item) => item.chunk);
}

function buildDocumentContext(prompt) {
  if (!attachedDocument || !Array.isArray(attachedDocument.chunks) || !attachedDocument.chunks.length) {
    return '';
  }

  const selectedChunks = pickRelevantChunks(prompt, attachedDocument.chunks);
  const fallbackChunks = attachedDocument.chunks.slice(0, MAX_CONTEXT_CHUNKS);
  const chunksToUse = selectedChunks.length ? selectedChunks : fallbackChunks;

  return `Document: ${attachedDocument.fileName}\n\n${chunksToUse.join('\n\n---\n\n')}`;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const payload = result.includes(',') ? result.split(',', 2)[1] : result;
      resolve(payload);
    };
    reader.onerror = () => reject(new Error('Failed to read selected file.'));
    reader.readAsDataURL(file);
  });
}

async function uploadDocument(file) {
  if (!file) return;

  if (file.size > MAX_UPLOAD_BYTES) {
    setDocumentStatus('File too large. Max size is 10 MB.', true);
    return;
  }

  setDocumentStatus(`Uploading ${file.name}...`);

  try {
    const fileContentBase64 = await fileToBase64(file);
    const response = await fetch('/api/document', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        fileName: file.name,
        fileContentBase64,
      }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      setDocumentStatus(data.error || 'Failed to process document.', true);
      return;
    }

    attachedDocument = {
      fileName: data.fileName || file.name,
      chunks: Array.isArray(data.chunks) ? data.chunks : [],
    };

    if (!attachedDocument.chunks.length) {
      setDocumentStatus('No usable text found in document.', true);
      return;
    }

    setDocumentStatus(`Attached ${attachedDocument.fileName} (${data.chunkCount || attachedDocument.chunks.length} chunks)`);
  } catch {
    setDocumentStatus('Network or server error while uploading document.', true);
  }
}

function renderSelectedModel() {
  if (!modelEl || !modelDescriptionEl || !modelNameEl) return;

  const selected = modelEl.selectedOptions?.[0];
  if (!selected) {
    modelDescriptionEl.textContent = 'Model';
    modelNameEl.textContent = '';
    return;
  }

  modelDescriptionEl.textContent = selected.dataset.typeLabel || 'Model';
  modelNameEl.textContent = selected.dataset.modelName || selected.value;
}

function closeModelMenu() {
  if (!modelMenuEl || !modelToggleBtn) return;
  modelMenuEl.hidden = true;
  modelToggleBtn.setAttribute('aria-expanded', 'false');
}

function openModelMenu() {
  if (!modelMenuEl || !modelToggleBtn) return;
  modelMenuEl.hidden = false;
  modelToggleBtn.setAttribute('aria-expanded', 'true');
}

function buildModelMenu() {
  if (!modelMenuEl || !modelEl) return;

  modelMenuEl.innerHTML = '';
  const options = Array.from(modelEl.options);

  for (const option of options) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'model-item';
    item.setAttribute('role', 'option');
    item.setAttribute('aria-selected', String(option.selected));

    const description = document.createElement('span');
    description.className = 'model-item-description';
    description.textContent = option.dataset.typeLabel || 'Model';

    const name = document.createElement('span');
    name.className = 'model-item-name';
    name.textContent = option.dataset.modelName || option.value;

    item.appendChild(description);
    item.appendChild(name);

    item.addEventListener('click', () => {
      modelEl.value = option.value;
      for (const menuChild of modelMenuEl.children) {
        menuChild.setAttribute('aria-selected', 'false');
      }
      item.setAttribute('aria-selected', 'true');
      renderSelectedModel();
      closeModelMenu();
      modelToggleBtn?.focus();
    });

    modelMenuEl.appendChild(item);
  }
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
      const typeLabel = formatModelType(model.type);
      option.dataset.typeLabel = typeLabel;
      option.dataset.modelName = model.label || model.id;
      option.textContent = `${typeLabel} - ${model.label || model.id}`;
      modelEl.appendChild(option);
    }

    if (!modelEl.options.length) {
      const fallback = document.createElement('option');
      fallback.value = 'gpt-35-turbo';
      fallback.dataset.typeLabel = 'Chat';
      fallback.dataset.modelName = 'gpt-35-turbo';
      fallback.textContent = 'Chat - gpt-35-turbo';
      modelEl.appendChild(fallback);
    }

    buildModelMenu();
    renderSelectedModel();
  } catch {
    modelEl.innerHTML = '';
    const fallback = document.createElement('option');
    fallback.value = 'gpt-35-turbo';
    fallback.dataset.typeLabel = 'Chat';
    fallback.dataset.modelName = 'gpt-35-turbo';
    fallback.textContent = 'Chat - gpt-35-turbo';
    modelEl.appendChild(fallback);

    buildModelMenu();
    renderSelectedModel();
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
    if (userInfoEl) userInfoEl.textContent = username ? `Welcome ${username}` : '';
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
        documentContext: buildDocumentContext(prompt),
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
    clearAttachedDocument();
  });
}

if (signOutBtn) {
  signOutBtn.addEventListener('click', () => {
    clearAttachedDocument();
    window.location.assign('/.auth/logout?post_logout_redirect_uri=%2Fsigned-out-full.html');
  });
}

if (attachDocBtn && docFileInput) {
  attachDocBtn.addEventListener('click', () => {
    docFileInput.click();
  });

  docFileInput.addEventListener('change', async () => {
    const file = docFileInput.files?.[0];
    await uploadDocument(file);
    docFileInput.value = '';
  });
}

if (modelToggleBtn) {
  modelToggleBtn.addEventListener('click', () => {
    if (modelMenuEl?.hidden) {
      openModelMenu();
    } else {
      closeModelMenu();
    }
  });

  modelToggleBtn.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openModelMenu();
      const firstItem = modelMenuEl?.querySelector('.model-item');
      if (firstItem instanceof HTMLElement) firstItem.focus();
    }
  });
}

if (modelMenuEl) {
  modelMenuEl.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeModelMenu();
      modelToggleBtn?.focus();
    }
  });
}

document.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (!target.closest('.model-selector')) {
    closeModelMenu();
  }
});

loadUser();
loadModels();
