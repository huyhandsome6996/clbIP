# PROMPT THIẾT KẾ GOOGLE STITCH AI: MÀN HÌNH ĐĂNG NHẬP & QUÊN MẬT KHẨU (PHONG CÁCH EDUCARELINK)

> **Mục tiêu**: Thiết kế lại toàn bộ màn hình **Đăng nhập & Quên mật khẩu** của CLB IP ĐHSP Huế 2.0.
> **Cảm hứng kiến trúc**: Học tập cấu trúc Split-Screen (2 cột cân xứng) từ **EduCareLink**, tối giản, sáng sủa, ấm áp, tương phản cao, loại bỏ hoàn toàn các icon và emoji rườm rà vô bổ.
> **Hệ màu chủ đạo**: Tông xuyệt tông theo **Logo CLB IP** — Deep Tech Navy (`#0A1931`), Binary Electric Cyan (`#0099FF`), nền Canvas Slate sáng tinh tế (`#F8FAFC`), và bề mặt thẻ trắng tinh khiết (`#FFFFFF`).

---

## NỘI DUNG PROMPT CHO STITCH AI (SAO CHÉP TOÀN BỘ ĐOẠN BÊN DƯỚI)

```markdown
Role & Task:
You are an elite Lead Product Designer and Design Systems Architect at Google Stitch. Design a production-ready, ultra-clean, high-contrast responsive Web Login & Password Reset interface for "Cổng Đăng Nhập CLB IP ĐHSP Huế 2.0" (Informatics & Pedagogy Club, Faculty of Informatics, Hue University of Education).

Design Philosophy & Style Guidelines (Faithfully Inspired by EduCareLink):
1. Architecture Model:
   - Split-screen layout (Left Panel: 50% width inspirational brand showcase with high-contrast dark navy backdrop; Right Panel: 50% width ultra-clean, warm and accessible form canvas).
   - On tablet & mobile (< 1024px): Seamlessly collapse to a single clean column, prioritizing the form with a compact top brand header.
2. Color Palette (Strictly Ton-Sur-Ton with the Binary Club Logo):
   - Primary Brand (Deep Tech Navy): #0A1931 (Deep Academic Navy for maximum authority, legibility, and high contrast).
   - Secondary Brand (Navy Depth): #0F254E (Mid navy for subtle gradient transitions).
   - Electric Binary Accent: #0099FF / #00A3FF (The exact bright cyan from the 0s and 1s of the club logo).
   - Soft Background Tint: #F8FAFC (Slate-50, clean, bright and comfortable to read, zero eye strain).
   - Surface White: #FFFFFF (Crisp elevated white surface for the card).
   - Borders & Dividers: #E2E8F0 (Slate-200, crisp hairline borders).
   - Text Hierarchy:
     * Headings & Primary Text: #0A1931 (Deep navy, solid contrast ratio > 12:1).
     * Secondary Text: #475569 (Slate-600, clean, easily legible).
     * Muted / Placeholder Text: #94A3B8 (Slate-400).
     * Error State: #DC2626 (Red-600) with soft light red background #FEF2F2.
     * Focus Glow: Focus ring #0099FF with 20% opacity.
3. Typography:
   - Headlines & Action Buttons: 'Manrope', sans-serif (weights 700, 800) with tight tracking (-0.02em).
   - Form Inputs, Labels & Explanatory Copy: 'Plus Jakarta Sans', sans-serif (weights 400, 500, 600, 700).
4. Zero Gimmicks & High Usability:
   - STRICT RULE: NO childish emojis (no 👋, 🔥, 🎉, 🚀, etc.).
   - Minimalist, purpose-driven Google Material Symbols Outlined ONLY (e.g., 'mail', 'lock', 'visibility', 'arrow_back', 'verified_user').
   - High visual contrast, large click targets (minimum 48px height for all inputs and buttons).

================================================================================
LAYOUT STRUCTURE & SECTION SPECIFICATIONS
================================================================================

1. LEFT PANEL: BRAND SHOWCASE & COMMUNITY PILLARS (Desktop Only, lg:flex, 50% width)
- Background: Gradient from #0A1931 to #0F254E with subtle ambient soft circular blurs (opacity 6% white and opacity 10% cyan blobs in the background, like EduCareLink's blob-1 and blob-2).
- Padding & Structure: p-12 xl:p-16 flex flex-col justify-between min-h-screen relative overflow-hidden text-white.
- Top Header:
  * Back to Homepage Link: A clean text link "← Quay lại trang chủ" (href="/" or "/frontend/landing.html") with text-white/80 hover:text-white font-semibold text-sm transition-colors.
  * Brand Identity Row:
    - Circular logo badge: 48px x 48px white circular badge containing the club logo (/frontend/assets/logo.png).
    - Club title: "CLB IP ĐH SƯ PHẠM HUẾ" (Manrope bold 16px tracking-wide) + sub-badge "Khoa Tin học".
- Middle Content (Hero Value Pitch):
  * Main Headline: "Nơi Đam Mê Lập Trình<br/><span class="text-[#38BDF8]">Gặp Gỡ Nghiệp Vụ Sư Phạm</span>" (Manrope font-extrabold text-4xl xl:text-5xl leading-[1.2] mb-4 text-white).
  * Supporting Paragraph: "Cổng điều hành và học tập số hóa dành riêng cho Ban chủ nhiệm và toàn thể thành viên CLB Tin học & Sư phạm, Trường ĐH Sư phạm — Đại học Huế." (text-white/80 text-base leading-relaxed mb-8 max-w-lg).
  * 3 Feature Highlight Cards (Direct EduCareLink layout lineage):
    - Stacked vertically, each card has bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/10 flex items-start gap-4 transition-all hover:bg-white/15:
      1. Card 1: Icon 'radar' (in 40px rounded-lg bg-white/20 container)
         - Title: "Điểm danh GPS Haversine" (text-white font-bold text-sm mb-0.5).
         - Description: "Xác thực vị trí check-in chuẩn xác trong bán kính phòng Lab 302A." (text-white/70 text-xs leading-relaxed).
      2. Card 2: Icon 'workspace_premium' (in 40px rounded-lg bg-white/20 container)
         - Title: "Bảng vàng & Điểm tích lũy XP" (text-white font-bold text-sm mb-0.5).
         - Description: "Đua top thi đấu thuật toán và ghi nhận đóng góp học thuật minh bạch." (text-white/70 text-xs leading-relaxed).
      3. Card 3: Icon 'menu_book' (in 40px rounded-lg bg-white/20 container)
         - Title: "Kho học liệu & Đề thi số hóa" (text-white font-bold text-sm mb-0.5).
         - Description: "Tìm kiếm tức thời cấu trúc dữ liệu, bài giảng và giáo án STEM chuyên sâu." (text-white/70 text-xs leading-relaxed).
- Bottom Footer:
  * Text: "© 2026 CLB IP — Trường Đại học Sư phạm, Đại học Huế. Bảo lưu mọi quyền." (text-white/40 text-xs font-normal).

--------------------------------------------------------------------------------

2. RIGHT PANEL: AUTHENTICATION FORM CANVAS (50% width on Desktop, Full Width on Mobile)
- Background: Warm, ultra-clean #F8FAFC (Slate-50).
- Container: flex flex-col justify-center items-center p-6 sm:p-12 min-h-screen.
- Mobile Brand Header (Visible only on < 1024px screen sizes):
  * Centered row with 40px circular club logo + "CLB IP ĐHSP Huế 2.0" in deep navy font-bold text.
- Form Card Wrapper:
  * max-w-[440px] w-full bg-white rounded-2xl border border-slate-200/80 p-8 sm:p-10 shadow-[0_10px_35px_rgba(10,25,49,0.05)].
- Card Header:
  * Back link for mobile: "← Về trang chủ CLB" (text-xs font-semibold text-slate-500 hover:text-slate-800 mb-4 inline-block lg:hidden).
  * Title: "Đăng nhập Cổng sinh viên" (Manrope bold 26px text-[#0A1931] tracking-tight mb-2).
  * Subtitle: "Sử dụng tài khoản email CLB do Ban chủ nhiệm cấp để truy cập hệ thống." (text-sm text-slate-600 leading-relaxed mb-6).
- Notification / Alert Box (#login-alert):
  * Hidden by default (class="hidden").
  * When visible: flex items-start gap-3 p-3.5 rounded-xl border border-blue-200 bg-blue-50 text-blue-900 text-sm font-medium mb-5.
  * Structure: <span id="login-alert-icon" class="material-symbols-outlined text-blue-600 text-lg">info</span> <span id="login-alert-text">...</span>
- Form Elements (#login-form):
  * Field 1: Email Address
    - Label: "Email thành viên" (text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5 block) with red star <span class="text-red-500">*</span>.
    - Input Container (relative):
      * Leading icon: <span class="absolute left-3.5 top-1/2 -translate-y-1/2 material-symbols-outlined text-slate-400 text-xl">mail</span>
      * Input tag: <input id="email" name="email" type="email" placeholder="ten@clbip.vn" class="w-full pl-11 pr-4 py-3 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[#0099FF] focus:ring-2 focus:ring-[#0099FF]/20 hover:border-slate-400 transition-all font-medium" required autocomplete="email" />
      * Field Error Message: <p id="email-error" class="hidden text-xs text-red-600 mt-1.5 font-medium"></p>
  * Field 2: Password
    - Label: "Mật khẩu" (text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5 block) with red star <span class="text-red-500">*</span>.
    - Input Container (relative):
      * Leading icon: <span class="absolute left-3.5 top-1/2 -translate-y-1/2 material-symbols-outlined text-slate-400 text-xl">lock</span>
      * Input tag: <input id="password" name="password" type="password" placeholder="••••••••" class="w-full pl-11 pr-11 py-3 bg-white border border-slate-300 rounded-xl text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-[#0099FF] focus:ring-2 focus:ring-[#0099FF]/20 hover:border-slate-400 transition-all font-medium" required autocomplete="current-password" />
      * Trailing visibility toggle: <button id="toggle-pw" type="button" aria-label="Hiện mật khẩu" class="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"><span id="toggle-pw-icon" class="material-symbols-outlined text-xl">visibility</span></button>
      * Field Error Message: <p id="password-error" class="hidden text-xs text-red-600 mt-1.5 font-medium"></p>
  * Utility Row:
    - Left: Note / Remember indicator: "Tài khoản bảo mật 2 lớp".
    - Right: Forgot Password Trigger: <button id="link-forgot" type="button" class="text-sm font-bold text-[#0099FF] hover:text-[#0A1931] hover:underline cursor-pointer transition-colors">Quên mật khẩu?</button>
  * Submit Button (#btn-login):
    - Full width, min-h-[48px] rounded-xl bg-[#0A1931] hover:bg-[#0099FF] text-white font-bold text-sm shadow-md hover:shadow-lg transition-all flex items-center justify-center gap-2 cursor-pointer.
    - Label: "Đăng nhập Cổng sinh viên" with icon 'arrow_forward'.
- Card Footer Note:
  * text-center text-xs text-slate-500 mt-6 leading-relaxed:
    "Chưa có tài khoản thành viên? Tìm hiểu đợt tuyển quân tại <a href='/' class='text-[#0099FF] font-bold hover:underline'>Trang chủ CLB IP</a>."

--------------------------------------------------------------------------------

3. INTERACTIVE 3-STEP PASSWORD RESET MODAL (#pw-modal)
- Backdrop: fixed inset-0 z-50 bg-[#0A1931]/60 backdrop-blur-sm flex items-center justify-center p-4.
- Modal Box: max-w-[460px] w-full bg-white rounded-2xl border border-slate-200 shadow-2xl p-6 sm:p-8 relative.
- Modal Header:
  * Close button: <button id="pw-modal-close" class="absolute top-5 right-5 text-slate-400 hover:text-slate-700 p-1 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"><span class="material-symbols-outlined text-xl">close</span></button>
  * Title: "Đặt lại mật khẩu" (Manrope bold 22px text-[#0A1931] mb-1).
  * Subtitle: "Thực hiện theo các bước để khôi phục quyền truy cập tài khoản." (text-xs text-slate-600 mb-5).
- Stepper Indicator Row (#pw-steps):
  * Step 1 chip (#pw-chip-1): "1. Email" (Active Navy / Cyan border).
  * Step arrow (#pw-arrow-1): "→"
  * Step 2 chip (#pw-chip-2): "2. Mã OTP"
  * Step arrow (#pw-arrow-2): "→"
  * Step 3 chip (#pw-chip-3): "3. Mật khẩu mới"
- Step 1: Form Email (#pw-form-email):
  * Label: "Email đã đăng ký"
  * Input: <input id="pw-email" type="email" placeholder="ten@clbip.vn" class="w-full px-4 py-2.5 border border-slate-300 rounded-xl text-sm mb-1" required />
  * Error: <p id="pw-email-error" class="hidden text-xs text-red-600 mb-3"></p>
  * Button: <button id="pw-btn-send" type="submit" class="w-full py-3 bg-[#0A1931] hover:bg-[#0099FF] text-white font-bold text-sm rounded-xl transition-all">Gửi mã xác minh OTP</button>
- Step 2: Form OTP Verification (#pw-form-otp, hidden by default):
  * Explanatory text: "Mã 6 số đã được gửi tới <strong id="pw-email-shown" class="text-[#0A1931]"></strong>."
  * Countdown Row: "Hiệu lực: <span id="pw-otp-countdown" class="font-mono font-bold text-[#0099FF]">10:00</span>" • <button id="pw-btn-resend" type="button" class="text-xs font-bold text-slate-600 hover:text-[#0099FF] disabled:opacity-50" disabled>Gửi lại mã</button>
  * Input OTP: <input id="pw-otp" maxlength="6" inputmode="numeric" placeholder="••••••" class="w-full py-3 text-center font-mono font-bold text-2xl tracking-[0.3em] border border-slate-300 rounded-xl text-[#0A1931] my-3" required />
  * Error: <p id="pw-otp-error" class="hidden text-xs text-red-600 mb-3"></p>
  * Button: <button id="pw-btn-verify" type="submit" class="w-full py-3 bg-[#0A1931] hover:bg-[#0099FF] text-white font-bold text-sm rounded-xl transition-all">Xác minh mã OTP</button>
  * Back link: <button id="pw-link-back" type="button" class="w-full text-center text-xs text-slate-500 hover:text-slate-800 font-semibold mt-3">← Nhập email khác</button>
- Step 3: Form Set New Password (#pw-form-confirm, hidden by default):
  * Field: Mật khẩu mới (<input id="pw-newpw" type="password" placeholder="Tối thiểu 8 ký tự" class="w-full px-4 py-2.5 border border-slate-300 rounded-xl text-sm" required />)
  * Field: Xác nhận mật khẩu mới (<input id="pw-confpw" type="password" placeholder="Nhập lại mật khẩu mới" class="w-full px-4 py-2.5 border border-slate-300 rounded-xl text-sm" required />)
  * Error: <p id="pw-confpw-error" class="hidden text-xs text-red-600 mb-3"></p>
  * Button: <button id="pw-btn-confirm" type="submit" class="w-full py-3 bg-[#0A1931] hover:bg-[#0099FF] text-white font-bold text-sm rounded-xl transition-all">Lưu mật khẩu mới & Đăng nhập</button>

================================================================================
CRITICAL BACKEND CONTRACT COMPATIBILITY:
================================================================================
Ensure the generated code retains all exact DOM element IDs to function seamlessly with api.js and auth.js:
- Form IDs: login-form, pw-form-email, pw-form-otp, pw-form-confirm
- Input IDs: email, password, pw-email, pw-otp, pw-newpw, pw-confpw
- Button IDs: btn-login, toggle-pw, link-forgot, pw-modal-close, pw-btn-send, pw-btn-verify, pw-btn-resend, pw-btn-confirm, pw-link-back
- Indicator IDs: pw-chip-1, pw-chip-2, pw-chip-3, pw-arrow-1, pw-arrow-2, pw-email-shown, pw-otp-countdown, toggle-pw-icon, login-alert, login-alert-text, login-alert-icon
```
