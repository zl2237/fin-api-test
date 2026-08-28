<template>
  <div class="page">
    <div class="page-head">
      <div class="head-left">
        <span class="page-title">用例管理</span>
        <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
        <el-dropdown style="margin-left: 12px" @command="(fmt: string) => onExport(fmt as 'excel' | 'json')">
          <el-button>
            导出<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excel">Excel 简表</el-dropdown-item>
              <el-dropdown-item command="json">JSON 全量（含 DAG/断言/提取）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="head-right">
        <el-select
          v-model="filterCreator"
          style="width: 140px"
          placeholder="创建人"
          clearable
          filterable
          @change="load"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-select
          v-model="filterUpdater"
          style="width: 140px"
          placeholder="更新人"
          clearable
          filterable
          @change="load"
        >
          <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-input v-model="keyword" style="width: 240px" placeholder="搜索用例名称" clearable>
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </div>

    <!-- 批量操作条：仅在有选中时浮现（与接口管理一致），未选中不占空间 -->
    <Transition name="bulk-bar">
      <div v-if="selectedCaseIds.length" class="bulk-bar">
        <span class="bulk-count">已选 {{ selectedCaseIds.length }} 项</span>
        <el-button size="small" @click="onBatchMove">移动到分组</el-button>
        <el-button
          size="small"
          type="success"
          :disabled="batchRunning"
          :loading="batchRunning"
          @click="onBatchRun"
        >批量执行</el-button>
        <el-button size="small" :disabled="selectedCaseIds.length < 2" @click="openCombine">组合</el-button>
        <el-button size="small" text @click="clearAllTables()">取消选择</el-button>
      </div>
    </Transition>

    <!-- 左分组导航 + 右组内列表（master-detail）；页面级加载遮罩 -->
    <div v-loading="loading" class="group-layout">
      <aside class="group-side">
        <div
          class="side-node"
          :class="{ on: selectedRowKey === 'all' }"
          @click="selectedRowKey = 'all'"
        >
          <el-icon class="group-icon"><Folder /></el-icon>
          <span class="side-name">全部用例</span>
          <span class="side-cnt">{{ filteredList.length }}</span>
        </div>
        <div
          v-for="row in visibleGroupRows"
          :key="row.key"
          class="side-node"
          :class="{ on: selectedRowKey === row.key }"
          :style="{ paddingLeft: 10 + row.depth * 14 + 'px' }"
          @click="onSideNodeClick(row)"
        >
          <el-icon
            v-if="hasChildGroups(row.groupId)"
            class="expand-icon"
            :class="{ expanded: isGroupExpanded(row.groupId!) }"
            title="展开/折叠子分组"
            @click.stop="onToggleGroup(row)"
          ><CaretRight /></el-icon>
          <span v-else class="expand-spacer" />
          <span class="side-name">{{ row.name }}</span>
          <span class="side-cnt">{{ row.isUngrouped ? casesOf(null).length : countCasesWithDescendants(row.groupId!) }}</span>
        </div>
        <div class="side-foot">
          <el-button size="small" @click="showGroupDialog = true">分组管理</el-button>
        </div>
      </aside>

      <div class="group-main">
        <!-- 页面级加载失败：内联错误块 + 重试（不用 toast 一闪而过） -->
        <div v-if="loadError" class="app-load-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ loadError }}</span>
          <el-button size="small" @click="load">重试</el-button>
        </div>

        <EmptyState v-else-if="!loading && !list.length" description="暂无用例">
          <div class="empty-actions">
            <el-button type="primary" @click="openCreate">+ 新建用例</el-button>
            <el-button text @click="router.push('/apis')">先去管理接口</el-button>
          </div>
        </EmptyState>

        <!-- 全部用例视图（跨分组平铺，无拖拽把手：跨组顺序无持久化语义） -->
        <template v-else-if="selectedRowKey === 'all'">
          <div class="main-head">
            <span class="main-title">全部用例</span>
            <span class="group-count">{{ filteredList.length }}</span>
          </div>
          <el-table
            :data="allPaged"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange('all', sel)"
          >
            <el-table-column type="selection" width="42" />
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip v-if="hasEnabledSchedule(row.id)" content="已配置定时任务" placement="top">
                  <el-icon class="schedule-mark"><Timer /></el-icon>
                </el-tooltip>{{ row.name }}
              </template>
            </el-table-column>
            <el-table-column label="节点数" width="90">
              <template #default="{ row }">{{ row.dag_config?.nodes?.length || 0 }}</template>
            </el-table-column>
            <el-table-column label="更新时间" width="120">
              <template #default="{ row }">
                <span :title="formatTime(row.updated_at)">{{ formatRelativeTime(row.updated_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="330" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="执行本行用例；勾选多行后按 Ctrl+Enter 从第一个勾选项开始执行" placement="top">
                  <el-button link type="success" size="small" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-button link type="primary" size="small" @click="goReport(row)">报告</el-button>
                <el-button link type="primary" size="small" @click="openSchedule(row)">定时</el-button>
                <el-tooltip :content="row.dataset_id ? '数据驱动：已绑定数据集，点击更换/解绑' : '绑定数据集启用数据驱动'" placement="top">
                  <el-button link :type="row.dataset_id ? 'warning' : 'primary'" size="small" @click="openBind(row)">数据</el-button>
                </el-tooltip>
                <el-button link type="primary" size="small" @click="onCopy(row)">复制</el-button>
                <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="pagination-wrap">
            <el-pagination
              small
              background
              :current-page="allPage"
              :page-size="pageSize"
              :total="filteredList.length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange('all', p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </template>

        <!-- 选中分组视图：单表 + 组内分页/勾选/拖拽（沿用 composable 按 key 驱动） -->
        <template v-else-if="selectedRow">
          <div class="main-head">
            <span class="main-title">{{ selectedRow.name }}</span>
            <span class="group-count">{{ selectedRow.isUngrouped ? casesOf(null).length : countCasesWithDescendants(selectedRow.groupId!) }}</span>
          </div>
          <el-table
            v-if="selectedCases.length"
            :ref="(el: any) => setTableRef(selectedRow?.key, el)"
            :data="selectedPaged"
            size="small"
            stripe
            row-key="id"
            @selection-change="(sel: any[]) => onSelectionChange(selectedRow!.key, sel)"
          >
            <el-table-column type="selection" width="42" :reserve-selection="true" />
            <el-table-column width="36" align="center">
              <template #default>
                <!-- 父分组视图是跨组聚合列表，顺序无持久化语义，不提供拖拽 -->
                <el-icon v-if="!isSubtreeView" class="drag-handle" title="拖拽排序"><Rank /></el-icon>
              </template>
            </el-table-column>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip v-if="hasEnabledSchedule(row.id)" content="已配置定时任务" placement="top">
                  <el-icon class="schedule-mark"><Timer /></el-icon>
                </el-tooltip>{{ row.name }}
              </template>
            </el-table-column>
            <el-table-column label="节点数" width="90">
              <template #default="{ row }">{{ row.dag_config?.nodes?.length || 0 }}</template>
            </el-table-column>
            <el-table-column label="更新时间" width="120">
              <template #default="{ row }">
                <span :title="formatTime(row.updated_at)">{{ formatRelativeTime(row.updated_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="创建人" width="100" align="center">
              <template #default="{ row }">{{ row.created_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="更新人" width="100" align="center">
              <template #default="{ row }">{{ row.updated_by_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="330" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="goDesign(row.id)">编排</el-button>
                <el-tooltip content="执行本行用例；勾选多行后按 Ctrl+Enter 从第一个勾选项开始执行" placement="top">
                  <el-button link type="success" size="small" @click="runCase(row)">执行</el-button>
                </el-tooltip>
                <el-button link type="primary" size="small" @click="goReport(row)">报告</el-button>
                <el-button link type="primary" size="small" @click="openSchedule(row)">定时</el-button>
                <el-tooltip :content="row.dataset_id ? '数据驱动：已绑定数据集，点击更换/解绑' : '绑定数据集启用数据驱动'" placement="top">
                  <el-button link :type="row.dataset_id ? 'warning' : 'primary'" size="small" @click="openBind(row)">数据</el-button>
                </el-tooltip>
                <el-button link type="primary" size="small" @click="onCopy(row)">复制</el-button>
                <el-button link type="danger" size="small" @click="onRemove(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else-if="!loading" :image-size="80" description="该分组暂无用例" />
          <div v-if="selectedCases.length" class="pagination-wrap">
            <el-pagination
              small
              background
              :current-page="pageMap[String(selectedRow!.key)] || 1"
              :page-size="pageSize"
              :total="selectedCases.length"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              @current-change="(p: number) => onPageChange(selectedRow!.key, p)"
              @size-change="onPageSizeChange"
            />
          </div>
        </template>
      </div>
    </div>

    <!-- 新建用例弹窗 -->
    <el-dialog v-model="dialogVisible" title="新建用例" width="420px" align-center :close-on-click-modal="false">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="创建订单-冒烟" />
        </el-form-item>
        <el-form-item label="分组">
          <el-tree-select
            v-model="form.group_id"
            :data="treeSelectData"
            node-key="id"
            :props="treeProps"
            placeholder="选择分组"
            clearable
            check-strictly
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 分组管理弹窗（多级：el-tree 拖拽调整层级与顺序） -->
    <el-dialog v-model="showGroupDialog" title="用例分组管理" width="620px" align-center class="group-manage-dialog" :close-on-click-modal="false">
      <div class="group-dialog-body">
        <div class="group-add">
          <el-input
            v-model="newGroupName"
            placeholder="新分组名称（如：冒烟组/订单组/付款组）"
            style="flex: 1"
            @keyup.enter="onAddGroup"
          />
          <el-tree-select
            v-model="newGroupParentId"
            :data="treeSelectData"
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
            ref="groupTreeRef"
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
          <el-empty v-if="!groupTreeNodes.length" description="暂无分组" :image-size="60" />
        </div>
      </div>
    </el-dialog>

    <!-- 批量移动弹窗 -->
    <el-dialog v-model="batchMoveVisible" title="批量移动到分组" width="420px" align-center :close-on-click-modal="false">
      <div style="margin-bottom: 12px; color: var(--app-text-muted);">
        将 {{ selectedCaseIds.length }} 个用例移动到：
      </div>
      <el-tree-select
        v-model="batchMoveTarget"
        :data="treeSelectWithUngrouped"
        node-key="id"
        :props="treeProps"
        placeholder="选择目标分组 / 输入搜索"
        clearable
        filterable
        check-strictly
        style="width: 100%"
      />
      <template #footer>
        <el-button @click="batchMoveVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchMoveLoading" @click="confirmBatchMove">确定移动</el-button>
      </template>
    </el-dialog>

    <!-- 批量执行配置弹窗：逐用例设置执行次数 + 并发数，确认后提交 -->
    <el-dialog v-model="batchRunVisible" title="批量执行" width="480px" align-center :close-on-click-modal="false">
      <div class="batch-run-tip">
        为每个用例设置执行次数，并发数 1 = 逐个串行执行（避免并发问题），&gt;1 并行（同环境共享登录）。绑定数据集的用例每轮按数据行展开。
      </div>
      <div class="batch-run-concurrency">
        <span class="batch-run-count-label">并发数</span>
        <el-input-number v-model="batchRunConcurrency" :min="1" :max="16" size="small" />
        <span class="batch-run-concurrency-hint">{{ batchRunConcurrency === 1 ? '串行：一个执行完再下一个' : `同时执行 ${batchRunConcurrency} 个` }}</span>
      </div>
      <div class="batch-run-list">
        <div v-for="it in batchRunItems" :key="it.id" class="batch-run-row">
          <span class="batch-run-name" :title="it.name">{{ it.name }}</span>
          <span class="batch-run-count-label">执行次数</span>
          <el-input-number v-model="batchRunCounts[it.id]" :min="1" :max="9999" size="small" />
        </div>
      </div>
      <template #footer>
        <span class="batch-run-total">共 {{ batchRunItems.length }} 个用例 / {{ batchRunTotal }} 轮</span>
        <el-button @click="batchRunVisible = false">取消</el-button>
        <el-button type="success" :loading="batchRunning" @click="confirmBatchRun">开始执行</el-button>
      </template>
    </el-dialog>

    <!-- 组合弹窗：拖拽调整拼接顺序，复制式生成新用例 -->
    <el-dialog v-model="combineVisible" title="组合用例" width="540px" align-center :close-on-click-modal="false">
      <div class="combine-tip">拖拽调整拼接顺序（自上而下依次执行）；组合将复制生成新用例，不影响原用例。前段提取的变量后段可直接引用。</div>
      <div ref="combineListRef" class="combine-list">
        <div v-for="c in combineItems" :key="c.id" class="combine-item">
          <el-icon class="drag-handle" title="拖拽排序"><Rank /></el-icon>
          <span class="combine-name" :title="c.name">{{ c.name }}</span>
          <span class="combine-nodes">{{ c.dag_config?.nodes?.length || 0 }} 节点</span>
        </div>
      </div>
      <el-form :model="combineForm" label-width="90px" style="margin-top: 14px">
        <el-form-item label="新用例名" required>
          <el-input v-model="combineForm.name" placeholder="如：冒烟全流程组合" maxlength="200" />
        </el-form-item>
        <el-form-item label="分组">
          <el-tree-select
            v-model="combineForm.group_id"
            :data="treeSelectData"
            node-key="id"
            :props="treeProps"
            placeholder="选择分组"
            clearable
            check-strictly
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="combineVisible = false">取消</el-button>
        <el-button type="primary" :loading="combineLoading" @click="confirmCombine">组合生成</el-button>
      </template>
    </el-dialog>

    <!-- 定时任务弹窗（用例行内联入口）：该用例的定时配置列表 + 增改表单（≤4 字段 → el-dialog） -->
    <el-dialog
      v-model="scheduleVisible"
      width="560px"
      align-center
      :close-on-click-modal="false"
      class="schedule-dialog"
    >
      <!-- 标题单行省略：用例名过长时不撑高弹窗（hover title 看全名） -->
      <template #header>
        <span class="schedule-dialog-title" :title="`定时任务 · ${scheduleCase?.name || ''}`">
          定时任务 · {{ scheduleCase?.name || '' }}
        </span>
      </template>
      <!-- 已配置的定时任务列表 -->
      <div v-if="caseSchedules.length" class="schedule-list">
        <div v-for="s in caseSchedules" :key="s.id" class="schedule-row">
          <div class="schedule-info">
            <span class="schedule-desc">{{ describeSchedule(s) }}</span>
            <span class="schedule-env">{{ s.env_name || `环境#${s.env_id}` }}</span>
            <span
              class="schedule-next"
              :title="s.next_run_at ? formatTime(s.next_run_at) : ''"
            >{{ s.next_run_at ? `下次 ${formatRelativeTime(s.next_run_at)}` : '未排期' }}</span>
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

      <el-divider v-if="caseSchedules.length && scheduleFormVisible" />

      <!-- 新增/编辑表单：无定时任务时直接展示，有时通过按钮展开 -->
      <div v-if="scheduleFormVisible">
        <el-form :model="scheduleForm" label-width="80px">
          <el-form-item label="环境" required>
            <el-select v-model="scheduleForm.env_id" placeholder="选择执行环境" style="width: 100%">
              <el-option v-for="e in store.environments" :key="e.id" :label="e.name" :value="e.id" />
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
        <el-button @click="scheduleVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 绑定数据集（数据驱动） -->
    <el-dialog v-model="bindVisible" title="绑定数据集" width="480px">
      <div class="bind-tip">
        绑定后执行该用例时按数据行展开：N 行数据 = N 次执行，行值以
        <code v-pre>${列名}</code> 注入变量（优先于同名环境变量）。数据集按用例隔离，仅可选本用例名下的数据集
      </div>
      <el-select v-model="bindDatasetId" placeholder="选择数据集（空=不绑定）" clearable style="width: 100%">
        <el-option v-for="d in projectDatasets" :key="d.id" :label="`${d.name}（${d.rows?.length ?? 0} 行）`" :value="d.id" />
      </el-select>
      <div v-if="!projectDatasets.length" class="bind-empty">
        该用例暂无数据集（数据集为用例私有），
        <el-button link type="primary" @click="router.push('/datasets')">去创建</el-button>
      </div>
      <template #footer>
        <el-button @click="bindVisible = false">取消</el-button>
        <el-button type="primary" :loading="bindSaving" @click="saveBind">保存</el-button>
      </template>
    </el-dialog>

    <!-- 数据驱动执行确认：N 行将执行 N 次，可临时换数据集/选行 -->
    <el-dialog v-model="ddVisible" :title="`数据驱动执行：${ddCase?.name || ''}`" width="640px">
      <div class="bind-tip">
        <el-icon style="color: var(--el-color-warning)"><WarningFilled /></el-icon>
        该用例绑定了数据集，<b>{{ ddSelectedRows.length }} 行数据将执行 {{ ddSelectedRows.length }} 次</b>（并行，并发上限 4）
      </div>
      <!-- 快照过期提示：数据集节点配置快照与用例当前编排不一致（执行按快照跑，先同步再执行） -->
      <el-alert v-if="ddDrift?.stale" type="warning" :closable="false" class="drift-alert">
        <template #title>
          数据集快照已过期：{{ ddDrift.nodes.length }} 个节点编排与用例当前不一致（执行按快照跑）
          <el-button link type="primary" size="small" :loading="ddResyncing" style="margin-left: 8px" @click="resyncFromDialog">
            一键同步（取用例当前编排）
          </el-button>
        </template>
        <div v-for="n in ddDrift.nodes" :key="n.node_id" class="drift-node">
          <b>{{ n.label }}</b>：{{ n.changes.join('；') }}
        </div>
      </el-alert>
      <el-select v-model="ddDatasetId" style="width: 260px; margin-bottom: 10px" @change="onDdDatasetChange">
        <el-option v-for="d in projectDatasets" :key="d.id" :label="`${d.name}（${d.rows?.length ?? 0} 行）`" :value="d.id" />
      </el-select>
      <el-table
        ref="ddTableRef"
        :data="ddRows"
        size="small"
        max-height="320"
        row-key="id"
        @selection-change="(sel: any[]) => (ddSelectedRows = sel)"
      >
        <el-table-column type="selection" width="42" />
        <el-table-column prop="row_index" label="#" width="50" />
        <el-table-column
          v-for="col in ddColumns"
          :key="col.key"
          :label="store.fieldDictMap?.[col.key] || col.key"
          min-width="120"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ row.data?.[col.key] ?? '—' }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="ddVisible = false">取消</el-button>
        <el-button type="success" :disabled="!ddSelectedRows.length" :loading="ddRunning" @click="confirmDataDrivenRun">
          执行 {{ ddSelectedRows.length }} 次
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import { Rank, Folder, CaretRight, Search, WarningFilled, Timer, ArrowDown } from '@element-plus/icons-vue'
import { caseApi, caseGroupApi, execApi, userApi, scheduleApi, datasetApi, type TestCase, type CaseGroup, type SimpleUser, type TestSchedule, type DataSet } from '@/api'
import { useAppStore } from '@/stores'
import { formatTime, formatRelativeTime } from '@/utils/format'
import { useGroupTree, collectDescendantIds, type GroupTreeNode } from '@/composables/useGroupTree'
import { useGroupedTable, collectTreeUpdates, setGroupSwitchNotifier } from '@/composables/useGroupedTable'
import { useFaviconStatus } from '@/composables/useFaviconStatus'
import EmptyState from '@/components/EmptyState.vue'

const favicon = useFaviconStatus()

const store = useAppStore()
const router = useRouter()

// 追踪所有执行轮询定时器，组件卸载时统一清理，避免切页后继续请求已失效的执行记录
const pollTimers: ReturnType<typeof setTimeout>[] = []
const list = ref<TestCase[]>([])
const loadError = ref('')
const groups = ref<CaseGroup[]>([])
const users = ref<SimpleUser[]>([])
const filterCreator = ref<number | null>(null)
const filterUpdater = ref<number | null>(null)
const loading = ref(false)
const keyword = ref('')

const filteredList = computed(() => {
  if (!keyword.value) return list.value
  const kw = keyword.value.toLowerCase()
  return list.value.filter(c => c.name.toLowerCase().includes(kw))
})

// 多级分组表格：树构建 + 展开记忆 + 分组过滤/计数/可见行/组内分页（样板已收敛进 composable）
const tableSel = useGroupedTable(groups, toRef(store, 'currentProjectId'), 'caseList', filteredList)
// 切分组勾选时提示（互斥勾选设计：不支持跨分组累计）
setGroupSwitchNotifier(() => ElMessage.info('不支持跨分组勾选，已切换为当前分组的选择'))
const {
  tree,
  treeSelectData,
  treeSelectWithUngrouped,
  isExpanded: isGroupExpanded,
  applyDefaultExpand,
  itemsOf: casesOf,
  countWithDescendants: countCasesWithDescendants,
  visibleGroupRows,
  onToggleGroup,
  pageSize,
  pageMap,
  onPageChange,
  onPageSizeChange,
  applyPageDragReorder,
  resetSelection,
  resetPages,
} = tableSel

// 搜索条件变化即回第 1 页，避免「第 3 页 + 结果不足一页」的空白死局
watch(keyword, () => resetPages())

// ===== 左分组导航选中态（master-detail）=====
const selectedRowKey = ref<string | number>('all')
const selectedRow = computed(() => visibleGroupRows.value.find(r => r.key === selectedRowKey.value))
// 左栏 caret 仅在「有子分组」时显示（composable 的 expandable 含"组内有数据"的旧手风琴语义，叶子分组展开无意义）
function hasChildGroups(groupId: number | null): boolean {
  if (groupId == null) return false
  return groups.value.some(g => g.parent_id === groupId)
}
// 单击整行 = 选中该组（父/叶子一致，右侧展示组内用例）；caret 单击 = 展开/折叠子分组
function onSideNodeClick(row: { key: string | number; groupId: number | null; isUngrouped?: boolean }) {
  selectedRowKey.value = row.key
}
// 父分组（有子分组）视图：右侧按计数徽章同口径展示子孙分组全部用例
const isSubtreeView = computed(() => {
  const row = selectedRow.value
  return !!row && !row.isUngrouped && hasChildGroups(row.groupId)
})
const selectedCases = computed<TestCase[]>(() => {
  const row = selectedRow.value
  if (!row) return []
  if (row.isUngrouped || row.groupId == null) return casesOf(null)
  if (hasChildGroups(row.groupId)) {
    const ids = [row.groupId, ...collectDescendantIds(tree.value, row.groupId)]
    return filteredList.value.filter(c => c.group_id != null && ids.includes(c.group_id))
  }
  return casesOf(row.groupId)
})
const selectedPaged = computed(() => {
  const page = pageMap.value[String(selectedRow.value?.key)] || 1
  const start = (page - 1) * pageSize.value
  return selectedCases.value.slice(start, start + pageSize.value)
})
// 分组重载/删除后选中项可能消失，回退到「全部」
watch(visibleGroupRows, (rows) => {
  if (selectedRowKey.value !== 'all' && !rows.some(r => r.key === selectedRowKey.value)) {
    selectedRowKey.value = 'all'
  }
})
// 「全部」视图分页：复用 composable 的 pageMap/pageSize（键 'all' 不与分组键冲突）
const allPage = computed(() => pageMap.value['all'] || 1)
const allPaged = computed(() => {
  const start = (allPage.value - 1) * pageSize.value
  return filteredList.value.slice(start, start + pageSize.value)
})

// el-tree / el-tree-select 公共字段映射
const treeProps = { label: 'label', children: 'children' }

const dialogVisible = ref(false)
const showGroupDialog = ref(false)
const newGroupName = ref('')
const newGroupParentId = ref<number | null>(null)
// el-tree 可变数据（管理弹窗拖拽用），groups 变化时重建
const groupTreeNodes = ref<GroupTreeNode[]>([])
const groupTreeRef = ref<any>(null)
const batchMoveVisible = ref(false)
const batchMoveTarget = ref<number | null>(null)
const batchMoveLoading = ref(false)
const batchRunning = ref(false)
// 批量执行配置弹窗：每个用例可单独设置执行次数（1~9999），并发数可配（1=串行）
const batchRunVisible = ref(false)
const batchRunCounts = ref<Record<number, number>>({})
const batchRunConcurrency = ref(4)
// 弹窗内所选用例的展示行（打开时按勾选快照生成，避免执行中列表刷新干扰）
const batchRunItems = ref<{ id: number; name: string }[]>([])
const form = ref<{ name: string; group_id: number | null; description: string }>({ name: '', group_id: null, description: '' })

// ===== 批量移动：互斥勾选状态机在 useGroupedTable；视图只持有表格实例引用 =====
const tableRefs = new Map<string | number, any>()
const selectedCaseIds = tableSel.selectedIds

function clearOtherTables(keep: string | number) {
  tableRefs.forEach((tableRef, key) => {
    if (key !== keep) tableRef?.clearSelection?.()
  })
}

function clearAllTables() {
  tableRefs.forEach((tableRef) => tableRef?.clearSelection?.())
}

// ===== 组内拖拽排序（SortableJS 绑定 el-table tbody）=====
const sortableInstances = new Map<string | number, any>()

function setTableRef(groupId: string | number | undefined, el: any) {
  if (el && groupId != null) {
    tableRefs.set(groupId, el)
    nextTick(() => {
      const tbody = el.$el?.querySelector?.('.el-table__body-wrapper tbody')
      if (!tbody) return
      const old = sortableInstances.get(groupId)
      if (old) old.destroy()
      const inst = Sortable.create(tbody, {
        handle: '.drag-handle',
        animation: 200,
        ghostClass: 'sortable-ghost',
        onEnd: (evt: any) => onCaseRowDragEnd(groupId, evt.oldIndex, evt.newIndex),
      })
      sortableInstances.set(groupId, inst)
    })
  } else if (!el) {
    // 卸载：ref(null) 触发时 selectedRowKey 已切走（如回「全部」），旧 key 不可知；
    // 分组视图同一时刻仅一个表格实例，直接清空即可。
    // 注意不能在此读取 selectedRow!.key —— 卸载时它是 undefined，会抛 TypeError 中断 patch，
    // 导致右侧列表冻结在旧分组（分组切回全部后不再变化的根因）。
    tableRefs.clear()
    sortableInstances.forEach((inst) => inst.destroy())
    sortableInstances.clear()
  }
}

async function onCaseRowDragEnd(groupId: string | number, oldIndex: number, newIndex: number) {
  // 父分组视图无拖拽把手（跨组聚合列表），守卫兜底防 Sortable 残留实例触发
  if (isSubtreeView.value) return
  try {
    const applied = await applyPageDragReorder(groupId, oldIndex, newIndex, (items) => caseApi.reorder(items))
    if (applied) ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '排序保存失败')
    await load()
  }
}

/** el-tree 拖拽落点：持久化 parent_id + sort_order */
async function onTreeNodeDrop() {
  // el-tree 拖拽后已就地更新 groupTreeNodes，收集树平面更新载荷
  const updates = collectTreeUpdates(groupTreeNodes.value)
  try {
    await Promise.all(updates.map(it => caseGroupApi.update(it.id, { parent_id: it.parent_id, sort_order: it.sort_order })))
    ElMessage.success('已保存')
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e.message || '分组排序保存失败')
    await loadGroups()
  }
}

function onSelectionChange(groupId: string | number, selection: TestCase[]) {
  tableSel.onSelectionChange(groupId, selection, clearOtherTables)
}

function onBatchMove() {
  if (selectedCaseIds.value.length === 0) return
  batchMoveTarget.value = null
  batchMoveVisible.value = true
}

async function confirmBatchMove() {
  if (batchMoveTarget.value === null) {
    ElMessage.warning('请选择目标分组')
    return
  }
  batchMoveLoading.value = true
  try {
    const targetGroupId = batchMoveTarget.value === 0 ? null : batchMoveTarget.value
    const res = await caseApi.batchMove(selectedCaseIds.value, targetGroupId)
    ElMessage.success(res.message)
    batchMoveVisible.value = false
    // 清空选中与 el-table 内部勾选态（reserve-selection 按 row-key 缓存，需主动 clearSelection）
    resetSelection(clearAllTables)
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '批量移动失败')
  } finally {
    batchMoveLoading.value = false
  }
}

// ===== 用例组合（复制式拼接，弹窗拖排序确定顺序）=====
const combineVisible = ref(false)
const combineItems = ref<TestCase[]>([])
const combineForm = ref<{ name: string; group_id: number | null }>({ name: '', group_id: null })
const combineLoading = ref(false)
const combineListRef = ref<HTMLElement | null>(null)
let combineSortable: Sortable | null = null

function openCombine() {
  const sel = selectedCaseIds.value
  if (sel.length < 2) return ElMessage.warning('组合至少需要勾选 2 个用例')
  // 按当前列表顺序排列（勾选顺序不稳定），弹窗内拖拽可再调整
  const selSet = new Set(sel)
  combineItems.value = list.value.filter(c => selSet.has(c.id))
  combineForm.value = { name: '', group_id: null }
  combineVisible.value = true
  nextTick(() => {
    if (combineSortable) { combineSortable.destroy(); combineSortable = null }
    if (combineListRef.value) {
      combineSortable = Sortable.create(combineListRef.value, {
        handle: '.drag-handle',
        animation: 200,
        ghostClass: 'sortable-ghost',
        onEnd: (evt: any) => {
          const { oldIndex, newIndex } = evt
          if (oldIndex == null || newIndex == null || oldIndex === newIndex) return
          const arr = combineItems.value
          const [moved] = arr.splice(oldIndex, 1)
          arr.splice(newIndex, 0, moved)
        },
      })
    }
  })
}

async function confirmCombine() {
  if (!combineForm.value.name?.trim()) return ElMessage.warning('请输入新用例名称')
  if (combineItems.value.length < 2) return ElMessage.warning('组合至少需要 2 个用例')
  combineLoading.value = true
  try {
    const created = await caseApi.combine(
      combineItems.value.map(c => c.id),
      combineForm.value.name.trim(),
      combineForm.value.group_id,
    )
    ElMessage.success(`已组合生成「${created.name}」（${created.dag_config?.nodes?.length || 0} 节点）`)
    combineVisible.value = false
    resetSelection(clearAllTables)
    await load()
    // 组合结果直接跳编排页检查
    router.push(`/cases/designer/${created.id}`)
  } catch (e: any) {
    ElMessage.error(e.message || '组合失败')
  } finally {
    combineLoading.value = false
  }
}

// ===== 列表导出（Excel 简表 / JSON 全量，筛选条件与列表页一致）=====
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

async function onExport(format: 'excel' | 'json') {
  if (!store.currentProjectId) return
  if (!filteredList.value.length) return ElMessage.warning('当前没有可导出的用例')
  try {
    const blob = await caseApi.exportList({
      project_id: store.currentProjectId,
      format,
      created_by: filterCreator.value ?? undefined,
      updated_by: filterUpdater.value ?? undefined,
    })
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14)
    downloadBlob(blob, `cases_${stamp}.${format === 'excel' ? 'xlsx' : 'json'}`)
    // 不报具体数量：keyword 是前端本地过滤、不参与后端导出，报数会与文件实际条数不符
    ElMessage.success(format === 'excel' ? '已导出 Excel 简表' : '已导出 JSON 全量')
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  }
}

// 分组过滤/计数/可见行/组内分页等样板已收敛至 useGroupedTable（见顶部解构）

async function load() {
  if (!store.currentProjectId) return
  loading.value = true
  loadError.value = ''
  try {
    list.value = await caseApi.list(store.currentProjectId, filterCreator.value ?? undefined, filterUpdater.value ?? undefined)
  } catch (e: any) {
    // 页面级失败：内联错误块 + 重试
    loadError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  try {
    users.value = await userApi.simple()
  } catch {
    users.value = []
  }
}

async function loadGroups() {
  if (!store.currentProjectId) return
  groups.value = await caseGroupApi.list(store.currentProjectId)
  // 重建 el-tree 可变数据（深拷贝，供管理弹窗拖拽就地修改）
  groupTreeNodes.value = JSON.parse(JSON.stringify(treeSelectData.value))
  // 无记忆时默认全部展开
  applyDefaultExpand()
  // 重置分页
  pageMap.value = {}
}

function openCreate() {
  form.value = { name: '', group_id: null, description: '' }
  dialogVisible.value = true
}

async function onCreate() {
  if (!form.value.name?.trim()) return ElMessage.warning('请输入用例名称')
  const created = await caseApi.create({
    project_id: store.currentProjectId!,
    group_id: form.value.group_id,
    name: form.value.name.trim(),
    description: form.value.description,
    dag_config: { nodes: [], edges: [] },
    node_configs: [],
  })
  ElMessage.success('已创建')
  dialogVisible.value = false
  goDesign(created.id)
}

function goDesign(id: number) {
  router.push(`/cases/designer/${id}`)
}

async function runCase(row: TestCase) {
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  // 数据驱动：绑定数据集的用例先弹确认面板（N 行执行 N 次，可临时换数据集/选行）
  if (row.dataset_id) {
    await openDataDrivenRun(row)
    return
  }
  try {
    // 异步执行：接口立即返回 running 状态的 record，后台线程池执行
    const rec = await caseApi.execute(row.id, store.currentEnvId)
    const execId = rec.id
    favicon.running()
    const msg = ElMessage({
      message: `用例「${row.name}」执行中...`,
      type: 'info',
      duration: 0,  // 不自动关闭
    })
    // 轮询执行状态，每 2 秒一次，最多 5 分钟
    const maxPolls = 150
    let pollCount = 0
    const poll = async () => {
      pollCount++
      try {
        const cur = await execApi.get(execId, true)
        if (cur.status === 'running' && pollCount < maxPolls) {
          const t = setTimeout(poll, 2000)
          pollTimers.push(t)
        } else {
          msg.close()
          if (cur.status === 'success') {
            favicon.success()
            ElMessage.success(`执行通过：${cur.summary.passed}/${cur.summary.total}`)
          } else if (pollCount >= maxPolls) {
            favicon.reset()
            ElMessage.warning('执行超时，请到执行记录查看结果')
          } else {
            favicon.failed()
            ElMessage.warning(`执行失败：${cur.summary.failed} 项未通过`)
          }
          router.push(`/reports/${execId}`)
        }
      } catch (e: any) {
        msg.close()
        favicon.reset()
        ElMessage.error(e.message || '轮询执行状态失败')
      }
    }
    const t = setTimeout(poll, 2000)
    pollTimers.push(t)
  } catch (e: any) {
    favicon.reset()
    ElMessage.error(e.message)
  }
}

// 批量执行入口：先弹配置窗（每个用例可设执行次数），确认后由 confirmBatchRun 提交
function onBatchRun() {
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  if (selectedCaseIds.value.length === 0) return ElMessage.warning('请先勾选用例')
  // 按当前勾选快照生成展示行，次数默认 1
  batchRunItems.value = selectedCaseIds.value
    .map((id) => ({ id, name: list.value.find((c) => c.id === id)?.name || `用例#${id}` }))
  const init: Record<number, number> = {}
  batchRunItems.value.forEach((it) => { init[it.id] = 1 })
  batchRunCounts.value = init
  batchRunConcurrency.value = 4
  batchRunVisible.value = true
}

// 配置弹窗内的总轮次（每用例次数之和）
const batchRunTotal = computed(() =>
  batchRunItems.value.reduce((sum, it) => sum + (batchRunCounts.value[it.id] || 0), 0),
)

// 确认批量执行：按配置的并发数提交（1=串行），同环境共享登录 token，前端并发轮询各记录
async function confirmBatchRun() {
  if (batchRunning.value) return
  // 弹窗开着期间环境可能被清空，提交前再守卫一次（同时收窄类型）
  if (!store.currentEnvId) return ElMessage.warning('请先在顶部选择环境')
  const caseIds = batchRunItems.value.map((it) => it.id)
  const counts = batchRunItems.value.map((it) => batchRunCounts.value[it.id] || 1)
  const concurrency = batchRunConcurrency.value
  const total = counts.reduce((a, b) => a + b, 0)
  batchRunVisible.value = false
  batchRunning.value = true
  favicon.running()
  const msg = ElMessage({
    message: `批量执行中（${caseIds.length} 个用例共 ${total} 轮，${concurrency === 1 ? '串行执行' : `并发 ${concurrency}`}）...`,
    type: 'info',
    duration: 0,
  })
  try {
    const records = await caseApi.batchExecute(caseIds, store.currentEnvId, counts, concurrency)
    // 并发轮询：各记录独立轮询，全部完成后汇总；同一用例多轮时标注轮次
    const seen: Record<number, number> = {}
    const results = await Promise.all(records.map(async (rec) => {
      const caseRow = list.value.find((c) => c.id === rec.case_id)
      const name = caseRow?.name || `用例#${rec.case_id}`
      seen[rec.case_id] = (seen[rec.case_id] || 0) + 1
      const multi = (batchRunCounts.value[rec.case_id] || 1) > 1
      const label = multi ? `${name}（第 ${seen[rec.case_id]} 轮）` : name
      const status = await pollOne(rec.id)
      return { name: label, status: status.status, summary: status.summary }
    }))
    msg.close()
    const passed = results.filter((r) => r.status === 'success').length
    const failed = results.length - passed
    if (failed === 0) favicon.success()
    else favicon.failed()
    const detail = results.map((r) => {
      if (r.status === 'success') return `✓ ${r.name}：通过（${r.summary?.passed}/${r.summary?.total}）`
      if (r.status === 'failed') return `✗ ${r.name}：失败（${r.summary?.failed} 项未通过）`
      return `! ${r.name}：${r.status}`
    }).join('\n')
    ElMessageBox.alert(detail, `批量执行完成：通过 ${passed}/${results.length}`, {
      confirmButtonText: '查看报告',
      cancelButtonText: '关闭',
      showCancelButton: true,
      type: passed === results.length ? 'success' : 'warning',
    }).then(() => {
      router.push('/executions')
    }).catch(() => {})
    await load()
  } catch (e: any) {
    msg.close()
    favicon.reset()
    ElMessage.error(e.message || '批量执行失败')
  } finally {
    batchRunning.value = false
  }
}

// 轮询单个执行记录直到完成，返回最终状态和汇总
function pollOne(execId: number): Promise<{ status: string; summary: any }> {
  return new Promise((resolve, reject) => {
    const maxPolls = 300
    let pollCount = 0
    const poll = async () => {
      pollCount++
      try {
        const cur = await execApi.get(execId, true)
        if (cur.status === 'running' && pollCount < maxPolls) {
          const t = setTimeout(poll, 2000)
          pollTimers.push(t)
        } else {
          resolve({ status: cur.status, summary: cur.summary })
        }
      } catch (e: any) {
        reject(e)
      }
    }
    const t = setTimeout(poll, 2000)
    pollTimers.push(t)
  })
}

function goReport(row: TestCase) {
  router.push({ path: '/executions', query: { case_id: row.id } })
}

async function onCopy(row: TestCase) {
  try {
    await caseApi.copy(row.id)
    ElMessage.success('已复制')
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '复制失败')
  }
}

async function onRemove(row: TestCase) {
  // 对齐 ApiManage 的删除交互：取消静默（不产生 unhandled rejection），失败有提示
  try {
    await ElMessageBox.confirm(`确认删除用例「${row.name}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await caseApi.remove(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

// ===== 定时任务（用例行内联入口：弹窗配置 + 列表图标标识）=====
const schedules = ref<TestSchedule[]>([])
const scheduleVisible = ref(false)
const scheduleCase = ref<TestCase | null>(null)
const scheduleFormVisible = ref(false)
const scheduleEditingId = ref<number | null>(null)
const scheduleSaving = ref(false)
const scheduleForm = ref<{
  env_id: number | null
  schedule_type: 'interval' | 'daily'
  interval_minutes: number | null
  daily_time: string | null
}>({ env_id: null, schedule_type: 'interval', interval_minutes: 30, daily_time: '08:00' })

// 当前弹窗用例的定时任务（列表 + 表单共用的单一数据源）
const caseSchedules = computed(() =>
  scheduleCase.value ? schedules.value.filter(s => s.case_id === scheduleCase.value!.id) : [],
)

// 用例名称列的图标标识：存在启用中的定时任务才显示
function hasEnabledSchedule(caseId: number): boolean {
  return schedules.value.some(s => s.case_id === caseId && s.enabled)
}

// 定时配置的人话描述：interval → 每 N 分钟；daily → 每日 HH:MM
function describeSchedule(s: TestSchedule): string {
  if (s.schedule_type === 'interval') return `每 ${s.interval_minutes ?? '?'} 分钟`
  return `每日 ${s.daily_time ?? '?'}`
}

async function loadSchedules() {
  if (!store.currentProjectId) return
  try {
    schedules.value = await scheduleApi.list({ project_id: store.currentProjectId })
  } catch {
    schedules.value = []  // 定时列表失败不阻塞页面主体
  }
}

function openSchedule(row: TestCase) {
  scheduleCase.value = row
  scheduleVisible.value = true
  // 已有配置则先看列表，无配置直接进新增表单
  const existing = schedules.value.filter(s => s.case_id === row.id)
  if (existing.length) {
    scheduleFormVisible.value = false
  } else {
    openScheduleForm()
  }
}

// ============ 数据集绑定 + 数据驱动执行（周期 6/7） ============

const projectDatasets = ref<DataSet[]>([])
const bindVisible = ref(false)
const bindSaving = ref(false)
const bindCase = ref<TestCase | null>(null)
const bindDatasetId = ref<number | null>(null)

async function loadDatasets(caseId: number) {
  if (!store.currentProjectId) return
  try {
    projectDatasets.value = await datasetApi.list({
      project_id: store.currentProjectId, case_id: caseId, with_rows: true,
    })
  } catch {
    projectDatasets.value = []  // 数据集加载失败不阻塞列表主体
  }
}

async function openBind(row: TestCase) {
  bindCase.value = row
  bindDatasetId.value = row.dataset_id ?? null
  await loadDatasets(row.id)
  bindVisible.value = true
}

async function saveBind() {
  if (!bindCase.value) return
  bindSaving.value = true
  try {
    await caseApi.update(bindCase.value.id, { dataset_id: bindDatasetId.value ?? null })
    bindCase.value.dataset_id = bindDatasetId.value ?? null
    ElMessage.success(bindDatasetId.value ? '已绑定数据集' : '已解绑')
    bindVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    bindSaving.value = false
  }
}

// ---------- 数据驱动执行确认面板 ----------
const ddVisible = ref(false)
const ddRunning = ref(false)
const ddCase = ref<TestCase | null>(null)
const ddDatasetId = ref<number | null>(null)
const ddRows = ref<any[]>([])
const ddColumns = ref<{ key: string; type?: string }[]>([])
const ddSelectedRows = ref<any[]>([])
const ddTableRef = ref<any>(null)

async function openDataDrivenRun(row: TestCase) {
  ddCase.value = row
  ddDatasetId.value = row.dataset_id ?? null
  await loadDatasets(row.id)
  await applyDdDataset()
  ddVisible.value = true
  // 默认全选所有行
  await nextTick()
  ddTableRef.value?.toggleAllSelection?.()
}

async function applyDdDataset() {
  const ds = projectDatasets.value.find((d) => d.id === ddDatasetId.value)
  ddRows.value = (ds?.rows as any[]) || []
  ddColumns.value = (ds?.columns as any[]) || []
  ddSelectedRows.value = ddRows.value
  checkDdDrift()
}

// 快照过期检测：执行按快照跑，与用例当前编排不一致时在弹窗内提示并支持一键同步
const ddDrift = ref<{ stale: boolean; nodes: { node_id: string; label: string; changes: string[] }[] } | null>(null)
const ddResyncing = ref(false)

async function checkDdDrift() {
  ddDrift.value = null
  if (!ddDatasetId.value) return
  try {
    ddDrift.value = await datasetApi.drift(ddDatasetId.value)
  } catch {
    // 检测失败不阻断执行流程
  }
}

async function resyncFromDialog() {
  if (!ddDatasetId.value) return
  ddResyncing.value = true
  try {
    await datasetApi.resync(ddDatasetId.value)
    ElMessage.success('已同步用例当前编排到数据集快照')
    await checkDdDrift()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '同步失败')
  } finally {
    ddResyncing.value = false
  }
}

async function onDdDatasetChange() {
  await applyDdDataset()
  await nextTick()
  ddTableRef.value?.toggleAllSelection?.()
}

async function confirmDataDrivenRun() {
  if (!ddCase.value || !ddSelectedRows.value.length) return
  ddRunning.value = true
  favicon.running()
  const msg = ElMessage({
    message: `数据驱动执行中（${ddSelectedRows.value.length} 行并行）...`,
    type: 'info',
    duration: 0,
  })
  try {
    // 后端按选行展开：N 行 → N 条记录（失败聚合成一条通知）
    const first = await caseApi.execute(ddCase.value.id, store.currentEnvId!, {
      dataset_id: ddDatasetId.value,
      row_ids: ddSelectedRows.value.map((r) => r.id),
    })
    ddVisible.value = false
    // 轮询首条记录（代表整批）；完成后去执行记录看全部
    const status = await pollOne(first.id)
    msg.close()
    if (status.status === 'success') {
      favicon.success()
      ElMessage.success(`数据驱动执行完成：首行通过（全部 ${ddSelectedRows.value.length} 条见执行记录）`)
    } else {
      favicon.failed()
      ElMessage.warning('数据驱动执行完成，存在失败行，详见执行记录')
    }
    router.push({ path: '/executions', query: { case_id: ddCase.value.id } })
  } catch (e: any) {
    msg.close()
    favicon.reset()
    ElMessage.error(e?.response?.data?.detail || e?.message || '执行失败')
  } finally {
    ddRunning.value = false
  }
}

function openScheduleForm() {
  scheduleEditingId.value = null
  scheduleForm.value = {
    env_id: store.currentEnvId ?? store.environments[0]?.id ?? null,
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
  if (!scheduleCase.value) return
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
        case_id: scheduleCase.value.id,
        env_id: f.env_id,
        schedule_type: f.schedule_type,
        interval_minutes: f.schedule_type === 'interval' ? f.interval_minutes : undefined,
        daily_time: f.schedule_type === 'daily' ? f.daily_time : undefined,
        enabled: true,
      })
      ElMessage.success('已添加定时任务')
    }
    scheduleFormVisible.value = false
    await loadSchedules()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    scheduleSaving.value = false
  }
}

async function onToggleSchedule(s: TestSchedule) {
  try {
    await scheduleApi.update(s.id, { enabled: !s.enabled })
    s.enabled = !s.enabled
    await loadSchedules()
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  }
}

async function onRunSchedule(s: TestSchedule) {
  try {
    await scheduleApi.run(s.id)
    ElMessage.success('已触发执行，结果可在执行记录查看')
    await loadSchedules()
  } catch (e: any) {
    ElMessage.error(e.message || '触发失败')
  }
}

async function onRemoveSchedule(s: TestSchedule) {
  try {
    await ElMessageBox.confirm(`确认删除定时任务「${describeSchedule(s)}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await scheduleApi.remove(s.id)
    ElMessage.success('已删除')
    await loadSchedules()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

async function onAddGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await caseGroupApi.create({
      project_id: store.currentProjectId!,
      parent_id: newGroupParentId.value,
      name: newGroupName.value.trim(),
    })
    newGroupName.value = ''
    newGroupParentId.value = null
    await loadGroups()
    ElMessage.success('已添加')
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  }
}

async function onRenameGroup(data: GroupTreeNode) {
  try {
    const { value } = await ElMessageBox.prompt('分组名称', '重命名', { inputValue: data.label })
    if (value && value !== data.label) {
      await caseGroupApi.update(data.id, { name: value })
      await loadGroups()
      ElMessage.success('已重命名')
    }
  } catch (e) {
    // cancel
  }
}

async function onDeleteGroup(data: GroupTreeNode) {
  try {
    await ElMessageBox.confirm(
      `确认删除分组「${data.label}」？\n注意：含子分组或用例时将阻止删除，请先处理`,
      '提示',
      { type: 'warning' },
    )
    await caseGroupApi.remove(data.id)
    await loadGroups()
    await load()
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.message || '删除失败')
  }
}

// 项目切换时：重置筛选并回第 1 页（统一行为，避免携带旧项目筛选）
watch(() => store.currentProjectId, () => {
  keyword.value = ''
  filterCreator.value = null
  filterUpdater.value = null
  resetPages()
  load()
  loadGroups()
  loadSchedules()
  projectDatasets.value = []  // 数据集按项目隔离，切换后按需重载
})
onMounted(() => {
  load()
  loadGroups()
  loadUsers()
  loadSchedules()
  window.addEventListener('keydown', onGlobalKey)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKey)
  // 清理所有执行轮询定时器，防止切页后继续请求
  pollTimers.forEach(t => clearTimeout(t))
  pollTimers.length = 0
})

