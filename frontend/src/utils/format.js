import dayjs from "dayjs";

// 通用日期时间格式化工具
// 注意：dayjs 版本与原页面内实现保持一致，未对空值做兜底（空值行为与 dayjs 相同）

/** YYYY-MM-DD HH:mm:ss */
export const formatDateTime = (value) =>
  dayjs(value).format("YYYY-MM-DD HH:mm:ss");

/** YYYY-MM-DD HH:mm */
export const formatDateMinute = (value) =>
  dayjs(value).format("YYYY-MM-DD HH:mm");

/**
 * 按浏览器/指定 locale 输出本地化日期时间（Date.prototype.toLocaleString）
 * @param {string|number|Date} value
 * @param {string} fallback 空值时的显示
 * @param {string} [locales] 如 "zh-CN" / "en-US"，不传使用浏览器默认
 */
export const formatLocaleDateTime = (value, fallback = "-", locales) =>
  value ? new Date(value).toLocaleString(locales) : fallback;

/** el-table-column :formatter 用：本地化日期时间，空值显示空字符串 */
export const localeDateTimeFormatter = (row, column, cellValue) =>
  formatLocaleDateTime(cellValue, "");
