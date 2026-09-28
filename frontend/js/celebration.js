/**
 * celebration.js — Hiệu ứng Confetti canvas (thuần JS, không phụ thuộc)
 * ====================================================================
 * Dùng khi check-in thành công / nhận huy hiệu.
 * Chỉ animate transform (translate), chạy trên canvas riêng
 * (#confetti-canvas, pointer-events none). Tôn trọng
 * prefers-reduced-motion: nếu bật reduce → không bắn gì cả.
 */
(() => {
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const COLORS = ["#6366F1", "#8B5CF6", "#22C55E", "#FCD34D", "#F472B6", "#38BDF8"];
  const GRAVITY = 0.14;
  const DRAG = 0.99;
  const FLAT = 2.4; // px bình phương: kích thước mảnh giấy

  let canvas = null;
  let ctx = null;
  let pieces = [];
  let running = false;
  let rafId = null;

  function ensureCanvas() {
    if (canvas) return canvas;
    canvas = document.createElement("canvas");
    canvas.id = "confetti-canvas";
    document.body.appendChild(canvas);
    ctx = canvas.getContext("2d");
    return canvas;
  }

  function resize() {
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = innerWidth * dpr;
    canvas.height = innerHeight * dpr;
    canvas.style.width = innerWidth + "px";
    canvas.style.height = innerHeight + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /**
   * Bắn confetti.
   * @param {object} opts {x, y, count, spread}
   */
  function burst(opts = {}) {
    if (REDUCED) return;
    ensureCanvas();
    resize();

    const count = opts.count || 90;
    const cx = opts.x ?? innerWidth / 2;
    const cy = opts.y ?? innerHeight * 0.34;

    for (let i = 0; i < count; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 5 + Math.random() * 9;
      pieces.push({
        x: cx,
        y: cy,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 6,
        size: FLAT + Math.random() * 2.5,
        color: COLORS[(Math.random() * COLORS.length) | 0],
        rot: Math.random() * Math.PI,
        vrot: (Math.random() - 0.5) * 0.28,
        life: 1,
      });
    }
    if (!running) {
      running = true;
      loop();
    }
  }

  function loop() {
    if (!ctx) return;
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    pieces = pieces.filter((p) => {
      p.vy += GRAVITY;
      p.vx *= DRAG;
      p.vy *= DRAG;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.vrot;
      if (p.y > innerHeight + 30) return false;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillStyle = p.color;
      ctx.globalAlpha = 0.92;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
      ctx.restore();
      return true;
    });
    if (pieces.length > 0) {
      rafId = requestAnimationFrame(loop);
    } else {
      running = false;
      cancelAnimationFrame(rafId);
      ctx.clearRect(0, 0, innerWidth, innerHeight);
    }
  }

  window.Celebrate = {
    /** Bắn chào mừng ở giữa màn hình (check-in thành công) */
    cheer() { burst({ count: 110 }); },
    /** Bắn tại vị trí một element (nhận huy hiệu...) */
    at(element, count = 70) {
      const r = element?.getBoundingClientRect();
      burst({ x: r ? r.left + r.width / 2 : undefined, y: r ? r.top + r.height / 2 : undefined, count });
    },
  };
})();
