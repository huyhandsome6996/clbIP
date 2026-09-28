/**
 * api.js — HTTP Client tập trung cho CLB IP ĐHSP Huế 2.0
 * =====================================================
 * Nhiệm vụ:
 *  - Gắn Bearer Token vào mọi request.
 *  - Tự động Refresh Token ĐÚNG 1 LẦN khi gặp 401 (single-flight:
 *    nhiều request lỗi 401 đồng thời chỉ tạo đúng 1 request refresh).
 *  - Chuẩn hóa envelope {success, data, message, errors} từ backend.
 *  - Báo lỗi tiếng Việt thân thiện qua ApiError.
 *
 * API base resolution:
 *  1. Trang được phục vụ từ Django (http://127.0.0.1:8000/frontend/...)
 *     → dùng cùng origin: `<origin>/api/v1`.
 *  2. Trang mở bằng file:// hoặc server tĩnh khác (Live Server :5500…)
 *     → fallback `http://127.0.0.1:8000/api/v1`.
 *  3. Có thể override thủ công: localStorage.setItem("clbip_api_base", "...").
 */
const API_BASE = (() => {
  const override = localStorage.getItem("clbip_api_base");
  if (override) return override.replace(/\/+$/, "");
  if (location.protocol === "http:" || location.protocol === "https:") {
    return `${location.origin}/api/v1`;
  }
  return "http://127.0.0.1:8000/api/v1";
})();

class ApiError extends Error {
  /**
   * @param {string} message  Thông báo hiển thị cho người dùng
   * @param {number} status   HTTP status code (0 = network lỗi)
   * @param {object|null} errors  Chi tiết lỗi field từ backend (DRF format)
   * @param {object|null} payload Toàn bộ envelope gốc (debug)
   */
  constructor(message, status = 0, errors = null, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errors = errors;
    this.payload = payload;
  }
}

class ApiClient {
  /* ---------------- Token storage ---------------- */
  static getAccessToken() {
    return localStorage.getItem("clbip_access_token");
  }
  static getRefreshToken() {
    return localStorage.getItem("clbip_refresh_token");
  }
  static setTokens(access, refresh) {
    if (access) localStorage.setItem("clbip_access_token", access);
    if (refresh) localStorage.setItem("clbip_refresh_token", refresh);
  }
  static clearTokens() {
    localStorage.removeItem("clbip_access_token");
    localStorage.removeItem("clbip_refresh_token");
    localStorage.removeItem("clbip_user_info");
  }

  /* ---------------- Refresh (single-flight) ---------------- */
  static #refreshPromise = null;

