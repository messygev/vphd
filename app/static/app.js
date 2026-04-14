const chatForm = document.getElementById('chat-form');
const dumpForm = document.getElementById('dump-form');
const retrieveForm = document.getElementById('retrieve-form');
const chatOutput = document.getElementById('chat-output');
const results = document.getElementById('results');
const toast = document.getElementById('toast');

function tenantHeader() {
  const tenantId = document.getElementById('tenant-id').value || 'default';
  return { 'X-Tenant-Id': tenantId };
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.style.background = isError ? '#d90000' : '#003a40';
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 2200);
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return { detail: 'Ungültige Serverantwort.' };
  }
}

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  chatOutput.textContent = 'Lädt ...';
  const payload = {
    model_profile: document.getElementById('model').value,
    prompt: document.getElementById('prompt').value,
    temperature: 0.2,
  };

  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...tenantHeader() },
    body: JSON.stringify(payload),
  });

  const data = await safeJson(response);
  if (!response.ok) {
    chatOutput.textContent = `Fehler: ${data.detail}`;
    showToast('Chat-Anfrage fehlgeschlagen', true);
    return;
  }

  chatOutput.textContent = `${data.model}\n\n${data.content}`;
  showToast('Antwort erfolgreich geladen');
});

dumpForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = {
    type: document.getElementById('dump-type').value,
    layer: document.getElementById('dump-layer').value,
    content: document.getElementById('dump-content').value,
    trust: 1.0,
    confidence: Number(document.getElementById('dump-confidence').value),
    metadata: { ui: 'vanilla-web' },
  };
  const response = await fetch('/api/dump', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...tenantHeader() },
    body: JSON.stringify(payload),
  });
  const data = await safeJson(response);
  if (!response.ok) {
    showToast(`Dump fehlgeschlagen: ${data.detail}`, true);
    return;
  }
  showToast(`Gespeichert: ${data.id}`);
});

retrieveForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  results.innerHTML = '';
  const payload = { query: document.getElementById('query').value, k: 10 };
  const response = await fetch('/api/retrieve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...tenantHeader() },
    body: JSON.stringify(payload),
  });
  const data = await safeJson(response);
  if (!response.ok) {
    results.innerHTML = `<li>Fehler: ${data.detail}</li>`;
    showToast('Retrieve fehlgeschlagen', true);
    return;
  }
  if (!data.results.length) {
    results.innerHTML = '<li>Keine Treffer gefunden.</li>';
    showToast('Keine Treffer gefunden');
    return;
  }

  data.results.forEach((row) => {
    const item = document.createElement('li');
    item.textContent = `[score=${row.score.toFixed(4)}][${new Date(row.ts * 1000).toISOString()}] ${row.content}`;
    results.appendChild(item);
  });
  showToast(`${data.results.length} Treffer geladen`);
});
