/**
 * toast.js — Thông báo nổi góc màn hình (Success / Error / Warning / Info)
 * =======================================================================
 * Dùng: Toast.success("Đã lưu"), Toast.error("Xảy ra lỗi"), ...
 * Mỗi toast tự hủy sau 4.2s (error 6s), đóng tay bằng nút X.
 * Đảm bảo #toast-root tồn tại: tự inject nếu thiếu.
 */
(() => {
  const ICONS = {
    success:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m9 12 2 2 4-4"/></svg>',
    error:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v4m0 4h.01"/></svg>',
    warning:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m10.29 3.86-8.53 14.14A2 2 0 0 0 3.43 21h17.14a2 2 0 0 0 1.67-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4m0 4h.01"/></svg>',
    info:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/></svg>',
  };
  const CLOSE_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';

  function ensureRoot() {
    let root = document.getElementById("toast-root");
    if (!root) {
      root = document.createElement("div");
      root.id = "toast-root";
      root.setAttribute("role", "status");
      root.setAttribute("aria-live", "polite");
      document.body.appendChild(root);
    }
    return root;
  }

  /**
   * @param {"success"|"error"|"warning"|"info"} type
   * @param {string} message Nội dung chính
   * @param {string} [title]  Tiêu đề (mặc định theo type)
   * @param {number} [ms]     Thời gian tự đóng
   */
  function show(type, message, title, ms) {
    const root = ensureRoot();
    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    const defaults = {
      success: "Thành công",
      error: "Lỗi",
      warning: "Cảnh báo",
      info: "Thông báo",
    };
    el.innerHTML = `
      <span class="toast-icon">${ICONS[type] || ICONS.info}</span>
      <div class="flex-1">
        <div class="toast-title"></div>
        <div class="toast-msg"></div>
      </div>
      <button class="toast-close" aria-label="Đóng thông báo" style="border:0;background:transparent;color:var(--tx-muted);cursor:pointer;padding:2px;">
        ${CLOSE_SVG}
      </button>`;
    el.querySelector(".toast-title").textContent = title || defaults[type] || "Thông báo";
    el.querySelector(".toast-msg").textContent = message || "";

    const close = () => {
      el.classList.add("out");
      el.addEventListener("animationend", () => el.remove(), { once: true });
    };
    el.querySelector(".toast-close").addEventListener("click", close);
    root.appendChild(el);
    setTimeout(close, ms || (type === "error" ? 6000 : 4200));
    return el;
  }

  window.Toast = {
    success: (msg, title, ms) => show("success", msg, title, ms),
    error: (msg, title, ms) => show("error", msg, title, ms),
    warning: (msg, title, ms) => show("warning", msg, title, ms),
    info: (msg, title, ms) => show("info", msg, title, ms),
  };
})();
