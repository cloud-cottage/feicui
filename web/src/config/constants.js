// 只放「spec 里写死的枚举 / 字段名」，不放任何业务真值。
// 依据：feicui/docs/feicui.spec.md §2.2（状态机）、§2.2/§3.1 E2（字段）、§3.1 E3（信封 6 字段）、
//       §3.1 E5（缺失清单形状）、§3.2 S-6（错误码族）。

// §2.2 job 状态机：QUEUED → RUNNING → (PAUSED) → DONE；异常分支 FAILED_PARTIAL
export const JOB_STATES = ['QUEUED', 'RUNNING', 'PAUSED', 'DONE', 'FAILED_PARTIAL']

// 仍在推进 / 需要轮询的状态（终态不轮询）
export const ACTIVE_STATES = ['QUEUED', 'RUNNING', 'PAUSED']

export const STATE_LABELS = {
  QUEUED: '排队中',
  RUNNING: '运行中',
  PAUSED: '已暂停',
  DONE: '完成',
  FAILED_PARTIAL: '部分失败',
}

// §3.1 E2 响应字段（用于原样展示 + 缺字段提示；不做任何派生估算）
export const E2_COUNTER_KEYS = ['detected', 'inserted', 'updated', 'skipped', 'ocr_empty']
export const E2_CURSOR_KEYS = ['chunk_lo', 'chunk_hi']

// §3.1 E3 分页信封 —— **6 字段**，逐字对应 S-3 的明确定义，顺序即校验顺序
export const E3_ENVELOPE_KEYS = ['items', 'page', 'limit', 'total', 'has_more', 'next_cursor']

// §3.1 E5 缺失清单 kind
export const MISSING_KINDS = [
  { value: 'image', label: '影像缺失（kind=image）' },
  { value: 'text', label: '释文缺失（kind=text）' },
]

export const MISSING_ITEM_KEYS = ['pdf_name', 'page', 'idx', 'img_path', 'reason']

// §3.2 S-6 已定义错误码族（枚举三值即可，不多造）
export const SPEC_ERROR_CODES = [400, 404, 409, 422, 500]

// 「端点尚未实现」的前端宽容判定（**不是规范口径**，见 README §4 G-5）
export const NOT_IMPLEMENTED_STATUSES = [404, 405, 501]
