<template>
  <div class="file-center">
    <!-- 左侧：分类树 + 标签云 -->
    <div class="file-sidebar">
      <div class="sidebar-section">
        <div class="sidebar-header">
          <span class="sidebar-title">分类</span>
          <el-button link type="primary" size="small" @click="openCategoryDialog(null)">
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
        <el-tree
          :data="categoryTree"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :expand-on-click-node="false"
          :current-node-key="filter.category_id === null ? -1 : filter.category_id"
          @node-click="onCategoryClick"
          empty-text="暂无分类"
        >
          <template #default="{ node, data }">
            <span class="tree-node">
              <span class="tree-node-label">{{ node.label }}</span>
              <span class="tree-node-actions">
                <el-icon @click.stop="openCategoryDialog(data)"><Edit /></el-icon>
                <el-icon @click.stop="confirmDeleteCategory(data)"><Delete /></el-icon>
              </span>
            </span>
          </template>
        </el-tree>
        <!-- 全部文件 + 未分类 快捷项 -->
        <div class="quick-filter" :class="{ active: filter.category_id === undefined }" @click="filter.category_id = undefined; loadFiles()">
          <el-icon><Files /></el-icon>
          <span>全部文件</span>
          <span class="count">{{ totalFiles }}</span>
        </div>
        <div class="quick-filter" :class="{ active: filter.category_id === null }" @click="filter.category_id = null; loadFiles()">
          <el-icon><FolderOpened /></el-icon>
          <span>未分类</span>
        </div>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-header">
          <span class="sidebar-title">标签</span>
          <el-button link type="primary" size="small" @click="tagDialog.visible = true; tagDialog.editing = null">
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
        <div class="tag-cloud">
          <span
            v-for="tag in tags"
            :key="tag.id"
            class="tag-chip"
            :class="{ active: filter.tag_id === tag.id }"
            :style="tag.color ? { backgroundColor: tag.color + '22', borderColor: tag.color, color: tag.color } : {}"
            @click="toggleTagFilter(tag)"
          >
            {{ tag.name }}
            <el-icon class="tag-edit" @click.stop="openTagDialog(tag)"><Edit /></el-icon>
          </span>
          <span v-if="!tags.length" class="empty-tip">暂无标签</span>
        </div>
      </div>
    </div>

    <!-- 右侧：文件列表 -->
    <div class="file-main">
      <div class="file-toolbar">
        <div class="toolbar-left">
          <el-upload
            :show-file-list="false"
            :before-upload="handleUpload"
            :http-request="() => {}"
          >
            <el-button type="primary" :icon="Upload">上传文件</el-button>
          </el-upload>
          <el-input
            v-model="filter.keyword"
            placeholder="按名称搜索"
            clearable
            style="width: 240px"
            @keyup.enter="loadFiles"
            @clear="loadFiles"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </div>
        <div class="toolbar-right">
          <span class="muted">共 {{ totalFiles }} 个文件</span>
        </div>
      </div>

      <el-table v-loading="loading" :data="files" stripe row-key="id" :row-style="{ height: '48px' }" :cell-style="{ padding: '4px 0' }">
        <el-table-column prop="name" label="文件名" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-icon class="file-icon" :style="{ color: fileIconColor(row.content_type) }">
              <component :is="fileIcon(row.content_type)" />
            </el-icon>
            <span>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ formatContentType(row.content_type) }}</template>
        </el-table-column>
        <el-table-column label="标签" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="tid in row.tag_ids"
              :key="tid"
              size="small"
              :color="tagMap[tid]?.color"
              :style="tagMap[tid]?.color ? { backgroundColor: tagMap[tid].color + '22', borderColor: tagMap[tid].color, color: tagMap[tid].color } : {}"
              class="file-tag"
            >
              {{ tagMap[tid]?.name || tid }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" label="上传人" width="100" />
        <el-table-column prop="created_at" label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="previewFile(row)" v-if="isPreviewable(row.content_type)">预览</el-button>
            <el-button link type="primary" size="small" @click="downloadFile(row)">下载</el-button>
            <el-button link type="primary" size="small" @click="openRenameDialog(row)">重命名</el-button>
            <el-button link type="danger" size="small" @click="confirmDeleteFile(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewFileObj?.name" width="80%" destroy-on-close @close="closePreview">
      <div class="preview-container" v-loading="previewLoading">
        <img v-if="previewType === 'image' && previewUrl" :src="previewUrl" class="preview-img" />
        <iframe v-else-if="previewType === 'pdf' && previewUrl" :src="previewUrl" class="preview-iframe"></iframe>
      </div>
    </el-dialog>

    <!-- 重命名/改分类/改标签 弹窗 -->
    <el-dialog v-model="renameVisible" title="编辑文件" width="480px">
      <el-form v-if="editingFile" label-width="80px">
        <el-form-item label="文件名">
          <el-input v-model="editingFile.name" />
        </el-form-item>
        <el-form-item label="分类">
          <el-tree-select
            v-model="editingFile.category_id"
            :data="categoryTreeForSelect"
            :props="{ label: 'name', children: 'children', value: 'id' }"
            check-strictly
            clearable
            placeholder="未分类"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="editingFile.tag_ids" multiple filterable allow-create default-first-option placeholder="选择标签" style="width: 100%">
            <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRename">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分类编辑弹窗 -->
    <el-dialog v-model="categoryDialog.visible" :title="categoryDialog.editing ? '编辑分类' : '新建分类'" width="400px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="categoryDialog.name" placeholder="如 身份证/合同/发票" />
        </el-form-item>
        <el-form-item label="父分类">
          <el-tree-select
            v-model="categoryDialog.parent_id"
            :data="categoryTreeForSelect"
            :props="{ label: 'name', children: 'children', value: 'id' }"
            check-strictly
            clearable
            placeholder="顶层分类"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="categoryDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveCategory">保存</el-button>
      </template>
    </el-dialog>

    <!-- 标签编辑弹窗 -->
    <el-dialog v-model="tagDialog.visible" :title="tagDialog.editing ? '编辑标签' : '新建标签'" width="400px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="tagDialog.name" placeholder="如 冒烟/回归/生产" />
        </el-form-item>
        <el-form-item label="颜色">
          <el-color-picker v-model="tagDialog.color" />
          <el-button link @click="tagDialog.color = ''">清除</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tagDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveTag">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Edit, Delete, Files, FolderOpened, Search, Upload,
  Picture, Document, VideoPlay, Files as FilesIcon,
} from '@element-plus/icons-vue'
import { useAppStore } from '@/stores'
import { fileApi, fileCategoryApi, fileTagApi, type TestFile, type FileCategory, type FileTag } from '@/api'

