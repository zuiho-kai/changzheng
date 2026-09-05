'use strict';
(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const observer = location.pathname === '/overlay';
  const sceneNames = {all: '所有场景', chat: '日常陪伴', work: '专注工作', live: '公开直播'};
  const statusNames = {idle: '安静陪着你', thinking: '想一想', speaking: '正在说话', listening: '认真听你说'};
  const taskNames = {queued: '等待开始', running: '正在进行', pausing: '正在暂停', completed: '已完成', paused: '已暂停', failed: '需要处理'};
  let state = {history: [], memories: [], tasks: [], settings: {}, scene: 'chat'};
  let ws, reconnect, connected = false, turnId = null, pendingRow = null, filter = 'all', stopPending = false;
  let audioContext, audioEpoch = 0, audioQueue = [], audioPlaying = false, activeSource = null;
  let completedSegments = [], firstPlaybackTurn = null, microphone = null, micSpeaking = false;
  let toastTimer, bubbleTimer, closing = false, currentPage = 'home';
  let inputRevision = 0, transcriptBatch = [], transcriptFlushTimer;
  let micStarting = false, micStartToken = 0;
  if (observer) {document.body.classList.add('overlay'); document.documentElement.classList.add('overlay');}

  const safe = (value) => String(value ?? '');
  function element(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; }
  function toast(message) { if (observer) return; $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 6000); }
  async function api(path, options = {}) {
    const config = {...options};
    if (config.body && !(config.body instanceof Blob) && !(config.body instanceof ArrayBuffer)) {config.headers = {'Content-Type': 'application/json', ...config.headers}; config.body = JSON.stringify(config.body);}
    const response = await fetch(path, config);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(safe(data.detail || `请求失败 (${response.status})`));
    return data;
  }
  function send(data) { if (ws?.readyState === WebSocket.OPEN) {ws.send(JSON.stringify(data)); return true;} toast('连接尚未就绪，请稍后再试。'); return false; }
  async function ensureAudio() { if (!audioContext) audioContext = new AudioContext(); if (audioContext.state !== 'running') await audioContext.resume(); return audioContext; }
  function setStatus(status) {
    const actual = micSpeaking ? 'listening' : status;
    document.body.classList.remove('thinking', 'speaking', 'listening');
    if (actual !== 'idle') document.body.classList.add(actual);
    $('#pet-status').textContent = statusNames[actual] || actual;
  }
  function bubble(text, persistent = false) { clearTimeout(bubbleTimer); $('#speech-bubble').textContent = text; $('#speech-bubble').hidden = !text; if (!persistent) bubbleTimer = setTimeout(() => {$('#speech-bubble').hidden = true;}, 6500); }
  function cancelPlayback() {
    audioEpoch += 1; audioQueue = []; audioPlaying = false;
    if (activeSource) {activeSource.onended = null; try { activeSource.stop(); } catch {} try { activeSource.disconnect(); } catch {} activeSource = null;}
    $('#speech-bubble').hidden = true; document.body.classList.remove('speaking');
  }
  function interrupt(preserveVoice = false) {
    if (preserveVoice !== true) {inputRevision++; transcriptBatch = []; clearTimeout(transcriptFlushTimer);}
    cancelPlayback();
    // A generation that arrives after local Stop must never restart playback.
    turnId = null; stopPending = true;
    if (!observer) send({type: 'interrupt', completed: completedSegments.splice(0)});
    setStatus('idle');
  }
  function ack(segment) {
    if (observer || segment.turn_id !== turnId) return;
    const value = {turn_id: segment.turn_id, id: segment.id};
    completedSegments.push(value); if (completedSegments.length > 20) completedSegments.shift();
    send({type: 'played', ...value});
  }
  async function drainAudio() {
    if (audioPlaying || observer) return;
    audioPlaying = true;
    const epoch = audioEpoch;
    try {
      while (audioQueue.length && epoch === audioEpoch) {
        const segment = audioQueue.shift();
        if (segment.turn_id !== turnId) continue;
        if (!segment.audio) {
          bubble(segment.text);
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          if (epoch === audioEpoch && segment.turn_id === turnId) ack(segment);
          continue;
        }
        const context = await ensureAudio();
        const bytes = Uint8Array.from(atob(segment.audio), c => c.charCodeAt(0));
        const buffer = await context.decodeAudioData(bytes.buffer);
        if (epoch !== audioEpoch || segment.turn_id !== turnId) break;
        await new Promise((resolve, reject) => {
          const source = context.createBufferSource(); source.buffer = buffer; source.connect(context.destination); activeSource = source;
          source.onended = () => {
            source.disconnect();
            if (activeSource === source) activeSource = null;
            if (epoch === audioEpoch && segment.turn_id === turnId) ack(segment);
            resolve();
          };
          // Cancellation stops the source and disconnects onended. Resolve the
          // local await as well; its continuation is guarded by the epoch.
          const poll = setInterval(() => {if (epoch !== audioEpoch) {clearInterval(poll); resolve();}}, 50);
          const ended = source.onended;
          source.onended = () => {clearInterval(poll); ended();};
          try {
            source.start(); bubble(segment.text, true); setStatus('speaking');
            if (firstPlaybackTurn !== turnId) {firstPlaybackTurn = turnId; send({type: 'playback_started', turn_id: turnId});}
          } catch (error) {clearInterval(poll); source.disconnect(); reject(error);}
        });
      }
    } catch (error) {
      if (epoch === audioEpoch) {toast('声音播放失败：' + error.message); interrupt();}
    } finally {if (epoch === audioEpoch) audioPlaying = false;}
  }
  function receiveSegment(segment) {
    if (segment.turn_id !== turnId) return;
    if (observer) return;
    audioQueue.push(segment); void drainAudio();
  }
  function addMessage(message, pending = false) {
    $('.empty-history')?.remove();
    let row = message.id && $('#history').querySelector(`[data-id="${CSS.escape(message.id)}"]`);
    if (!row) {
      row = element('div', 'message-row ' + message.role + (pending ? ' pending' : ''));
      if (message.id) row.dataset.id = message.id;
      const meta = element('div', 'message-meta', message.role === 'user' ? '你' : '小征');
      if (message.role === 'user' && message.id) {const remember = element('button', 'remember-button', '记住'); remember.onclick = () => openMemory({content: message.content, source_id: message.id}); meta.append(remember);}
      row.append(meta, element('div', 'message-text', message.content)); $('#history').append(row);
    } else {row.querySelector('.message-text').textContent = message.content;}
    row.classList.toggle('pending', pending);
    $('#history').scrollTop = $('#history').scrollHeight;
    return row;
  }
  function renderHistory() {
    $('#history').replaceChildren(); pendingRow = null;
    if (!state.history?.length) {
      const empty = element('div', 'empty-history'); empty.append(element('span', '', '✦'), element('p', '', '从一句「你好」开始。'), element('small', '', '听见的回应，才会成为我们的对话。')); $('#history').append(empty);
    } else state.history.forEach(message => addMessage(message));
  }
  function renderState(data) {
    state = {...state, ...data, settings: {...state.settings, ...data.settings}};
    setStatus(data.status || 'idle');
    if (state.settings.avatar) {$('#custom-avatar').src = state.settings.avatar; $('#custom-avatar').hidden = false; $('.cat-svg').setAttribute('hidden','');}
    if (observer) {bubble(''); turnId = null; return;}
    renderHistory(); renderMemories(); renderTasks();
    $$('.scene-tabs button').forEach(button => button.classList.toggle('active', button.dataset.scene === state.scene));
    $('#scene-note').textContent = `${sceneNames[state.scene] || '日常陪伴'} · 简短回应`;
    $('#live-demo').hidden = state.scene !== 'live';
    $('#audio-button').textContent = state.settings.audio_enabled === false ? '语音关' : '语音开';
    $('#audio-button').classList.toggle('off', state.settings.audio_enabled === false);
    $('#setting-audio').checked = state.settings.audio_enabled !== false;
    $('#setting-memory').checked = state.settings.auto_memory !== false;
    if (state.settings.fast_model && ![...$('#setting-model').options].some(x => x.value === state.settings.fast_model)) $('#setting-model').add(new Option(state.settings.fast_model, state.settings.fast_model));
    $('#setting-model').value = state.settings.fast_model || 'Qwen/Qwen3.5-35B-A3B';
    $('#setting-voice').value = state.settings.voice || 'claire';
    $('#setting-cwd').value = state.settings.cwd || '';
    $('#key-state').textContent = state.key_configured ? '密钥已配置。留空即可继续使用。' : '填写 SiliconFlow 密钥后，就可以开始聊天。';
  }
  function onEvent(event) {
    switch (event.type) {
      case 'state': renderState(event); break;
      case 'status': state.status = event.status; if (event.status === 'idle') stopPending = false; setStatus(event.status); break;
      case 'turn_started': if (stopPending) break; cancelPlayback(); turnId = event.turn_id; completedSegments = []; firstPlaybackTurn = null; pendingRow = null; break;
      case 'segment': receiveSegment(event); break;
      case 'segment_committed':
        if (observer) {bubble(event.heard); break;}
        if (!observer && event.turn_id === turnId) pendingRow = addMessage({id: event.turn_id, role: 'assistant', content: event.heard}, true);
        break;
      case 'turn_finished':
        if (event.interrupted) cancelPlayback();
        if (!observer && event.heard) {
          const message = {id: event.turn_id, role: 'assistant', content: event.heard};
          if (!state.history.some(x => x.id === message.id)) state.history.push(message);
          const row = addMessage(message);
          if (event.interrupted && !row.querySelector('.interrupted-label')) row.append(element('span', 'interrupted-label', '已打断 · 未播出的部分已丢弃'));
        }
        if (event.turn_id === turnId) {turnId = null; pendingRow = null;}
        if (!event.interrupted) bubble(event.heard || '');
        if (event.metrics && !observer) {
          const parts = [];
          if (event.metrics.model_ttft_ms != null) parts.push(`首字 ${event.metrics.model_ttft_ms} ms`);
          if (event.metrics.audible_wait_ms != null) parts.push(`开口 ${(event.metrics.audible_wait_ms / 1000).toFixed(1)} s`);
          $('#latency').textContent = parts.join(' · ');
        }
        break;
      case 'user_message': state.history.push(event.message); addMessage(event.message); break;
      case 'recall':
        $('#recall-hint').hidden = !event.memories.length;
        $('#recall-hint').textContent = '✧ 想起了 ' + event.memories.map(x => x.content).join(' · ');
        $('#recall-hint').title = $('#recall-hint').textContent; break;
      case 'memories_updated': state.memories = event.memories; renderMemories(); break;
      case 'task_updated': {const index = state.tasks.findIndex(x => x.id === event.task.id); if (index >= 0) state.tasks[index] = event.task; else state.tasks.unshift(event.task); renderTasks(); break;}
      case 'task_progress': {const task = state.tasks.find(x => x.id === event.task_id); if (task) {task.summary = event.text; renderTasks();} break;}
      case 'approval': showApproval(event); break;
      case 'live_batch': $('#live-batch-state').textContent = `本次合并 ${event.selected} 条 · 跳过 ${event.dropped} 条`; break;
      case 'error': case 'notice': toast(event.message); break;
    }
  }
  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws${observer ? '?role=observer' : ''}`);
    ws.onopen = () => {connected = true; $('.connection-dot').classList.add('online'); $('#connection').textContent = '已连接';};
    ws.onmessage = (message) => {try {onEvent(JSON.parse(message.data));} catch (error) {console.error('Event handling failed', error);}};
    ws.onclose = (event) => {
      connected = false; cancelPlayback(); turnId = null; $('.connection-dot').classList.remove('online'); $('#connection').textContent = '未连接';
      if (!closing && event.code !== 1008) reconnect = setTimeout(connect, 2000);
      if (event.code === 1008) toast('已有对话窗口正在控制小征。请关闭另一个窗口后刷新。');
    };
  }
  async function submitMessage(text, fromMic = false) {
    text = text.trim(); if (!text || !connected) {if (!connected) toast('小征还没连接好，请稍后再试。'); return;}
    await ensureAudio().catch(() => {});
    if (!fromMic) {inputRevision++; transcriptBatch = []; clearTimeout(transcriptFlushTimer);}
    interrupt(true);
    if (send({type: 'message', text, voice: state.settings.audio_enabled !== false})) $('#message').value = '';
  }
  function page(name) {
    currentPage = name;
    $$('.page').forEach(x => x.classList.toggle('active', x.id === 'page-' + name));
    $$('.nav[data-page]').forEach(x => x.classList.toggle('active', x.dataset.page === name));
    $('#page-title').textContent = {home: '今天，也在你身边。', memories: '那些关于你的事。', tasks: '一起，把事情做好。'}[name];
  }
  function renderMemories() {
    const list = $('#memory-list'); list.replaceChildren();
    const items = (state.memories || []).filter(x => filter === 'all' || x.scene === filter || x.scene === 'all');
    if (!items.length) {list.append(element('div', 'empty-card', '还没有记忆。聊聊你的习惯，或者手动记下一件事。')); return;}
    for (const memory of items) {
      const card = element('article', 'memory-card'); card.append(element('p', '', memory.content));
      const bottom = element('div', 'card-bottom'), tags = element('div', 'tags'), actions = element('div', 'card-actions');
      tags.append(element('span', 'tag', sceneNames[memory.scene] || memory.scene), element('span', 'tag ' + memory.visibility, memory.visibility === 'public' ? '可以公开' : '仅私人'));
      const edit = element('button', '', '修改'), remove = element('button', 'danger', '忘记');
      edit.onclick = () => openMemory(memory);
      remove.onclick = async () => {try {await api('/api/memories/' + encodeURIComponent(memory.id), {method: 'DELETE'}); state.memories = state.memories.filter(x => x.id !== memory.id); renderMemories(); toast('已忘记这条记忆，并清理相关旧上下文。');} catch (error) {toast(error.message);}};
      actions.append(edit, remove); bottom.append(tags, actions); card.append(bottom);
      const details = element('details'); details.append(element('summary', '', memory.source_text ? '查看记忆来源' : '手动记录'));
      if (memory.source_text) details.append(element('p', '', memory.source_text));
      details.append(element('small', '', new Date(memory.updated_at).toLocaleString('zh-CN'))); card.append(details); list.append(card);
    }
  }
  let memorySource = null;
  function openMemory(memory = {}) {
    memorySource = memory.id ? null : memory.source_id;
    $('#memory-id').value = memory.id || ''; $('#memory-content').value = memory.content || '';
    $('#memory-scene').value = memory.scene || 'all'; $('#memory-visibility').value = memory.visibility || 'private';
    $('#memory-dialog-title').textContent = memory.id ? '重新记住这件事' : '记住一件事'; $('#memory-dialog').showModal(); $('#memory-content').focus();
  }
  function renderTasks() {
    const list = $('#task-list'); list.replaceChildren();
    const active = (state.tasks || []).filter(x => ['running','queued','pausing'].includes(x.status)).length;
    $('#task-count').textContent = active || '';
    if (!state.tasks?.length) {list.append(element('div', 'empty-card', '暂时没有后台任务。你可以继续陪聊，任务进展会出现在这里。')); return;}
    for (const task of state.tasks) {
      const card = element('article', 'task-card'); card.dataset.taskId = task.id;
      const heading = element('div', 'card-bottom'); heading.append(element('h3', '', task.prompt), element('span', 'tag status-' + task.status, taskNames[task.status] || task.status)); card.append(heading);
      if (task.summary) card.append(element('div', 'task-summary', task.summary));
      const bottom = element('div', 'card-bottom'); bottom.append(element('span', 'task-cwd', task.cwd));
      const action = ['running', 'queued'].includes(task.status) ? 'pause' : ['paused', 'failed'].includes(task.status) ? 'resume' : null;
      if (action) {const button = element('button', 'text-button', action === 'pause' ? '暂停任务' : '继续任务 ↗'); button.onclick = async () => {button.disabled = true; try {const updated = await api(`/api/tasks/${encodeURIComponent(task.id)}/${action}`, {method:'POST'}); Object.assign(task, updated); renderTasks();} catch (error) {toast(error.message); button.disabled = false;}}; bottom.append(button);}
      card.append(bottom); list.append(card);
    }
  }
  function showApproval(event) {
    const card = element('section', 'approval-card'); card.append(element('h3', '', 'Codex 需要你的确认'), element('p', '', event.reason || '接下来的操作需要许可。'));
    if (event.command) card.append(element('pre', '', Array.isArray(event.command) ? event.command.join(' ') : event.command));
    const actions = element('div'), no = element('button', 'text-button', '不允许'), yes = element('button', 'primary-button', '允许本次');
    const decide = async (accepted) => {no.disabled = yes.disabled = true; try {await api('/api/approval', {method:'POST', body:{request_id:event.request_id,accepted}}); card.remove();} catch (error) {toast(error.message); no.disabled = yes.disabled = false;}};
    no.onclick = () => decide(false); yes.onclick = () => decide(true); actions.append(no, yes); card.append(actions); $('#approvals').append(card);
  }

  // Mono PCM capture stays on this machine until a completed utterance is sent
  // to the configured transcription provider. Echo cancellation is requested.
  function wav(chunks, sampleRate) {
    const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0), buffer = new ArrayBuffer(44 + length * 2), view = new DataView(buffer);
    const string = (offset, value) => [...value].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
    string(0,'RIFF'); view.setUint32(4,36 + length*2,true); string(8,'WAVE'); string(12,'fmt '); view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true); view.setUint32(24,sampleRate,true); view.setUint32(28,sampleRate*2,true); view.setUint16(32,2,true); view.setUint16(34,16,true); string(36,'data'); view.setUint32(40,length*2,true);
    let offset = 44; for (const chunk of chunks) for (const sample of chunk) {const s = Math.max(-1, Math.min(1, sample)); view.setInt16(offset, s < 0 ? s * 32768 : s * 32767, true); offset += 2;}
    return new Blob([buffer], {type:'audio/wav'});
  }
  async function toggleMic() {
    if (microphone) {stopMic(); return;}
    if (micStarting || closing) return;
    micStarting = true;
    const startToken = ++micStartToken;
    let acquiredStream;
    $('#mic-button').disabled = true;
    try {
      const context = await ensureAudio();
      if (startToken !== micStartToken || closing) return;
      const stream = acquiredStream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1},video:false});
      if (startToken !== micStartToken || closing) return;
      const input = context.createMediaStreamSource(stream), processor = context.createScriptProcessor(2048,1,1), mute = context.createGain(); mute.gain.value = 0;
      input.connect(processor); processor.connect(mute); mute.connect(context.destination);
      microphone = {stream,input,processor,mute};
      let preroll = [], frames = [], speechMs = 0, silenceMs = 0, totalMs = 0, noise = .003, captureRevision = inputRevision;
      const micSession = microphone;
      let pendingRecordings = [], transcribing = false;
      const flushTranscripts = () => {
        clearTimeout(transcriptFlushTimer);
        transcriptFlushTimer = setTimeout(() => {
          if (microphone !== micSession) return;
          if (transcribing || pendingRecordings.length) return;
          if (micSpeaking || speechMs > 0) {flushTranscripts(); return;}
          const ready = transcriptBatch.filter(x => x.revision === inputRevision);
          transcriptBatch = [];
          if (ready.length) void submitMessage(ready.map(x => x.text).join('。'), true);
        }, 220);
      };
      const processRecordings = async () => {
        if (transcribing) return;
        transcribing = true;
        try {
          while (microphone === micSession && pendingRecordings.length) {
            pendingRecordings = pendingRecordings.filter(x => x.revision === inputRevision);
            if (!pendingRecordings.length) break;
            const first = pendingRecordings.shift(), batch = [first];
            let samples = first.samples;
            // One request in flight. Merge every waiting utterance that fits
            // below the upload limit; retain the remainder for the next batch.
            const maxSamples = Math.min(context.sampleRate * 55, 3_800_000);
            while (pendingRecordings.length && samples + pendingRecordings[0].samples <= maxSamples) {
              const next = pendingRecordings.shift(); batch.push(next); samples += next.samples;
            }
            const revision = first.revision, recording = wav(batch.flatMap(x => x.chunks), context.sampleRate);
            try {
              const result = await api('/api/transcribe', {method:'POST',body:recording});
              if (revision !== inputRevision || microphone !== micSession) continue;
              if (result.text?.trim()) transcriptBatch.push({revision,text:result.text.trim()}); else toast('这次没有听清，请再说一次。');
            } catch (error) {
              if (revision === inputRevision && microphone === micSession) {
                pendingRecordings.unshift(...batch);
                toast('语音识别暂时失败，录音已保留；继续说话会重试，关闭麦克风会清理。');
              }
              break;
            }
          }
        } finally {
          transcribing = false;
          if (microphone === micSession && !micSpeaking) $('#mic-state').textContent = pendingRecordings.length ? '语音等待重新识别' : '麦克风已开启 · 随时可打断';
          if (transcriptBatch.length) flushTranscripts();
        }
      };
      processor.onaudioprocess = (event) => {
        if (!microphone) return;
        const samples = new Float32Array(event.inputBuffer.getChannelData(0)), ms = samples.length/context.sampleRate*1000;
        let power = 0; for (const sample of samples) power += sample*sample; const rms = Math.sqrt(power/samples.length);
        const threshold = Math.max(.012, noise*3);
        if (!micSpeaking && rms < threshold) noise = noise*.97 + rms*.03;
        const voiced = rms > threshold;
        if (!micSpeaking) {
          preroll.push(samples); while (preroll.length > Math.ceil(.25*context.sampleRate/2048)) preroll.shift();
          speechMs = voiced ? speechMs+ms : Math.max(0,speechMs-ms*2);
          if (speechMs >= 140) {
            micSpeaking = true; frames = preroll; preroll = []; totalMs = speechMs; silenceMs = 0; captureRevision = inputRevision;
            interrupt(true); setStatus('listening'); $('#listening-indicator').hidden = false; $('#mic-state').textContent = '正在听你说';
          }
        } else {
          frames.push(samples); totalMs += ms; silenceMs = voiced ? 0 : silenceMs+ms;
          if (silenceMs > 650 || totalMs > 25000) {
            const recording = {chunks:frames, samples:frames.reduce((sum,chunk)=>sum+chunk.length,0), revision:captureRevision}; micSpeaking = false; frames = []; speechMs = 0; silenceMs = 0;
            $('#listening-indicator').hidden = true; $('#mic-state').textContent = '正在识别…'; setStatus('thinking');
            pendingRecordings.push(recording);
            void processRecordings();
          }
        }
      };
      $('#mic-button').classList.add('active'); $('#mic-button').title = '关闭麦克风'; $('#mic-state').textContent = '麦克风已开启 · 随时可打断';
    } catch (error) {
      if (startToken === micStartToken && !closing) {toast(error.name === 'NotAllowedError' ? '麦克风未获许可，请允许本机页面使用麦克风。' : '麦克风启动失败：'+error.message); stopMic();}
    } finally {
      if (acquiredStream && microphone?.stream !== acquiredStream) acquiredStream.getTracks().forEach(track => track.stop());
      micStarting = false;
      $('#mic-button').disabled = false;
    }
  }
  function stopMic() {
    micStartToken++;
    inputRevision++; transcriptBatch = []; clearTimeout(transcriptFlushTimer);
    if (microphone) {microphone.processor.onaudioprocess = null; microphone.stream.getTracks().forEach(x => x.stop()); microphone.input.disconnect(); microphone.processor.disconnect(); microphone.mute.disconnect(); microphone = null;}
    micSpeaking = false; $('#mic-button').classList.remove('active'); $('#mic-button').title = '开启麦克风'; $('#mic-state').textContent = '麦克风未开启'; $('#listening-indicator').hidden = true; setStatus(state.status || 'idle');
  }

  if (!observer) {
    document.addEventListener('pointerdown', () => {void ensureAudio().catch(() => {});}, {once:true});
    $$('.nav[data-page]').forEach(button => button.onclick = () => page(button.dataset.page));
    $('#chat-form').onsubmit = (event) => {event.preventDefault(); void submitMessage($('#message').value);};
    $('#message').onkeydown = (event) => {if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); void submitMessage($('#message').value);}};
    $('#stop-button').onclick = interrupt; $('#compact-stop').onclick = interrupt;
    document.addEventListener('keydown', (event) => {if (event.key === 'Escape') {interrupt(); $('#settings-scrim').hidden = true;}});
    $('#mic-button').onclick = toggleMic;
    $('#audio-button').onclick = async () => {try {const enabled = state.settings.audio_enabled === false; if (!enabled) interrupt(); const result = await api('/api/settings',{method:'POST',body:{audio_enabled:enabled}}); renderState(result);} catch(error) {toast(error.message);}};
    $('#new-session').onclick = async () => {interrupt(); try {renderState(await api('/api/session',{method:'POST',body:{scene:state.scene}}));} catch(error) {toast(error.message);}};
    $$('.scene-tabs button').forEach(button => button.onclick = async () => {if (button.dataset.scene === state.scene) return; interrupt(); try {renderState(await api('/api/session',{method:'POST',body:{scene:button.dataset.scene}}));} catch(error) {toast(error.message);}});
    $$('.settings-open').forEach(button => button.onclick = () => {$('#settings-scrim').hidden = false;});
    $('[data-close="settings-scrim"]').onclick = () => {$('#settings-scrim').hidden = true; $('#setting-key').value = '';};
    $('#settings-scrim').onclick = (event) => {if (event.target === $('#settings-scrim')) {$('#settings-scrim').hidden = true; $('#setting-key').value = '';}};
    $('#settings-form').onsubmit = async (event) => {
      event.preventDefault(); const button = $('#settings-form button[type="submit"]') || $('#settings-form .primary-button'); button.disabled = true;
      const body = {fast_model:$('#setting-model').value,voice:$('#setting-voice').value,cwd:$('#setting-cwd').value,audio_enabled:$('#setting-audio').checked,auto_memory:$('#setting-memory').checked};
      if ($('#setting-key').value.trim()) body.api_key = $('#setting-key').value.trim();
      try {renderState(await api('/api/settings',{method:'POST',body})); $('#setting-key').value = ''; $('#settings-scrim').hidden = true; toast('已保存，按你的习惯来。');} catch(error) {toast(error.message);} finally {button.disabled = false;}
    };
    $('#avatar-button').onclick = () => $('#avatar-file').click();
    $('#avatar-file').onchange = async () => {const file = $('#avatar-file').files[0]; if (!file) return; try {const result = await api('/api/avatar?ext='+encodeURIComponent(file.name.split('.').pop().toLowerCase()),{method:'POST',body:file}); renderState({settings:{avatar:result.avatar}}); toast('换好啦。');} catch(error) {toast(error.message);} $('#avatar-file').value = '';};
    $('#add-memory').onclick = () => openMemory(); $('#close-memory').onclick = () => $('#memory-dialog').close();
    $$('#memory-filters button').forEach(button => button.onclick = () => {filter = button.dataset.filter; $$('#memory-filters button').forEach(x => x.classList.toggle('active', x === button)); renderMemories();});
    $('#memory-form').onsubmit = async (event) => {event.preventDefault(); const id = $('#memory-id').value, body = {content:$('#memory-content').value,scene:$('#memory-scene').value,visibility:$('#memory-visibility').value}; if (memorySource) body.source_id = memorySource; try {await api('/api/memories'+(id ? '/'+encodeURIComponent(id) : ''),{method:id ? 'PUT':'POST',body}); state.memories = await api('/api/memories'); renderMemories(); $('#memory-dialog').close(); toast('记住了。');} catch(error) {toast(error.message);}};
    $('#task-form').onsubmit = async (event) => {event.preventDefault(); const button = $('#task-form button'); button.disabled = true; try {const task = await api('/api/tasks',{method:'POST',body:{prompt:$('#task-prompt').value,read_only:$('#task-readonly').checked}}); if (!state.tasks.some(x=>x.id === task.id)) state.tasks.unshift(task); renderTasks(); $('#task-prompt').value = ''; toast('Codex 已接到任务，你可以继续聊天。');} catch(error) {toast(error.message);} finally {button.disabled = false;}};
    $('#live-form').onsubmit = async (event) => {event.preventDefault(); const text = $('#live-text').value.trim(); if (!text) return; try {await api('/api/live/messages',{method:'POST',body:{user:$('#live-user').value.trim() || '路过的观众',text}}); $('#live-text').value = ''; $('#live-batch-state').textContent = '已进入候选弹幕，空闲时选择回应';} catch(error) {toast(error.message);}};
    async function compact() {if (window.companionDesktop) {page('home'); const result = await window.companionDesktop.toggleCompact(); document.body.classList.toggle('compact', result);} else toast('桌宠小窗需要使用「启动小征.cmd」打开桌面版。');}
    $('#compact-button').onclick = compact; $('#compact-expand').onclick = compact;
    window.companionDesktop?.onCompact((enabled) => {page('home'); document.body.classList.toggle('compact',enabled);});
    void api('/api/state').then(renderState).catch(error => toast(error.message));
  }
  window.addEventListener('beforeunload', () => {closing = true; clearTimeout(reconnect); cancelPlayback(); stopMic(); ws?.close();});
  connect();
})();
