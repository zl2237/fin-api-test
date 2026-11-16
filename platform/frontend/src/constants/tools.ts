/**
 * 工具箱注册表：唯一维护点。侧边栏不再随工具增长——工具型功能
 * （无状态、粘贴即用、不产生被引用实体）一律收进 /tools，新工具只需：
 * 1. views/tools/ 下加页面  2. router 加路由  3. 此表加一项。
 * 资源型功能（有 CRUD、被用例/环境引用）仍进侧边栏「系统管理」。
 *
 * 本表消费方：Toolbox 索引卡片、CommandPalette 导航项。
 */
import type { Component } from 'vue'
import { Lock, Timer, Document, Link, Stamp, MagicStick, Postcard } from '@element-plus/icons-vue'

export interface ToolMeta {
  /** 路由路径（/tools/xxx，与 router/index.ts 保持一致） */
  path: string
  name: string
  desc: string
  icon: Component
}

export const TOOLS: ToolMeta[] = [
  {
    path: '/tools/callback-verify',
    name: '回调验签',
    desc: 'RSA2 回调报文验签',
    icon: Lock,
  },
  {
    path: '/tools/timestamp',
    name: '时间戳转换',
    desc: '秒/毫秒/微秒 ↔ 日期时间',
    icon: Timer,
  },
  {
    path: '/tools/json',
    name: 'JSON 格式化',
    desc: '格式化 / 压缩 / 校验 / 键排序',
    icon: Document,
  },
  {
    path: '/tools/codec',
    name: '编解码',
    desc: 'URL / Base64',
    icon: Link,
  },
  {
    path: '/tools/hash',
    name: '哈希计算',
    desc: 'MD5 / SHA 系列',
    icon: Stamp,
  },
  {
    path: '/tools/uuid',
    name: 'UUID 生成',
    desc: '批量 v4 随机 UUID',
    icon: MagicStick,
  },
  {
    path: '/tools/jwt',
    name: 'JWT 解码',
    desc: 'header / payload 解码',
    icon: Postcard,
  },
]

/** 报告页「去验签」与回调验签页之间的报文交接键（sessionStorage，读后即焚） */
export const CALLBACK_PREFILL_KEY = 'toolbox:callback-verify-prefill'
