import * as ort from 'onnxruntime-web/webgpu';

const root = document.documentElement;
const status = document.getElementById('status');
const shape = [1, 4, 600, 81];
const size = shape.reduce((a, b) => a * b, 1);
const input = new Float32Array(size);
for (let i = 0; i < input.length; i++) input[i] = Math.sin(i * 0.0017) * 0.25;

function setResult(value, detail = '') {
  root.dataset.sectionAiOrtweb = value;
  status.textContent = value + (detail ? '\n' + detail : '');
}

async function run(provider) {
  if (provider === 'wasm') {
    ort.env.wasm.wasmPaths = './ort-wasm/';
    ort.env.wasm.numThreads = 1;
  }
  const session = await ort.InferenceSession.create('./model.onnx', {
    executionProviders: [provider],
    graphOptimizationLevel: 'all'
  });
  const tensor = new ort.Tensor('float32', input, shape);
  const started = performance.now();
  const outputs = await session.run({ spectrograms: tensor });
  const elapsed = performance.now() - started;
  const section = outputs.section_logits;
  const func = outputs.function_logits;
  if (!section || !func) throw new Error('expected section/function outputs');
  root.dataset.sectionShape = section.dims.join('x');
  root.dataset.functionShape = func.dims.join('x');
  root.dataset.provider = provider;
  root.dataset.inferenceMs = elapsed.toFixed(1);
  return { elapsed, section: section.dims, func: func.dims };
}

(async () => {
  root.dataset.webgpuAvailable = navigator.gpu ? 'true' : 'false';
  if (navigator.gpu) {
    try {
      const result = await run('webgpu');
      setResult('WEBGPU_PASS', JSON.stringify(result));
      return;
    } catch (err) {
      root.dataset.webgpuError = String(err?.message || err).slice(0, 400);
      console.error('WebGPU probe failed', err);
    }
  }

  try {
    const result = await run('wasm');
    setResult(navigator.gpu ? 'WEBGPU_FAIL_WASM_PASS' : 'NO_WEBGPU_WASM_PASS', JSON.stringify(result));
  } catch (err) {
    root.dataset.wasmError = String(err?.message || err).slice(0, 400);
    console.error('WASM probe failed', err);
    setResult(navigator.gpu ? 'WEBGPU_FAIL_WASM_FAIL' : 'NO_WEBGPU_WASM_FAIL', String(err?.stack || err));
  }
})();
