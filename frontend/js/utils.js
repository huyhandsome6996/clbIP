/**
 * utils.js — Tiện ích dùng chung toàn frontend
 * ============================================
 * - fmtVND / fmtDate / fmtDateTime / timeAgo : định dạng VN
 * - debounce: gõ tìm kiếm Trie không giật lag
 * - escapeHtml: chặn XSS khi render dữ liệu động
 * - initials: tạo chữ trong avatar
 * - skeleton/empty helpers: trạng thái tải / trống đồng nhất
 * - getQueryParam, rangeDate helpers
 */
const Utils = {
  /* ---------- Tiền tệ ---------- */
  /** 2750000 → "2.750.000 ₫" */
  fmtVND(amount) {
    if (amount === null || amount === undefined || isNaN(Number(amount))) return "—";
    return new Intl.NumberFormat("vi-VN").format(Number(amount)) + " ₫";
  },
  /** 2750000 → "2.750.000" (không đơn vị, dùng trong bảng) */
  fmtNum(amount) {
    if (amount === null || amount === undefined || isNaN(Number(amount))) return "—";
    return new Intl.NumberFormat("vi-VN").format(Number(amount));
  },

  /* ---------- Ngày giờ ---------- */
  fmtDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
  },
  fmtDateTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    return (
      d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" }) +
      " " +
      d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })
    );
  },
  fmtTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  },
  /** "5 phút trước" — dùng cho feed bảng tin */
  timeAgo(value) {
    if (!value) return "";
    const diff = (Date.now() - new Date(value).getTime()) / 1000;
    if (isNaN(diff)) return "";
    if (diff < 60) return "vừa xong";
    if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
    if (diff < 604800) return `${Math.floor(diff / 86400)} ngày trước`;
    return Utils.fmtDate(value);
  },

  /* ---------- Chuỗi ---------- */
  /** "Nguyễn Nhật Nam" → "NN" (avatar initials) */
  initials(name) {
    if (!name) return "?";
    const parts = String(name).trim().split(/\s+/);
    const first = parts[0]?.[0] || "";
    const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
    return (first + last).toUpperCase() || "?";
  },
  escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  },

  /* ---------- DOM helpers ---------- */
  qs(sel, root = document) { return root.querySelector(sel); },
  qsa(sel, root = document) { return [...root.querySelectorAll(sel)]; },
  getQueryParam(name) {
    return new URLSearchParams(location.search).get(name);
  },

  /* ---------- Async ---------- */
  /**
   * debounce: gõ "ngu" → chỉ gọi API 300ms sau khi ngừng gõ.
   * Dùng cho Trie autocomplete.
   */
  debounce(fn, wait = 300) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  },

  /** Bọc async handler: bắt ApiError → toast, không để unhandled rejection. */
  guard(fn, { toastOnError = true } = {}) {
    return async function (...args) {
      try {
        return await fn.apply(this, args);
      } catch (err) {
        console.error(err);
        if (toastOnError && window.Toast) {
          Toast.error(err?.message || "Có lỗi không xác định");
        }
        throw err;
      }
    };
  },

  /* ---------- Trạng thái tải / trống / lỗi (đồng nhất mọi trang) ---------- */
  /** Chèn N hàng skeleton vào container */
  skeleton(container, rows = 4, { avatar = false } = {}) {
    if (!container) return;
    let html = "";
    for (let i = 0; i < rows; i++) {
      html += avatar
        ? `<div class="skeleton-row">
             <div class="skeleton skeleton-avatar"></div>
             <div class="skeleton-lines">
               <div class="skeleton" style="width:45%"></div>
               <div class="skeleton"></div>
             </div>
           </div>`
        : `<div class="skeleton-row">
             <div class="skeleton-lines">
               <div class="skeleton" style="width:60%"></div>
               <div class="skeleton"></div>
             </div>
           </div>`;
    }
    container.innerHTML = html;
  },

  /**
   * Trạng thái trống: icon + tiêu đề + mô tả + nút hành động (tùy chọn)
   * @param {object} opts {icon, title, desc, actionLabel, onAction}
   */
  empty(container, opts = {}) {
    if (!container) return;
    const icon = opts.icon || "inbox";
    const { title = "Chưa có dữ liệu", desc = "", actionLabel = "", onAction = null } = opts;
    container.innerHTML = `
      <div class="empty">
        <div class="empty-icon">${window.Icons ? Icons.render(icon) : ""}</div>
        <h3></h3>
        ${desc ? "<p></p>" : ""}
        ${actionLabel ? '<button class="btn btn-primary btn-sm mt-2"></button>' : ""}
      </div>`;
    container.querySelector("h3").textContent = title;
    if (desc) container.querySelector("p").textContent = desc;
    if (actionLabel) {
      const b = container.querySelector("button");
      b.textContent = actionLabel;
      if (onAction) b.addEventListener("click", onAction);
    }
  },

  /** Đổi nhãn nút sang trạng thái loading và khóa bấm. Trả hàm hoàn tác. */
  btnLoading(btn, loadingText = "Đang xử lý...") {
    if (!btn) return () => {};
    const original = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span>${loadingText}`;
    return () => {
      btn.disabled = false;
      btn.innerHTML = original;
    };
  },

  /* ---------- Badge trạng thái (map code backend → nhãn + màu) ---------- */
  badge(text, tone = "neutral") {
    return `<span class="badge badge-${tone}">${Utils.escapeHtml(text)}</span>`;
  },
};

/* Spinner mini cho nút loading */
(() => {
  const style = document.createElement("style");
  style.textContent = `
    .spinner {
      display: inline-block;
      width: 14px; height: 14px;
      border: 2px solid currentColor;
      border-right-color: transparent;
      border-radius: 50%;
      animation: spin .7s linear infinite;
      margin-right: 6px;
      vertical-align: -2px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  `;
  document.head.appendChild(style);
})();

window.Utils = Utils;
