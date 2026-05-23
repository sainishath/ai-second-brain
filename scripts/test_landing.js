import puppeteer from 'puppeteer-core';
import path from 'path';

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const outputDir = 'C:\\Users\\saini\\.gemini\\antigravity\\brain\\534c215d-1aa1-4508-a3f4-e7675c83a300';

async function testLanding() {
  console.log('Starting puppeteer landing page test...');

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const errors = [];
  page.on('pageerror', (err) => {
    console.error('[BROWSER ERROR]:', err.toString());
    errors.push(err.toString());
  });

  page.on('response', (response) => {
    if (response.status() >= 400) {
      console.error(`[HTTP ERROR ${response.status()}]: ${response.url()}`);
    }
  });

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      console.error('[BROWSER CONSOLE ERROR]:', msg.text());
    } else {
      console.log('[BROWSER CONSOLE]:', msg.text());
    }
  });

  console.log('Navigating to http://localhost:8000...');
  await page.goto('http://localhost:8000', { waitUntil: 'networkidle2' });

  // 1. Verify page elements exist
  console.log('Verifying key elements...');
  
  // Hero section or video or canvas
  const hasVideo = await page.evaluate(() => {
    const video = document.getElementById('hero-video');
    return video && video.style.display !== 'none';
  });
  console.log(`Hero video playing/active: ${hasVideo}`);

  const hasCanvas = await page.evaluate(() => {
    const canvas = document.getElementById('bg-canvas');
    return canvas && canvas.style.display !== 'none';
  });
  console.log(`Fallback Canvas active: ${hasCanvas}`);

  // Live stats bar
  await page.waitForSelector('#live-stats-strip', { timeout: 5000 });
  const statsContent = await page.evaluate(() => {
    return document.getElementById('live-stats-strip').innerText;
  });
  console.log('Live Stats Strip text:', statsContent);

  // Take hero screenshot
  await page.screenshot({ path: path.join(outputDir, 'landing_1_hero.png') });

  // Scroll to D3 graph
  console.log('Scrolling to D3 visualizer graph...');
  await page.evaluate(() => {
    const el = document.getElementById('visualizer');
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  });
  await new Promise(r => setTimeout(r, 2000));

  // Verify D3 graph SVG exists
  const hasD3 = await page.evaluate(() => {
    const svg = document.getElementById('d3-mini-graph');
    return svg && svg.children.length > 0;
  });
  console.log('D3 Graph elements found:', hasD3);
  await page.screenshot({ path: path.join(outputDir, 'landing_2_graph.png') });

  // 2. Open chat widget and send a query
  console.log('Opening chat widget...');
  const chatToggle = '#chat-widget-toggle';
  await page.waitForSelector(chatToggle, { timeout: 5000 });
  await page.click(chatToggle);

  // Wait for card to be open
  await page.waitForSelector('#chat-widget-card.open', { timeout: 3000 });
  console.log('Chat widget opened.');

  console.log('Typing query into floating chat widget...');
  const chatInput = '#chat-widget-container input';
  await page.type(chatInput, 'Hello, list some tags in my second brain');
  
  console.log('Sending message...');
  const sendBtn = '#chat-widget-container button';
  await page.click(sendBtn);

  // Wait for brain response (allow up to 8 seconds for LLM response)
  console.log('Waiting for backend response...');
  await new Promise(r => setTimeout(r, 6000));

  const messages = await page.evaluate(() => {
    const msgs = Array.from(document.querySelectorAll('.chat-message'));
    return msgs.map(m => ({
      sender: m.classList.contains('user') ? 'user' : 'brain',
      text: m.innerText
    }));
  });
  console.log('Chat Messages in widget:', messages);

  await page.screenshot({ path: path.join(outputDir, 'landing_3_chat_response.png') });

  // 3. Test Launch CTA click (Task 3: loading pulse + redirect)
  console.log('Clicking "Launch Brain" CTA...');
  await page.click('#launch-cta');

  // Verify loading pulse is added
  const isPulse = await page.evaluate(() => {
    const btn = document.getElementById('launch-cta');
    return btn && btn.classList.contains('loading-pulse');
  });
  console.log('Launch CTA loader pulse class added:', isPulse);

  // Wait for 1.5s for redirect to occur
  await new Promise(r => setTimeout(r, 2000));
  
  const currentUrl = page.url();
  console.log('Redirected URL:', currentUrl);

  await page.screenshot({ path: path.join(outputDir, 'landing_4_dashboard.png') });

  await browser.close();

  if (errors.length > 0) {
    console.error('Test completed with browser errors.');
    process.exit(1);
  } else {
    console.log('Test completed successfully with no errors.');
  }
}

testLanding().catch(err => {
  console.error('Unhandled test failure:', err);
  process.exit(1);
});
