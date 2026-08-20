<template>
  <div class="page">
    <div class="page-head">
      <el-button type="primary" @click="openCreate">+ 新增字典</el-button>
      <el-button type="success" @click="openBatch">批量导入</el-button>
      <span style="flex: 1" />
      <el-input
        v-model="keyword"
        style="width: 240px"
        placeholder="搜索字段名 / 中文名"
        clearable
        @input="onSearchInput"
        @clear="onSearchInput"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
    </div>
    <div class="table-wrap">
      <el-card shadow="never" class="card">
        <el-skeleton v-if="loading" :rows="5" animated class="skeleton-wrap" />
        <el-table v-else :data="pagedList" stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="key" label="字段名（英文）" min-width="200" show-overflow-tooltip />
          <el-table-column prop="label" label="中文名" min-width="180" show-overflow-tooltip />
          <el-table-column label="创建人" width="100" align="center">
            <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="更新人" width="100" align="center">
            <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" min-width="170" show-overflow-tooltip />
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="onEdit(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-wrap">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="list.length"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            background
          />
        </div>
      </el-card>
    </div>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑字典' : '新增字典'" width="460px" align-center>
      <el-form :model="form" label-width="80px">
        <el-form-item label="字段名" required>
          <el-input v-model="form.key" placeholder="如 order_id / bl_no" />
        </el-form-item>
        <el-form-item label="中文名" required>
          <el-input v-model="form.label" placeholder="如 订单ID / 提单号" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入弹窗 -->
    <el-dialog v-model="batchVisible" title="批量导入字典" width="600px" align-center>
      <el-alert type="info" :closable="false" style="margin-bottom: 12px">
        <div class="batch-guide">
          <div class="guide-title">导入格式说明</div>
          <div class="guide-line">每行一条，格式：<code>字段名=中文名</code>（支持 <code>=</code>、Tab、逗号分隔）</div>
          <div class="guide-line">同名字段将更新中文含义，新字段会新增</div>
          <div class="guide-line">仅作用于当前项目，不影响其他项目</div>
          <div class="guide-example">
            <div>order_id=订单ID</div>
            <div>bl_no=提单号</div>
            <div>container_no=集装箱号</div>
            <div>put_amount=投放金额</div>
          </div>
        </div>
      </el-alert>
      <el-input
        v-model="batchText"
        type="textarea"
        :rows="10"
        placeholder="order_id=订单ID&#10;bl_no=提单号&#10;container_no=集装箱号"
      />
      <div v-if="batchPreview.count > 0" style="margin-top: 8px; font-size: 12px; color: var(--app-text-muted)">
        已解析 {{ batchPreview.count }} 条，新增 {{ batchPreview.newCount }} 条，更新 {{ batchPreview.updateCount }} 条
      </div>
      <template #footer>
        <el-button @click="batchVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onBatchSave">导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { dictApi, type FieldDictionary } from '@/api'
import { useAppStore } from '@/stores'
import { debounce } from '@/utils/ui'

const store = useAppStore()
const list = ref<FieldDictionary[]>([])
const loading = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(10)

const pagedList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return list.value.slice(start, start + pageSize.value)
})

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  try {
    list.value = await dictApi.list(store.currentProjectId, keyword.value || undefined)
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// 搜索输入：回第 1 页 + 300ms 防抖（避免每敲一键发一次请求）
const onSearchInput = debounce(() => {
  page.value = 1
  load()
}, 300)

// ===== 新增/编辑 =====
const dialogVisible = ref(false)
const editing = ref<FieldDictionary | null>(null)
const form = ref({ key: '', label: '' })
const saving = ref(false)

function openCreate() {
  editing.value = null
  form.value = { key: '', label: '' }
  dialogVisible.value = true
}

function onEdit(row: FieldDictionary) {
  editing.value = row
  form.value = { key: row.key, label: row.label }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.value.key.trim() || !form.value.label.trim()) {
    ElMessage.warning('字段名和中文名都不能为空')
    return
  }
  if (!store.currentProjectId) return
  saving.value = true
  try {
    if (editing.value) {
      await dictApi.update(editing.value.id, { key: form.value.key.trim(), label: form.value.label.trim() })
      ElMessage.success('已更新')
    } else {
      await dictApi.create({ project_id: store.currentProjectId, key: form.value.key.trim(), label: form.value.label.trim() })
      ElMessage.success('已新增')
    }
    dialogVisible.value = false
    await load()
    await store.loadFieldDict()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onRemove(row: FieldDictionary) {
  try {
    await ElMessageBox.confirm(`确认删除字段「${row.key}」的字典映射？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await dictApi.remove(row.id)
    ElMessage.success('已删除')
    await load()
    await store.loadFieldDict()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

// ===== 批量导入 =====
const batchVisible = ref(false)
const batchText = ref('')

const batchPreview = computed(() => {
  const lines = batchText.value.split('\n').map(l => l.trim()).filter(Boolean)
  const existingKeys = new Set(list.value.map(d => d.key))
  let newCount = 0
  let updateCount = 0
  for (const line of lines) {
    const parts = line.split(/[=\t,]/).map(s => s.trim())
    if (parts.length >= 2 && parts[0]) {
      if (existingKeys.has(parts[0])) updateCount++
      else newCount++
    }
  }
  return { count: newCount + updateCount, newCount, updateCount }
})

function openBatch() {
  batchText.value = ''
  batchVisible.value = true
}

async function onBatchSave() {
  const lines = batchText.value.split('\n').map(l => l.trim()).filter(Boolean)
  const items: { key: string; label: string }[] = []
  for (const line of lines) {
    const parts = line.split(/[=\t,]/).map(s => s.trim())
    if (parts.length >= 2 && parts[0] && parts[1]) {
      items.push({ key: parts[0], label: parts[1] })
    }
  }
  if (!items.length) {
    ElMessage.warning('未解析到有效数据，请检查格式')
    return
  }
  if (!store.currentProjectId) return
  saving.value = true
  try {
    const res = await dictApi.batch(store.currentProjectId, items)
    ElMessage.success(res.message)
    batchVisible.value = false
    await load()
    await store.loadFieldDict()
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
})

// 切换项目时重新加载，确保字典数据按项目隔离
watch(() => store.currentProjectId, (n, old) => {
  if (n !== old) {
    page.value = 1
    keyword.value = ''
    load()
  }
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.page-head {
  display: flex;
  align-items: center;
  padding: 0 0 16px;
  flex-shrink: 0;
}
.table-wrap {
  flex: 1;
  min-height: 0;
}
.card {
  height: 100%;
  overflow: auto;
}
.skeleton-wrap {
  padding: 20px;
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.batch-guide .guide-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.batch-guide .guide-line {
  line-height: 1.8;
  font-size: 13px;
}
.batch-guide .guide-example {
  margin-top: 6px;
  padding: 8px 10px;
  /* 用已定义的主题 token（原 --app-bg-muted/--app-text-secondary 未定义，暗色下永久浅色） */
  background: var(--app-hover);
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: var(--app-text-muted);
}
</style>
