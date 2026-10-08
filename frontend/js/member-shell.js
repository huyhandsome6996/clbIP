/* ============================================================
 * CLB IP ĐHSP Huế 2.0 — member-shell.js (CHỈ cho 6 trang member)
 * ============================================================
 * Mục đích (audit luồng thành viên 1114efd):
 *   - MemberModal  (M07): modal chuẩn a11y dùng chung — Escape đóng,
 *     focus trap Tab/Shift+Tab, trả focus về nút mở, khóa scroll nền,
 *     dọn listener sạch. Thay 2 họ modal cũ (openModal + lp-modal)
 *     đang KHÔNG có keyboard behavior.
 *   - MemberShell  (M06): đồng bộ XP/streak/level lên mọi vị trí shell
 *     (sidebar, topbar pill, legacy header, hero/card ở home) sau khi
 *     một mutation cộng XP (check-in, chia sẻ tài liệu...) — luôn refetch
 *     `/gamification/me/` làm nguồn chuẩn, KHÔNG cộng lạc quan, KHÔNG
 *     ghi 0 khi fetch lỗi (giữ nguyên giá trị cũ).
 *
 * Phạm vi: file mới, KHÔNG đụng api.js/auth.js dùng chung với admin.
 * Nạp SAU: api.js, icons.js, toast.js, utils.js, auth.js.
 * ============================================================ */
(function () {
  "use strict";

  /* ------------------------------------------------------------
   * MemberModal (M07)
   * ------------------------------------------------------------ */
  const FOCUSABLE = [
    "a[href]", "button:not([disabled])", "input:not([disabled])",
    "select:not([disabled])", "textarea:not([disabled])",
    '[tabindex]:not([tabindex="-1"])',
  ].join(",");

  function focusables(root) {
    return Array.prototype.filter.call(
      root.querySelectorAll(FOCUSABLE),
      (el) => el.offsetParent !== null || el === document.activeElement
    );
  }

  function open(opts) {
    const { title, bodyHTML, footerHTML = "", onMount, onClose } = opts;
    const esc = window.Utils && Utils.escapeHtml ? Utils.escapeHtml : (s) => String(s);
    const opener = document.activeElement;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden"; // khóa scroll nền

    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="modal-head"><h3>${esc(title)}</h3>
          <button type="button" class="modal-close" aria-label="Đóng hộp thoại">${window.Icons ? Icons.render("x", 20) : "×"}</button></div>
        <div class="modal-body">${bodyHTML}</div>
        ${footerHTML ? `<div class="modal-foot">${footerHTML}</div>` : ""}
      </div>`;

    let closed = false;
    function close() {
      if (closed) return;
      closed = true;
      document.removeEventListener("keydown", onKeydown, true);
      backdrop.remove();
      document.body.style.overflow = prevOverflow; // trả scroll
      if (opener && document.contains(opener)) {
        try { opener.focus({ preventScroll: true }); } catch (_) { /* noop */ }
      }
      if (typeof onClose === "function") onClose();
    }

    function onKeydown(e) {
      if (closed) return;
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
        return;
      }
      if (e.key === "Tab") {
        // Focus trap: Tab/Shift+Tab luôn giữ trong modal
        const list = focusables(backdrop);
        if (list.length === 0) return;
        const first = list[0];
        const last = list[list.length - 1];
        if (e.shiftKey && (document.activeElement === first || !backdrop.contains(document.activeElement))) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && (document.activeElement === last || !backdrop.contains(document.activeElement))) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close();
    });
    backdrop.querySelectorAll(".modal-close, [data-close]").forEach((b) => {
      b.addEventListener("click", close);
    });
    document.addEventListener("keydown", onKeydown, true);
    document.body.appendChild(backdrop);

    // Focus phần tử hợp lý: [data-autofocus] → input → nút chính → modal
    const modalEl = backdrop.querySelector(".modal");
    modalEl.tabIndex = -1;
    const target =
      backdrop.querySelector("[data-autofocus]") ||
      backdrop.querySelector(".modal-body input, .modal-body textarea, .modal-body select") ||
      backdrop.querySelector(".modal-foot .btn-primary, .modal-close");
    if (target) target.focus({ preventScroll: true });
    else modalEl.focus();

    if (typeof onMount === "function") onMount(backdrop, close);
    return { el: backdrop, close };
  }

  /* ------------------------------------------------------------
   * MemberShell (M06) — XP/streak sync
   * ------------------------------------------------------------ */
  let syncInFlight = null;

  function paint(me) {
    if (!me) return;
    const $ = (id) => document.getElementById(id);
    const fmt = (n) => (window.Utils && Utils.fmtNum ? Utils.fmtNum(n) : String(n));
    const xp = Number(me.xp ?? me.xp_points ?? 0);
    const level = Number(me.level ?? me.current_level ?? 1);
    const streak = Number(me.streak_count ?? 0);
    const lp = me.level_progress || null;

    // Sidebar mini-profile
    if ($("sb-level")) {
      $("sb-level").textContent = `Lv.${level}`;
    }
    if ($("sb-xp")) {
      $("sb-xp").textContent = lp && !lp.max_level
        ? `${fmt(xp)} XP · còn ${fmt(lp.xp_to_next)} lên Lv.${lp.current_level + 1}`
        : `${fmt(xp)} XP · cấp tối đa`;
    }
    // Legacy bridge (ẩn trên shell 2.0 nhưng vẫn tồn tại trong DOM)
    if ($("me-level")) {
      $("me-level").textContent = `Level ${level} · ${fmt(xp)} XP`;
    }
    // Topbar pills
    if ($("pill-streak")) {
      if (streak > 0) {
        $("pill-streak").hidden = false;
        if ($("pill-streak-text")) $("pill-streak-text").textContent = `${streak} ngày chuyên cần`;
      }
    }
    if ($("pill-xp")) {
      $("pill-xp").hidden = false;
      if ($("pill-xp-text")) $("pill-xp-text").textContent = `${fmt(xp)} XP`;
    }
    // Home: hero streak + member card
    if ($("hero-streak-text")) $("hero-streak-text").textContent = `${streak} ngày 🔥`;
    if ($("card-level")) $("card-level").textContent = `Level ${level}`;
    if ($("card-xp")) $("card-xp").textContent = `${fmt(xp)} XP`;

    // Đồng bộ cached user (/auth/me) để auth.js không vẽ số cũ khi render lại
    try {
      const cached = window.Auth && Auth.cachedUser ? Auth.cachedUser() : null;
      if (cached && window.localStorage) {
        const KEY = "clbip_user_info";
        const raw = localStorage.getItem(KEY);
        if (raw) {
          const u = JSON.parse(raw);
          if (u && (u.id === cached.id || u.email === cached.email)) {
            u.xp_points = xp;
            u.current_level = level;
            u.streak_count = streak;
            localStorage.setItem(KEY, JSON.stringify(u));
          }
        }
      }
    } catch (_) { /* localStorage lỗi — bỏ qua, không chặn UI */ }
  }

  async function refreshGamification() {
    if (syncInFlight) return syncInFlight; // chống double-fetch khi bấm liên tục
    syncInFlight = (async () => {
      try {
        const me = await ApiClient.get("/gamification/me/");
        paint(me);
        return me;
      } catch (_) {
        // LỖI FETCH: giữ nguyên số cũ trên shell — KHÔNG ghi 0 đè (M06)
        return null;
      } finally {
        syncInFlight = null;
      }
    })();
    return syncInFlight;
  }

  window.MemberModal = { open };
  window.MemberShell = { refreshGamification, paint };
})();
