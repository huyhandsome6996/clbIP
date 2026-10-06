# PROMPT THIẾT KẾ GOOGLE STITCH AI: LANDING PAGE GIỚI THIỆU CLB IP ĐHSP HUẾ

> **Mục tiêu**: Thiết kế Landing Page hoàn chỉnh giới thiệu **Câu lạc bộ Tin học & Sư phạm (IP Club)** — Khoa Tin học, Trường ĐH Sư phạm, ĐH Huế. 
> **Phong cách**: Đẳng cấp Agency hiện đại, bố cục đa tầng như **EduCareLink**, phối màu xanh Navy công nghệ & Cyan nhị phân chuẩn theo **Logo CLB IP**. Tập trung giới thiệu **CON NGƯỜI, HOẠT ĐỘNG, SỨ MỆNH & GIÁ TRỊ CÂU LẠC BỘ** (kèm hình ảnh minh họa chân thực), không biến thành trang chào bán phần mềm.

---

## NỘI DUNG PROMPT (SAO CHÉP TOÀN BỘ VÀ DÁN VÀO GOOGLE STITCH / AI DESIGN TOOL)

```markdown
Role & Task:
You are an elite Creative Director and Lead Design Systems Architect at Google Stitch. Design a world-class, human-centric, aesthetically breath-taking responsive Web Landing Page for "CLB Tin học & Sư phạm" (Informatics & Pedagogy Club - IP Club), established under the Faculty of Informatics, University of Education, Hue University (Trường Đại học Sư phạm, Đại học Huế).

Critical Purpose:
This landing page is dedicated to INTRODUCING THE CLUB ITSELF (its identity, history, educational & technical mission, core academic tracks, real-life student activities, achievements, mentors, and recruitment) — NOT a software feature catalog. The club's custom-built digital portal (Cổng số IP 2.0) should only be featured as a proud proof-of-work showcase, not the main premise of the page.

Design System & Visual Language (Inspired by EduCareLink's Polish & Ergonomics):
1. Color Palette (Derived directly from the IP Club Binary Logo):
   - Primary Brand (Deep Tech Navy): #0A1931 (Deep Academic & Tech Navy, convey prestige and depth), with #0F2042 for surface depths.
   - Electric Accent (Binary Cyan): #0099FF / #00A3FF (The exact bright sky-cyan from the 0s & 1s binary digits in the logo).
   - Secondary Tech Hue: #0284C7 (Vivid Azure) and #38BDF8 (Soft Sky Blue for glow & pill badges).
   - Vibrant Energy Accent: #10B981 (Emerald Mint for active badges, live status, and success pills).
   - Backgrounds: Ultra-clean crisp canvas #F8FAFC (Slate-50), with layered cards on pure #FFFFFF.
   - Borders: Subtle hairline borders border-slate-200/80 (rgba(226, 232, 240, 0.85)).
   - Shadows: Multi-tiered ambient soft shadows (shadow-[0_20px_50px_rgba(10,25,49,0.06)], hover:shadow-[0_24px_60px_rgba(0,153,255,0.15)]).
2. Typography:
   - Headlines & Big Metrics: 'Manrope', sans-serif (weights 700, 800) with tight letter-spacing (-0.02em).
   - Body & Navigation: 'Plus Jakarta Sans', sans-serif (weights 400, 500, 600, 700) for pristine Vietnamese typography rendering.
3. Iconography:
   - Google Material Symbols Outlined (clean 24px, opsz 24, filled styles on accents).
4. Authentic Visual Imagery & Photo Placeholders:
   - Provide concrete, contextual photography placeholders (Unsplash high-res URLs with university/tech tags or descriptive SVG/CSS frames) showing: students collaborating in modern computer labs, hackathon coding sessions, pedagogy micro-teaching workshops, national Olympic Informatics award podiums, and student gatherings in Hue along the Perfume River.

Page Architecture & Detailed Section Layout:

================================================================================
1. GLASSMORPHIC TOP NAVBAR (Sticky header, z-50, h-[76px])
================================================================================
- Left (Brand Identity):
  * Logo Icon: An elegant rounded-xl container featuring the binary "I P" motif (styled with navy and cyan 0/1 bits) + clean typography.
  * Brand Text: "CLB IP" (Manrope bold 20px, #0A1931) with a pill badge "ĐH Sư Phạm Huế" (bg-sky-100 text-sky-700 font-bold text-[11px] px-2 py-0.5 rounded-full).
  * Subline: "Informatics & Pedagogy Club • Khoa Tin học".
- Center (Navigation Links - Hidden on mobile, flex on desktop):
  * Links: "Về câu lạc bộ", "Mảng hoạt động", "Dấu ấn & Dự án", "Đội ngũ", "Thư viện ảnh", "Cổng số 2.0".
  * Hover state: Text transitions from slate-600 to #0099FF with subtle underline indicator.
- Right (Action Buttons):
  * Ghost Button: "Cổng thành viên" (Link to login, icon 'login', text-slate-700 hover:text-blue-600).
  * Primary Button: "Ứng tuyển thành viên →" (Pill shape, gradient from #0A1931 to #0099FF, text-white font-bold px-5 py-2.5 shadow-[0_8px_20px_rgba(0,153,255,0.25)] hover:scale-[1.02] transition-all).
  * Mobile hamburger trigger for responsive drawer.

================================================================================
2. HERO SECTION — "NUÔI DƯỠNG ĐAM MÊ CÔNG NGHỆ & BẢN LĨNH SƯ PHẠM"
================================================================================
- Layout: 2-column asymmetric grid (1.05fr vs 0.95fr) on an ethereal mesh background with radial cyan & navy blurs.
- Left Column (Content & Emotional Hook):
  * Eyebrow Pill: Pill tag with glowing emerald live dot: "✨ CLB HỌC THUẬT & CÔNG NGHỆ NÒNG CỐT • KHOA TIN HỌC ĐHSP HUẾ".
  * H1 Headline: "Code Your Future —<br><span class="text-transparent bg-clip-text bg-gradient-to-r from-[#0099FF] to-[#0A1931]">Nơi Đam Mê Lập Trình</span> Hòa Quyện <span class="text-transparent bg-clip-text bg-gradient-to-r from-[#0A1931] to-[#0099FF]">Nghiệp Vụ Sư Phạm</span>".
  * Sub-headline / Mission:
    "Câu lạc bộ Tin học & Sư phạm (IP Club) là cái nôi kết nối các thế hệ sinh viên đam mê lập trình, nghiên cứu công nghệ và đổi mới giáo dục tại Trường ĐH Sư phạm, ĐH Huế. Cùng nhau học thuật toán, xây dựng dự án thực chiến và rèn luyện kỹ năng truyền cảm hứng cho thế hệ tương lai."
  * Hero CTAs:
    - Primary CTA: "Gia nhập CLB IP ngay" (with icon 'rocket_launch', rounded-full, navy-cyan gradient, pulse hover).
    - Secondary CTA: "Khám phá hoạt động" (with icon 'play_circle', ghost white button with border-slate-300).
  * Trust Proof Badges (Inline flex row):
    - [🏛️ Trực thuộc Khoa Tin học - ĐHSP Huế]
    - [🏆 50+ Giải thưởng Olympic Tin học]
    - [🌱 15+ Năm thế hệ sinh viên trưởng thành]
- Right Column (Hero Visual Composition & Multi-layered Floating Cards):
  * Main Hero Visual: A prominent, rounded-3xl high-resolution photo card showcasing enthusiastic Vietnamese computer science and pedagogy students collaborating around a laptop in a vibrant university workspace.
  * Floating Glass Card #1 (Top-Right): "🏆 Giải Nhì Toàn quốc • OLP Tin học Sinh viên" with gold trophy badge and sparkle effects.
  * Floating Glass Card #2 (Bottom-Left): "⚡ Cổng điều hành số IP 2.0" featuring a mini QR check-in & member streak chip ("🔥 142 thành viên online").
  * Floating Badge #3 (Center-Right): "🎓 100% Mentorship 1:1 từ cựu sinh viên & giảng viên".

================================================================================
3. MISSION & VALUE PILLARS (4 CORE PILLARS — Phong cách Bento Cards EduCareLink)
================================================================================
- Section Header:
  * Eyebrow: "SỨ MỆNH & ĐỊNH HƯỚNG"
  * Title: "Bốn Trụ Cột Phát Triển Toàn Diện Tại CLB IP"
  * Description: "Chúng tôi không chỉ rèn luyện tư duy lập trình viên xuất sắc, mà còn đào tạo những nhà giáo dục và lãnh đạo công nghệ tự tin."
- 4-Card Grid (Grid 1 col -> 2 col -> 4 col):
  1. Card 1 [Học thuật & Olympic Tin học]:
     - Icon: 'terminal' (in soft cyan tint background).
     - Title: "Thuật toán & Thi đấu đỉnh cao".
     - Details: Luyện tập cấu trúc dữ liệu, giải thuật, ICPC và Olympic Tin học sinh viên toàn quốc dưới sự cố vấn trực tiếp của thầy cô Khoa Tin học.
     - Tag: "C++ / Python / Java".
  2. Card 2 [Dự án Công nghệ Thực chiến]:
     - Icon: 'deployed_code' (in soft navy-blue tint background).
     - Title: "Sản phẩm thực tế cho cộng đồng".
     - Details: Sinh viên trực tiếp làm việc nhóm theo mô hình Agile/Scrum, tự tay phát triển web app, mobile app, hệ thống số hóa phục vụ nhà trường.
     - Tag: "Fullstack / Cloud / DevOps".
  3. Card 3 [Sư phạm Số & Giáo dục STEM]:
     - Icon: 'school' (in soft emerald tint background).
     - Title: "Nghiệp vụ Sư phạm Hiện đại".
     - Details: Thiết kế bài giảng số, ứng dụng Trí tuệ Nhân tạo (AI) trong giáo dục, tổ chức các lớp học lập trình miễn phí cho học sinh phổ thông.
     - Tag: "EdTech / STEM / AI in Teaching".
  4. Card 4 [Kỹ năng mềm & Kết nối Doanh nghiệp]:
     - Icon: 'groups_3' (in soft amber tint background).
     - Title: "Gia đình IP & Mạng lưới cựu SV".
     - Details: Hội thảo TechTalk cùng kỹ sư từ FPT, Viettel, VNG; rèn luyện kỹ năng thuyết trình, làm việc nhóm và sinh hoạt ngoại khóa gắn kết.
     - Tag: "TechTalk / Hackathon / Soft Skills".

================================================================================
4. STATS & IMPACT COUNTER (Con số biết nói — Manrope 800)
================================================================================
- Modern rounded-3xl container with Deep Navy background (#0A1931) accented with electric cyan neon border highlights.
- 4 Key Statistics:
  * Metric 1: "15+" (Năm hình thành & phát triển vững mạnh).
  * Metric 2: "500+" (Thành viên & Cựu sinh viên trên toàn quốc).
  * Metric 3: "50+" (Huy chương & Bằng khen Olympic Tin học, NCKH).
  * Metric 4: "100%" (Thành viên có đồ án & kinh nghiệm thực chiến trước khi ra trường).

================================================================================
5. REAL-LIFE ACTIVITIES & MOMENTS (Hình ảnh minh họa cụ thể về hoạt động CLB)
================================================================================
- Section Header:
  * Eyebrow: "CUỘC SỐNG TẠI CLB IP"
  * Title: "Những Khoảnh Khắc Tạo Nên Bản Sắc CLB IP"
  * Description: "Học hết sức, chơi hết mình — từ những đêm thức trắng debug trước giờ nộp bài đến những chuyến dã ngoại đầy ắp tiếng cười tại xứ Huế."
- Asymmetric Photo Gallery Grid (Bento Gallery with captions & category chips):
  1. Photo Card A (Large Spotlight, span 2 cols):
     - Image: Phòng máy Khoa Tin học rực sáng ánh đèn trong đêm thi Hackathon nội bộ.
     - Overlay Badge: "🔥 Hackathon Thường niên IP TechJam".
     - Caption: "48 giờ liên tục kiến tạo giải pháp công nghệ cho giáo dục."
  2. Photo Card B:
     - Image: Đội tuyển CLB IP nhận giải tại Lễ trao giải Olympic Tin học Sinh viên Toàn quốc.
     - Overlay Badge: "🏆 Vinh quang Olympic".
     - Caption: "Tự hào mang thành tích về cho mái trường ĐH Sư phạm Huế."
  3. Photo Card C:
     - Image: Thành viên CLB đứng lớp giảng dạy trải nghiệm STEM và Scratch cho học sinh THCS.
     - Overlay Badge: "🌱 Lớp học STEM Cộng đồng".
     - Caption: "Ươm mầm đam mê lập trình cho thế hệ măng non."
  4. Photo Card D:
     - Image: Workshop giao lưu cùng diễn giả cựu sinh viên đang làm Tech Lead tại TP.HCM.
     - Overlay Badge: "💡 TechTalk Chuyên sâu".
     - Caption: "Cập nhật xu hướng AI, Cloud Computing và kinh nghiệm phỏng vấn IT."
  5. Photo Card E:
     - Image: Buổi dã ngoại team building bên dòng sông Hương và cắm trại cuối tuần.
     - Overlay Badge: "⛺ Gắn kết tình thân".
     - Caption: "Nơi tình bạn và những người đồng đội gắn bó suốt 4 năm đại học."

================================================================================
6. PROOF OF INNOVATION — CỔNG NỀN TẢNG SỐ IP 2.0 (Product Showcase)
================================================================================
- Framing: Giới thiệu như một sản phẩm độc quyền do chính thành viên CLB tự thiết kế và lập trình:
  * Left: Mô tả sự tự hào: "Tự hào vận hành trên Cổng Quản lý Số 2.0 do chính tay sinh viên CLB xây dựng".
    - Điểm danh thông minh qua định vị GPS (khoảng cách Haversine).
    - Hệ thống Gamification: Tích lũy XP, đua Top bảng vàng và huy hiệu vinh danh.
    - Kho tài liệu học tập, giáo án và đề thi được số hóa với tìm kiếm Trie tức thì.
    - Sổ quỹ thu chi công khai, minh bạch tuyệt đối trên toàn hệ thống.
  * Right: Mockup tương tác sống động thể hiện giao diện Member Dashboard với Thẻ sinh viên số, huy hiệu "Dev Tập Sự", thanh tiến trình XP và QR code check-in.
  * CTA Button: "Trải nghiệm Cổng số (Dành cho thành viên) →".

================================================================================
7. BAN CHỦ NHIỆM & CỐ VẤN HỌC THUẬT (Mentors & Leadership)
================================================================================
- Section Header:
  * Eyebrow: "ĐỘI NGŨ DẪN DẮT"
  * Title: "Những Người Thầy Tận Tâm & Ban Chủ Nhiệm Nhiệt Huyết"
- Leadership Cards Grid:
  * Card 1: Giảng viên Cố vấn Chuyên môn (Khoa Tin học - ĐHSP Huế) · "Định hướng học thuật và bồi dưỡng đội tuyển Olympic".
  * Card 2: Chủ nhiệm CLB · "Điều hành chiến lược và kết nối các hoạt động toàn CLB".
  * Card 3: Phó Chủ nhiệm Ban Chuyên môn & Dự án · "Chủ trì các buổi seminar code và quản lý sản phẩm công nghệ".
  * Card 4: Phó Chủ nhiệm Ban Truyền thông & Sự kiện · "Lan tỏa thương hiệu CLB và tổ chức các sân chơi gắn kết".

================================================================================
8. ALUMNI VOICES & TESTIMONIALS (Cảm nhận thành viên & Cựu sinh viên)
================================================================================
- 3 Authentic Quote Cards (Trích dẫn kèm ảnh chân dung, khóa học và vị trí công tác):
  * Quote 1: "CLB IP là bệ phóng lớn nhất thời đại học của mình. Từ một cậu sinh viên năm nhất chưa biết viết hàm đệ quy, mình đã tự tin đoạt giải OLP và hiện đang làm Software Engineer tại TP. Đà Nẵng." — Hoàng Nhật Nam (Cựu thành viên K41).
  * Quote 2: "Tại IP Club, mình học được cách làm cho bài giảng tin học trở nên lôi cuốn với AI và đồ họa trực quan. Kỹ năng đó giúp mình rất nhiều khi đứng lớp giảng dạy tại trường THPT Chuyên." — Lê Thị Mai Anh (Cựu thành viên K43, Giáo viên Tin học).
  * Quote 3: "Không có khoảng cách giữa các khóa! Các anh chị năm 3, năm 4 luôn sẵn sàng kèm 1:1 cho tân sinh viên từng dòng code đầu tiên." — Nguyễn Đức Huy (Thành viên K48).

================================================================================
9. FAQ — CÂU HỎI THƯỜNG GẶP (Accordion Interactive)
================================================================================
- Accordion questions specifically for prospective club members:
  1. "Tôi là tân sinh viên chưa biết lập trình nhiều thì có tham gia được không?" -> CLB có lộ trình đào tạo từ con số 0 cho tân binh, luôn có mentor kèm cặp.
  2. "Sinh viên ngoài Khoa Tin học có thể đăng ký ứng tuyển không?" -> CLB luôn chào đón mọi bạn trẻ đam mê công nghệ và sáng tạo nội dung từ các khoa bạn trong trường.
  3. "CLB sinh hoạt vào thời gian nào trong tuần?" -> Lịch sinh hoạt học thuật và giao lưu được sắp xếp linh hoạt vào buổi tối hoặc cuối tuần tại phòng thực hành.
  4. "Thành viên CLB có quyền lợi gì khi tham gia?" -> Được cấp tài khoản Cổng số IP 2.0, cấp chứng nhận hoạt động, ưu tiên tham gia đội tuyển Olympic và cơ hội thực tập sớm.

================================================================================
10. RECRUITMENT CALL-TO-ACTION BAND (Banner kêu gọi ứng tuyển cong vòm)
================================================================================
- Styling: Rounded-3xl container (border-radius: 2rem), background Deep Navy #0A1931 with an energetic gradient mesh blending into Electric Cyan #0099FF.
- Content:
  * Eyebrow: "ĐỢT TUYỂN QUÂN GEN MỚI ĐANG MỞ"
  * Title: "Sẵn Sàng Cùng CLB IP 'Code Your Future'?"
  * Description: "Đừng ngần ngại bước ra khỏi vùng an toàn. Dù bạn muốn trở thành chuyên gia lập trình, nhà giáo dục tương lai hay một nhà truyền thông tài ba — cánh cửa CLB IP luôn rộng mở."
  * Action Buttons:
    - "Đăng ký ứng tuyển ngay hôm nay (Google Form / Portal)" (White button, navy bold text, glow shadow).
    - "Nhắn tin cho Fanpage CLB" (Ghost border-white button).

================================================================================
11. MODERN MULTI-COLUMN FOOTER
================================================================================
- Dark Slate Surface (#060D1A) with soft muted slate typography.
- Column 1: Logo IP binary motif, "CLB Tin học & Sư phạm — Trường ĐH Sư phạm, ĐH Huế. Khẩu hiệu: Code your Future • Nâng tầm công nghệ & giáo dục."
- Column 2: Liên kết nhanh (Về CLB, Mảng hoạt động, Dấu ấn, Đăng ký thành viên, Cổng sinh viên).
- Column 3: Thông tin liên hệ (Địa chỉ: Khoa Tin học, Tầng 3 Nhà A, 34 Lê Lợi, TP. Huế; Email: clbip.dhsphue@gmail.com; Fanpage Facebook).
- Column 4: Mạng xã hội & Huy hiệu bảo trợ bởi Khoa Tin học - Trường ĐH Sư phạm, ĐH Huế.
- Bottom Bar: "© 2026 CLB IP ĐHSP Huế. Xây dựng bởi Ban Công nghệ CLB IP với tinh thần tự hào mã nguồn mở."

Interactive Behaviors & Accessibility Standards:
- Semantic HTML5 structure (header, main, section, footer, article, nav, aside).
- Mobile menu toggle with smooth transitions and backdrop blur.
- Details/summary interactive accordion with rotating '+' or arrow indicator for FAQ.
- All CTA buttons have tactile hover/active transitions (transform: translateY(-2px)).
- Full responsive fidelity across mobile (375px), tablet (768px), and desktop (1280px+).
```
