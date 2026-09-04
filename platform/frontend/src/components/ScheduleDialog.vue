<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { scheduleApi } from '@/api'
import { formatTime, formatRelativeTime } from '@/utils/format'
import type { TestCase, TestSchedule } from '@/api'

/**
 * 定时任务弹窗（用例行内联入口）：该用例的定时配置列表 + 增改表单。
 * 自治子系统——增删改/启停/立即执行走 scheduleApi，任何成功变更后
 * emit('changed') 由父视图 loadSchedules 重载（列表图标标识同源）。
 */
const props = defineProps<{
  modelValue: boolean
  /** 当前弹窗对应的用例 */
  caseItem: TestCase | null
  /** 该用例已配置的定时任务（父视图 schedules 过滤后的单一数据源） */
  schedules: TestSchedule[]
  /** 可选执行环境 */
  envs: { id: number; name: string }[]
  /** 新增表单的环境默认值（当前所选环境，无则第一个） */
  defaultEnvId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'changed'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const scheduleFormVisible = ref(false)
const scheduleEditingId = ref<number | null>(null)
const scheduleSaving = ref(false)
const scheduleForm = ref<{
  env_id: number | null
  schedule_type: 'interval' | 'daily'
  interval_minutes: number | null
  daily_time: string | null
}>({ env_id: null, schedule_type: 'interval', interval_minutes: 30, daily_time: '08:00' })

// 打开时：已有配置则先看列表，无配置直接进新增表单
watch(() => props.modelValue, (open) => {
  if (open) scheduleFormVisible.value = props.schedules.length === 0
})

// 定时配置的人话描述：interval → 每 N 分钟；daily → 每日 HH:MM
function describeSchedule(s: TestSchedule): string {
  if (s.schedule_type === 'interval') return `每 ${s.interval_minutes ?? '?'} 分钟`
  return `每日 ${s.daily_time ?? '?'}`
}

function openScheduleForm() {
  scheduleEditingId.value = null
  scheduleForm.value = {
    env_id: props.defaultEnvId ?? props.envs[0]?.id ?? null,
    schedule_type: 'interval',
    interval_minutes: 30,
    daily_time: '08:00',
  }
  scheduleFormVisible.value = true
}

function onEditSchedule(s: TestSchedule) {
  scheduleEditingId.value = s.id
  scheduleForm.value = {
    env_id: s.env_id,
    schedule_type: s.schedule_type,
    interval_minutes: s.interval_minutes ?? 30,
    daily_time: s.daily_time ?? '08:00',
  }
  scheduleFormVisible.value = true
}

async function onSaveSchedule() {
  if (!props.caseItem) return
  const f = scheduleForm.value
  if (!f.env_id) return ElMessage.warning('请选择执行环境')
  if (f.schedule_type === 'interval' && (!f.interval_minutes || f.interval_minutes < 1)) {
    return ElMessage.warning('间隔分钟数需 ≥ 1')
  }
  if (f.schedule_type === 'daily' && !f.daily_time) return ElMessage.warning('请选择每日执行时刻')
  scheduleSaving.value = true
  try {
    if (scheduleEditingId.value) {
      await scheduleApi.update(scheduleEditingId.value, {
        env_id: f.env_id,
        schedule_type: f.schedule_type,
        interval_minutes: f.schedule_type === 'interval' ? f.interval_minutes : null,
        daily_time: f.schedule_type === 'daily' ? f.daily_time : null,
      })
      ElMessage.success('已保存')
    } else {
      await scheduleApi.create({
        case_id: props.caseItem.id,
        env_id: f.env_id,
        schedule_type: f.schedule_type,
        interval_minutes: f.schedule_type === 'interval' ? f.interval_minutes : undefined,
        daily_time: f.schedule_type === 'daily' ? f.daily_time : undefined,
        enabled: true,
      })
      ElMessage.success('已添加定时任务')
    }
    scheduleFormVisible.value = false
    emit('changed')
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    scheduleSaving.value = false
  }
}

async function onToggleSchedule(s: TestSchedule) {
  try {
    await scheduleApi.update(s.id, { enabled: !s.enabled })
    emit('changed')
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  }
}

async function onRunSchedule(s: TestSchedule) {
  try {
    await scheduleApi.run(s.id)
    ElMessage.success('已触发执行，结果可在执行记录查看')
    emit('changed')
  } catch (e: any) {
    ElMessage.error(e.message || '触发失败')
  }
}

async function onRemoveSchedule(s: TestSchedule) {
  try {
    await ElMessageBox.confirm(
      `确认删除定时任务「${describeSchedule(s)}」？删除后将不再自动执行，此操作不可恢复`,
      '删除定时任务',
      { type: 'warning', confirmButtonText: '删除' },
    )
  } catch {
    return
  }
  try {
    await scheduleApi.remove(s.id)
    ElMessage.success('已删除')
    emit('changed')
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}
</script>

<template>
  <!-- 标题单行省略：用例名过长时不撑高弹窗（hover title 看全名）；外壳样式在全局 style.css -->
  <el-dialog
    v-model="visible"
    width="560px"
    align-center
    :close-on-click-modal="false"
    class="schedule-dialog"
  >
    <template #header>
      <el-tooltip :content="`定时任务 · ${caseItem?.name || ''}`" placement="top" popper-class="app-tip">
        <span class="schedule-dialog-title">
          定时任务 · {{ caseItem?.name || '' }}
        </span>
      </el-tooltip>
    </template>
    <!-- 已配置的定时任务列表 -->
    <div v-if="schedules.length" class="schedule-list">
      <div v-for="s in schedules" :key="s.id" class="schedule-row">
        <div class="schedule-info">
          <span class="schedule-desc">{{ describeSchedule(s) }}</span>
          <span class="schedule-env">{{ s.env_name || `环境#${s.env_id}` }}</span>
          <el-tooltip
            :content="s.next_run_at ? formatTime(s.next_run_at) : ''"
            :disabled="!s.next_run_at"
            placement="top"
            popper-class="app-tip"
          >
            <span class="schedule-next">{{ s.next_run_at ? `下次 ${formatRelativeTime(s.next_run_at)}` : '未排期' }}</span>
          </el-tooltip>
        </div>
        <div class="schedule-ops">
          <el-tooltip :content="s.enabled ? '停用定时' : '启用定时'" placement="top">
            <el-switch :model-value="s.enabled" size="small" @change="onToggleSchedule(s)" />
          </el-tooltip>
          <el-button link type="success" size="small" @click="onRunSchedule(s)">执行</el-button>
          <el-button link type="primary" size="small" @click="onEditSchedule(s)">编辑</el-button>
          <el-button link type="danger" size="small" @click="onRemoveSchedule(s)">删除</el-button>
        </div>
      </div>
    </div>

    <el-divider v-if="schedules.length && scheduleFormVisible" />

    <!-- 新增/编辑表单：无定时任务时直接展示，有时通过按钮展开 -->
    <div v-if="scheduleFormVisible">
      <el-form :model="scheduleForm" label-width="80px">
        <el-form-item label="环境" required>
          <el-select v-model="scheduleForm.env_id" placeholder="选择执行环境" style="width: 100%">
            <el-option v-for="e in envs" :key="e.id" :label="e.name" :value="e.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="调度类型" required>
          <el-radio-group v-model="scheduleForm.schedule_type">
            <el-radio value="interval">间隔执行</el-radio>
            <el-radio value="daily">每日定时</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="scheduleForm.schedule_type === 'interval'" label="间隔分钟" required>
          <el-input-number v-model="scheduleForm.interval_minutes" :min="1" :max="525600" style="width: 180px" />
        </el-form-item>
        <el-form-item v-else label="每日时刻" required>
          <el-time-picker
            v-model="scheduleForm.daily_time"
            format="HH:mm"
            value-format="HH:mm"
            placeholder="如 08:30"
            style="width: 180px"
          />
        </el-form-item>
      </el-form>
      <div class="schedule-form-foot">
        <el-button size="small" @click="scheduleFormVisible = false">取消</el-button>
        <el-button type="primary" size="small" :loading="scheduleSaving" @click="onSaveSchedule">
          {{ scheduleEditingId ? '保存修改' : '添加定时' }}
        </el-button>
      </div>
    </div>
    <div v-else class="schedule-add-entry">
      <el-button size="small" @click="openScheduleForm()">+ 新增定时</el-button>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 原 CaseList scoped 样式迁移（.schedule-mark 列表图标标识留在视图；外壳样式在 style.css） */
.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.schedule-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
}
.schedule-info {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
  font-size: 13px;
}
.schedule-desc {
  font-weight: 500;
  color: var(--app-text);
  white-space: nowrap;
}
.schedule-env {
  color: var(--app-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 130px; /* 环境名过长截断，防把行撑宽 */
  flex-shrink: 1;
}
.schedule-next {
  color: var(--app-text-faint);
  font-size: 12px;
  white-space: nowrap;
}
.schedule-ops {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.schedule-form-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.schedule-add-entry {
  display: flex;
  justify-content: center;
  padding: 4px 0;
}
/* 弹窗标题单行省略（header slot 内容；padding-right 避让右上角关闭按钮） */
.schedule-dialog-title {
  display: block;
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: 32px;
}
</style>
