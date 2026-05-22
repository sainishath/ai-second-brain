import React, { useEffect, useRef, useState } from 'react';

const CanvasScroll = ({ scrollContainerRef, onProgressUpdate }) => {
  const canvasRef = useRef(null);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loading, setLoading] = useState(true);
  const [useFallback, setUseFallback] = useState(false);

  const totalFrames = 300;
  const imagesRef = useRef([]);
  const frameIndexRef = useRef({ current: 0, target: 0 });
  const requestRef = useRef(null);
  const proceduralPointsRef = useRef([]);

  // Generate 3D particle cloud points for the procedural fallback
  useEffect(() => {
    const points = [];
    const numPoints = 400;
    for (let i = 0; i < numPoints; i++) {
      const isLeftLobe = Math.random() > 0.5;
      const lobeSign = isLeftLobe ? -1 : 1;
      const u = Math.random() * Math.PI * 2;
      const v = Math.random() * Math.PI - Math.PI / 2;

      // Base cerebrum lobes shape
      let x = 1.25 * Math.cos(v) * Math.cos(u) + lobeSign * 0.45;
      let y = 1.05 * Math.cos(v) * Math.sin(u) + 0.2;
      let z = 0.95 * Math.sin(v);

      // Folds (gyri/sulci)
      const folds = Math.sin(x * 6) * Math.cos(y * 6) * Math.sin(z * 6) * 0.15;
      x += folds;
      y += folds;
      z += folds;

      // Cerebellum back clusters
      if (Math.random() > 0.75) {
        x = 0.7 * Math.cos(v) * Math.cos(u) + lobeSign * 0.25;
        y = 0.5 * Math.cos(v) * Math.sin(u) - 0.6;
        z = 0.6 * Math.sin(v) - 0.4;
      }

      points.push({ x, y, z });
    }
    proceduralPointsRef.current = points;
  }, []);

  // Preload sequential frames
  useEffect(() => {
    let loadedCount = 0;
    let failedCount = 0;
    const preloadedImages = [];

    const handleImageLoad = () => {
      loadedCount++;
      const progress = Math.round((loadedCount / totalFrames) * 100);
      setLoadingProgress(progress);
      if (loadedCount + failedCount === totalFrames) {
        setLoading(false);
        if (failedCount > totalFrames * 0.5) {
          // If more than 50% of frames fail to load, switch to fallback
          console.warn("Vite App: Visual frames directory '/frames/' is empty or missing. Triggering premium procedural 3D visualizer fallback.");
          setUseFallback(true);
        }
      }
    };

    const handleImageError = () => {
      failedCount++;
      if (loadedCount + failedCount === totalFrames) {
        setLoading(false);
        if (failedCount > totalFrames * 0.5) {
          console.warn("Vite App: Visual frames directory '/frames/' is empty or missing. Triggering premium procedural 3D visualizer fallback.");
          setUseFallback(true);
        }
      }
    };

    // Preload image objects
    for (let i = 1; i <= totalFrames; i++) {
      const img = new Image();
      const paddedNum = String(i).padStart(3, '0');
      img.src = `/frames/${paddedNum}.jpg`;
      img.onload = handleImageLoad;
      img.onerror = handleImageError;
      preloadedImages.push(img);
    }

    imagesRef.current = preloadedImages;

    return () => {
      imagesRef.current = [];
    };
  }, []);

  // Set up resize handler
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Render loop tracking window scroll percentage with ease inertia
  useEffect(() => {
    const handleScroll = () => {
      const container = scrollContainerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const scrollHeight = rect.height - window.innerHeight;
      const scrolled = -rect.top;
      
      // Calculate scroll progress (0 to 1)
      let progress = scrolled / scrollHeight;
      progress = Math.max(0, Math.min(1, progress));

      // Map progress to target frame index (0 to 149)
      frameIndexRef.current.target = progress * (totalFrames - 1);

      if (onProgressUpdate) {
        onProgressUpdate(progress);
      }
    };

    window.addEventListener('scroll', handleScroll);
    handleScroll(); // Initial position

    return () => window.removeEventListener('scroll', handleScroll);
  }, [scrollContainerRef, onProgressUpdate]);

  // RequestAnimationFrame animation render loop
  useEffect(() => {
    const render = () => {
      const canvas = canvasRef.current;
      if (!canvas) {
        requestRef.current = requestAnimationFrame(render);
        return;
      }

      const ctx = canvas.getContext('2d');
      const width = canvas.width;
      const height = canvas.height;

      // Apply linear interpolation for smooth scrolling inertia
      const indexObj = frameIndexRef.current;
      indexObj.current += (indexObj.target - indexObj.current) * 0.12;

      // Draw active visual sequence
      if (!useFallback && imagesRef.current.length > 0) {
        const activeFrame = Math.round(indexObj.current);
        const img = imagesRef.current[activeFrame];

        if (img && img.complete && img.naturalWidth !== 0) {
          ctx.clearRect(0, 0, width, height);
          
          // Image 'cover' fit calculations
          const imgRatio = img.width / img.height;
          const canvasRatio = width / height;
          let drawWidth, drawHeight, xOffset, yOffset;

          if (canvasRatio > imgRatio) {
            drawWidth = width;
            drawHeight = width / imgRatio;
            xOffset = 0;
            yOffset = (height - drawHeight) / 2;
          } else {
            drawWidth = height * imgRatio;
            drawHeight = height;
            xOffset = (width - drawWidth) / 2;
            yOffset = 0;
          }

          ctx.drawImage(img, xOffset, yOffset, drawWidth, drawHeight);
        } else {
          // Temporarily fallback if frame isn't loaded completely
          drawProceduralVisuals(ctx, width, height, indexObj.current / (totalFrames - 1));
        }
      } else {
        // Run procedural particle visualizer fallback
        drawProceduralVisuals(ctx, width, height, indexObj.current / (totalFrames - 1));
      }

      requestRef.current = requestAnimationFrame(render);
    };

    requestRef.current = requestAnimationFrame(render);
    return () => cancelAnimationFrame(requestRef.current);
  }, [useFallback]);

  // High performance procedural neural node visualizer
  const drawProceduralVisuals = (ctx, w, h, progress) => {
    ctx.clearRect(0, 0, w, h);

    // Deep space dark radial gradient
    const gradient = ctx.createRadialGradient(w / 2, h / 2, 50, w / 2, h / 2, Math.max(w, h));
    gradient.addColorStop(0, '#09081e');
    gradient.addColorStop(1, '#020204');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);

    // Particle brain rotation angles bound to scroll position plus time
    const scrollAngle = progress * Math.PI * 3.5;
    const timeAngle = Date.now() * 0.00015;
    const angleY = scrollAngle + timeAngle;
    const angleX = 0.25 + progress * 0.6;

    const cosY = Math.cos(angleY);
    const sinY = Math.sin(angleY);
    const cosX = Math.cos(angleX);
    const sinX = Math.sin(angleX);

    const points = proceduralPointsRef.current;
    if (points.length === 0) return;

    // Project points into 2D space
    const scaleFactor = Math.min(w, h) * (0.24 + progress * 0.06); // Expands slightly as you scroll
    const projected = points.map((p, idx) => {
      // Rotate around Y axis
      let x1 = p.x * cosY - p.z * sinY;
      let z1 = p.x * sinY + p.z * cosY;

      // Rotate around X axis
      let y2 = p.y * cosX - z1 * sinX;
      let z2 = p.y * sinX + z1 * cosX;

      const perspective = 300 / (300 + z2);
      const xProjected = w / 2 + x1 * perspective * scaleFactor;
      // Slide upward as scroll progress completes
      const yProjected = h / 2 - y2 * perspective * scaleFactor - (progress * 80);

      return { x: xProjected, y: yProjected, z: z2, index: idx };
    });

    // Painter's algorithm depth sort
    projected.sort((a, b) => b.z - a.z);

    // Draw connecting synapses
    ctx.lineWidth = 0.55;
    for (let i = 0; i < projected.length; i++) {
      const p1 = projected[i];
      const orig1 = points[p1.index];

      for (let j = i + 1; j < projected.length; j++) {
        const p2 = projected[j];
        const orig2 = points[p2.index];

        const dx = orig1.x - orig2.x;
        const dy = orig1.y - orig2.y;
        const dz = orig1.z - orig2.z;
        const dist = dx * dx + dy * dy + dz * dz;

        // Draw connections if points are close in 3D space
        if (dist < 0.15) {
          const avgZ = (p1.z + p2.z) / 2;
          const alpha = Math.max(0.01, (1 - (avgZ + 1.5) / 3) * 0.12);
          
          // Color fades from Purple to Cyan as scroll progress finishes
          const r = Math.round(139 - (139 - 6) * progress);
          const g = Math.round(92 + (182 - 92) * progress);
          const b = Math.round(246 - (246 - 212) * progress);

          ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.stroke();
        }
      }
    }

    // Draw particle nodes
    projected.forEach(p => {
      const depthRatio = (p.z + 1.5) / 3;
      const size = Math.max(0.6, (1 - depthRatio) * 3 + 0.6);

      ctx.beginPath();
      ctx.arc(p.x, p.y, size, 0, Math.PI * 2);

      // Interpolate colors between Purple (deep) and Cyan (scrolled forward)
      const colorVal = Math.max(0, Math.min(1, depthRatio));
      const purplePart = 1 - progress;
      const cyanPart = progress;

      if (colorVal < 0.35) {
        // Bright foreground nodes
        ctx.fillStyle = `rgba(${Math.round(168 * purplePart + 6 * cyanPart)}, ${Math.round(85 * purplePart + 200 * cyanPart)}, ${Math.round(247 * purplePart + 240 * cyanPart)}, ${1 - colorVal})`;
      } else {
        // Dark background nodes
        ctx.fillStyle = `rgba(${Math.round(107 * purplePart + 8 * cyanPart)}, ${Math.round(33 * purplePart + 110 * cyanPart)}, ${Math.round(168 * purplePart + 140 * cyanPart)}, ${1 - colorVal})`;
      }
      ctx.fill();
    });

    // Draw a digital sine-wave abstract grid at the bottom
    ctx.lineWidth = 1;
    ctx.strokeStyle = `rgba(6, 182, 212, ${0.08 + progress * 0.08})`;
    ctx.beginPath();
    for (let x = 0; x < w; x += 15) {
      const sineWave = Math.sin(x * 0.005 + timeAngle * 8) * 40 * (1 - progress);
      const noise = Math.cos(x * 0.01 - timeAngle * 5) * 15 * progress;
      const y = h - 100 + sineWave + noise - (progress * 60);

      if (x === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  };

  return (
    <div className="absolute inset-0 w-full h-full">
      <canvas ref={canvasRef} className="block w-full h-full" />
      
      {/* Cinematic Glass Loading Screen */}
      {loading && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-[#020204]/90 backdrop-blur-xl">
          <div className="w-80 p-6 glass-panel rounded-2xl glass-panel-glow-purple flex flex-col items-center">
            <h3 className="font-title text-xl font-semibold mb-3 tracking-wide text-white">Preloading Synaptic Map</h3>
            <p className="text-sm text-text-muted mb-4 text-center">Caching 3D visualization layers into local memory...</p>
            <div className="w-full bg-white/5 h-2 rounded-full overflow-hidden">
              <div 
                className="bg-gradient-to-r from-purple to-cyan h-full transition-all duration-300 ease-out"
                style={{ width: `${loadingProgress}%` }}
              />
            </div>
            <span className="text-xs text-text-muted mt-2 font-mono">{loadingProgress}%</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default CanvasScroll;
