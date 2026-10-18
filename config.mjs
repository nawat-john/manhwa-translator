// ตั้งค่ากลาง — ใช้ร่วมกันทั้ง pick-box.mjs และ scrape.mjs
// สำคัญ: viewport/deviceScaleFactor ต้องเหมือนกันทั้งสองสคริปต์
// ไม่งั้นพิกัดกรอบที่ลากไว้จะเลื่อน
export default {
  // URL ที่จะแคป (ใช้กับ scrape.mjs) — โหมดกดลูกศรใช้ click.startUrl แทน
  urls: ["https://comic-days.com/episode/3270375685434847971"],

  pad: 4, // จำนวนหลักของชื่อไฟล์ (4 → 0001.png)

  outDir: 'vol2',

  viewport: { width: 1280, height: 900 },
  deviceScaleFactor: 2, // 2 = ภาพคมขึ้นเท่าตัว

  waitFor: 'canvas', // selector ที่รอให้โผล่ก่อนแคป (null = ไม่รอ)
  scrollToBottom: true, // เลื่อนลงล่างก่อน เพื่อกระตุ้น lazy-load
  settleMs: 600, // รอหลังโหลดเสร็จ ให้ภาพ/ฟอนต์นิ่ง
  politeDelayMs: 1200, // เว้นระยะระหว่างหน้า อย่ายิงรัวเกินไป

  headless: true,
  overwrite: false, // false = ข้ามไฟล์ที่มีอยู่แล้ว (resume ได้)

  // โหมดกดลูกศรซ้าย (scrape-click.mjs) — snapshot → กดลูกศร → รอโหลด → วนใหม่
  click: {
    startUrl: '', // หน้าแรกที่จะเริ่มวน (ส่งทาง argv ก็ได้)

    // วิธีไปหน้าถัดไป เลือกอย่างใดอย่างหนึ่ง (ลำดับความสำคัญ: selector > key > point)
    key: null, // กดคีย์บอร์ด เช่น 'ArrowLeft'
    selector: null, // คลิกปุ่มตาม CSS selector
    point: { x: 0, y: 300 }, // คลิกพิกัดในจอ — ใส่ { xPct, yPct } แทนก็ได้ถ้าอยากคิดเป็นสัดส่วน

    maxPages: 500, // กันวนไม่รู้จบ
    afterClickMs: 5000, // รอหลังกดนานสุดเท่านี้ (ออกเร็วถ้าเนื้อหาเปลี่ยนก่อน)
    imgWaitMs: 8000, // เพดานเวลารอรูปโหลด กันค้างเวลารูปโหลดไม่ขึ้น
    startIndex: 1, // เลขลำดับเริ่มต้นของชื่อไฟล์/log
    logFile: 'pages.log', // ไฟล์เก็บ url ของแต่ละหน้า
  },
};