// Ctrl+Enter：执行当前选中的用例（取第一个），无选中则提示
function onGlobalKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    if (selectedCaseIds.value.length === 0) {
      ElMessage.warning('请先勾选用例后再按 Ctrl+Enter 执行')
      return
    }
    e.preventDefault()
    const firstId = selectedCaseIds.value[0]
    const row = list.value.find((c) => c.id === firstId)
    if (row) runCase(row)
  }
}
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg);
}
/* 批量操作条（与接口管理一致） */
.bulk-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 20px;
  background: color-mix(in srgb, var(--app-primary) 7%, var(--app-card));
  border-bottom: 1px solid color-mix(in srgb, var(--app-primary) 22%, var(--app-border));
}
.bulk-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-primary);
}
.bulk-bar-enter-active,
.bulk-bar-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.bulk-bar-enter-from,
.bulk-bar-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
/* 左分组导航 + 右组内列表（master-detail） */
.group-layout {
  flex: 1;
  min-height: 0;
  display: flex;
}
.group-side {
  width: 220px;
  flex-shrink: 0;
  overflow: auto;
  padding: 12px 8px;
  background: var(--app-card);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
}
.side-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  height: 32px;
  border-radius: var(--app-radius-sm);
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  color: var(--app-text-muted);
  white-space: nowrap;
}
.side-node:hover {
  background: var(--app-hover);
  color: var(--app-text);
}
.side-node.on {
  background: var(--app-active);
  color: var(--app-primary);
  font-weight: 500;
}
.side-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
.side-cnt {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--app-text-faint);
}
.side-node.on .side-cnt {
  color: var(--app-primary);
}
.side-foot {
  margin-top: auto;
  padding: 10px 6px 2px;
  border-top: 1px solid var(--app-border);
}
.group-main {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
}
.main-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.main-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
}
.expand-icon {
  font-size: 14px;
  color: var(--app-text-muted);
  cursor: pointer; /* caret 单击展开/折叠（与整行选中分离） */
  transition: transform 0.18s ease;
}
.expand-icon.expanded {
  transform: rotate(90deg);
}
.expand-spacer {
  display: inline-block;
  width: 14px;
}
.group-icon {
  font-size: 16px;
  color: var(--app-primary);
}
.group-count {
  background: var(--app-primary);
  color: #fff;
  border-radius: 10px;
  padding: 1px 10px;
  font-size: 12px;
  font-weight: 500;
  min-width: 24px;
  text-align: center;
  margin-right: 16px;
}
.group-body {
  padding: 0 16px 12px;
}
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
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.empty-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}
.drag-handle {
  cursor: grab;
  color: var(--app-text-muted);
  font-size: 16px;
}
.drag-handle:active {
  cursor: grabbing;
}
.sortable-ghost {
  opacity: 0.4;
  background: var(--app-active) !important;
}
/* ===== 组合弹窗 ===== */
/* 批量执行配置弹窗：列表限高滚动（同数据集列编辑器做法） */
.batch-run-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-bottom: 10px;
  line-height: 1.5;
}
.batch-run-concurrency {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0;
}
.batch-run-concurrency-hint {
  font-size: 12px;
  color: var(--app-text-muted);
}
.batch-run-list {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 4px 12px;
}
.batch-run-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.batch-run-row + .batch-run-row {
  border-top: 1px solid var(--app-border);
}
.batch-run-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.batch-run-count-label {
  font-size: 12px;
  color: var(--app-text-muted);
  white-space: nowrap;
}
.batch-run-total {
  float: left;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 32px;
}

.combine-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-bottom: 10px;
  line-height: 1.5;
}
.combine-list {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  max-height: 260px;
  overflow-y: auto;
}
.combine-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--app-border);
  background: var(--el-bg-color);
}
.combine-item:last-child {
  border-bottom: none;
}
.combine-item .drag-handle {
  cursor: grab;
  color: var(--app-text-muted);
  font-size: 16px;
  flex-shrink: 0;
}
.combine-item .drag-handle:active {
  cursor: grabbing;
}
.combine-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.combine-nodes {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--app-text-muted);
}
.group-drag-tip {
  font-size: 12px;
  color: var(--app-text-muted);
  margin: 12px 0 8px;
  flex-shrink: 0;
}
/* ===== 定时任务：列表图标标识 + 弹窗 ===== */
.schedule-mark {
  color: var(--el-color-warning);
  margin-right: 4px;
  vertical-align: -2px;
}
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
/* 数据集绑定/数据驱动执行弹窗 */
.bind-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.drift-alert {
  margin-bottom: 10px;
}
.drift-node {
  font-size: 12px;
  line-height: 1.8;
}
.bind-empty {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
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
<!-- group-manage-dialog 全局样式已收敛至 style.css（原与 ApiManage 逐字符重复，两处漂移风险） -->
