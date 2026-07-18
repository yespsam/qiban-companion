/* 栖伴控制台前端（原生 JS，无构建步骤、无外部依赖） */
(function () {
  'use strict';

  // ------------------------------------------------------------------ 小工具
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function toast(msg, isErr) {
    var t = $('toast');
    t.textContent = msg;
    t.className = 'toast' + (isErr ? ' error' : '');
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.classList.add('hidden'); }, 3200);
  }
  function apiGet(path) {
    return fetch(path).then(function (r) { return r.json(); });
  }
  function apiPost(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) {
          var err = new Error(data.error || ('请求失败 ' + r.status));
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  var MOOD_LABELS = {
    happy: '😊 开心', calm: '😌 平静', worried: '🥺 担心',
    jealous: '😤 吃醋', sleepy: '😴 困倦', excited: '🤩 兴奋'
  };
  var PERSONA_VISUALS = {
    female_companion: {
      image: '/static/assets/xiao-qi-avatar.png',
      line: '温柔、亲近、会记住你的心事。声音和语言模型会随关系身份一起调整。'
    },
    male_companion: {
      image: '/static/assets/qi-an-avatar.png',
      line: '沉稳、可靠、低声陪伴。先稳住情绪，再给你最实在的行动建议。'
    }
  };
  var ARCHETYPES = {
    female: [
      ['', '自动'],
      ['loli', '轻亮'],
      ['yujie', '御姐'],
      ['funny', '跳脱']
    ],
    male: [
      ['', '自动'],
      ['shonen', '少年'],
      ['uncle', '大叔'],
      ['funny', '跳脱']
    ]
  };

  // ------------------------------------------------------------------ 全局态
  var state = {
    persona: null,
    personas: [],
    relationships: [],
    emotion: null,
    showThinking: true,
    voice: { enabled: false },
    settings: {},
    engineAvailable: true,
    masterName: '主人'
  };
  var ws = null;
  var wsAlive = false;
  var sending = false;
  var pending = null; // 进行中的回复 {thinkEl, thinkBody, textEl, thinkText, text}

  // ------------------------------------------------------------------ 渲染
  function renderPersona() {
    var p = state.persona;
    var appName = state.settings.app_name || '栖伴';
    document.title = appName + ' · 本地 AI 情感伴侣控制台';
    if ($('brand-name')) $('brand-name').textContent = appName;
    $('persona-name').textContent = p ? p.display_name : '伴侣';
    $('persona-avatar').textContent = p && p.gender === 'male' ? '🛡️' : '🌸';
    $('persona-traits').textContent = p && p.traits && p.traits.length ? p.traits.join(' · ') : '';
    $('thinking-owner').textContent = (p ? p.display_name : 'TA') + ' 的内心';
    renderAvatarStage();

    var box = $('persona-switch');
    box.innerHTML = '';
    state.personas.forEach(function (item) {
      var btn = el('button', 'persona-btn' + (p && item.id === p.id ? ' active' : ''),
        (item.gender === 'male' ? '♂ ' : '♀ ') + item.display_name);
      btn.type = 'button';
      btn.onclick = function () { selectPersona(item.id); };
      box.appendChild(btn);
    });

    var banner = $('engine-banner');
    if (!state.engineAvailable) {
      banner.textContent = '⚠️ 对话引擎暂不可用，聊天会失败。请检查模型后端（可在 config/settings.yaml 改用 mock 演示）。';
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
    }
  }

  function renderAvatarStage() {
    var p = state.persona || {};
    var gender = p.gender === 'male' ? 'male' : 'female';
    var visual = PERSONA_VISUALS[p.id] || PERSONA_VISUALS.female_companion;
    var portrait = $('stage-portrait');
    if (portrait) {
      portrait.src = visual.image;
      portrait.alt = (p.display_name || '伴侣') + ' 虚拟人物形象';
    }
    document.body.dataset.persona = gender;
    $('stage-name').textContent = p.display_name || (state.settings.app_name || '栖伴');
    $('stage-line').textContent = visual.line;
    var cast = (state.voice && state.voice.cast) || {};
    var arch = state.settings.active_archetype || '';
    $('stage-voice').textContent = (cast.archetype || arch || (gender === 'male' ? '温暖男声' : '温柔女声')) +
      (cast.voice ? ' · ' + cast.voice.replace(/^zh-CN-/, '').replace(/Neural$/, '') : '');
    $('stage-model').textContent = (state.settings.llm_backend || 'local') +
      ' model · T=' + (state.settings.llm_temperature || 0.72);
    renderArchetypes(gender, arch);
  }

  function renderArchetypes(gender, active) {
    var box = $('archetype-switch');
    if (!box) return;
    box.innerHTML = '';
    (ARCHETYPES[gender] || ARCHETYPES.female).forEach(function (pair) {
      var btn = el('button', 'arch-chip' + (pair[0] === active ? ' active' : ''), pair[1]);
      btn.type = 'button';
      btn.onclick = function () { selectArchetype(pair[0]); };
      box.appendChild(btn);
    });
  }

  function renderRelationships() {
    var box = $('relationship-switch');
    if (!box) return;
    box.innerHTML = '';
    state.relationships.forEach(function (item) {
      var chip = el('button', 'rel-chip' + (item.active ? ' active' : ''), item.display_name);
      chip.type = 'button';
      chip.onclick = function () { selectRelationship(item.id); };
      box.appendChild(chip);
    });
  }

  function renderEmotion() {
    var emo = state.emotion || { mood: 'calm', affection: 50 };
    var aff = Math.max(0, Math.min(100, parseInt(emo.affection, 10) || 0));
    $('affection-fill').style.width = aff + '%';
    $('affection-num').textContent = aff;
    $('mood').textContent = MOOD_LABELS[emo.mood] || ('😐 ' + (emo.mood || '未知'));
  }

  function renderThinkingToggle() {
    $('thinking-toggle').checked = !!state.showThinking;
    document.body.classList.toggle('hide-thinking', !state.showThinking);
  }

  function renderVoice() {
    var mic = $('mic-btn');
    mic.disabled = !state.voice.enabled;
    mic.title = state.voice.enabled
      ? '点击开始 / 停止录音（语音转文字）'
      : '语音未启用：请在 config/settings.yaml 设置 voice_enabled=true 并安装语音依赖';
  }

  function scrollChat() {
    var stream = $('chat-stream');
    stream.scrollTop = stream.scrollHeight;
  }

  function personaName() { return state.persona ? state.persona.display_name : '伴侣'; }

  // ------------------------------------------------------------------ 首屏
  function loadState() {
    return apiGet('/api/state').then(function (s) {
      state.persona = s.persona;
      state.emotion = s.emotion;
      state.showThinking = !!s.show_thinking;
      state.masterName = s.master_name || '主人';
      state.voice = s.voice || { enabled: false };
      state.settings = s.settings || {};
      state.engineAvailable = !!(s.engine && s.engine.available);
      renderPersona(); renderEmotion(); renderThinkingToggle(); renderVoice();
    }).catch(function () { toast('状态加载失败', true); });
  }

  function loadPersonas() {
    return apiGet('/api/personas').then(function (list) {
      if (Array.isArray(list)) { state.personas = list; renderPersona(); }
    }).catch(function () { /* 人格系统不可用时保持现状 */ });
  }

  function selectPersona(id) {
    apiPost('/api/persona/select', { persona_id: id }).then(function (r) {
      toast('已切换到 ' + r.display_name);
      return loadState();
    }).catch(function (e) { toast(e.message || '切换失败', true); });
  }

  function loadRelationships() {
    return apiGet('/api/relationships').then(function (list) {
      if (Array.isArray(list)) { state.relationships = list; renderRelationships(); }
    }).catch(function () { /* 人格系统不可用时保持现状 */ });
  }

  function selectRelationship(id) {
    apiPost('/api/relationship/select', { relationship_id: id }).then(function (r) {
      state.relationships.forEach(function (item) { item.active = (item.id === r.active_relationship); });
      renderRelationships();
      toast('关系身份已切换为「' + r.display_name + '」');
    }).catch(function (e) { toast(e.message || '切换失败', true); });
  }

  function selectArchetype(id) {
    apiPost('/api/settings', { active_archetype: id }).then(function (r) {
      state.settings = r.settings || state.settings;
      toast(id ? '声线已切换' : '声线已恢复自动');
      return loadState();
    }).catch(function (e) { toast(e.message || '声线切换失败', true); });
  }

  // ------------------------------------------------------------------ 聊天
  function addBubble(role, text) {
    var row = el('div', 'msg-row ' + role);
    row.appendChild(el('div', 'bubble', text));
    $('chat-stream').appendChild(row);
    scrollChat();
    return row;
  }

  function newPending() {
    var row = el('div', 'msg-row ai');
    var wrap = el('div', null);
    wrap.style.maxWidth = '100%';
    var typing = el('div', 'typing', personaName() + ' 正在输入…');
    wrap.appendChild(typing);
    row.appendChild(wrap);
    $('chat-stream').appendChild(row);
    scrollChat();
    return { wrap: wrap, typing: typing, thinkEl: null, thinkBody: null, textEl: null, thinkText: '', text: '' };
  }

  function pendThink(p, delta) {
    p.thinkText += delta;
    if (!p.thinkEl) {
      p.typing.remove();
      p.thinkEl = el('details', 'thinking-bubble');
      p.thinkEl.open = true;
      p.thinkEl.appendChild(el('summary', null, '💭 ' + personaName() + ' 的内心'));
      p.thinkBody = el('div', 'thinking-body');
      p.thinkEl.appendChild(p.thinkBody);
      p.wrap.appendChild(p.thinkEl);
    }
    p.thinkBody.textContent = p.thinkText;
    scrollChat();
  }

  function pendText(p, delta) {
    p.text += delta;
    if (!p.textEl) {
      p.typing.remove();
      p.textEl = el('div', 'bubble');
      p.wrap.appendChild(p.textEl);
    }
    p.textEl.textContent = p.text;
    scrollChat();
  }

  function pendFail(p, msg) {
    p.typing.remove();
    var row = addBubble('error', '⚠️ ' + msg);
    p.wrap.remove();
    return row;
  }

  function pendDone(p, result) {
    p.typing.remove();
    if (!result) { p.wrap.remove(); return; }
    if (!p.thinkEl && result.thinking) { pendThink(p, result.thinking); }
    if (!p.textEl && result.text) { pendText(p, result.text); }
    // 朗读按钮（语音启用时）
    if (state.voice.enabled && result.text) {
      var bar = el('div', 'bubble-actions');
      var btn = el('button', 'speak-btn', '🔊 朗读');
      btn.type = 'button';
      btn.onclick = function () { speakText(result.text); };
      bar.appendChild(btn);
      p.textEl.appendChild(bar);
    }
    // 设备动作提示
    if (result.actions && result.actions.length) {
      var chips = el('div', null);
      result.actions.forEach(function (a) {
        chips.appendChild(el('span', 'action-chip', '已执行：' + (a.target || a.did || '设备') + ' → ' + (a.action || '')));
      });
      p.wrap.appendChild(chips);
    }
    if (result.emotion) { state.emotion = result.emotion; renderEmotion(); }
    // 同步左栏「最新内心」
    var latest = result.thinking || p.thinkText;
    if (latest) {
      var box = $('latest-thinking-content');
      box.textContent = latest;
      box.classList.remove('empty');
    }
    scrollChat();
  }

  function sendChat(text) {
    if (sending) { toast('上一条还在回复中…'); return; }
    sending = true;
    $('send-btn').disabled = true;
    addBubble('user', text);
    pending = newPending();

    if (wsAlive && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ text: text }));
    } else {
      // WS 不可用时 REST 兜底（无流式，一次性返回）
      apiPost('/api/chat', { text: text }).then(function (result) {
        pendDone(pending, result);
        finishSend();
      }).catch(function (e) {
        pendFail(pending, e.message || '对话失败');
        finishSend();
      });
    }
  }

  function finishSend() {
    sending = false;
    pending = null;
    $('send-btn').disabled = false;
    $('chat-input').focus();
  }

  // ------------------------------------------------------------------ WebSocket
  function setConn(cls, text) {
    var c = $('conn');
    c.className = 'conn ' + cls;
    c.textContent = text;
  }

  function connectWS() {
    var proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
    try { ws = new WebSocket(proto + location.host + '/ws/chat'); }
    catch (e) { setConn('conn-bad', '流式不可用（REST 兜底）'); return; }

    setConn('conn-connecting', '连接中…');
    ws.onopen = function () { wsAlive = true; setConn('conn-ok', '已连接 · 流式'); };
    ws.onclose = function () {
      wsAlive = false;
      setConn('conn-bad', '已断开（REST 兜底，5s 后重连）');
      if (pending) { pendFail(pending, '连接中断'); finishSend(); }
      setTimeout(connectWS, 5000);
    };
    ws.onerror = function () { wsAlive = false; };
    ws.onmessage = function (ev) {
      var frame;
      try { frame = JSON.parse(ev.data); } catch (e) { return; }
      if (!pending) pending = newPending();
      if (frame.type === 'thinking') {
        pendThink(pending, frame.delta || '');
      } else if (frame.type === 'text') {
        pendText(pending, frame.delta || '');
      } else if (frame.type === 'done') {
        pendDone(pending, frame.result);
        finishSend();
      } else if (frame.type === 'error') {
        pendFail(pending, frame.message || '对话失败');
        finishSend();
      }
    };
  }

  // ------------------------------------------------------------------ 语音
  var recorder = null;
  var recChunks = [];

  function toggleRecord() {
    if (recorder && recorder.state === 'recording') { recorder.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      toast('当前浏览器不支持录音（MediaRecorder）', true); return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      recChunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = function (e) { if (e.data.size) recChunks.push(e.data); };
      recorder.onstart = function () { $('mic-btn').classList.add('recording'); };
      recorder.onstop = function () {
        $('mic-btn').classList.remove('recording');
        stream.getTracks().forEach(function (t) { t.stop(); });
        uploadRecording(new Blob(recChunks, { type: recorder.mimeType || 'audio/webm' }));
      };
      recorder.start();
      toast('录音中…再点一次停止');
    }).catch(function () { toast('无法访问麦克风', true); });
  }

  function uploadRecording(blob) {
    var fdHeaders = { 'Content-Type': blob.type || 'audio/webm' };
    fetch('/api/voice/speak', { method: 'POST', headers: fdHeaders, body: blob })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.enabled === false) { toast(data.error || '语音未启用', true); return; }
        if (!data.ok) { toast(data.error || '识别失败', true); return; }
        var text = (data.text || '').trim();
        if (!text) { toast('没有听清，请再说一次'); return; }
        $('chat-input').value = text;
        $('chat-input').focus();
        toast('已识别：' + (text.length > 20 ? text.slice(0, 20) + '…' : text));
      })
      .catch(function () { toast('语音上传失败', true); });
  }

  function speakText(text) {
    fetch('/api/voice/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text,
        mood: state.emotion && state.emotion.mood,
        archetype: state.settings.active_archetype || ''
      })
    }).then(function (r) {
      var ctype = r.headers.get('Content-Type') || '';
      if (ctype.indexOf('audio/') === 0) {
        return r.blob().then(function (b) {
          new Audio(URL.createObjectURL(b)).play();
        });
      }
      return r.json().then(function (data) {
        if (data.ok) toast('已在服务端播放语音');
        else toast(data.error || 'TTS 不可用', true);
      });
    }).catch(function () { toast('语音请求失败', true); });
  }

  // ------------------------------------------------------------------ 设备
  function devNote(container, text) {
    container.innerHTML = '';
    container.appendChild(el('p', 'muted', text));
  }

  function loadDevices() {
    apiGet('/api/devices').then(function (d) {
      renderMihome(d.mihome || { enabled: false });
      renderBluetooth(d.bluetooth || { enabled: false });
    }).catch(function () {
      devNote($('mihome-list'), '设备信息加载失败');
      devNote($('bt-list'), '设备信息加载失败');
    });
  }

  function renderMihome(mi) {
    var box = $('mihome-list');
    box.innerHTML = '';
    if (!mi.enabled) { box.appendChild(el('p', 'muted', mi.error || '米家未启用（settings.mihome_enabled）')); return; }
    if (mi.error) box.appendChild(el('p', 'muted', '发现设备时出错：' + mi.error));
    if (!mi.devices || !mi.devices.length) { box.appendChild(el('p', 'muted', '未发现设备')); return; }
    mi.devices.forEach(function (dev) {
      var item = el('div', 'dev-item');
      var left = el('div', null);
        left.appendChild(el('div', 'dev-name', dev.name || dev.did));
      left.appendChild(el('div', 'dev-meta', (dev.model || '') + (dev.online === false ? ' · 离线' : '')));
      var actions = el('div', 'dev-actions');
      [['开', 'on'], ['关', 'off']].forEach(function (pair) {
        var btn = el('button', 'mini-btn' + (pair[1] === 'on' ? ' primary' : ''), pair[0]);
        btn.type = 'button';
        btn.onclick = function () {
          btn.disabled = true;
          apiPost('/api/devices/control', { did: dev.did, action: pair[1] })
            .then(function (r) { toast(r.ok === false ? ('控制失败：' + (r.error || '')) : (dev.name + ' 已' + pair[0]), r.ok === false); })
            .catch(function (e) { toast(e.message, true); })
            .finally(function () { btn.disabled = false; });
        };
        actions.appendChild(btn);
      });
      item.appendChild(left); item.appendChild(actions);
      box.appendChild(item);
    });
  }

  function renderBluetooth(bt, scanned) {
    var box = $('bt-list');
    box.innerHTML = '';
    if (!bt.enabled) { box.appendChild(el('p', 'muted', bt.error || '蓝牙未启用（settings.bluetooth_enabled）')); return; }
    var devices = scanned || bt.devices || [];
    if (!devices.length) { box.appendChild(el('p', 'muted', '暂无设备，点「扫描」搜索')); return; }
    devices.forEach(function (dev) {
      var item = el('div', 'dev-item');
      var left = el('div', null);
      left.appendChild(el('div', 'dev-name', dev.name || '(未命名)'));
      left.appendChild(el('div', 'dev-meta', dev.address + (dev.rssi ? ' · ' + dev.rssi + 'dBm' : '')));
      if (dev.paired) left.querySelector('.dev-name').appendChild(el('span', 'tag ok', '已配对'));
      var actions = el('div', 'dev-actions');
      var pairBtn = el('button', 'mini-btn', '配对');
      pairBtn.type = 'button';
      pairBtn.onclick = function () {
        pairBtn.disabled = true;
        apiPost('/api/devices/control', { did: dev.address, action: 'pair', target: 'bluetooth' })
          .then(function (r) { toast(r.ok ? '配对成功' : ('配对失败：' + (r.error || '')), !r.ok); loadDevices(); })
          .catch(function (e) { toast(e.message, true); })
          .finally(function () { pairBtn.disabled = false; });
      };
      actions.appendChild(pairBtn);
      item.appendChild(left); item.appendChild(actions);
      box.appendChild(item);
    });
  }

  function scanBluetooth() {
    var btn = $('bt-scan');
    btn.disabled = true; btn.textContent = '扫描中…';
    apiPost('/api/devices/control', { action: 'scan', target: 'bluetooth' })
      .then(function (r) {
        if (r.enabled === false) { renderBluetooth({ enabled: false, error: r.error }); return; }
        if (!r.ok) { toast(r.error || '扫描失败', true); loadDevices(); return; }
        renderBluetooth({ enabled: true }, r.devices || []);
        toast('扫描完成：发现 ' + (r.devices || []).length + ' 台设备');
      })
      .catch(function (e) { toast(e.message, true); })
      .finally(function () { btn.disabled = false; btn.textContent = '扫描'; });
  }

  // ------------------------------------------------------------------ 集群
  function loadCluster() {
    apiGet('/api/cluster/nodes').then(function (d) {
      var box = $('cluster-list');
      box.innerHTML = '';
      if (!d.enabled) { box.appendChild(el('p', 'muted', d.error || '集群未启用（settings.cluster_enabled）')); return; }
      if (!d.nodes || !d.nodes.length) { box.appendChild(el('p', 'muted', '暂无在线节点')); return; }
      d.nodes.forEach(function (n) {
        var item = el('div', 'node-item');
        var head = el('div', 'node-head');
        head.appendChild(el('span', null, n.node_id || '?'));
        head.appendChild(el('span', 'tag' + (n.role === 'master' ? ' ok' : ''), n.role || ''));
        item.appendChild(head);
        item.appendChild(el('div', 'node-meta',
          (n.host || '') + ':' + (n.port || '') +
          ' · 负载 ' + (typeof n.load === 'number' ? Math.round(n.load * 100) + '%' : '-') +
          ' · 显存 ' + (n.gpu_vram_mb || 0) + 'MB'));
        if (n.models && n.models.length) item.appendChild(el('div', 'node-meta', '模型：' + n.models.join('、')));
        box.appendChild(item);
      });
    }).catch(function () { devNote($('cluster-list'), '集群信息加载失败'); });
  }

  // ------------------------------------------------------------------ 事件绑定
  function bind() {
    $('chat-form').addEventListener('submit', function (e) {
      e.preventDefault();
      var input = $('chat-input');
      var text = input.value.trim();
      if (!text) return;
      input.value = '';
      sendChat(text);
    });
    $('mic-btn').addEventListener('click', toggleRecord);
    $('thinking-toggle').addEventListener('change', function (e) {
      var show = e.target.checked;
      apiPost('/api/thinking/toggle', { show: show }).then(function (r) {
        state.showThinking = !!r.show_thinking;
        renderThinkingToggle();
        toast(state.showThinking ? '思考链已显示' : '思考链已隐藏');
      }).catch(function () { toast('设置失败', true); e.target.checked = state.showThinking; });
    });
    $('mihome-refresh').addEventListener('click', loadDevices);
    $('cluster-refresh').addEventListener('click', loadCluster);
    $('bt-scan').addEventListener('click', scanBluetooth);
  }

  // ------------------------------------------------------------------ 启动
  bind();
  loadState().then(loadPersonas);
  loadRelationships();
  loadDevices();
  loadCluster();
  connectWS();
  setInterval(loadCluster, 20000); // 集群状态轻量轮询
})();
