import { useEffect, useRef } from 'react';
import gsap from 'gsap';

/**
 * Premium animated background for the login brand panel.
 * Features glowing aurora orbs, a network mesh with pulsing nodes,
 * and flowing particles along curved paths.
 */
export function LoginGeometry() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId: number;
    let width: number;
    let height: number;

    // ── State objects animated by GSAP ──
    const orbs = [
      { x: 0.2, y: 0.3, r: 0.35, opacity: 0.12, hue: 200, sat: 80, light: 50 },
      { x: 0.7, y: 0.2, r: 0.28, opacity: 0.1, hue: 195, sat: 70, light: 45 },
      { x: 0.5, y: 0.75, r: 0.32, opacity: 0.08, hue: 210, sat: 60, light: 40 },
      {
        x: 0.85,
        y: 0.65,
        r: 0.22,
        opacity: 0.14,
        hue: 188,
        sat: 85,
        light: 48,
      },
    ];

    // Network nodes
    const nodeCount = 40;
    const nodes: {
      x: number;
      y: number;
      baseX: number;
      baseY: number;
      r: number;
      pulse: number;
      glowOpacity: number;
    }[] = [];
    for (let i = 0; i < nodeCount; i++) {
      const bx = Math.random();
      const by = Math.random();
      nodes.push({
        x: bx,
        y: by,
        baseX: bx,
        baseY: by,
        r: 1 + Math.random() * 2,
        pulse: 0,
        glowOpacity: 0.15 + Math.random() * 0.2,
      });
    }

    // Flowing particles along curves
    const particleCount = 18;
    const particles: {
      progress: number;
      speed: number;
      pathIndex: number;
      size: number;
      opacity: number;
    }[] = [];
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        progress: Math.random(),
        speed: 0.0004 + Math.random() * 0.0008,
        pathIndex: Math.floor(Math.random() * 4),
        size: 1.5 + Math.random() * 2.5,
        opacity: 0.3 + Math.random() * 0.5,
      });
    }

    // Curved paths for particles (control points as fractions)
    const paths = [
      {
        x0: 0.05,
        y0: 0.15,
        cx1: 0.35,
        cy1: 0.05,
        cx2: 0.65,
        cy2: 0.45,
        x1: 0.95,
        y1: 0.25,
      },
      {
        x0: 0.1,
        y0: 0.85,
        cx1: 0.3,
        cy1: 0.55,
        cx2: 0.7,
        cy2: 0.75,
        x1: 0.9,
        y1: 0.45,
      },
      {
        x0: 0.0,
        y0: 0.5,
        cx1: 0.25,
        cy1: 0.2,
        cx2: 0.75,
        cy2: 0.8,
        x1: 1.0,
        y1: 0.5,
      },
      {
        x0: 0.15,
        y0: 0.0,
        cx1: 0.4,
        cy1: 0.4,
        cx2: 0.6,
        cy2: 0.6,
        x1: 0.85,
        y1: 1.0,
      },
    ];

    // Master opacity for entrance
    const master = { opacity: 0 };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio, 2);
      const rect = canvas.parentElement?.getBoundingClientRect();
      width = rect?.width ?? window.innerWidth;
      height = rect?.height ?? window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    window.addEventListener('resize', resize);

    // Cubic bezier point helper
    const bezierPoint = (
      t: number,
      p0: number,
      p1: number,
      p2: number,
      p3: number,
    ) => {
      const u = 1 - t;
      return (
        u * u * u * p0 +
        3 * u * u * t * p1 +
        3 * u * t * t * p2 +
        t * t * t * p3
      );
    };

    // ── GSAP Animations ──

    // Entrance fade
    gsap.to(master, { opacity: 1, duration: 2.5, ease: 'power2.inOut' });

    // Orbs: slow drift + breathing
    orbs.forEach((orb) => {
      gsap.to(orb, {
        x: `+=${0.08 + Math.random() * 0.12}`,
        y: `+=${0.06 + Math.random() * 0.1}`,
        duration: 12 + Math.random() * 10,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });
      gsap.to(orb, {
        r: orb.r + 0.06 + Math.random() * 0.08,
        opacity: orb.opacity + 0.04,
        duration: 6 + Math.random() * 6,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });
    });

    // Nodes: gentle sway
    nodes.forEach((node) => {
      gsap.to(node, {
        x: node.baseX + (Math.random() - 0.5) * 0.04,
        y: node.baseY + (Math.random() - 0.5) * 0.04,
        duration: 4 + Math.random() * 4,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });
    });

    // Random node pulses
    const pulseRandom = () => {
      const n = nodes[Math.floor(Math.random() * nodes.length)];
      if (!n) return;
      gsap.to(n, {
        pulse: 1,
        duration: 0.6,
        ease: 'power2.out',
        onComplete: () => {
          gsap.to(n, { pulse: 0, duration: 1.2, ease: 'power2.in' });
        },
      });
    };
    const pulseInterval = setInterval(pulseRandom, 400);

    // ── Render loop ──
    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      ctx.globalAlpha = master.opacity;

      // Draw aurora orbs
      for (const orb of orbs) {
        const cx = orb.x * width;
        const cy = orb.y * height;
        const radius = orb.r * Math.max(width, height);
        const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
        gradient.addColorStop(
          0,
          `hsla(${orb.hue}, ${orb.sat}%, ${orb.light}%, ${orb.opacity})`,
        );
        gradient.addColorStop(
          0.5,
          `hsla(${orb.hue}, ${orb.sat}%, ${orb.light}%, ${orb.opacity * 0.4})`,
        );
        gradient.addColorStop(
          1,
          `hsla(${orb.hue}, ${orb.sat}%, ${orb.light}%, 0)`,
        );
        ctx.fillStyle = gradient;
        ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2);
      }

      // Draw network edges (connect nearby nodes)
      ctx.strokeStyle = 'rgba(75, 169, 212, 0.06)';
      ctx.lineWidth = 0.5;
      for (let i = 0; i < nodes.length; i++) {
        const ni = nodes[i];
        if (!ni) continue;
        for (let j = i + 1; j < nodes.length; j++) {
          const nj = nodes[j];
          if (!nj) continue;
          const dx = (ni.x - nj.x) * width;
          const dy = (ni.y - nj.y) * height;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const maxDist = 140;
          if (dist < maxDist) {
            const alpha =
              0.06 * (1 - dist / maxDist) + (ni.pulse + nj.pulse) * 0.12;
            ctx.strokeStyle = `rgba(75, 169, 212, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(ni.x * width, ni.y * height);
            ctx.lineTo(nj.x * width, nj.y * height);
            ctx.stroke();
          }
        }
      }

      // Draw nodes
      for (const node of nodes) {
        const nx = node.x * width;
        const ny = node.y * height;

        // Glow when pulsing
        if (node.pulse > 0.05) {
          const glowR = node.r + node.pulse * 18;
          const glowGrad = ctx.createRadialGradient(nx, ny, 0, nx, ny, glowR);
          glowGrad.addColorStop(0, `rgba(75, 169, 212, ${node.pulse * 0.4})`);
          glowGrad.addColorStop(1, 'rgba(75, 169, 212, 0)');
          ctx.fillStyle = glowGrad;
          ctx.beginPath();
          ctx.arc(nx, ny, glowR, 0, Math.PI * 2);
          ctx.fill();
        }

        // Node dot
        ctx.fillStyle = `rgba(165, 205, 228, ${node.glowOpacity + node.pulse * 0.5})`;
        ctx.beginPath();
        ctx.arc(nx, ny, node.r + node.pulse * 2, 0, Math.PI * 2);
        ctx.fill();
      }

      // Draw flowing particles along curves
      for (const particle of particles) {
        particle.progress += particle.speed;
        if (particle.progress > 1) particle.progress -= 1;

        const p = paths[particle.pathIndex];
        if (!p) continue;
        const t = particle.progress;
        const px = bezierPoint(
          t,
          p.x0 * width,
          p.cx1 * width,
          p.cx2 * width,
          p.x1 * width,
        );
        const py = bezierPoint(
          t,
          p.y0 * height,
          p.cy1 * height,
          p.cy2 * height,
          p.y1 * height,
        );

        // Trail
        const trailGrad = ctx.createRadialGradient(
          px,
          py,
          0,
          px,
          py,
          particle.size * 5,
        );
        trailGrad.addColorStop(
          0,
          `rgba(75, 169, 212, ${particle.opacity * 0.4})`,
        );
        trailGrad.addColorStop(1, 'rgba(75, 169, 212, 0)');
        ctx.fillStyle = trailGrad;
        ctx.beginPath();
        ctx.arc(px, py, particle.size * 5, 0, Math.PI * 2);
        ctx.fill();

        // Core
        ctx.fillStyle = `rgba(160, 215, 240, ${particle.opacity})`;
        ctx.beginPath();
        ctx.arc(px, py, particle.size, 0, Math.PI * 2);
        ctx.fill();
      }

      // Draw subtle curve paths themselves
      ctx.strokeStyle = 'rgba(75, 169, 212, 0.04)';
      ctx.lineWidth = 1;
      for (const p of paths) {
        ctx.beginPath();
        ctx.moveTo(p.x0 * width, p.y0 * height);
        ctx.bezierCurveTo(
          p.cx1 * width,
          p.cy1 * height,
          p.cx2 * width,
          p.cy2 * height,
          p.x1 * width,
          p.y1 * height,
        );
        ctx.stroke();
      }

      animationId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationId);
      clearInterval(pulseInterval);
      window.removeEventListener('resize', resize);
      gsap.killTweensOf(master);
      orbs.forEach((o) => gsap.killTweensOf(o));
      nodes.forEach((n) => gsap.killTweensOf(n));
    };
  }, []);

  return (
    <canvas ref={canvasRef} className="login-geometry" aria-hidden="true" />
  );
}
