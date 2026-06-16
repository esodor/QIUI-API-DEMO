/* ─── STATE ─────────────────────────────────────────────────── */
let sessionId = localStorage.getItem('sb_session') || '';
let pendingFiles = [];
let currentArea = null;
let currentFileContent = '';
let currentFilePath = '';

const AREA_ICONS = {
  memoria: '🧠', diario: '📓', lavoro: '💼', trading: '📈',
  finanze: '💰', salute: '❤️', casa: '🏠', relazioni: '👥',
  progetti: '🚀', decisioni: '⚖️', documenti: '📄',
  schemi: '🔍', regole: '📋'
};

/* ─── INIT ──────────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  marked.setOptions({ breaks: true, gfm: true });
  checkStatus();
  loadBrainNav();
});

/* ─── STATUS CHECK ──────────────────────────────────────────── */
async function checkStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    const dot = document.getElementById('statusDot');
    if (data.has_key) {
      dot.className = 'status-dot ok';
      dot.title = `Connesso — ${data.model}`;
      document.getElementById('apiBanner').style.display = 'none';
    } else {
      dot.className = 'status-dot error';
      dot.title = 'API key mancante';
      document.getElementById('apiBanner').style.display = 'block';
    }
  } catch {
    document.getElementById('statusDot').className = 'status-dot error';
  }
}

/* ─── BRAIN NAV ─────────────────────────────────────────────── */
async function loadBrainNav() {
  try {
    const r = await fetch('/api/brain');
    const brain = await r.json();
    const nav = document.getElementById('brainNav');
    nav.innerHTML = '';
    for (const [area, files] of Object.entries(brain)) {
      const btn = document.createElement('button');
      btn.innerHTML = `
        <span class="area-icon">${AREA_ICONS[area] || '📁'}</span>
        <span>${capitalize(area)}</span>
        ${files.length ? `<span class="area-count">${files.length}</span>` : ''}
      `;
      btn.onclick = () => selectArea(area, files, btn);
      nav.appendChild(btn);
    }
  } catch (e) {
    console.error('Brain nav error', e);
  }
}

