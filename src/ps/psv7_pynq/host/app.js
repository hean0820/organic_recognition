/* 上位机交互入口：复用同一viewer，模型数据只读，视角与板端独立。 */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const data = window.MOLECULE_DATA;
  const colors = {C: 0x4a6580, H: 0xf4f8fc, Cl: 0x50a97a, O: 0xd4604b, N: 0x2d70bc, Br: 0x965f39, I: 0x8265a4};
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let viewer = null, current = null, initialView = null, generation = 0;
  let rotating = !reducedMotion.matches, speed = 36, lastTime = null, phase = "loading";
  const choices = new Map();

  function formula(element, value) {
    element.replaceChildren();
    for (const part of value.match(/\d+|[^\d]+/g) || []) {
      if (/^\d+$/.test(part)) { const sub = document.createElement("sub"); sub.textContent = part; element.append(sub); }
      else element.append(document.createTextNode(part));
    }
  }

  function controls() {
    const valid = phase === "ready" && current;
    $("rotationButton").disabled = !valid;
    $("resetButton").disabled = !valid;
    $("rotationSpeed").disabled = !valid;
    $("clearButton").disabled = !viewer || Boolean(window.moleculeLink?.isSending());
    $("rotationButton").textContent = rotating ? "暂停旋转" : "恢复旋转";
    $("rotationButton").setAttribute("aria-pressed", String(Boolean(valid && rotating)));
    $("speedValue").textContent = `${speed}°/秒`;
    for (const [id, button] of choices) {
      button.disabled = !viewer || Boolean(window.moleculeLink?.isPending());
      const selected = current?.class_id === id && phase === "ready";
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", String(selected));
    }
  }

  function empty(title, detail, isError = false) {
    $("emptyTitle").textContent = title;
    $("emptyDetail").textContent = detail;
    $("emptyState").hidden = false;
    $("modelName").textContent = isError ? "模型不可用" : "等待选择";
    $("modelEnglish").textContent = "选择一个分子，查看空间结构";
    $("modelFormula").textContent = "—";
    $("modelCounts").textContent = "";
    $("statusText").textContent = detail;
    controls();
  }

  function setRotating(enabled, message) {
    rotating = Boolean(enabled);
    lastTime = null;
    if (phase === "ready") $("statusText").textContent = message || (rotating ? "自动旋转中" : "旋转已暂停，可自由观察");
    controls();
  }

  function clear(message = "从左侧选择一个分子，开始观察。") {
    ++generation;
    current = null; initialView = null; lastTime = null; phase = "waiting";
    if (viewer) { viewer.clear(); viewer.render(); }
    empty("等待选择分子", message);
  }

  async function select(classId) {
    const id = typeof classId === "number" ? classId : NaN;
    const model = Number.isInteger(id) && data?.models.find(m => m.class_id === id);
    if (!model) { clear("没有对应的有效模型，请选择已准备的分子。"); return false; }
    if (!viewer) { phase = "error"; empty("无法打开三维视图", "请检查本地库文件，并使用支持WebGL的浏览器。", true); return false; }
    if (current?.class_id === id && phase === "ready") return true;
    const ticket = ++generation;
    const wasEmpty = current === null;
    phase = "loading"; lastTime = null; controls();
    await Promise.resolve();
    if (ticket !== generation) return false;
    try {
      viewer.clear();
      const added = viewer.addModel(model.sdf, "sdf", {keepH: true});
      const atoms = added.selectedAtoms({});
      if (atoms.length !== model.atom_count) throw new Error("原子数量与模型数据不一致");
      viewer.setStyle({}, {sphere: {scale: 0.28, colorscheme: colors}, stick: {radius: 0.12, colorscheme: colors}});
      viewer.setProjection("orthographic");
      /* clear只移除模型；显式复位四元数，避免继承前一个分子的角度。 */
      viewer.setView([0, 0, 0, 0, 0, 0, 0, 1]);
      viewer.zoomTo();
      viewer.zoom(1.5);
      viewer.rotate(18, "x");
      viewer.rotate(-18, "y");
      viewer.render();
      initialView = viewer.getView().slice();
      current = model; phase = "ready";
      if (wasEmpty) rotating = !reducedMotion.matches;
      $("modelName").textContent = model.name_zh;
      $("modelEnglish").textContent = model.name_en;
      formula($("modelFormula"), model.formula);
      $("modelFormula").setAttribute("aria-label", `分子式 ${model.formula}`);
      $("modelCounts").textContent = `${model.atom_count} 个原子 · ${model.bond_count} 条键连接`;
      $("emptyState").hidden = true;
      $("statusText").textContent = rotating ? "自动旋转中" : "旋转已暂停，可自由观察";
      if (!window.moleculeLink?.isConnected())
        $("recognizedText").textContent = `${model.name_zh}（本地手动观察，未同步开发板）`;
      controls();
      return true;
    } catch (error) {
      viewer.clear(); viewer.render(); current = null; initialView = null; phase = "error";
      empty("模型加载失败", "本地模型数据不可用，请重新生成模型资源后打开页面。", true);
      console.error(error);
      return false;
    }
  }

  function reset() {
    if (!current || !initialView) return;
    viewer.setView(initialView.slice()); viewer.render(); lastTime = null;
    $("statusText").textContent = rotating ? "视角已复位，继续旋转" : "视角已复位，旋转保持暂停";
  }

  function interact() {
    if (phase === "ready") setRotating(false, "已暂停旋转；点击“恢复旋转”继续。");
  }

  function frame(time) {
    if (lastTime !== null && rotating && phase === "ready" && !document.hidden) {
      const delta = Math.min((time-lastTime)/1000, 0.25);
      viewer.rotate(speed * delta, "y"); viewer.render();
    }
    lastTime = time;
    window.requestAnimationFrame(frame);
  }

  try {
    if (!data?.models?.length || !window.$3Dmol) throw new Error("缺少本地模型或3Dmol.js库");
    for (const model of data.models) {
      const button = document.createElement("button"); button.type = "button"; button.className = "model-choice";
      button.dataset.classId = model.class_id;
      button.setAttribute("aria-label", `选择${model.name_zh}`);
      const text = document.createElement("span"), name = document.createElement("span"), english = document.createElement("span");
      name.className = "choice-name"; name.textContent = model.name_zh;
      english.className = "choice-english"; english.textContent = model.name_en;
      text.append(name, english);
      const chemicalFormula = document.createElement("span"); chemicalFormula.className = "choice-formula"; formula(chemicalFormula, model.formula);
      button.append(text, chemicalFormula); button.addEventListener("click", () =>
        window.moleculeLink?.isConnected() ? window.moleculeLink.select(model.class_id) : select(model.class_id));
      choices.set(model.class_id, button); $("modelList").append(button);
    }
    viewer = window.$3Dmol.createViewer($("viewer"), {backgroundColor: 0xeaf2f8, orthographic: true, antialias: true});
    $("viewer").addEventListener("pointerdown", interact, {capture: true});
    $("viewer").addEventListener("mousedown", interact, {capture: true});
    $("viewer").addEventListener("touchstart", interact, {capture: true, passive: true});
    $("viewer").addEventListener("wheel", interact, {capture: true, passive: true});
    $("viewer").addEventListener("contextmenu", event => event.preventDefault());
    $("rotationButton").addEventListener("click", () => setRotating(!rotating));
    $("resetButton").addEventListener("click", reset);
    $("clearButton").addEventListener("click", () =>
      window.moleculeLink?.isConnected() ? window.moleculeLink.clear() : clear());
    $("rotationSpeed").addEventListener("input", event => { speed = Number(event.target.value); lastTime = null; controls(); });
    document.addEventListener("visibilitychange", () => { lastTime = null; });
    const resize = () => { viewer.resize(); viewer.render(); };
    new ResizeObserver(resize).observe($("viewer"));
    window.moleculeApp = Object.freeze({select, clear, refreshControls: controls, pause: () => setRotating(false), resume: () => setRotating(true), reset,
      snapshot: () => {
        const atoms = viewer.selectedAtoms({});
        return {phase, class_id: current?.class_id ?? null, molecule_id: current?.molecule_id ?? null,
                        rotating: Boolean(rotating && phase === "ready"), speed, generation,
                        atom_count: atoms.length, view: viewer.getView().slice(),
                        atoms: atoms.map(a => ({element: a.elem, x: a.x, y: a.y, z: a.z})),
                        bonds: atoms.flatMap((a, i) => a.bonds.filter(b => b > i).map(b =>
                          ({a: i, b, order: a.bondOrder[a.bonds.indexOf(b)]}))),
                        mapping_version: data.mapping_version};
      }});
    select(0);
    window.requestAnimationFrame(frame);
  } catch (error) {
    current = null; phase = "error";
    empty("无法打开三维视图", "请确认vendor和模型文件完整，并使用支持WebGL的浏览器。", true);
    console.error(error);
  }
})();
