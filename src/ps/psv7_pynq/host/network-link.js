/* Same-origin PYNQ commands; renderer and board share selections, not views. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id), data = window.MOLECULE_DATA;
  const messages = {
    WAIT: '点击开始进行一次识别。', MODE_CHANGED: '模式已切换，可开始一次识别。',
    KEEP_QUIET_500MS: '先保持安静约0.5秒。', SPEAK_NOW: '请读一个化学名称。',
    LISTENING: '正在收音，说完后保持安静。', PROCESSING: '正在识别，请稍候。',
    REQUEST_STARTED: '本次识别已开始。', OK: '本次识别完成，请核对显示名称。',
    CANCELLED: '已取消并清除当前结果。', NO_SPEECH: '没有检测到语音，请重试。',
    SILENCE: '没有有效语音，请重试。', TOO_SHORT: '有效声音过短，请重试。',
    TOO_LONG: '说话时间过长，请只读一个名称。', UNKNOWN_OR_LOW_SCORE: '本次未通过识别阈值，请重试。',
    AUDIO_DROPPED: '采音丢样，请重试。', AUDIO_NOT_READY: '音频尚未就绪。',
    MODEL_NOT_READY: '语音模型尚未就绪。', BUSY: '上一项操作尚未结束。',
    STALE_STATE: '开发板状态已改变，请根据最新状态重新操作。',
    STALE_SERVER: '服务已重新启动，请重新连接。', APPLICATION_STOPPED: '板端应用已停止。',
    APPLICATION_ERROR: '板端操作失败，请查看Notebook及运行报告。',
    TEST_INJECTION: '已同步人工选择，这不是识别结果。', REFERENCE: '已同步参考样本。',
    EDGE: '图像未通过预处理，请调整纸片位置。'
  };
  let connected = false, connecting = false, pending = false, syncing = false, token = null;
  let epoch = 0, board = null, timer = null, selectionKey = null, pollFailures = 0;
  const controllers = new Set();
  class TransportError extends Error {}

  function controls() {
    const ready = connected && board?.running && !pending && !syncing;
    $('connectButton').disabled = connected || connecting;
    $('disconnectButton').disabled = !connected && !connecting;
    $('modeButton').disabled = !ready;
    $('modeButton').textContent = board?.request.mode === 'VOICE' ? '切换到摄像头模式' : '切换到语音模式';
    $('recognizeButton').disabled = !ready || board.busy || (board.request.mode === 'VOICE' && !board.request.recognizer_ready);
    $('recognizeButton').textContent = board?.request.mode === 'VOICE' ? '开始语音识别' : '开始摄像头识别';
    $('audioInput').disabled = !ready || board.busy;
    $('cancelButton').disabled = !ready || !board.busy;
    window.moleculeApp?.refreshControls();
  }

  function disconnect(message = '已断开，可手动观察。') {
    ++epoch; clearTimeout(timer);
    for (const controller of controllers) controller.abort();
    controllers.clear();
    connected = connecting = pending = syncing = false; pollFailures = 0;
    token = null; board = null; selectionKey = null;
    window.moleculeApp?.clear('连接已断开，可手动选择分子。');
    $('recognitionMode').textContent = '模式未同步';
    $('voiceStatus').textContent = '重新连接后同步开发板当前状态。';
    $('recognizedText').textContent = '尚未识别';
    $('computeTiming').textContent = '计算耗时：—';
    $('computeTiming').title = '';
    $('connectionStatus').textContent = message; controls();
  }

  async function request(path, options = {}) {
    const abort = new AbortController(); controllers.add(abort);
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; abort.abort(); }, 3500);
    try {
      const response = await fetch(path, {...options, cache: 'no-store', signal: abort.signal});
      const result = await response.json();
      if (!response.ok && !result.state) throw new Error(messages[result.reason] || result.reason || '服务请求失败');
      return result;
    } catch (error) {
      if (timedOut || error.name === 'AbortError' || error.name === 'TypeError')
        throw new TransportError(timedOut ? '状态请求超时' : '网络暂时不可达');
      throw error;
    } finally { clearTimeout(timeout); controllers.delete(abort); }
  }

  function waitForState(message) {
    syncing = true;
    $('connectionStatus').textContent = message;
    $('voiceStatus').textContent = '正在自动查询开发板状态，请稍候。';
    controls();
  }

  async function applyState(state, ticket = epoch) {
    if (ticket !== epoch || !connected) return false;
    if (state?.protocol_version !== 1 || state.mapping_version !== data.mapping_version ||
        !Number.isInteger(state.revision) || !state.request || !['CAMERA', 'VOICE'].includes(state.request.mode))
      throw new Error('网页与板端协议不匹配，请使用配套工程。');
    if (board && state.server_id !== board.server_id) throw new Error('服务已重新启动，请重新连接。');
    if (board && (state.revision < board.revision || state.revision === board.revision && !syncing)) return false;
    if (!state.running || !state.accepting) throw new Error('板端应用已停止，请按说明重新启动。');
    const selection = state.selection;
    const model = selection.valid && data.models.find(m => m.class_id === selection.class_id);
    if (selection.valid && (!model || model.molecule_id !== selection.molecule_id || model.name_zh !== selection.name))
      throw new Error('分子映射不匹配，已停止同步。');
    board = state;
    const r = state.request;
    const t = state.voice_timing;
    const currentTiming = t && r.mode === 'VOICE' && !r.active &&
      ['RESULT', 'REJECTED', 'ERROR'].includes(r.state) && ['VOICE', 'NONE'].includes(r.source) &&
      ['mode_epoch', 'request_epoch', 'request_id', 'selection_seq'].every(k => t[k] === r[k]) &&
      t.clock === 'PROCESS_CPU_CLOCK' && ['total_us', 'frontend_us', 'cnn_us'].every(k => Number.isFinite(t[k]) && t[k] >= 0);
    const ms = us => (us / 1000).toFixed(3);
    const ct = state.camera_timing;
    const currentCameraTiming = ct && r.mode === 'CAMERA' && r.state === 'RESULT' && r.source === 'CAMERA' &&
      r.valid && !r.active && selection.valid && ct.class_id === selection.class_id &&
      ['mode_epoch', 'request_epoch', 'request_id', 'selection_seq', 'class_id'].every(k => ct[k] === r[k]) &&
      ct.clock === 'PERF_COUNTER_WALL_CLOCK' &&
      ['inference_wall_ms', 'fc_wait_ms', 'total_us'].every(k => Number.isFinite(ct[k]) && ct[k] >= 0);
    $('computeTiming').textContent = currentCameraTiming ?
      `${ct.input_source === 'SAVED_CAMERA_FRAME_REGRESSION' ? '保存帧回归' : '本次摄像'} #${r.request_id} · 推理 ${ct.inference_wall_ms.toFixed(3)} ms（墙钟） · FC等待 ${ct.fc_wait_ms.toFixed(3)} ms · 本次耗时 ${ms(ct.total_us)} ms` : currentTiming ?
      `${t.input_source === 'EXISTING_TRAINING_PCM_REGRESSION' ? '参考样本' : '本次语音'} #${r.request_id} · 计算 ${ms(t.total_us)} ms（CPU） · 前端 ${ms(t.frontend_us)} ms · CNN ${ms(t.cnn_us)} ms` :
      r.state === 'REJECTED' ? '计算耗时：—（本次未进入模型计算）' : '计算耗时：—';
    $('computeTiming').title = currentCameraTiming ?
      '推理包含卷积输入输出传输及PL FC和缓存处理；不含采图、预处理、报告保存和显示。FC等待包含轮询。本次耗时与HDMI Time相同，诊断文件在结果显示后保存，不计入本次耗时。' : '';
    $('recognitionMode').textContent = r.mode === 'VOICE' ? '语音识别模式 · 单次' : '摄像头识别模式';
    $('audioInput').value = r.line_input ? 'linein' : 'mic';
    $('voiceStatus').textContent = state.job?.state === 'error' ? '操作未完成，请查看Notebook报告或重新操作。' :
      messages[r.reason] || (r.state === 'REJECTED' ? '本次未通过识别，请重试。' :
        r.state === 'ERROR' ? '本次操作失败，请查看Notebook及运行报告。' : '正在处理本次操作。');
    const sources = {camera: '摄像头识别', voice: '语音识别', manual: '人工选择，非识别结果', reference: '参考样本，非实时识别'};
    $('recognizedText').textContent = selection.valid ? `${model.name_zh}（${sources[selection.source] || '未知来源'}）` :
      r.state === 'REJECTED' ? '本次未识别出有效分子' : state.busy ? '正在处理本次请求…' : '当前没有有效结果';
    const key = `${r.mode_epoch}/${r.selection_seq}/${selection.class_id}/${selection.valid}/${selection.valid ? '' : state.busy}`;
    controls();
    if (key !== selectionKey) {
      selectionKey = key;
      if (selection.valid) {
        const loaded = await window.moleculeApp.select(model.class_id);
        if (ticket !== epoch || board.revision !== state.revision) return false;
        if (!loaded) throw new Error('模型加载失败，请重新打开网页。');
      } else window.moleculeApp.clear(state.busy ? '正在处理操作，等待有效结果。' : '开发板当前没有有效结果。');
    }
    if (ticket !== epoch || board.revision !== state.revision) return false;
    $('connectionStatus').textContent = selection.valid ? `已同步：${model.name_zh} · ${sources[selection.source]}` : '已连接，状态同步正常。';
    return true;
  }

  async function poll(ticket) {
    if (ticket !== epoch || !connected) return;
    try {
      // Queries never replay an operation. Older replies cannot replace a
      // newer revision, and disconnect invalidates every pending reply.
      if (!pending) {
        const result = await request('/api/state');
        await applyState(result.state, ticket);
        if (ticket === epoch && connected) {
          pollFailures = 0; syncing = false; controls();
        }
      }
    } catch (error) {
      if (ticket === epoch) {
        if (error instanceof TransportError && ++pollFailures < 3)
          waitForState('状态读取暂时失败，正在自动恢复连接…');
        else disconnect(`连接中断：${error.message}`);
      }
    } finally {
      if (ticket === epoch && connected)
        timer = setTimeout(() => poll(ticket), pollFailures ? 500 * pollFailures : 250);
    }
  }

  async function connect() {
    if (connected || connecting) return;
    if (!/^https?:$/.test(location.protocol)) {
      $('connectionStatus').textContent = '请打开Notebook提供的开发板网页地址。'; return;
    }
    const ticket = ++epoch; connecting = true; controls();
    try {
      const result = await request('/api/connect');
      if (ticket !== epoch) return;
      token = result.token; connected = true; board = null;
      await applyState(result.state, ticket);
      if (ticket === epoch) timer = setTimeout(() => poll(ticket), 250);
    } catch (error) { if (ticket === epoch) disconnect(`无法连接：${error.message}`); }
    finally { if (ticket === epoch) { connecting = false; controls(); } }
  }

  async function command(name, value) {
    if (!connected || !board || pending || syncing) return false;
    // A manual/clear action must keep its board path until it is confirmed;
    // never fall back to local selection while a connected request is pending.
    const ticket = epoch, state = board;
    pending = true; controls();
    try {
      const result = await request('/api/command', {method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-PSV7-Token': token},
        body: JSON.stringify({command: name, value, server_id: state.server_id,
                             mode_epoch: state.request.mode_epoch, request_id: state.request.request_id})});
      if (ticket !== epoch) return false;
      if (result.state) await applyState(result.state, ticket);
      if (!result.ok) $('voiceStatus').textContent = messages[result.reason] || `操作未完成：${result.reason}`;
      return Boolean(result.ok);
    } catch (error) {
      if (ticket === epoch) {
        if (error instanceof TransportError)
          waitForState('暂未收到操作确认，正在查询状态；本次操作不会重复发送。');
        else disconnect(`连接中断：${error.message}`);
      }
      return false;
    }
    finally { if (ticket === epoch) { pending = false; controls(); } }
  }

  $('connectButton').addEventListener('click', connect);
  $('disconnectButton').addEventListener('click', () => disconnect());
  $('modeButton').addEventListener('click', () => command('mode', board.request.mode === 'VOICE' ? 'camera' : 'voice'));
  $('recognizeButton').addEventListener('click', () => command('recognize'));
  $('cancelButton').addEventListener('click', () => command('cancel'));
  $('audioInput').addEventListener('change', event => {
    const value = event.target.value;
    if (board) $('audioInput').value = board.request.line_input ? 'linein' : 'mic';
    void command('audio_input', value);
  });
  window.moleculeLink = Object.freeze({connect, disconnect,
    isSending: () => pending || connecting || syncing,
    isConnected: () => connected, isPending: () => pending || connecting || syncing || (connected && (!board || board.busy)),
    select: id => command('select', id), clear: () => command('clear'),
    snapshot: () => ({connected, connecting, pending, syncing, pollFailures, epoch, board})});
  $('connectionStatus').textContent = '未连接，可手动观察。点击连接同步PYNQ应用。';
  controls();
})();