function selectArea(area, files, btn) {
  document.querySelectorAll('.brain-nav button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentArea = area;

  const fileList = document.getElementById('fileList');
  const label = document.getElementById('filesLabel');

  if (files.length === 0) {
    fileList.innerHTML = '<div style="padding:12px 16px;font-size:12.5px;color:var(--muted)">Nessun file ancora</div>';
  } else {
    fileList.innerHTML = files.map(f => `
      <div class="file-item" onclick="viewFile('${f.path}')">
        <span>📄</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.name}</span>
        <span class="file-date">${f.modified}</span>
      </div>
    `).join('');
  }
  label.style.display = 'block';
}

/* ─── SEND MESSAGE ──────────────────────────────────────────── */
async function sendMessage() {
  const input = document.getElementById('msgInput');
  const text = input.value.trim();
  if (!text && pendingFiles.length === 0) return;

  const welcome = document.getElementById('welcome');
  if (welcome) welcome.remove();

  appendMessage('user', text || `[${pendingFiles.length} file allegati]`, pendingFiles);

  input.value = '';
  input.style.height = 'auto';
  clearUploadPreview();

  setSending(true);
  const typingId = showTyping();

  try {
    const form = new FormData();
    form.append('message', text);
    form.append('session_id', sessionId);
    for (const f of pendingFiles) form.append('files', f);

    const r = await fetch('/api/chat', { method: 'POST', body: form });
    const data = await r.json();

    removeTyping(typingId);

    if (!r.ok) {
      appendMessage('assistant', `❌ Errore: ${data.detail || 'Qualcosa è andato storto'}`);
      return;
    }

    sessionId = data.session_id;
    localStorage.setItem('sb_session', sessionId);

    appendMessage('assistant', data.response, [], data.tokens);
    pendingFiles = [];

  } catch (e) {
    removeTyping(typingId);
    appendMessage('assistant', `❌ Errore di connessione: ${e.message}`);
  } finally {
    setSending(false);
  }
}

/* ─── APPEND MESSAGE ────────────────────────────────────────── */
function appendMessage(role, content, files = [], tokens = null) {
  const chat = document.getElementById('chatArea');
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = role === 'user' ? 'Tu' : '🧠 Secondo Cervello';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  if (role === 'assistant') {
    bubble.innerHTML = marked.parse(content);
  } else {
    bubble.textContent = content;
    // Show file thumbnails in user bubble
    if (files.length > 0) {
      const fileInfo = document.createElement('div');
      fileInfo.style.cssText = 'margin-top:8px;font-size:12px;color:var(--muted)';
      fileInfo.textContent = files.map(f => `📎 ${f.name}`).join(' · ');
      bubble.appendChild(fileInfo);
    }
  }

  div.appendChild(label);
  div.appendChild(bubble);

  if (role === 'assistant') {
    const actions = document.createElement('div');
    actions.className = 'msg-actions';

    // Copy button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'msg-action-btn';
    copyBtn.textContent = '📋 Copia';
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(content);
      copyBtn.textContent = '✓ Copiato';
      setTimeout(() => copyBtn.textContent = '📋 Copia', 2000);
    };
    actions.appendChild(copyBtn);

    // Save button
    const saveBtn = document.createElement('button');
    saveBtn.className = 'msg-action-btn save-btn';
    saveBtn.textContent = '💾 Salva nel Cervello';
    saveBtn.onclick = () => {
      const proposal = parseSaveProposal(content);
      openSaveModal(proposal.path, proposal.content || content);
    };
    actions.appendChild(saveBtn);

    if (tokens) {
      const tokBtn = document.createElement('button');
      tokBtn.className = 'msg-action-btn';
      tokBtn.textContent = `🔢 ${tokens.in + tokens.out} token`;
      tokBtn.style.cursor = 'default';
      tokBtn.title = `Input: ${tokens.in} | Output: ${tokens.out}`;
      actions.appendChild(tokBtn);
    }

    div.appendChild(actions);
  }

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

/* ─── PARSE SAVE PROPOSAL ───────────────────────────────────── */
function parseSaveProposal(text) {
  const pathMatch = text.match(/File:\s*`?([^\s`\n]+secondo-cervello\/[^\s`\n]+\.md)`?/i)
                 || text.match(/`?(secondo-cervello\/[^\s`\n]+\.md)`?/i);
  const path = pathMatch ? pathMatch[1].trim() : '';

  // Try to extract content block
  const contentMatch = text.match(/CONTENUTO[:\s]*\n([\s\S]+?)(?=---|\n#|$)/i);
  const content = contentMatch ? contentMatch[1].trim() : '';

  return { path, content };
}

/* ─── QUICK ACTIONS ─────────────────────────────────────────── */
function quickAction(prefix) {
  const input = document.getElementById('msgInput');
  if (prefix.endsWith(': ')) {
    input.value = prefix;
    input.focus();
  } else {
    input.value = prefix;
    sendMessage();
  }
}

/* ─── FILE UPLOAD ───────────────────────────────────────────── */
function handleFiles(fileList) {
  for (const f of fileList) {
    if (!pendingFiles.find(p => p.name === f.name)) {
      pendingFiles.push(f);
    }
  }
  renderUploadPreview();
  document.getElementById('fileInput').value = '';
}

function renderUploadPreview() {
  const preview = document.getElementById('uploadPreview');
  preview.innerHTML = '';
  for (let i = 0; i < pendingFiles.length; i++) {
    const f = pendingFiles[i];
    const tag = document.createElement('div');
    tag.className = 'file-tag';
    if (f.type.startsWith('image/')) {
      const img = document.createElement('img');
      img.src = URL.createObjectURL(f);
      tag.appendChild(img);
    } else {
      const icon = document.createElement('span');
      icon.textContent = fileIcon(f);
      tag.appendChild(icon);
    }
    tag.innerHTML += `<span>${f.name}</span><span class="remove-file" onclick="removeFile(${i})">✕</span>`;
    preview.appendChild(tag);
  }
}

function removeFile(i) {
  pendingFiles.splice(i, 1);
  renderUploadPreview();
}

function clearUploadPreview() {
  document.getElementById('uploadPreview').innerHTML = '';
}

function fileIcon(f) {
  if (f.type === 'application/pdf') return '📄';
  if (f.type.startsWith('video/')) return '🎥';
  if (f.type.startsWith('text/')) return '📝';
  return '📎';
}

/* ─── SAVE MODAL ────────────────────────────────────────────── */
function openSaveModal(path = '', content = '') {
  document.getElementById('savePath').value = path;
  document.getElementById('saveContent').value = content;
  document.getElementById('saveAction').value = 'create';
  document.getElementById('saveBackdrop').classList.add('open');
  document.getElementById('saveModal').classList.add('open');
}

function closeSaveModal() {
  document.getElementById('saveBackdrop').classList.remove('open');
  document.getElementById('saveModal').classList.remove('open');
}

async function confirmSave() {
  const path = document.getElementById('savePath').value.trim();
  const content = document.getElementById('saveContent').value.trim();
  const action = document.getElementById('saveAction').value;

  if (!path || !content) {
    alert('Inserisci percorso e contenuto');
    return;
  }

  try {
    const form = new FormData();
    form.append('path', path);
    form.append('content', content);
    form.append('action', action);

    const r = await fetch('/api/save', { method: 'POST', body: form });
    const data = await r.json();

    if (data.saved) {
      closeSaveModal();
      loadBrainNav();
      appendMessage('assistant', `✅ Salvato in \`${data.path}\``);
    } else {
      alert('Errore nel salvataggio');
    }
  } catch (e) {
    alert(`Errore: ${e.message}`);
  }
}