const store = useAppStore()
const projectId = computed(() => store.currentProjectId)

// ===== 文件列表 =====
const files = ref<TestFile[]>([])
const loading = ref(false)
const filter = ref<{ category_id?: number | null; tag_id?: number; keyword?: string }>({})

const totalFiles = computed(() => files.value.length)

async function loadFiles() {
  if (!projectId.value) return
  loading.value = true
  try {
    files.value = await fileApi.list(projectId.value, {
      category_id: filter.value.category_id,
      tag_id: filter.value.tag_id,
      keyword: filter.value.keyword,
    })
  } catch (e: any) {
    ElMessage.error(e.message || '加载文件失败')
  } finally {
    loading.value = false
  }
}

// ===== 分类树 =====
const categories = ref<FileCategory[]>([])
const categoryTree = computed(() => buildTree(categories.value))

const categoryTreeForSelect = computed(() => buildTree(categories.value))

function buildTree(list: FileCategory[]): any[] {
  const map = new Map<number, any>()
  const roots: any[] = []
  list.forEach((c) => map.set(c.id, { ...c, children: [] }))
  list.forEach((c) => {
    const node = map.get(c.id)!
    if (c.parent_id && map.has(c.parent_id)) {
      map.get(c.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  })
  return roots
}

async function loadCategories() {
  if (!projectId.value) return
  categories.value = await fileCategoryApi.list(projectId.value)
}

function onCategoryClick(data: any) {
  filter.value.category_id = data.id
  loadFiles()
}

const categoryDialog = ref<{ visible: boolean; editing: FileCategory | null; name: string; parent_id: number | null }>({
  visible: false, editing: null, name: '', parent_id: null,
})

function openCategoryDialog(cat: FileCategory | null) {
  categoryDialog.value.editing = cat
  categoryDialog.value.name = cat?.name || ''
  categoryDialog.value.parent_id = cat?.parent_id ?? null
  categoryDialog.value.visible = true
}

async function saveCategory() {
  if (!categoryDialog.value.name.trim()) {
    ElMessage.warning('请输入分类名称')
    return
  }
  try {
    if (categoryDialog.value.editing) {
      await fileCategoryApi.update(categoryDialog.value.editing.id, {
        name: categoryDialog.value.name,
        parent_id: categoryDialog.value.parent_id,
      })
      ElMessage.success('已更新')
    } else {
      await fileCategoryApi.create({
        project_id: projectId.value!,
        name: categoryDialog.value.name,
        parent_id: categoryDialog.value.parent_id,
      })
      ElMessage.success('已创建')
    }
    categoryDialog.value.visible = false
    await loadCategories()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function confirmDeleteCategory(cat: FileCategory) {
  try {
    await ElMessageBox.confirm(`确定删除分类「${cat.name}」？子分类和文件会一并删除`, '提示', { type: 'warning' })
    await fileCategoryApi.remove(cat.id)
    ElMessage.success('已删除')
    if (filter.value.category_id === cat.id) filter.value.category_id = undefined
    await loadCategories()
    await loadFiles()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

// ===== 标签 =====
const tags = ref<FileTag[]>([])
const tagMap = computed(() => {
  const m: Record<number, FileTag> = {}
  tags.value.forEach((t) => (m[t.id] = t))
  return m
})

async function loadTags() {
  if (!projectId.value) return
  tags.value = await fileTagApi.list(projectId.value)
}

function toggleTagFilter(tag: FileTag) {
  filter.value.tag_id = filter.value.tag_id === tag.id ? undefined : tag.id
  loadFiles()
}

const tagDialog = ref<{ visible: boolean; editing: FileTag | null; name: string; color: string }>({
  visible: false, editing: null, name: '', color: '',
})

function openTagDialog(tag: FileTag) {
  tagDialog.value.editing = tag
  tagDialog.value.name = tag?.name || ''
  tagDialog.value.color = tag?.color || ''
  tagDialog.value.visible = true
}

async function saveTag() {
  if (!tagDialog.value.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  try {
    if (tagDialog.value.editing) {
      await fileTagApi.update(tagDialog.value.editing.id, {
        name: tagDialog.value.name,
        color: tagDialog.value.color,
      })
      ElMessage.success('已更新')
    } else {
      await fileTagApi.create({
        project_id: projectId.value!,
        name: tagDialog.value.name,
        color: tagDialog.value.color,
      })
      ElMessage.success('已创建')
    }
    tagDialog.value.visible = false
    await loadTags()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

// ===== 上传 =====
async function handleUpload(file: File) {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return false
  }
  try {
    await fileApi.upload(file, projectId.value, filter.value.category_id ?? null)
    ElMessage.success(`${file.name} 上传成功`)
    await loadFiles()
  } catch (e: any) {
    ElMessage.error(e.message || '上传失败')
  }
  return false // 阻止 el-upload 默认上传
}

// ===== 预览/下载 =====
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewFileObj = ref<TestFile | null>(null)
const previewUrl = ref<string>('')
const previewType = ref<'image' | 'pdf' | ''>('')

const IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml', 'image/bmp']

function isPreviewable(contentType: string): boolean {
  return IMAGE_TYPES.includes(contentType) || contentType === 'application/pdf'
}

async function previewFile(file: TestFile) {
  if (!isPreviewable(file.content_type)) {
    ElMessage.warning('该类型不支持预览')
    return
  }
  previewFileObj.value = file
  previewVisible.value = true
  previewLoading.value = true
  try {
    const { url } = await fileApi.fetchBlob(file.id, true)
    previewUrl.value = url
    previewType.value = IMAGE_TYPES.includes(file.content_type) ? 'image' : 'pdf'
  } catch (e: any) {
    ElMessage.error(e.message || '预览失败')
    previewVisible.value = false
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
  previewType.value = ''
  previewFileObj.value = null
}

async function downloadFile(file: TestFile) {
  try {
    const { url } = await fileApi.fetchBlob(file.id, false)
    const a = document.createElement('a')
    a.href = url
    a.download = file.name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e: any) {
    ElMessage.error(e.message || '下载失败')
  }
}

// ===== 重命名/编辑 =====
const renameVisible = ref(false)
const editingFile = ref<TestFile | null>(null)

function openRenameDialog(file: TestFile) {
  editingFile.value = { ...file, tag_ids: [...file.tag_ids] }
  renameVisible.value = true
}

async function saveRename() {
  if (!editingFile.value) return
  try {
    await fileApi.update(editingFile.value.id, {
      name: editingFile.value.name,
      category_id: editingFile.value.category_id ?? null,
      tag_ids: editingFile.value.tag_ids,
    })
    ElMessage.success('已保存')
    renameVisible.value = false
    await loadFiles()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function confirmDeleteFile(file: TestFile) {
  try {
    await ElMessageBox.confirm(`确定删除文件「${file.name}」？引用计数 -1，归零时删除物理文件`, '提示', { type: 'warning' })
    await fileApi.remove(file.id)
    ElMessage.success('已删除')
    await loadFiles()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

// ===== 工具函数 =====
function formatSize(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatTime(t?: string): string {
  if (!t) return ''
  return t.replace('T', ' ').slice(0, 19)
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
  // 截断过长的类型字符串
  if (ct.length > 18) return ct.slice(0, 16) + '...'
  return ct
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

// ===== 监听项目变化 =====
watch(projectId, () => {
  filter.value = {}
  loadFiles()
  loadCategories()
  loadTags()
})

onMounted(() => {
  loadFiles()
  loadCategories()
  loadTags()
})
</script>

<style scoped>
.file-center {
  display: flex;
  gap: 16px;
  height: 100%;
  min-height: 0;
}
.file-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-muted);
}
.tree-node {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-right: 8px;
}
.tree-node-actions {
  display: none;
  gap: 4px;
}
.tree-node:hover .tree-node-actions {
  display: inline-flex;
}
.tree-node-actions .el-icon {
  font-size: 12px;
  cursor: pointer;
  color: var(--app-text-muted);
}
.tree-node-actions .el-icon:hover {
  color: var(--el-color-primary);
}
.quick-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: var(--app-text);
}
.quick-filter:hover {
  background: var(--el-fill-color-light);
}
.quick-filter.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.quick-filter .count {
  margin-left: auto;
  font-size: 11px;
  color: var(--app-text-muted);
}
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid var(--el-border-color);
  color: var(--app-text);
  background: var(--el-fill-color-light);
}
.tag-chip.active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.tag-edit {
  font-size: 10px;
  opacity: 0;
  transition: opacity 0.2s;
}
.tag-chip:hover .tag-edit {
  opacity: 0.8;
}
.empty-tip {
  color: var(--app-text-muted);
  font-size: 12px;
}

.file-main {
  flex: 1;
  min-width: 0;
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}
.file-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.toolbar-left {
  display: flex;
  gap: 12px;
  align-items: center;
}
.muted {
  color: var(--app-text-muted);
  font-size: 13px;
}
.file-icon {
  margin-right: 6px;
  vertical-align: middle;
}
.file-tag {
  margin-right: 4px;
}

.preview-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}
.preview-img {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
}
.preview-iframe {
  width: 100%;
  height: 70vh;
  border: none;
}
</style>
