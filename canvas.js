(function initCanvas() {
  var canvas = document.getElementById('nodes-canvas');
  if (!canvas) {
    console.warn('[canvas] nodes-canvas not found in DOM');
    return;
  }
  console.log('[canvas] init OK, size:', canvas.offsetWidth, 'x', canvas.offsetHeight);

  var ctx = canvas.getContext('2d');
  var particles = [];
  var isMobile = window.innerWidth < 768 || /Mobi|Android/i.test(navigator.userAgent);
  var MAX = isMobile ? 8 : 25;
  var LOGO_RADIUS = 80;
  var frameSkip = isMobile ? 2 : 1;
  var frameCount = 0;

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  function getCX() { return canvas.width * 0.5; }
  function getCY() { return canvas.height * 0.38; }

  function drawStar(x, y, r, alpha, color) {
    var g1 = ctx.createRadialGradient(x, y, 0, x, y, r * 3);
    g1.addColorStop(0, 'rgba(' + color + ',' + alpha + ')');
    g1.addColorStop(1, 'rgba(' + color + ',0)');
    ctx.beginPath();
    ctx.arc(x, y, r * 3, 0, Math.PI * 2);
    ctx.fillStyle = g1;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,255,255,' + Math.min(alpha, 1) + ')';
    ctx.fill();
    if (!isMobile && r > 1.5) {
      var sp = r * 6;
      [0, Math.PI / 2, Math.PI, Math.PI * 1.5].forEach(function (a) {
        var g = ctx.createLinearGradient(x, y, x + Math.cos(a) * sp, y + Math.sin(a) * sp);
        g.addColorStop(0, 'rgba(180,210,255,' + (alpha * 0.5) + ')');
        g.addColorStop(1, 'rgba(180,210,255,0)');
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + Math.cos(a) * sp, y + Math.sin(a) * sp);
        ctx.strokeStyle = g;
        ctx.lineWidth = Math.max(0.3, r * 0.2);
        ctx.stroke();
      });
    }
  }

  function drawRedStar(x, y, r, alpha) {
    var g1 = ctx.createRadialGradient(x, y, 0, x, y, r * 4);
    g1.addColorStop(0, 'rgba(255,80,80,' + alpha + ')');
    g1.addColorStop(1, 'rgba(255,0,0,0)');
    ctx.beginPath();
    ctx.arc(x, y, r * 4, 0, Math.PI * 2);
    ctx.fillStyle = g1;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255,200,200,' + Math.min(alpha * 2, 1) + ')';
    ctx.fill();
    if (!isMobile) {
      var sp = r * 8;
      [0, Math.PI / 4, Math.PI / 2, Math.PI * 0.75, Math.PI, Math.PI * 1.25, Math.PI * 1.5, Math.PI * 1.75].forEach(function (a, idx) {
        var len = idx % 2 === 0 ? sp : sp * 0.5;
        var g = ctx.createLinearGradient(x, y, x + Math.cos(a) * len, y + Math.sin(a) * len);
        g.addColorStop(0, 'rgba(255,100,100,' + (alpha * 0.7) + ')');
        g.addColorStop(1, 'rgba(255,0,0,0)');
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
        ctx.strokeStyle = g;
        ctx.lineWidth = Math.max(0.4, r * 0.3);
        ctx.stroke();
      });
    }
  }

  function spawnParticle() {
    var cx = getCX(), cy = getCY();
    var outward = Math.random() > 0.5;
    var x, y, vx, vy;
    var speed = Math.random() * 0.8 + 0.4;
    if (outward) {
      x = cx + (Math.random() - 0.5) * 40;
      y = cy + (Math.random() - 0.5) * 40;
      var angle = Math.random() * Math.PI * 2;
      vx = Math.cos(angle) * speed;
      vy = Math.sin(angle) * speed;
    } else {
      var side = Math.floor(Math.random() * 4);
      if (side === 0) { x = Math.random() * canvas.width; y = -10; }
      else if (side === 1) { x = canvas.width + 10; y = Math.random() * canvas.height; }
      else if (side === 2) { x = Math.random() * canvas.width; y = canvas.height + 10; }
      else { x = -10; y = Math.random() * canvas.height; }
      var dx = cx - x, dy = cy - y, dist = Math.sqrt(dx * dx + dy * dy);
      vx = (dx / dist) * speed;
      vy = (dy / dist) * speed;
    }
    return {
      x: x, y: y, vx: vx, vy: vy,
      r: Math.random() * 2.5 + 1.2,
      alpha: 0, life: 0,
      maxLife: Math.random() * 300 + 200,
      outward: outward, red: false, redScale: 1,
      color: Math.random() > 0.3 ? '100,160,255' : '160,200,255'
    };
  }

  for (var i = 0; i < MAX; i++) {
    var p = spawnParticle();
    p.life = Math.floor(Math.random() * p.maxLife);
    p.alpha = 0.7;
    particles.push(p);
  }

  function draw() {
    frameCount++;
    if (isMobile && frameCount % frameSkip !== 0) {
      requestAnimationFrame(draw);
      return;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    var cx = getCX(), cy = getCY();
    for (var i = particles.length - 1; i >= 0; i--) {
      var p = particles[i];
      p.life++;
      p.x += p.vx * frameSkip;
      p.y += p.vy * frameSkip;
      var lr = p.life / p.maxLife;
      if (lr < 0.08) p.alpha = lr / 0.08 * 0.85;
      else if (lr > 0.85) p.alpha = (1 - (lr - 0.85) / 0.15) * 0.85;
      else p.alpha = 0.85;
      var dx = p.x - cx, dy = p.y - cy;
      if (!p.outward && Math.sqrt(dx * dx + dy * dy) < LOGO_RADIUS && !p.red) p.red = true;
      if (p.red) {
        p.redScale = Math.min(p.redScale + 0.06, 3.5);
        p.alpha = Math.max(p.alpha - 0.025, 0);
        drawRedStar(p.x, p.y, p.r * p.redScale, p.alpha);
      } else {
        drawStar(p.x, p.y, p.r, p.alpha, p.color);
      }
      if (p.life >= p.maxLife || p.alpha <= 0 || p.x < -100 || p.x > canvas.width + 100 || p.y < -100 || p.y > canvas.height + 100) {
        particles.splice(i, 1);
        particles.push(spawnParticle());
      }
    }
    while (particles.length < MAX) particles.push(spawnParticle());
    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();
