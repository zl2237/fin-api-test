<template>
  <el-dialog
    v-model="visible"
    title="选择文件"
    width="780px"
    append-to-body
    destroy-on-close
    class="file-picker-dialog"
    @close="onClose"
  >
    <!-- 顶部：搜索 + 上传 -->
    <div class="picker-toolbar">
      <el-input
        v-model="keyword"
        placeholder="按名称搜索"
        clearable
        size="default"
        style="width: 260px"
        @keyup.enter="loadFiles"
        @clear="loadFiles"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select
        v-model="filterCategory"
        placeholder="按分类筛选"
        clearable
        size="default"
        style="width: 180px"
        @change="loadFiles"
      >
        <el-option label="全部分类" :value="undefined" />
        <el-option
          v-for="c in categories"
          :key="c.id"
          :label="c.name"
          :value="c.id"
        />
      </el-select>
      <el-select
        v-model="filterTag"
        placeholder="按标签筛选"
        clearable
        size="default"
        style="width: 160px"
        @change="loadFiles"
      >
        <el-option label="全部标签" :value="undefined" />
        <el-option
          v-for="t in tags"
          :key="t.id"
          :label="t.name"
          :value="t.id"
        />
      </el-select>
      <el-upload
        :show-file-list="false"
        :before-upload="handleUpload"
        :http-request="() => {}"
        class="picker-upload"
      >
        <el-button type="primary" :icon="Upload" size="default">上传</el-button>
      </el-upload>
    </div>

    <!-- 文件列表 -->
    <el-table
      v-loading="loading"
      :data="files"
      stripe
      size="small"
      row-key="id"
      height="380"
      highlight-current-row
      @current-change="onCurrentChange"
      @row-dblclick="onRowDblClick"
      empty-text="暂无文件，可点右上角「上传」"
    >
      <el-table-column label="" width="40" align="center">
        <template #default="{ row }">
          <el-radio v-model="selectedId" :value="row.id" :label="row.id" class="picker-radio">
            <span></span>
          </el-radio>
        </template>
      </el-table-column>
      <el-table-column label="文件名" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <el-icon class="file-icon" :style="{ color: fileIconColor(row.content_type) }">
            <component :is="fileIcon(row.content_type)" />
          </el-icon>
          <span>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="90">
        <template #default="{ row }">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="类型" width="110" show-overflow-tooltip>
        <template #default="{ row }">{{ formatContentType(row.content_type) }}</template>
      </el-table-column>
      <el-table-column label="标签" min-width="120">
        <template #default="{ row }">
          <el-tag
            v-for="tid in row.tag_ids"
            :key="tid"
            size="small"
            :style="tagMap[tid]?.color ? { backgroundColor: tagMap[tid].color + '22', borderColor: tagMap[tid].color, color: tagMap[tid].color } : {}"
            class="file-tag"
          >
            {{ tagMap[tid]?.name || tid }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <span class="picker-tip" v-if="selectedFile">
        已选：{{ selectedFile.name }}
      </span>
      <span class="picker-tip" v-else>请选择一个文件</span>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedFile" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Search, Upload, Picture, Document, VideoPlay, Files as FilesIcon,
} from '@element-plus/icons-vue'
import { useAppStore } from '@/stores'
import { fileApi, fileCategoryApi, fileTagApi, type TestFile, type FileCategory, type FileTag } from '@/api'

const props = defineProps<{
  modelValue: boolean
  /** 当前已选中的 file_id，用于回显 */
  modelFileId?: number | string | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'select', file: TestFile): void
}>()

const store = useAppStore()
const projectId = computed(() => store.currentProjectId)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ===== 数据 =====
const files = ref<TestFile[]>([])
const categories = ref<FileCategory[]>([])
const tags = ref<FileTag[]>([])
const loading = ref(false)
const keyword = ref('')
const filterCategory = ref<number | undefined>(undefined)
const filterTag = ref<number | undefined>(undefined)
const selectedId = ref<number | null>(null)

const tagMap = computed(() => {
  const m: Record<number, FileTag> = {}
  tags.value.forEach((t) => (m[t.id] = t))
  return m
})

