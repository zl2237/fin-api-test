<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import EmptyState from './EmptyState.vue'
import { collectTreeUpdates, type GroupTreeNode } from '../composables/useGroupedTable'

/**
 * 分组管理弹窗（多级：el-tree 拖拽调整层级与顺序）。
 * 接口分组 / 用例分组共用：CRUD API 经 props.api 注入（apiGroupApi / caseGroupApi），
 * 任何成功变更后 emit('changed', kind)，由父视图重载分组（kind='delete' 时还需重载条目）。
 */

/** 分组 CRUD 适配器：签名与 apiGroupApi / caseGroupApi 一致 */
export interface GroupCrudApi {
  create: (data: { project_id: number; parent_id?: number | null; name: string }) => Promise<unknown>
  update: (id: number, data: { name?: string; parent_id?: number | null; sort_order?: number }) => Promise<unknown>
  remove: (id: number) => Promise<unknown>
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  /** 弹窗标题（如「接口分组管理」） */
  title: string
  /** useGroupTree.treeSelectData（分组树，仅 label/children 结构） */
  treeData: GroupTreeNode[]
  /** 分组 CRUD API（apiGroupApi / caseGroupApi） */
  api: GroupCrudApi
  projectId: number | null
  /** 删除确认文案中的资源词（接口 / 用例） */
  itemWord?: string
}>(), { itemWord: '条目' })

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'changed', kind: 'add' | 'rename' | 'delete' | 'reorder'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const newGroupName = ref('')
const newGroupParentId = ref<number | null>(null)
// el-tree 可变数据（管理弹窗拖拽用），treeData 变化（分组重载）或弹窗打开时重建
const groupTreeNodes = ref<GroupTreeNode[]>([])
const treeProps = { label: 'label', children: 'children' }

function rebuildNodes() {
  groupTreeNodes.value = JSON.parse(JSON.stringify(props.treeData))
}

watch([() => props.modelValue, () => props.treeData], ([open]) => {
  if (open) rebuildNodes()
})

async function onAddGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await props.api.create({
      project_id: props.projectId!,
      parent_id: newGroupParentId.value,
      name: newGroupName.value.trim(),
    })
    newGroupName.value = ''
    newGroupParentId.value = null
    emit('changed', 'add')
    ElMessage.success('已添加')
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  }
}

async function onRenameGroup(data: GroupTreeNode) {
  try {
    const { value } = await ElMessageBox.prompt('分组名称', '重命名', { inputValue: data.label })
    if (value && value !== data.label) {
      await props.api.update(data.id, { name: value })
      emit('changed', 'rename')
      ElMessage.success('已重命名')
    }
  } catch {
    // cancel
  }
}

async function onDeleteGroup(data: GroupTreeNode) {
  try {
    await ElMessageBox.confirm(
      `确认删除分组「${data.label}」？\n注意：含子分组或${props.itemWord}时将阻止删除，请先处理。`,
      '提示',
      { type: 'warning' },
    )
    await props.api.remove(data.id)
    emit('changed', 'delete')
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

/** el-tree 拖拽落点：持久化 parent_id + sort_order */
async function onTreeNodeDrop() {
  // el-tree 拖拽后已就地更新 groupTreeNodes，收集树平面更新载荷
  const updates = collectTreeUpdates(groupTreeNodes.value)
  try {
    await Promise.all(updates.map((it) => props.api.update(it.id, { parent_id: it.parent_id, sort_order: it.sort_order })))
    ElMessage.success('分组层级与顺序已保存')
    emit('changed', 'reorder')
  } catch (e: any) {
    ElMessage.error(e.message || '分组排序保存失败')
    // 失败也重载：把拖乱的树恢复为服务端状态
    emit('changed', 'reorder')
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="title" width="620px" align-center class="group-manage-dialog" :close-on-click-modal="false">
    <div class="group-dialog-body">
      <div class="group-add">
        <el-input
          v-model="newGroupName"
          placeholder="新分组名称"
          style="flex: 1"
          @keyup.enter="onAddGroup"
        />
        <el-tree-select
          v-model="newGroupParentId"
          :data="treeData"
          node-key="id"
          :props="treeProps"
          placeholder="父分组（留空为顶层）"
          clearable
          check-strictly
          style="width: 220px"
        />
        <el-button type="primary" @click="onAddGroup">添加</el-button>
      </div>
      <div class="group-drag-tip">拖拽节点可调整层级与顺序，松开自动保存</div>
      <div class="group-tree-scroll">
        <el-tree
          :data="groupTreeNodes"
          node-key="id"
          :props="treeProps"
          :expand-on-click-node="false"
          default-expand-all
          draggable
          @node-drop="onTreeNodeDrop"
        >
          <template #default="{ data }">
            <div class="group-tree-row">
              <span class="group-tree-name">{{ data.label }}</span>
              <div class="group-tree-actions">
                <el-button link type="primary" size="small" @click.stop="onRenameGroup(data)">重命名</el-button>
                <el-button link type="danger" size="small" @click.stop="onDeleteGroup(data)">删除</el-button>
              </div>
            </div>
          </template>
        </el-tree>
        <EmptyState v-if="!groupTreeNodes.length" description="暂无分组" :image-size="60" />
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
/* 原 ApiManage/CaseList 逐字重复的 scoped 样式（el-dialog 外壳样式在全局 style.css 的 .group-manage-dialog） */
.group-dialog-body {
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  height: 100%;
}
.group-add {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
.group-tree-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 6px;
}
.group-tree-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}
.group-tree-name {
  font-size: 14px;
  color: var(--app-text);
}
.group-tree-actions {
  display: flex;
  gap: 4px;
}
.group-drag-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  margin: 12px 0 8px;
  flex-shrink: 0;
}
</style>
