import { describe, expect, it } from 'vitest'
import { extractCurlData, parseFormString, parseImportText } from '../importPayload'

describe('parseFormString', () => {
  it('a=1&b=2 解析为扁平 dict，值字符串化', () => {
    expect(parseFormString('wd=BL123&page=1&size=15')).toEqual({
      wd: 'BL123', page: '1', size: '15',
    })
  })

  it('方括号 key 保持整体（平台表单类请求的参数路径口径）', () => {
    expect(parseFormString('id=367144804871570143&feedbacks[entrust_7][feedback]=&feedbacks[entrust_7][error_code]=')).toEqual({
      id: '367144804871570143',
      'feedbacks[entrust_7][feedback]': '',
      'feedbacks[entrust_7][error_code]': '',
    })
  })

  it('URL 编码值解码、+ 转空格、非法 % 序列原样保留', () => {
    expect(parseFormString('q=%E4%B8%AD%E6%96%87&s=hello+world&bad=100%')).toEqual({
      q: '中文', s: 'hello world', bad: '100%',
    })
  })

  it('换行分隔兼容；无 = 段与空 key 跳过', () => {
    expect(parseFormString('a=1\nb=2\r\nc=3&&=x')).toEqual({ a: '1', b: '2', c: '3' })
  })

  it('值中含 = 只按首个 = 分割', () => {
    expect(parseFormString('expr=1+2=3')).toEqual({ expr: '1 2=3' })
  })
})

describe('extractCurlData', () => {
  it('提取 --data-raw 单引号载荷（含 & 不被截断）', () => {
    const cmd = `curl 'https://test.21eline.com/SyncLogorder/check_deal.html' -H 'Content-Type: application/x-www-form-urlencoded' --data-raw 'id=123&verify_cmt='`
    expect(extractCurlData(cmd)).toBe('id=123&verify_cmt=')
  })

  it('多个 -d 段按 & 拼接（curl 真实语义）', () => {
    expect(extractCurlData(`curl http://x -d 'a=1' -d 'b=2'`)).toBe('a=1&b=2')
  })

  it('-F/--form multipart 载荷提取', () => {
    expect(extractCurlData(`curl http://x -F 'id=123' --form 'type=8'`)).toBe('id=123&type=8')
  })

  it('无 data 参数返回 null；-H 的 = 不误伤', () => {
    expect(extractCurlData(`curl 'http://x?a=1' -H 'X-Token: abc=def'`)).toBeNull()
  })
})

describe('parseImportText', () => {
  it('JSON 对象直接解析', () => {
    expect(parseImportText('  {"bl_no":"SMOK1","amount":100} ')).toEqual({
      format: 'json', data: { bl_no: 'SMOK1', amount: 100 },
    })
  })

  it('JSON 数组直接解析', () => {
    expect(parseImportText('[{"a":1}]')).toEqual({ format: 'json', data: [{ a: 1 }] })
  })

  it('坏 JSON 返回解析失败文案', () => {
    const r = parseImportText('{"a":}')
    expect('error' in r).toBe(true)
  })

  it('cURL 表单载荷：format=curl + 扁平 dict', () => {
    const r = parseImportText(`curl 'https://x/y.html' --data-raw 'wd=BL123&feedbacks[k][v]='`)
    expect(r).toEqual({
      format: 'curl',
      data: { wd: 'BL123', 'feedbacks[k][v]': '' },
    })
  })

  it('cURL JSON 载荷：format=curl + 对象', () => {
    const r = parseImportText(`curl 'https://x' --data-raw '{"order_no":"YHL123"}'`)
    expect(r).toEqual({ format: 'curl', data: { order_no: 'YHL123' } })
  })

  it('cURL 无 data 载荷报错', () => {
    const r = parseImportText(`curl 'https://x?a=1'`)
    expect('error' in r).toBe(true)
  })

  it('裸表单串：format=form', () => {
    expect(parseImportText('id=367144804871570143&hope_financing_cny=0')).toEqual({
      format: 'form',
      data: { id: '367144804871570143', hope_financing_cny: '0' },
    })
  })

  it('空文本与无法识别格式报错', () => {
    expect('error' in parseImportText('   ')).toBe(true)
    expect('error' in parseImportText('hello world')).toBe(true)
  })
})
