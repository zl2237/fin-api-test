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
    desc: '粘贴回调报文，按 Fastjson2 规则重建待签串，RSA2 公钥验签（密钥取环境加密配置）',
    icon: Lock,
  },
  {
    path: '/tools/timestamp',
    name: '时间戳转换',
    desc: 'Unix 秒/毫秒/微秒 ↔ 日期时间互转，ISO / UTC / 相对时间多格式对照',
    icon: Timer,
  },
  {
    path: '/tools/json',
    name: 'JSON 格式化',
    desc: '格式化 / 压缩 / 校验，错误定位到行列；可递归键排序（验签原串排查配套）',
    icon: Document,
  },
  {
    path: '/tools/codec',
    name: '编解码',
    desc: 'URL 编解码、Base64 编解码（UTF-8 安全，支持 URL-safe 变体）',
    icon: Link,
  },
  {
    path: '/tools/hash',
    name: '哈希计算',
    desc: 'MD5 / SHA-1 / SHA-256 / SHA-512，与后端表达式 md5() 同口径',
    icon: Stamp,
  },
  {
    path: '/tools/uuid',
    name: 'UUID 生成',
    desc: '批量生成 v4 随机 UUID，可去横杠 / 转大写',
    icon: MagicStick,
  },
  {
    path: '/tools/jwt',
    name: 'JWT 解码',
    desc: '解码 header / payload，exp / iat / nbf 时间声明转可读时间（仅解码不验签）',
    icon: Postcard,
  },
]

/** 报告页「去验签」与回调验签页之间的报文交接键（sessionStorage，读后即焚） */
export const CALLBACK_PREFILL_KEY = 'toolbox:callback-verify-prefill'
