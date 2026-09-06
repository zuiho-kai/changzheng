'use strict';
(() => {
  const avatar = document.querySelector('#avatar');
  const caption = document.querySelector('#caption');
  const label = document.querySelector('.label');
  const replyContext = document.querySelector('#reply-context');
  const audioPlayer = new URLSearchParams(location.search).get('audio') === '1';
  let captionObserver, chatVersion = '', timer, pending, closed = false;
  let playerError = '', playerAudio = 'uninitialized', latestStatus;

  const chatPanel = document.createElement('section');
  chatPanel.className = 'live-chat';
  chatPanel.innerHTML = '<h2>大家在聊</h2><ol id="live-messages"></ol><div class="chat-empty">发条弹幕，和小征打个招呼吧。</div>';
  document.querySelector('.paper').insertBefore(chatPanel, document.querySelector('.note'));
  const messagesList = chatPanel.querySelector('ol');
  const enableAudio = document.createElement('button');
  enableAudio.className = 'enable-audio';
  enableAudio.textContent = '点击启用声音';
  enableAudio.hidden = true;
  document.querySelector('.room').append(enableAudio);
  enableAudio.onclick = () => avatar.contentWindow.postMessage({type:'broadcast-enable-audio'}, location.origin);

  avatar.addEventListener('load', () => {
    captionObserver?.disconnect();
    caption.textContent = '';
    const doc = avatar.contentDocument;
    const style = doc.createElement('style');
    style.textContent = '.speech-bubble{visibility:hidden!important}';
    doc.head.append(style);
    const bubble = doc.querySelector('.speech-bubble');
    if (!bubble) return;
    const sync = () => {
      caption.textContent = bubble.hidden ? '' : bubble.textContent;
      caption.scrollTop = caption.scrollHeight;
    };
    captionObserver = new MutationObserver(sync);
    captionObserver.observe(bubble, {childList:true, subtree:true, characterData:true, attributes:true});
    sync();
  });
  if (audioPlayer) avatar.src = '/?broadcast=1';

  function renderStatus() {
    const data = latestStatus;
    if (!data) {label.textContent = '本地连接已断开';enableAudio.hidden = true;return;}
    let voice = data.audio_state === 'running' ? '声音已就绪' : '播音端已连接';
    if (data.scene !== 'live') voice = '回应已暂停';
    else if (!data.player_connected) voice = '声音未连接';
    else if (data.audio_enabled === false) voice = '语音已关闭';
    else if (playerError) voice = '声音未就绪';
    else if (data.audio_state && data.audio_state !== 'running') voice = '声音等待启用';
    else if (data.status === 'speaking') voice = '小征正在说';
    else if (data.status === 'thinking') voice = '小征在想';
    label.textContent = (data.connected ? '弹幕在线' : '弹幕重连中') + ' · ' + voice;
    label.title = playerError;
    enableAudio.hidden = !audioPlayer || data.scene !== 'live' || data.audio_enabled === false || playerAudio !== 'suspended';
  }
  addEventListener('message', event => {
    if (!audioPlayer || event.origin !== location.origin || event.source !== avatar.contentWindow) return;
    if (event.data?.type === 'broadcast-error') playerError = String(event.data.message || '声音未就绪');
    if (event.data?.type === 'broadcast-state') {
      playerAudio = event.data.audio;
      if (event.data.connected && playerAudio === 'running') playerError = '';
    }
    renderStatus();
  });

  function renderMessages(data) {
    const messages = (data.messages || []).slice(-5);
    const version = JSON.stringify(messages);
    chatPanel.querySelector('h2').textContent = messages.length ? '大家在聊' : '等你开个话题';
    const attention = Array.isArray(data.attention) ? data.attention : [];
    replyContext.hidden = !attention.length || !['thinking', 'speaking'].includes(data.status);
    replyContext.textContent = attention.length ? '这轮在聊 · ' + attention.map(m => String(m.text || '')).join(' / ') : '';
    if (version === chatVersion) return;
    if(chatVersion && messages.length)avatar.contentWindow.postMessage({type:'avatar-attention'},location.origin);
    chatVersion = version;
    // Keep existing DOM rows so one new message does not animate the entire panel.
    const oldRows = [...messagesList.children];
    const available = new Set(oldRows);
    const rows = [];
    for (const message of messages) {
      const key = JSON.stringify(message);
      const existing = oldRows.find(row => available.has(row) && row.dataset.key === key);
      if (existing) {available.delete(existing);rows.push(existing);continue;}
      const row = document.createElement('li');row.className = 'chat-row';row.dataset.key = key;
      const name = document.createElement('span');name.className = 'chat-user';
      name.textContent = String(message.user || '观众');
      const text = document.createElement('span');text.className = 'chat-text';
      text.textContent = String(message.text || '');
      row.append(name, text);rows.push(row);
    }
    for (const row of available) row.remove();
    rows.forEach((row, index) => {if (messagesList.children[index] !== row) messagesList.insertBefore(row, messagesList.children[index] || null);});
    messagesList.scrollTop = messagesList.scrollHeight;
    chatPanel.querySelector('.chat-empty').hidden = messages.length > 0;
  }
  async function refreshChat() {
    pending = new AbortController();
    const timeout = setTimeout(() => pending?.abort(), 3000);
    try {
      const response = await fetch('/api/live/status', {cache:'no-store', signal:pending.signal});
      if (!response.ok) throw Error('offline');
      latestStatus = await response.json();
      if (!closed) {renderMessages(latestStatus);renderStatus();}
    } catch {
      latestStatus = null;
      if (!closed) renderStatus();
    } finally {
      clearTimeout(timeout);pending = null;
      if (!closed) timer = setTimeout(refreshChat, 1000);
    }
  }
  addEventListener('pagehide', () => {closed = true;clearTimeout(timer);pending?.abort();captionObserver?.disconnect();});
  void refreshChat();
})();
