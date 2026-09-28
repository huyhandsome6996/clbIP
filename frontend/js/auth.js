/**
 * auth.js — Quản lý phiên đăng nhập & RBAC điều hướng
 * ===================================================
 * - login(email, password): gọi /auth/token/, lưu access+refresh+user_info
 * - currentUser(): đọc cache từ localStorage (fallback /auth/me/)
 * - requireAuth / requireRole: gác trang, đẩy về login hoặc trang đúng role
 * - logout(): gọi refresh blacklist (tốt nhất) rồi xóa session cục bộ
 *
 * RBAC:
 *   ADMIN, BCN  → /frontend/admin/dashboard.html
 *   MEMBER      → /frontend/member/home.html
 */
const Auth = {
  ROLE_HOME: {
    ADMIN: "/frontend/admin/dashboard.html",
    BCN: "/frontend/admin/dashboard.html",
    MEMBER: "/frontend/member/home.html",
  },

  /** Đăng nhập bằng email + mật khẩu. Trả về user info. */
  async login(email, password) {
    const data = await ApiClient.request("/auth/token/", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    ApiClient.setTokens(data.access, data.refresh);
    localStorage.setItem("clbip_user_info", JSON.stringify(data.user || {}));
    return data.user || {};
  },

  /** Thông tin user đã cache (đồng bộ, có thể null). */
  cachedUser() {
    try {
      return JSON.parse(localStorage.getItem("clbip_user_info") || "null");
    } catch {
      return null;
    }
  },

  /** Lấy user từ server /auth/me/ (kể cả refresh cache). */
  async me() {
    const data = await ApiClient.get("/auth/me/");
    localStorage.setItem("clbip_user_info", JSON.stringify(data || {}));
    return data;
  },

  /** True nếu user là Ban chủ nhiệm / Quản trị. */
  isBoard(user = null) {
    const u = user || this.cachedUser();
    const role = u?.role;
    return role === "ADMIN" || role === "BCN";
  },

  /**
   * Gác trang: chưa đăng nhập → login.html?next=...
   * @param {string[]} roles  Danh sách role được phép, ví dụ ["ADMIN","BCN"]
   */
  async requireRole(roles = null) {
    if (!ApiClient.getAccessToken()) {
      window.location.href = `/frontend/login.html?next=${encodeURIComponent(location.pathname)}`;
      throw new Error("unauthenticated");
    }
    let user = this.cachedUser();
    // Login response không chứa xp/level/streak → luôn làm mới hồ sơ 1 lần
    // để header "Level ? · 0 XP" không bị treo giá trị cũ.
    try {
      user = await this.me();
    } catch (e) {
      // Lỗi /me/ → nếu vẫn có cache thì tiếp tục với cache, không thì đuổi về login
      if (!user) {
        ApiClient.clearTokens();
        window.location.href = "/frontend/login.html?expired=1";
        throw new Error("unauthenticated");
      }
    }
    if (roles && !roles.includes(user.role)) {
      // Đúng người, sai cửa → về đúng trang nhà theo role
      window.location.href = this.ROLE_HOME[user.role] || "/frontend/login.html";
      throw new Error("forbidden");
    }
    this.updateMemberHeader(user);
    return user;
  },

  /**
   * Cập nhật header member chuẩn (me-avatar / me-name / me-level) nếu trang
   * có các id này — gọi sau khi hồ sơ được làm mới, tránh giá trị stale.
   */
  updateMemberHeader(user) {
    if (!user) return;
    const av = document.getElementById("me-avatar");
    if (av) av.textContent = Utils.initials(user.ho_ten || user.email);
    const nm = document.getElementById("me-name");
    if (nm) nm.textContent = user.ho_ten || user.email || "";
    const lv = document.getElementById("me-level");
    if (lv) {
      const lvText =
        user.current_level != null
          ? `Level ${user.current_level} · ${user.xp_points ?? 0} XP`
          : "Ban chủ nhiệm";
      lv.textContent = lvText;
    }
  },

  /** Chuyển hướng người đã đăng nhập khỏi trang login về trang nhà. */
  redirectIfLoggedIn() {
    if (!ApiClient.getAccessToken()) return false;
    const user = this.cachedUser();
    if (user?.role && this.ROLE_HOME[user.role]) {
      window.location.replace(this.ROLE_HOME[user.role]);
      return true;
    }
    return false;
  },

  /** Đăng xuất: blacklist refresh token (nếu còn), xóa session, về login. */
  async logout() {
    const refresh = ApiClient.getRefreshToken();
    try {
      if (refresh) {
        await fetch(`${API_BASE}/auth/token/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh }),
        }).catch(() => {}); // blacklist endpoint = refresh rồi discard; lỗi bỏ qua
      }
    } finally {
      ApiClient.clearTokens();
      window.location.href = "/frontend/login.html";
    }
  },
};

window.Auth = Auth;