/* ─── FILE VIEWER MODAL ─────────────────────────────────────── */
async function viewFile(path) {
  try {
    const r = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    const data = await r.json();
    currentFilePath = data.path;
    currentFileContent = data.content;

    document.getElementById('fileModalTitle').textContent = `📄 ${path.split('/').pop()}`;
    document.getElementById('fileModalContent').innerHTML = marked.parse(data.content);
    document.getElementById('fileBackdrop').classList.add('open');
    document.getElementById('fileModal').classList.add('open');
  } catch (e) {
    alert(`Errore nel caricare il file: ${e.message}`);
  }
}

function closeFileModal() {
  document.getElementById('fileBackdrop').classList.remove('open');
  document.getElementById('fileModal').classList.remove('open');
}

function editFileInModal() {
  closeFileModal();
  openSaveModal(currentFilePath, currentFileContent);
  document.getElementById('saveAction').value = 'create';
}

/* ─── NEW CHAT ──────────────────────────────────────────────── */
async function newChat() {
  if (sessionId) {
    try { await fetch(`/api/session/${sessionId}`, { method: 'DELETE' }); } catch {}
  }
  sessionId = '';
  localStorage.removeItem('sb_session');

  const chat = document.getElementById('chatArea');
  chat.innerHTML = `
    <div class="welcome" id="welcome">
      <div class="welcome-icon">🧠</div>
      <h2>Benvenuto nel tuo Secondo Cervello</h2>
      <p>Scrivimi qualcosa, carica un file, o usa i pulsanti rapidi qui sotto.</p>
      <div class="welcome-chips">
        <button class="chip" onclick="quickAction('Modalità analisi profonda: ')">🔍 Analisi Profonda</button>
        <button class="chip" onclick="quickAction('Aggiorna il mio sistema')">🔄 Aggiorna Sistema</button>
        <button class="chip" onclick="quickAction('Revisione settimanale')">📊 Revisione</button>
      </div>
    </div>
  `;
}

/* ─── TYPING INDICATOR ──────────────────────────────────────── */
function showTyping() {
  const chat = document.getElementById('chatArea');
  const id = `typing-${Date.now()}`;
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.id = id;
  div.innerHTML = `
    <div class="msg-label">🧠 Secondo Cervello</div>
    <div class="typing-indicator"><span></span><span></span><span></span></div>
  `;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return id;
}

function removeTyping(id) {
  document.getElementById(id)?.remove();
}

/* ─── SIDEBAR ───────────────────────────────────────────────── */
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (window.innerWidth <= 700) {
    sidebar.classList.toggle('open');
  } else {
    sidebar.classList.toggle('closed');
  }
}

/* ─── HELPERS ───────────────────────────────────────────────── */
function setSending(loading) {
  const btn = document.getElementById('sendBtn');
  document.getElementById('sendIcon').style.display = loading ? 'none' : 'block';
  document.getElementById('loadingIcon').style.display = loading ? 'block' : 'none';
  btn.disabled = loading;
  document.getElementById('msgInput').disabled = loading;
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/* ─── DRAG & DROP ───────────────────────────────────────────── */
const chatArea = document.getElementById('chatArea');
chatArea.addEventListener('dragover', e => { e.preventDefault(); chatArea.style.outline = '2px dashed var(--accent)'; });
chatArea.addEventListener('dragleave', () => { chatArea.style.outline = ''; });
chatArea.addEventListener('drop', e => {
  e.preventDefault();
  chatArea.style.outline = '';
  if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
});
