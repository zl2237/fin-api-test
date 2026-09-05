<template>
  <!-- 头像裁剪弹窗：1:1 画布即裁剪区，拖动定位 + 滚轮/双指缩放（Pointer Events 统一鼠标与触屏） -->
  <el-dialog v-model="visible" title="裁剪头像" width="460px" :close-on-click-modal="false">
    <div class="crop-body">
      <canvas
        ref="canvasRef"
        class="crop-canvas"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @wheel.prevent="onWheel"
        @dblclick="resetView"
      />
      <div class="crop-hint">拖动调整位置 · 滚轮或双指缩放 · 双击复位</div>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="uploading" :disabled="!ready" @click="onConfirm">
        确认上传
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

/** 显隐由父级持有；file 置入即加载图片（父级同时把 visible 置 true）；confirm 输出 256×256 JPEG base64 */
const visible = defineModel<boolean>({ default: false })
const props = defineProps<{ file: File | null; uploading?: boolean }>()
const emit = defineEmits<{ confirm: [dataUrl: string] }>()

// 画布逻辑尺寸：整个画布就是 1:1 裁剪区（超出画布的图片部分被裁掉）
const SIZE = 400
const OUT_SIZE = 256
const QUALITY = 0.85

const canvasRef = ref<HTMLCanvasElement | null>(null)
const imgEl = ref<HTMLImageElement | null>(null)
const ready = computed(() => !!imgEl.value)
// 图片视图状态：offset=图片左上角在画布中的坐标，scale=显示缩放
const view = ref({ x: 0, y: 0, scale: 1 })
const coverScale = ref(1)

function clampScale(s: number): number {
  // 下限=cover（画布不露白），上限=cover×10（放大细节足够用）
  return Math.min(Math.max(s, coverScale.value), coverScale.value * 10)
}

/** 约束 offset：图片必须完整覆盖画布（四边都不露白） */
function clampOffset(x: number, y: number, scale: number) {
  const img = imgEl.value!
  view.value.x = Math.min(0, Math.max(x, SIZE - img.width * scale))
  view.value.y = Math.min(0, Math.max(y, SIZE - img.height * scale))
}

function render() {
  const canvas = canvasRef.value
  const img = imgEl.value
  if (!canvas || !img) return
  canvas.width = SIZE
  canvas.height = SIZE
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, SIZE, SIZE)
  ctx.drawImage(img, view.value.x, view.value.y, img.width * view.value.scale, img.height * view.value.scale)
}

function resetView() {
  const img = imgEl.value
  if (!img) return
  coverScale.value = Math.max(SIZE / img.width, SIZE / img.height)
  view.value.scale = coverScale.value
  clampOffset((SIZE - img.width * coverScale.value) / 2, (SIZE - img.height * coverScale.value) / 2, coverScale.value)
  render()
}

// ===== 缩放（锚点不动公式：画布锚点对应的原图位置在缩放前后保持不变） =====
function zoomAt(anchorX: number, anchorY: number, nextScale: number) {
  const img = imgEl.value
  if (!img) return
  const s = clampScale(nextScale)
  if (s === view.value.scale) return
  const imgX = (anchorX - view.value.x) / view.value.scale
  const imgY = (anchorY - view.value.y) / view.value.scale
  view.value.scale = s
  clampOffset(anchorX - imgX * s, anchorY - imgY * s, s)
  render()
}

function onWheel(e: WheelEvent) {
  if (!imgEl.value) return
  const factor = Math.exp(-e.deltaY * 0.0015)
  zoomAt(e.offsetX, e.offsetY, view.value.scale * factor)
}

// ===== 指针交互：单指拖动；双指捏合缩放（触屏顺带可用） =====
const pointers = new Map<number, { x: number; y: number }>()
let pinchBase: { dist: number; scale: number } | null = null

function localPos(e: PointerEvent): { x: number; y: number } {
  const rect = canvasRef.value!.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function onPointerDown(e: PointerEvent) {
  if (!imgEl.value) return
  canvasRef.value?.setPointerCapture(e.pointerId)
  pointers.set(e.pointerId, localPos(e))
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()]
    pinchBase = { dist: Math.hypot(a.x - b.x, a.y - b.y), scale: view.value.scale }
  }
}

function onPointerMove(e: PointerEvent) {
  if (!pointers.has(e.pointerId)) return
  const prev = pointers.get(e.pointerId)!
  const cur = localPos(e)
  pointers.set(e.pointerId, cur)
  if (pointers.size === 1) {
    clampOffset(view.value.x + cur.x - prev.x, view.value.y + cur.y - prev.y, view.value.scale)
    render()
  } else if (pointers.size === 2 && pinchBase) {
    // 双指：以两指中点为锚按距离比例缩放
    const [a, b] = [...pointers.values()]
    const dist = Math.hypot(a.x - b.x, a.y - b.y)
    zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, pinchBase.scale * (dist / pinchBase.dist))
  }
}

function onPointerUp(e: PointerEvent) {
  pointers.delete(e.pointerId)
  if (pointers.size < 2) pinchBase = null
}

// ===== 载入与输出 =====
watch(() => props.file, (file) => {
  if (!file) {
    imgEl.value = null
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const img = new Image()
    img.onload = () => {
      imgEl.value = img
      resetView()
    }
    img.src = reader.result as string
  }
  reader.readAsDataURL(file)
}, { immediate: true })

function onConfirm() {
  const img = imgEl.value
  if (!img) return
  // 画布坐标系 → 原图坐标：画布 1px = 1/scale 原图像素
  const srcSide = SIZE / view.value.scale
  const sx = -view.value.x / view.value.scale
  const sy = -view.value.y / view.value.scale
  const out = document.createElement('canvas')
  out.width = OUT_SIZE
  out.height = OUT_SIZE
  const ctx = out.getContext('2d')!
  ctx.fillStyle = '#fff' // PNG 透明底铺白，避免 JPEG 转黑
  ctx.fillRect(0, 0, OUT_SIZE, OUT_SIZE)
  ctx.drawImage(img, sx, sy, srcSide, srcSide, 0, 0, OUT_SIZE, OUT_SIZE)
  emit('confirm', out.toDataURL('image/jpeg', QUALITY))
}
</script>

<style scoped>
.crop-body { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.crop-canvas {
  width: 400px;
  height: 400px;
  max-width: 100%;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  cursor: grab;
  touch-action: none; /* 触屏拖动不触发页面滚动 */
  user-select: none;
}
.crop-canvas:active { cursor: grabbing; }
.crop-hint { font-size: 12px; color: var(--app-text-muted); }
</style>
