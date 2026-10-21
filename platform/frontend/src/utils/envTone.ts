/** 环境色阶：按环境名推断 test / pre / prod 三档语义色 + 兜底 unknown。
 *  环境是测试平台最关键的业务维度（在哪个环境执行、是否高风险），
 *  列表与报告页统一用色点标识，prod 额外配警示底色。
 *  名称匹配从大到小：先 pre（preprod 属预发），再 prod，最后 test/dev 族。 */

export type EnvTone = 'test' | 'pre' | 'prod' | 'unknown'

const PRE_RE = /pre|staging|stage|uat|gray|grey|灰度|预发|预生产/
const PROD_RE = /prod|production|线上|生产/
const TEST_RE = /test|dev|qa|sit|fat|uat2?[^a-z]|联调|测试|开发/

export function envTone(name?: string | null): EnvTone {
  const s = (name || '').toLowerCase()
  if (!s) return 'unknown'
  if (PRE_RE.test(s)) return 'pre'
  if (PROD_RE.test(s)) return 'prod'
  if (TEST_RE.test(s)) return 'test'
  return 'unknown'
}
