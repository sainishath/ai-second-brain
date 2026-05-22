import puppeteer from 'puppeteer-core';
import { exec } from 'child_process';
import fs from 'fs';
import path from 'path';

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const outputDir = './frames_record';
const videoOutput = './website_scroll.mp4';
const totalSteps = 240; // 8 seconds of video at 30 fps
const fps = 30;

async function record() {
  console.log('Starting puppeteer recording...');
  
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  // Launch browser pointing to local Chrome installation
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });

  console.log('Navigating to local Vite app (http://localhost:5173)...');
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle2' });

  console.log('Waiting for preloader to complete...');
  // Wait until the "Preloading Synaptic Map" loading screen is gone
  await page.waitForFunction(() => {
    const loader = document.querySelector('h3');
    return !loader || !loader.textContent.includes('Preloading Synaptic Map');
  }, { timeout: 45000 });

  // Wait an extra 2 seconds to settle
  await new Promise(r => setTimeout(r, 2000));
  console.log('Preloader completed. Starting scroll capture...');

  const maxScrollHeight = await page.evaluate(() => {
    return document.documentElement.scrollHeight - window.innerHeight;
  });

  console.log(`Max scroll height: ${maxScrollHeight}px. Capturing ${totalSteps} frames...`);

  for (let i = 0; i <= totalSteps; i++) {
    const progress = i / totalSteps;
    const scrollTop = progress * maxScrollHeight;

    await page.evaluate((scrollVal) => {
      window.scrollTo(0, scrollVal);
    }, scrollTop);

    // Wait 80ms for canvas interpolation / animation to render smoothly
    await new Promise(r => setTimeout(r, 80));

    const frameName = `frame_${String(i).padStart(3, '0')}.jpg`;
    const framePath = path.join(outputDir, frameName);

    await page.screenshot({
      path: framePath,
      type: 'jpeg',
      quality: 90
    });

    if (i % 30 === 0) {
      console.log(`Captured frame ${i}/${totalSteps} (${Math.round(progress * 100)}%)`);
    }
  }

  await browser.close();
  console.log('Browser closed. Compiling video using FFmpeg...');

  const ffmpegCmd = `ffmpeg -y -framerate ${fps} -i "${outputDir}/frame_%03d.jpg" -c:v libx264 -pix_fmt yuv420p "${videoOutput}"`;

  exec(ffmpegCmd, (error, stdout, stderr) => {
    if (error) {
      console.error(`FFmpeg compilation error: ${error.message}`);
      return;
    }
    console.log('FFmpeg compiled successfully!');
    console.log(`Saved video to: ${videoOutput}`);

    // Cleanup frames
    console.log('Cleaning up temporary frame images...');
    fs.readdir(outputDir, (err, files) => {
      if (err) throw err;
      for (const file of files) {
        fs.unlinkSync(path.join(outputDir, file));
      }
      fs.rmdirSync(outputDir);
      console.log('Cleanup completed successfully.');
    });
  });
}

record().catch(console.error);