  /** Làm mới access token. Trả true nếu thành công. */
  static async refreshToken() {
    // Có refresh đang chạy → dùng lại kết quả (tránh refresh 2 lần)
    if (ApiClient.#refreshPromise) return ApiClient.#refreshPromise;

    ApiClient.#refreshPromise = (async () => {
      try {
        const refresh = this.getRefreshToken();
        if (!refresh) return false;
        const res = await fetch(`${API_BASE}/auth/token/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh }),
        });
        if (!res.ok) return false;
        const json = await res.json();
        const data = json && json.data ? json.data : json;
        if (!data || !data.access) return false;
        this.setTokens(data.access, data.refresh || refresh);
        return true;
      } catch (e) {
        console.error("Lỗi làm mới token:", e);
        return false;
      } finally {
        ApiClient.#refreshPromise = null;
      }
    })();

    return ApiClient.#refreshPromise;
  }

  /** Bị đẩy về login khi refresh thất bại (token chết / bị khóa). */
  static forceLogout() {
    this.clearTokens();
    const isMemberPage = location.pathname.includes("/member/");
    window.location.href = `/frontend/login.html?expired=1&next=${encodeURIComponent(location.pathname)}`;
    void isMemberPage; // giữ cho log gọn khi debug
  }

  /* ---------------- Core request ---------------- */
  /**
   * Gọi API và trả về `data` (đã unwrap envelope).
   * @param {string} endpoint  Bắt đầu bằng "/", ví dụ "/auth/me/"
   * @param {object} options   Fetch options (method, body, headers, raw...)
   * @param {boolean} options.raw  Trả nguyên envelope thay vì unwrap
   */
  static async request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    options.headers = { ...(options.headers || {}) };

    const token = this.getAccessToken();
    if (token) options.headers["Authorization"] = `Bearer ${token}`;

    if (!(options.body instanceof FormData) && !options.headers["Content-Type"]) {
      options.headers["Content-Type"] = "application/json";
    }

    let response = await fetch(url, options);

    // 401 → thử refresh đúng 1 lần rồi gọi lại
    if (response.status === 401 && this.getRefreshToken() && !endpoint.includes("/auth/token/")) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        options.headers["Authorization"] = `Bearer ${this.getAccessToken()}`;
        response = await fetch(url, options);
      } else {
        this.forceLogout();
        throw new ApiError("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại", 401);
      }
    }

    // Parse JSON an toàn (204 / server chết → không có body)
    let envelope = null;
    try { envelope = await response.json(); } catch { envelope = null; }

    if (!response.ok) {
      const message =
        (envelope && (envelope.message || envelope.detail)) ||
        this.#defaultError(response.status);
      throw new ApiError(message, response.status, envelope?.errors || null, envelope);
    }

    if (options.raw) return envelope;
    return envelope && typeof envelope === "object" && "success" in envelope
      ? envelope.data
      : envelope;
  }

  static #defaultError(status) {
    switch (status) {
      case 0:    return "Không kết nối được máy chủ. Kiểm tra backend đã chạy chưa.";
      case 400:  return "Dữ liệu gửi lên không hợp lệ.";
      case 401:  return "Phiên đăng nhập hết hạn hoặc không hợp lệ.";
      case 403:  return "Bạn không có quyền thực hiện thao tác này.";
      case 404:  return "Không tìm thấy dữ liệu yêu cầu.";
      case 409:  return "Dữ liệu xung đột, có thể đã được thực hiện trước đó.";
      case 429:  return "Bạn thao tác quá nhanh, vui lòng chờ chút rồi thử lại.";
      case 500:  return "Lỗi máy chủ, vui lòng thử lại sau.";
      default:   return `Có lỗi xảy ra (HTTP ${status}).`;
    }
  }

  /* ---------------- REST helpers ---------------- */
  static get(endpoint, params = null, options = {}) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request(endpoint + qs, { method: "GET", ...options });
  }
  static post(endpoint, body = null, options = {}) {
    return this.request(endpoint, {
      method: "POST",
      body: body instanceof FormData ? body : JSON.stringify(body),
      ...options,
    });
  }
  static patch(endpoint, body = null, options = {}) {
    return this.request(endpoint, {
      method: "PATCH",
      body: body instanceof FormData ? body : JSON.stringify(body),
      ...options,
    });
  }
  static put(endpoint, body = null, options = {}) {
    return this.request(endpoint, {
      method: "PUT",
      body: body instanceof FormData ? body : JSON.stringify(body),
      ...options,
    });
  }
  static delete(endpoint, options = {}) {
    return this.request(endpoint, { method: "DELETE", ...options });
  }

  /**
   * GET danh sách có phân trang chuẩn backend.
   * @returns {Promise<{items: Array, pagination: object}>}
   */
  static async getList(endpoint, params = null) {
    const data = await this.get(endpoint, params);
    if (Array.isArray(data)) return { items: data, pagination: null };
    return {
      items: data?.items || [],
      pagination: data?.pagination || null,
    };
  }

  /** Đọc blob (file Excel / tài liệu) rồi tải xuống máy. */
  static async download(endpoint, filename = "download", params = null) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    const res = await fetch(`${API_BASE}${endpoint}${qs}`, {
      headers: { Authorization: `Bearer ${this.getAccessToken()}` },
    });
    if (!res.ok) throw new ApiError(this.#defaultError(res.status), res.status);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
}

window.API_BASE = API_BASE;
window.ApiClient = ApiClient;
window.ApiError = ApiError;
