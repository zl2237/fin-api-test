import { ElMessage } from 'element-plus'

/** 写剪贴板（ReportDetail 迁出）：navigator.clipboard 仅安全上下文（HTTPS/
 *  localhost）可用，线上以 http://IP 访问时为 undefined 直接抛错——
 * 降级隐藏 textarea + execCommand('copy') */
export async function writeClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 权限被拒等场景落入降级方案
    }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.focus()
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(ta)
  return ok
}

/** 复制并提示（成功/失败 toast）；文本由调用方序列化 */
export async function copyText(text: string, successMsg = '已复制'): Promise<void> {
  if (await writeClipboard(text)) {
    ElMessage.success(successMsg)
  } else {
    ElMessage.error('复制失败，请手动选择复制')
  }
}