const selectedFile = computed(() => files.value.find((f) => f.id === selectedId.value) || null)

// ===== 加载 =====
async function loadFiles() {
  if (!projectId.value) return
  loading.value = true
  try {
    files.value = await fileApi.list(projectId.value, {
      category_id: filterCategory.value,
      tag_id: filterTag.value,
      keyword: keyword.value,
    })
  } catch (e: any) {
    ElMessage.error(e.message || '加载文件失败')
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  if (!projectId.value) return
  try {
    categories.value = await fileCategoryApi.list(projectId.value)
  } catch { /* ignore */ }
}

async function loadTags() {
  if (!projectId.value) return
  try {
    tags.value = await fileTagApi.list(projectId.value)
  } catch { /* ignore */ }
}

// ===== 选择 =====
function onCurrentChange(row: TestFile | null) {
  if (row) selectedId.value = row.id
}

function onRowDblClick(row: TestFile) {
  selectedId.value = row.id
  confirm()
}

function confirm() {
  if (!selectedFile.value) return
  emit('select', selectedFile.value)
  visible.value = false
}

function onClose() {
  selectedId.value = null
  keyword.value = ''
  filterCategory.value = undefined
  filterTag.value = undefined
}

// ===== 上传 =====
async function handleUpload(file: File) {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return false
  }
  try {
    const obj = await fileApi.upload(file, projectId.value, filterCategory.value ?? null)
    ElMessage.success(`${file.name} 上传成功`)
    await loadFiles()
    // 自动选中新上传的文件
    selectedId.value = obj.id
  } catch (e: any) {
    ElMessage.error(e.message || '上传失败')
  }
  return false
}

// ===== 工具函数 =====
function formatSize(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function fileIcon(contentType: string) {
  if (contentType.startsWith('image/')) return Picture
  if (contentType === 'application/pdf') return Document
  if (contentType.startsWith('video/')) return VideoPlay
  return FilesIcon
}

function fileIconColor(contentType: string): string {
  if (contentType.startsWith('image/')) return '#67c23a'
  if (contentType === 'application/pdf') return '#f56c6c'
  if (contentType.startsWith('video/')) return '#e6a23c'
  return '#909399'
}

// 简化过长的 MIME 类型显示：如 application/vnd.openxmlformats-officedocument.spreadsheetml.sheet → xlsx
function formatContentType(ct: string): string {
  if (!ct) return '未知'
  const SHORT: Record<string, string> = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/vnd.ms-excel': 'xls',
    'application/msword': 'doc',
    'application/vnd.ms-powerpoint': 'ppt',
    'application/vnd.rar': 'rar',
    'application/x-rar-compressed': 'rar',
    'application/x-7z-compressed': '7z',
    'application/gzip': 'gz',
    'application/x-tar': 'tar',
    'application/zip': 'zip',
    'text/plain': 'txt',
    'text/csv': 'csv',
    'text/html': 'html',
    'text/xml': 'xml',
    'application/json': 'json',
    'application/xml': 'xml',
    'application/octet-stream': 'bin',
  }
  if (SHORT[ct]) return SHORT[ct]
  if (ct.length > 16) return ct.slice(0, 14) + '...'
  return ct
}

// ===== 弹窗打开时加载数据 + 回显选中 =====
watch(visible, (v) => {
  if (v) {
    loadFiles()
    loadCategories()
    loadTags()
    // 回显已选 file_id
    if (props.modelFileId != null && props.modelFileId !== '') {
      selectedId.value = Number(props.modelFileId)
    }
  }
})
</script>

<style scoped>
.picker-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.picker-upload {
  margin-left: auto;
}
.picker-radio :deep(.el-radio__label) {
  display: none;
}
.file-icon {
  margin-right: 6px;
  vertical-align: middle;
}
.file-tag {
  margin-right: 4px;
}
.picker-tip {
  flex: 1;
  font-size: 13px;
  color: var(--app-text-muted);
  margin-right: auto;
}
</style>

<style>
.file-picker-dialog .el-dialog__footer {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
