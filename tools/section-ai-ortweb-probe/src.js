import * as ort from 'onnxruntime-web/webgpu';

const root = document.documentElement;
const status = document.getElementById('status');
const shape = [1, 4, 600, 81];
const size = shape.reduce((a, b) => a * b, 1);
const input = new Float32Array(size);
for (let i = 0; i < input.length; i++) input[i] = Math.sin(i * 0.0017) * 0.25;

function setStatus(value, detail = '') {
  status.textContent = value + (detail ? '\n' + detail : '');
}

async function withTimeout(promise, ms, label) {
  return await Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(label + ' timeout after ' + ms + ' ms')), ms))
  ]);
}

async function run(provider) {
  if (provider === 'wasm') {
    ort.env.wasm.wasmPaths = new URL('./ort-wasm/', window.location.href).href;
    ort.env.wasm.numThreads = 1;
  }
  const createStart = performance.now();
  const session = await ort.InferenceSession.create('./model.onnx', {
    executionProviders: [provider],
    graphOptimizationLevel: 'all'
  });
  const createMs = performance.now() - createStart;
  const tensor = new ort.Tensor('float32', input, shape);
  const started = performance.now();
  const outputs = await session.run({ spectrograms: tensor });
  const elapsed = performance.now() - started;
  const section = outputs.section_logits;
  const func = outputs.function_logits;
  if (!section || !func) throw new Error('expected section/function outputs');
  return {
    provider,
    createMs,
    elapsed,
    section: section.dims,
    func: func.dims
  };
}

(async () => {
  root.dataset.webgpuAvailable = navigator.gpu ? 'true' : 'false';

  try {
    setStatus('running wasm');
    const wasm = await withTimeout(run('wasm'), 25000, 'WASM');
    root.dataset.wasmResult = 'PASS';
    root.dataset.wasmInferenceMs = wasm.elapsed.toFixed(1);
    root.dataset.wasmCreateMs = wasm.createMs.toFixed(1);
    setStatus('WASM_PASS', JSON.stringify(wasm));
  } catch (err) {
    root.dataset.wasmResult = 'FAIL';
    root.dataset.wasmError = String(err?.message || err).slice(0, 400);
    root.dataset.sectionAiOrtweb = 'WASM_FAIL';
    setStatus('WASM_FAIL', String(err?.stack || err));
    return;
  }

  if (!navigator.gpu) {
    root.dataset.sectionAiOrtweb = 'NO_WEBGPU_WASM_PASS';
    return;
  }

  try {
    setStatus('running webgpu');
    const gpu = await withTimeout(run('webgpu'), 15000, 'WebGPU');
    root.dataset.provider = 'webgpu';
    root.dataset.sectionShape = gpu.section.join('x');
    root.dataset.functionShape = gpu.func.join('x');
    root.dataset.inferenceMs = gpu.elapsed.toFixed(1);
    root.dataset.sectionAiOrtweb = 'WEBGPU_PASS';
    setStatus('WEBGPU_PASS', JSON.stringify(gpu));
  } catch (err) {
    root.dataset.webgpuError = String(err?.message || err).slice(0, 400);
    root.dataset.sectionAiOrtweb = 'WEBGPU_FAIL_WASM_PASS';
    setStatus('WEBGPU_FAIL_WASM_PASS', String(err?.stack || err));
  }
})();
