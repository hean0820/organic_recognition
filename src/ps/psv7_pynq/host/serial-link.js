/* Web Serial adapter. Only opens the port chosen by the user's button click. */
(() => {
  'use strict';
  const PREFIX = 'MOL3D_EVT ', MAX_LINE = 512;
  const data = window.MOLECULE_DATA;
  const $ = id => document.getElementById(id);
  let port = null, reader = null, readTask = null, epoch = 0, session = 0, lastSeq = 0;
  let acknowledged = false, line = '', dropping = false, closing = false, connecting = false, watchdog = null;
  let writeChain = Promise.resolve();
  let applicationRevision = 0;
  let boardState = null, commandPending = false, stateTimer = null, lastSelectionSeq = 0;
  const messages = {
    OK: '本次识别完成，请核对显示的名称。',
    MODEL_NOT_READY: '语音识别模型尚未就绪，请检查开发板固件和启动状态。',
    AUDIO_NOT_READY: '音频尚未就绪，请等待初始化。',
    KEEP_QUIET_500MS: '先保持安静约0.5秒。', SPEAK_NOW: '请读一个化学名称。',
    LISTENING: '正在收音，说完后保持安静。', DIAGNOSTIC_RECORDING_3S: '正在录音测试（3秒），这不是语音识别。',
    DIAGNOSTIC_CAPTURE_READY_NO_ASR: '3秒录音完成，尚未执行语音识别。',
    CAPTURE_READY: '录音完成，正在准备本次识别。',
    VAD_CAPTURE_READY_DIAGNOSTIC: '语音录音测试完成，未执行识别；保留上一次资料和模型。',
    CAPTURE_READY_MODEL_NOT_CONNECTED: '录音完成，识别模型尚未接入。',
    PROCESSING: '正在开发板内识别本次语音，请稍候。',
    UNKNOWN_OR_LOW_SCORE: '本次语音未通过识别阈值，请重试；保留上一次资料和模型。',
    SILENCE: '本次录音没有有效语音，请重试；保留上一次资料和模型。',
    MODEL_ERROR: '本次模型推理失败，请查看串口诊断；保留上一次资料和模型。',
    NO_SPEECH: '没有检测到语音，请重试。', TOO_SHORT: '有效声音过短，请重试。',
    TOO_LONG: '说话时间过长，请只读一个名称。', AUDIO_DROPPED: '音频丢样，请重试。',
    AUDIO_RECONFIGURING: '正在切换音频输入。', CANCELLED: '已清除当前结果。'
  };
  function status(text) { $('connectionStatus').textContent = text; }
  function controls() {
    $('connectButton').disabled = Boolean(port || closing || connecting);
    $('disconnectButton').disabled = !port || closing;
    const ready = Boolean(port && acknowledged && boardState && !closing && !commandPending && !boardState.active);
    $('modeButton').disabled = !ready;
    $('modeButton').textContent = boardState?.mode === 'VOICE' ? '切换到摄像头模式' : '切换到语音模式';
    $('recognizeButton').disabled = !ready || (boardState.mode === 'VOICE' && (!boardState.audio_ready || !boardState.recognizer_ready));
    $('recognizeButton').textContent = boardState?.mode === 'VOICE' ? '开始语音识别' : '开始摄像头识别';
    $('audioInput').disabled = !ready;
  }
  function resetSession(token) {
    ++applicationRevision;
    session = token; lastSeq = 0; acknowledged = false; line = ''; dropping = false;
    boardState = null; commandPending = false; lastSelectionSeq = 0; clearTimeout(stateTimer);
    $('recognitionMode').textContent = '模式未同步';
    $('voiceStatus').textContent = '等待开发板确认模式。'; $('recognizedText').textContent = '尚未识别';
    window.moleculeApp.clear('等待开发板发送当前分子。'); controls();
  }
  function send(text) {
    const target = port, ticket = epoch;
    const task = writeChain.catch(() => {}).then(async () => {
      if (!target?.writable || target !== port || ticket !== epoch || closing) throw new Error('串口已断开');
      const writer = target.writable.getWriter();
      try { await writer.write(new TextEncoder().encode(text)); }
      finally { writer.releaseLock(); }
    });
    writeChain = task;
    return task;
  }
  function handshake() {
    clearTimeout(watchdog);
    let token = crypto.getRandomValues(new Uint32Array(1))[0];
    if (!token || token === session) token = (session + 1) >>> 0 || 1;
    resetSession(token);
    status('已连接，等待开发板确认…');
    send(`@${token}\n`).catch(error => status(`发送失败：${error.message}`));
    const ticket = epoch;
    watchdog = setTimeout(() => {
      if (ticket === epoch && !acknowledged) status('开发板未确认。请运行3D_VOICE工程，或检查所选串口。');
    }, 5000);
  }
  async function applyEvent(event) {
    if (!event || event.session_id !== session || !session) return false;
    if (!Number.isInteger(event.event_seq) || event.event_seq <= lastSeq || event.event_seq > 0xffffffff) return false;
    const validProtocol = event.protocol_version === 1 && event.mapping_version === data.mapping_version &&
      ['manual', 'cnn', 'golden', 'voice'].includes(event.source) && typeof event.pending === 'boolean' &&
      typeof event.snapshot === 'boolean' && (acknowledged || event.snapshot && event.event_seq === 1);
    const model = data.models.find(m => m.class_id === event.class_id);
    const validSelection = event.action === 'select' && Number.isInteger(event.class_id) && model && model.molecule_id === event.molecule_id;
    const validClear = event.action === 'clear' && event.class_id === -1 && event.molecule_id === '';
    if (!validProtocol || !(validSelection || validClear)) {
      ++applicationRevision;
      window.moleculeApp.clear('开发板与网页的数据不匹配，请使用同一份第五阶段工程。');
      status('收到不匹配的分子事件，已清除模型。'); return false;
    }
    const firstSnapshot = !acknowledged;
    lastSeq = event.event_seq; acknowledged = true; clearTimeout(watchdog); controls();
    if (firstSnapshot) void send(':status\n').catch(error => status(error.message));
    const ticket = epoch, seq = lastSeq, revision = ++applicationRevision;
    let loaded = true;
    if (validSelection) loaded = await window.moleculeApp.select(event.class_id);
    else window.moleculeApp.clear(event.pending ? '正在识别，等待有效结果。' : '开发板当前没有有效识别结果。');
    if (ticket !== epoch || seq !== lastSeq || revision !== applicationRevision) return false;
    if (!loaded) { status('模型加载失败，请重新打开网页。'); return false; }
    status(event.pending ? validSelection ? '正在识别，保留上一次模型。' : '正在识别，等待有效结果。' : validSelection ? `已同步：${model.name_zh} · ${event.source === 'cnn' ? '摄像头识别' : event.source === 'voice' ? '语音选择' : event.source === 'golden' ? '固定图测试' : '手动选择'}` : '已同步：等待有效结果。');
    return true;
  }
  function receiveLine(value) {
    if (value === 'MOL3D_READY') { if (port && !closing) handshake(); return; }
    if (value.startsWith('@EVT ') && acknowledged) {
      try { applyControlEvent(JSON.parse(value.slice(5))); } catch { $('voiceStatus').textContent = '模式消息损坏，等待重新同步。'; }
      return;
    }
    if (value.startsWith('@ACK ') && acknowledged) {
      try {
        const ack = JSON.parse(value.slice(5));
        if (ack.ok === false) { commandPending = false; clearTimeout(stateTimer); $('voiceStatus').textContent = messages[ack.reason] || `操作未完成：${ack.reason}`; controls(); }
      } catch {}
      return;
    }
    if (!value.startsWith(PREFIX)) return;
    try { void applyEvent(JSON.parse(value.slice(PREFIX.length))); }
    catch { ++applicationRevision; window.moleculeApp.clear('分子消息损坏，等待下一个有效结果。'); status('分子消息损坏。'); }
  }
  function feed(text) {
    for (const char of text) {
      if (char === '\n') { if (!dropping) receiveLine(line.replace(/\r$/, '')); line = ''; dropping = false; }
      else if (!dropping) {
        line += char;
        if (line.length > MAX_LINE) { line = ''; dropping = true; }
      }
    }
  }
  async function readLoop(target, ticket) {
    const decoder = new TextDecoder();
    try {
      while (target.readable && target === port && ticket === epoch && !closing) {
        reader = target.readable.getReader();
        try {
          while (true) {
            const result = await reader.read();
            if (result.done || ticket !== epoch || closing) break;
            feed(decoder.decode(result.value, {stream: true}));
          }
        } finally { reader.releaseLock(); reader = null; }
        // A stream end without an explicit disconnect is treated as a disconnect.
        if (ticket === epoch && !closing) break;
      }
    } catch (error) { if (!closing && ticket === epoch) status(`串口读取中断：${error.message}`); }
    finally {
      if (!closing && target === port && ticket === epoch) {
        port = null; ++epoch; resetSession(0); clearTimeout(watchdog);
        await writeChain.catch(() => {});
        try { await target.close(); } catch {}
        status('连接已断开，模型已清除。可重新连接。'); controls();
      }
    }
  }
  async function connect() {
    if (port || closing || connecting) return;
    if (!navigator.serial || !window.isSecureContext) { status('请使用桌面版 Edge 或 Chrome 打开本地页面。'); return; }
    let target = null;
    connecting = true; controls();
    try {
      // Must remain directly under the user's gesture; never auto-select a port.
      target = await navigator.serial.requestPort();
      await target.open({baudRate: 115200, dataBits: 8, stopBits: 1, parity: 'none', flowControl: 'none'});
      port = target; ++epoch; closing = false; writeChain = Promise.resolve();
      readTask = readLoop(target, epoch); handshake(); controls();
    } catch (error) {
      if (target && target !== port) { try { await target.close(); } catch {} }
      status(error.name === 'NotFoundError' ? '未选择串口，可继续手动观察。' : '无法连接。请关闭占用此串口的 Vitis 终端或串口助手后重试。'); controls();
    } finally { connecting = false; controls(); }
  }
  async function disconnect() {
    if (!port || closing) return;
    const target = port;
    closing = true; ++epoch; clearTimeout(watchdog); controls();
    try {
      if (reader) await reader.cancel();
      if (readTask) await readTask;
      await writeChain.catch(() => {});
      await target.close();
    } catch (error) { status(`关闭串口：${error.message}`); }
    finally { port = null; closing = false; resetSession(0); status('已断开，模型已清除。可手动观察。'); controls(); }
  }
  async function choose(id, voice = false) {
    if (!Number.isInteger(id) || !data.models.some(m => m.class_id === id)) throw new Error('分子编号必须为0..21');
    if (!port || !acknowledged) throw new Error('请先连接开发板并等待确认');
    await send(`${voice ? 'V' : 'i'}${id}\n`);
  }
  function command(value) { return send(value).catch(error => status(`发送失败：${error.message}`)); }
  function newer(value, previous) { const delta = (value - previous) >>> 0; return delta !== 0 && delta < 0x80000000; }
  function applyControlEvent(event) {
    if (!event || event.v !== 1 || !['CAMERA', 'VOICE'].includes(event.mode) || !Number.isInteger(event.mode_epoch) || !Number.isInteger(event.request_id)) return false;
    if (boardState && event.mode_epoch !== boardState.mode_epoch && !newer(event.mode_epoch, boardState.mode_epoch)) return false;
    if (event.type === 'state') {
      if (typeof event.active !== 'boolean' || typeof event.audio_ready !== 'boolean' || typeof event.recognizer_ready !== 'boolean' || !['ONBOARD_MIC','LINE_IN'].includes(event.audio_input)) return false;
      if (boardState && event.mode_epoch === boardState.mode_epoch && event.request_id !== boardState.request_id && !newer(event.request_id, boardState.request_id)) return false;
      const modeChanged = !boardState || event.mode !== boardState.mode;
      boardState = {...event}; commandPending = false; clearTimeout(stateTimer);
      $('recognitionMode').textContent = event.mode === 'VOICE' ? '语音识别模式 · 单次' : '摄像头识别模式';
      $('audioInput').value = event.audio_input === 'LINE_IN' ? 'linein' : 'mic';
      $('voiceStatus').textContent = messages[event.reason] || (event.mode === 'VOICE' ? event.recognizer_ready ? '点击开始，读一个化学名称。' : messages.MODEL_NOT_READY : '点击开始进行一次摄像头识别。');
      if (modeChanged || event.active) $('recognizedText').textContent = event.mode === 'VOICE' ? '等待语音识别' : '语音文字在语音模式下显示';
      controls(); return true;
    }
    if (event.type === 'selection' && boardState && event.mode === boardState.mode && event.mode_epoch === boardState.mode_epoch && event.request_id === boardState.request_id) {
      if (!Number.isInteger(event.selection_seq) || event.selection_seq <= 0 || event.selection_seq > 0xffffffff ||
          (lastSelectionSeq && !newer(event.selection_seq,lastSelectionSeq))) return false;
      lastSelectionSeq = event.selection_seq;
      if (!event.valid) { if (event.mode === 'VOICE') $('recognizedText').textContent = '等待语音识别'; return true; }
      const model = data.models.find(m => m.class_id === event.class_id);
      if (!model || event.name !== model.name_zh) return false;
      if (event.source === 'VOICE' && event.backend === 'BOARD' && boardState.recognizer_ready)
        $('recognizedText').textContent = model.name_zh;
      else if (event.source === 'TEST' || event.source === 'EXTERNAL')
        $('recognizedText').textContent = `${model.name_zh}（${event.source === 'TEST' ? '测试注入' : '外部编号'}，非板载语音识别）`;
      return true;
    }
    return false;
  }
  async function controlCommand(value) {
    if (!port || !acknowledged || !boardState || commandPending || boardState.active) return false;
    commandPending = true; controls();
    const ticket = epoch;
    stateTimer = setTimeout(() => {
      if (ticket !== epoch) return;
      commandPending = false; $('voiceStatus').textContent = '未收到操作确认，正在重新查询开发板状态。'; controls();
      void command(':status\n');
    }, 4000);
    try { await send(value); return true; }
    catch (error) { commandPending = false; clearTimeout(stateTimer); status(error.message); controls(); return false; }
  }
  $('connectButton').addEventListener('click', connect);
  $('disconnectButton').addEventListener('click', disconnect);
  $('modeButton').addEventListener('click', () => { if (boardState) void controlCommand(boardState.mode === 'VOICE' ? ':mode camera\n' : ':mode voice\n'); });
  $('recognizeButton').addEventListener('click', () => {
    if (!boardState || $('recognizeButton').disabled) return;
    void controlCommand(boardState.mode === 'VOICE' ? ':voice once\n' : 'e');
  });
  $('audioInput').addEventListener('change', event => {
    const desired = event.target.value;
    if (boardState) $('audioInput').value = boardState.audio_input === 'LINE_IN' ? 'linein' : 'mic';
    void controlCommand(desired === 'linein' ? ':audio linein\n' : ':audio mic\n');
  });
  window.moleculeLink = Object.freeze({connect, disconnect, applyEvent, feed,
    isConnected: () => Boolean(port), select: id => choose(id).catch(error => status(error.message)),
    voiceSelect: id => choose(id, true), clear: () => controlCommand(':clear\n'),
    snapshot: () => ({connected: Boolean(port), acknowledged, session, lastSeq, epoch, buffered: line.length, boardState, commandPending})});
  controls();
  if (!navigator.serial || !window.isSecureContext) status('当前浏览器不支持串口连接；手动观察可用。请使用桌面版 Edge 或 Chrome。');
})();
