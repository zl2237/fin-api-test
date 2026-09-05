<template>
  <div class="file-center">
    <!-- 顶部工具栏（与接口/用例页同构：标题+主操作在左，搜索/计数在右） -->
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">文件中心</span>
        <el-upload
          :show-file-list="false"
          :before-upload="handleUpload"
          :http-request="() => {}"
          multiple
        >
          <el-button type="primary" :icon="Upload" :loading="pendingUploads > 0">
            {{ pendingUploads > 0 ? `上传中（${pendingUploads}）` : '上传文件' }}
          </el-button>
        </el-upload>
      </div>
      <div class="head-right">
        <el-input
          v-model="filter.keyword"
          placeholder="搜索文件名"
          clearable
          style="width: 220px"
          @input="onKeywordInput"
          @clear="onKeywordInput"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <!-- 显示当前过滤结果数（全量计数只在左侧树），避免「筛后 5 行却写共 120 个」的误导 -->
        <span class="muted">共 {{ files.length }} 个文件</span>
      </div>
    </div>

    <!-- 左侧：分类导航树（单选互斥，文件夹隐喻） -->
    <div class="file-body">
      <div class="file-sidebar">
        <div class="sidebar-section">
          <div class="sidebar-header">
            <span class="sidebar-title">分类</span>
            <el-button link type="primary" size="small" @click="openCategoryDialog(null)">
              <el-icon><Plus /></el-icon>
            </el-button>
          </div>
          <!-- 固定导航项：全部文件 / 未分类（树顶常驻，与分类同级单选） -->
          <div class="quick-filter" :class="{ active: filter.category_id === undefined }" @click="setCategoryFilter(undefined)">
            <el-icon><Files /></el-icon>
            <span>全部文件</span>
            <span class="count">{{ totalFiles }}</span>
          </div>
          <div class="quick-filter" :class="{ active: filter.category_id === 0 }" @click="setCategoryFilter(0)">
            <el-icon><FolderOpened /></el-icon>
            <span>未分类</span>
            <span class="count">{{ uncategorizedCount }}</span>
          </div>
          <el-tree
            :data="categoryTree"
            node-key="id"
            :props="{ label: 'label', children: 'children' }"
            :expand-on-click-node="false"
            :current-node-key="filter.category_id === null ? -1 : filter.category_id"
            @node-click="onCategoryClick"
            empty-text="暂无分类"
          >
            <template #default="{ node, data }">
              <span class="tree-node">
                <span class="tree-node-label">{{ node.label }}</span>
                <span class="tree-node-count">{{ countFilesInCategory(data.id) }}</span>
                <span class="tree-node-actions">
                  <el-icon @click.stop="openCategoryDialog(data)"><Edit /></el-icon>
                  <el-icon @click.stop="confirmDeleteCategory(data)"><Delete /></el-icon>
                </span>
              </span>
            </template>
          </el-tree>
        </div>
      </div>

      <!-- 右侧：文件列表（支持拖拽文件到此处上传） -->
      <div
        class="file-main"
        :class="{ 'drag-active': dragOver }"
        @dragover.prevent="dragOver = true"
        @dragleave="onDragLeave"
        @drop.prevent="onDrop"
      >
        <div v-if="dragOver" class="drop-overlay">
          <el-icon :size="40"><Upload /></el-icon>
          <span>松开鼠标，上传到{{ filter.category_id ? '当前分类' : '文件中心' }}</span>
        </div>
        <el-table v-loading="loading" :data="pagedFiles" stripe size="small" row-key="id" @sort-change="onSortChange">
          <template #empty>
            <EmptyState description="暂无文件" :image-size="80">
              <span class="empty-hint">点击左上角「上传文件」，或直接把文件拖到这里</span>
            </EmptyState>
          </template>
          <el-table-column prop="id" label="ID" width="70" sortable="custom" />
          <el-table-column prop="name" label="文件名" min-width="220" show-overflow-tooltip sortable="custom">
            <template #default="{ row }">
              <el-icon class="file-icon" :style="{ color: fileIconColor(row.content_type) }">
                <component :is="fileIcon(row.content_type)" />
              </el-icon>
              <span>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="size" label="大小" width="100" sortable="custom">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="类型" width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ formatContentType(row.content_type) }}</template>
          </el-table-column>
          <el-table-column prop="created_by_name" label="上传人" width="100" />
          <el-table-column prop="created_at" label="上传时间" width="120" sortable="custom">
            <template #default="{ row }">
              <el-tooltip :content="formatTime(row.created_at)" placement="top" popper-class="app-tip">
                <span>{{ formatRelativeTime(row.created_at) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="previewFile(row)" v-if="isPreviewable(row.content_type)">预览</el-button>
              <el-button link type="primary" size="small" @click="downloadFile(row)">下载</el-button>
              <el-button link type="primary" size="small" @click="openRenameDialog(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="confirmDeleteFile(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="files.length" class="pagination-wrap">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="files.length"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            small
            background
          />
        </div>
      </div>
    </div>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewFileObj?.name" width="80%" align-center destroy-on-close @close="closePreview">
      <div class="preview-container" v-loading="previewLoading">
        <img v-if="previewType === 'image' && previewUrl" :src="previewUrl" width="800" height="600" class="preview-img" :alt="previewFileObj?.name || '文件预览'" />
        <iframe v-else-if="previewType === 'pdf' && previewUrl" :src="previewUrl" class="preview-iframe"></iframe>
      </div>
    </el-dialog>

    <!-- 重命名/改分类 弹窗 -->
    <el-dialog v-model="renameVisible" title="编辑文件" width="420px" align-center :close-on-click-modal="false">
      <el-form v-if="editingFile" label-width="80px">
        <el-form-item label="文件名" required>
          <el-input v-model="editingFile.name" />
        </el-form-item>
        <el-form-item label="分类">
          <el-tree-select
            v-model="editingFile.category_id"
            :data="categoryTreeForSelect"
            :props="{ label: 'label', children: 'children', value: 'id' }"
            check-strictly
            clearable
            placeholder="未分类"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRename">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分类编辑弹窗 -->
    <el-dialog v-model="categoryDialog.visible" :title="categoryDialog.editing ? '编辑分类' : '新建分类'" width="420px" align-center :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="categoryDialog.name" placeholder="如 身份证/合同/发票" />
        </el-form-item>
        <el-form-item label="父分类">
          <el-tree-select
            v-model="categoryDialog.parent_id"
            :data="categoryTreeForSelect"
            :props="{ label: 'label', children: 'children', value: 'id' }"
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
import { buildGroupTree, collectDescendantIds } from '@/composables/useGroupTree'
import { fileApi, fileCategoryApi, type TestFile, type FileCategory } from '@/api'
import { debounce } from '@/utils/ui'
import { formatTime, formatRelativeTime } from '@/utils/format'
import { useClientSort } from '@/composables/useClientSort'
import EmptyState from '@/components/EmptyState.vue'

const store = useAppStore()
const projectId = computed(() => store.currentProjectId)

// ===== 文件列表 =====
const files = ref<TestFile[]>([])
// 全量文件列表（不带过滤条件），用于侧边栏各分类计数
const allFiles = ref<TestFile[]>([])
const loading = ref(false)
const filter = ref<{ category_id?: number | null; keyword?: string }>({})
const page = ref(1)
const pageSize = ref(10)
// 表头排序（sortable="custom"）：先排全量再分页切片，避免只排当前页的假象
const { onSortChange, sorted: sortedFiles } = useClientSort(files, {
  id: f => f.id,
  name: f => f.name,
  size: f => f.size,
  created_at: f => f.created_at ?? '',
}, () => { page.value = 1 })
const pagedFiles = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return sortedFiles.value.slice(start, start + pageSize.value)
})

const totalFiles = computed(() => allFiles.value.length)
const uncategorizedCount = computed(() => allFiles.value.filter(f => f.category_id == null).length)

/** 统计分类下文件数量（含所有子分类，子孙 ID 收集复用公共 collectDescendantIds） */
function countFilesInCategory(catId: number): number {
  const ids = [catId, ...collectDescendantIds(categoryTree.value, catId)]
  return allFiles.value.filter(f => f.category_id != null && ids.includes(f.category_id)).length
}

async function loadFiles() {
  if (!projectId.value) return
  loading.value = true
  try {
    const params = {
      category_id: filter.value.category_id,
      keyword: filter.value.keyword,
    }
    files.value = await fileApi.list(projectId.value, params)
    // 同时加载全量文件用于侧边栏计数（仅在无 keyword 过滤时复用 files 避免重复请求）
    const hasFilter = params.keyword
    if (!hasFilter && params.category_id === undefined) {
      allFiles.value = files.value
    } else {
      allFiles.value = await fileApi.list(projectId.value, {})
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载文件失败')
  } finally {
    loading.value = false
  }
}

// 搜索输入：300ms 防抖统一搜索范式（与 DictManage 一致，替代原「回车才触发」）
const onKeywordInput = debounce(() => {
  page.value = 1
  loadFiles()
}, 300)

// ===== 分类树（树构建/子孙计数复用 useGroupTree 公共纯函数，消除第 4 份平行实现） =====
const categories = ref<FileCategory[]>([])
const categoryTree = computed(() => buildGroupTree(categories.value))

const categoryTreeForSelect = categoryTree

async function loadCategories() {
  if (!projectId.value) return
  categories.value = await fileCategoryApi.list(projectId.value)
}

function onCategoryClick(data: any) {
  setCategoryFilter(data.id)
}

// 分类切换（含「全部/未分类」固定项）：回第 1 页再加载
function setCategoryFilter(categoryId: number | undefined) {
  filter.value.category_id = categoryId
  page.value = 1
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
      ElMessage.success('已保存')
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
    await ElMessageBox.confirm(
      `确认删除分类「${cat.name}」？子分类和文件会一并删除，此操作不可恢复`,
      '删除分类',
      { type: 'warning', confirmButtonText: '删除' },
    )
    await fileCategoryApi.remove(cat.id)
    ElMessage.success('已删除')
    if (filter.value.category_id === cat.id) filter.value.category_id = undefined
    await loadCategories()
    await loadFiles()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

// ===== 上传（多文件 + 拖拽 + 前端预校验；上限与后端 MAX_UPLOAD_SIZE_MB 默认值对齐） =====
const MAX_UPLOAD_MB = 50
const pendingUploads = ref(0)
const dragOver = ref(false)

// el-upload 多选时 before-upload 逐个触发：统一走 uploadOne，计数归零后刷新列表
function handleUpload(file: File) {
  void uploadOne(file)
  return false // 阻止 el-upload 默认上传
}

async function uploadOne(file: File) {
  // 计数含校验不通过的文件：统一在 finally 递减，避免多入口计数错位
  pendingUploads.value++
  try {
    if (!projectId.value) {
      ElMessage.warning('请先选择项目')
      return
    }
    // 前端预校验：空文件 / 超限直接跳过，不发起请求（后端同样校验兜底）
    if (file.size === 0) {
      ElMessage.warning(`「${file.name}」是空文件，已跳过`)
      return
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      ElMessage.error(`「${file.name}」超过 ${MAX_UPLOAD_MB}MB 上限，已跳过`)
      return
    }
    await fileApi.upload(file, projectId.value, filter.value.category_id ?? null)
    ElMessage.success(`${file.name} 上传成功`)
  } catch (e: any) {
    ElMessage.error(e.message || `「${file.name}」上传失败`)
  } finally {
    pendingUploads.value--
    if (pendingUploads.value === 0) await loadFiles()
  }
}

// 拖拽上传：拖入文件区（file-main）即上传，落点在当前分类
function onDrop(e: DragEvent) {
  dragOver.value = false
  const dropped = e.dataTransfer?.files
  if (!dropped?.length) return
  Array.from(dropped).forEach(f => void uploadOne(f))
}

// dragleave 在经过子元素时也会触发：仅当真正离开容器时才取消高亮
function onDragLeave(e: DragEvent) {
  const target = e.currentTarget as Node | null
  if (!target?.contains(e.relatedTarget as Node | null)) dragOver.value = false
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
  editingFile.value = { ...file }
  renameVisible.value = true
}

async function saveRename() {
  if (!editingFile.value) return
  // 必填校验对齐同页分类弹窗（原可保存空文件名）
  if (!editingFile.value.name.trim()) return ElMessage.warning('文件名不能为空')
  try {
    await fileApi.update(editingFile.value.id, {
      name: editingFile.value.name.trim(),
      category_id: editingFile.value.category_id ?? null,
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
    // ref_count 是同内容重复上传的去重计数（同项目同 sha256 再传 +1），非用例引用：
    // 普通文件删除即清物理文件；重复上传过的只在计数归零时才清，避免误删同内容副本
    const consequence = (file.ref_count ?? 1) > 1
      ? `相同内容的文件还有 ${file.ref_count - 1} 份副本，物理文件将保留至副本全部删除`
      : '文件将同时从服务器删除'
    await ElMessageBox.confirm(
      `确认删除「${file.name}」？${consequence}，此操作不可恢复`,
      '删除文件',
      { type: 'warning', confirmButtonText: '删除' },
    )
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
  if (contentType.startsWith('image/')) return 'var(--app-success)'
  if (contentType === 'application/pdf') return 'var(--app-danger)'
  if (contentType.startsWith('video/')) return 'var(--app-warn-text)'
  return 'var(--app-text-muted)'
}

// ===== 监听项目变化 =====
watch(projectId, () => {
  filter.value = {}
  loadFiles()
  loadCategories()
})

onMounted(() => {
  loadFiles()
  loadCategories()
})
</script>

<style scoped>
.file-center {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
/* 左树右列表主体区（与接口/用例页 group-layout 同构） */
.file-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
}
.file-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--app-card);
  border-radius: var(--app-radius);
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
  align-items: center;
  gap: 6px;
  padding-right: 8px;
}
.tree-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tree-node-count {
  font-size: 11px;
  color: var(--app-text-muted);
  background: var(--app-chip-bg);
  border-radius: var(--app-radius-sm);
  padding: 0 6px;
  min-width: 18px;
  text-align: center;
  flex-shrink: 0;
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
  color: var(--app-primary);
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
  background: var(--app-hover);
}
.quick-filter.active {
  background: var(--app-active);
  color: var(--app-primary);
}
.quick-filter .count {
  margin-left: auto;
  font-size: 11px;
  color: var(--app-text-muted);
}

.file-main {
  position: relative;
  flex: 1;
  min-width: 0;
  background: var(--app-card);
  border-radius: var(--app-radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}
/* 拖拽上传反馈：虚线高亮 + 居中遮罩提示 */
.file-main.drag-active {
  outline: 2px dashed var(--app-primary);
  outline-offset: -6px;
}
.drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 10px;
  border-radius: var(--app-radius);
  background: var(--app-active, rgba(64, 158, 255, 0.08));
  color: var(--app-primary);
  font-size: 14px;
  pointer-events: none;
}
.empty-hint {
  font-size: 12px;
  color: var(--app-text-muted);
}
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
}
.muted {
  color: var(--app-text-muted);
  font-size: 13px;
}
.file-icon {
  margin-right: 6px;
  vertical-align: middle;
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
