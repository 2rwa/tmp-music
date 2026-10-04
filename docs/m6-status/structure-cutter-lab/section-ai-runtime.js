import * as ort from 'onnxruntime-web/webgpu';

const MODEL_URL = './models/harmonix-fold0-section-function-long.onnx';
const MIN_FRAMES = 10240;
const MAX_FRAMES = 66000;
const BANDS = 81;
const STEMS = 4;
const WASM_PATHS = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.26.0/dist/';

let webgpuSession = null;
let wasmSession = null;
let webgpuDisabled = false;

function prepareInput(features) {
  const shape = features?.shape;
  if (!features?.data || !Array.isArray(shape) || shape.length !== 4) throw new Error('invalid Section AI feature tensor');
  const originalFrames = shape[2];
  if (shape[0] !== 1 || shape[1] !== STEMS || shape[3] !== BANDS) throw new Error('Section AI expects [1,4,T,81]');
  if (originalFrames > MAX_FRAMES) throw new Error('Section AI supports tracks up to 660 seconds');
  const frames = Math.max(MIN_FRAMES, originalFrames);
  if (frames === originalFrames) return {data: features.data, frames, originalFrames};
  const padded = new Float32Array(STEMS * frames * BANDS);
  for (let stem = 0; stem < STEMS; stem++) {
    const srcStart = stem * originalFrames * BANDS;
    const dstStart = stem * frames * BANDS;
    padded.set(features.data.subarray(srcStart, srcStart + originalFrames * BANDS), dstStart);
  }
  return {data: padded, frames, originalFrames};
}

async function getSession(provider) {
  if (provider === 'webgpu') {
    if (webgpuSession) return webgpuSession;
    webgpuSession = await ort.InferenceSession.create(MODEL_URL, {
      executionProviders: ['webgpu'],
      graphOptimizationLevel: 'all'
    });
    return webgpuSession;
  }
  if (wasmSession) return wasmSession;
  ort.env.wasm.wasmPaths = WASM_PATHS;
  ort.env.wasm.numThreads = crossOriginIsolated ? 4 : 1;
  wasmSession = await ort.InferenceSession.create(MODEL_URL, {
    executionProviders: ['wasm'],
    graphOptimizationLevel: 'all'
  });
  return wasmSession;
}

function cropOutputs(outputs, frames, originalFrames) {
  const section = outputs.section_logits;
  const func = outputs.function_logits;
  if (!section || !func) throw new Error('Section AI outputs missing');
  const sectionData = Float32Array.from(section.data.subarray(0, originalFrames));
  const classes = func.dims[1] || 10;
  const functionData = new Float32Array(classes * originalFrames);
  for (let c = 0; c < classes; c++) {
    const src = func.data.subarray(c * frames, c * frames + originalFrames);
    functionData.set(src, c * originalFrames);
  }
  return {sectionLogits: sectionData, functionLogits: functionData, classes};
}

async function infer(provider, prepared) {
  const session = await getSession(provider);
  const tensor = new ort.Tensor('float32', prepared.data, [1, STEMS, prepared.frames, BANDS]);
  const started = performance.now();
  const outputs = await session.run({spectrograms: tensor});
  return {
    ...cropOutputs(outputs, prepared.frames, prepared.originalFrames),
    provider,
    inferenceMs: performance.now() - started,
    inputFrames: prepared.frames,
    originalFrames: prepared.originalFrames
  };
}

export async function runSectionAIInference(features, {preferWebGPU = true} = {}) {
  const prepared = prepareInput(features);
  if (preferWebGPU && navigator.gpu && !webgpuDisabled) {
    try {
      return await infer('webgpu', prepared);
    } catch (err) {
      webgpuDisabled = true;
      console.warn('Section AI WebGPU failed; falling back to WASM', err);
    }
  }
  return await infer('wasm', prepared);
}

export const SECTION_AI_MODEL_LIMITS = {minFrames: MIN_FRAMES, maxFrames: MAX_FRAMES, fps: 100};
