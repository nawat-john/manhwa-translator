# hanaori-san-scrape

## Version control

Git เก็บโค้ด การตั้งค่าที่ไม่มีความลับ คู่มือ และ dependency lockfile ส่วนรูปที่ดาวน์โหลด โมเดล venv cache ผลลัพธ์ และ token เก็บเฉพาะในเครื่อง ไม่รวมในประวัติ Git

เครื่องใหม่ให้กู้ upstream ตาม [คู่มือ patch](translator/patches/README.md) ก่อนติดตั้ง Python environment และใช้ `npm ci` สำหรับ Node dependencies รูปตัวอย่างและผลแปลที่ลิงก์ด้านล่างต้องสร้างหรือดาวน์โหลดใหม่

```powershell
git status
git diff
git add <ไฟล์ที่แก้>
git commit -m "Describe the change"
git log --oneline
```

Git ในเครื่องช่วยย้อนเวอร์ชันโค้ด แต่ยังไม่ใช่การสำรองข้อมูลนอกเครื่อง ดู [ข้อมูลฝึกภาษาพูด](translator/DATASETS.md) สำหรับแนวทางปรับโมเดลเกาหลี–อังกฤษ

## Chrome extension — แปลภาพบน Naver

ภาพเกาหลีจะถูกต่อข้ามรอยต่อไฟล์และแบ่งที่ช่องว่างแนวนอนก่อนแปล ดู [ผลทดลอง 10 หน้าย่อยใหม่](samples/naver-845456-25/english-panels-10/index.html) และ [แผนที่การแบ่งหน้า](samples/naver-845456-25/panels/README.md)

รัน `npm run extension:serve` แล้วเปิด `chrome://extensions` → Developer mode → Load unpacked → เลือกโฟลเดอร์ `extension` รีเฟรชหน้าอ่าน Naver จะมีปุ่ม **แปลภาพนี้ · EN** และปุ่มสลับกลับต้นฉบับ ดู [วิธีติดตั้งและข้อจำกัด](extension/README.md)

## Manga Lab — ทดสอบแปลภาพญี่ปุ่นเป็นอังกฤษ

รัน `npm run lab` แล้วเปิด **http://127.0.0.1:4173** เพื่อเทียบต้นฉบับกับคำแปล เลือกดูภาพที่มีอยู่ และสั่งแปลใหม่ทีละหน้า ดูการวิเคราะห์ ข้อจำกัด และแนวทางต่อ Chrome extension ที่ [lab/README.md](lab/README.md)

เก็บภาพหน้าเว็บด้วย Playwright โดยกำหนด "กรอบ" ที่จะแคปเองได้ผ่านการลากเมาส์

## โครงไฟล์

| ไฟล์ | หน้าที่ |
| --- | --- |
| `config.mjs` | ตั้งค่ากลาง — URL, ช่วงหน้า, viewport, จังหวะรอ |
| `pick-box.mjs` | เปิดเบราว์เซอร์จริงให้ลากกรอบ แล้วเซฟพิกัดลง `box.json` |
| `scrape.mjs` | วนทุกหน้า **จาก URL** แคปตามกรอบใน `box.json` |
| `scrape-click.mjs` | วนหน้าด้วย **การกดลูกศรซ้าย** — snapshot → คลิก → รอโหลด |
| `pages.log` | URL ของแต่ละหน้าจากโหมดกดลูกศร พร้อมเลขลำดับ |
| `debug.mjs` | ไล่ปัญหา — รายงานว่าหน้าเว็บมีอะไร กดแล้วเกิดอะไร |
| `debug/` | ภาพจาก `debug.mjs` (`full-N.png`, `clip-N.png`) |
| `box.json` | ผลจากขั้นตอนตีกรอบ (สร้างอัตโนมัติ) |
| `failed.json` | สรุปหน้าที่แคปไม่สำเร็จ (สร้างเมื่อมีปัญหา) |
| `vol1/` | ปลายทางไฟล์ภาพ |

## ติดตั้ง

```powershell
npm install
npx playwright install chromium
```

## ใช้งาน

### 1. ตั้งค่า

แก้ `config.mjs`

- URL ไม่มีเลขหน้า เลยไม่มีการไล่เลขใน URL — เลือกเอาอย่างใดอย่างหนึ่ง
  - `click.startUrl` — หน้าแรกของโหมดกดลูกศร (ทางหลัก ดูข้อ 3b)
  - `urls: []` — ลิสต์ URL ตรง ๆ ถ้ารู้ทุกหน้าอยู่แล้ว (ใช้กับ `scrape.mjs`)
- `pad` — จำนวนหลักของชื่อไฟล์ (`4` → `0001.png`)
- `waitFor` — selector ที่ต้องรอให้โผล่ก่อนแคป ใส่ให้ตรงกับภาพ/เนื้อหาจริงของหน้านั้น ใส่ `null` ถ้าไม่ต้องรอ

### 2. ตีกรอบ

```powershell
npm run pick              # ใช้ click.startUrl (หรือ urls[0]) จาก config
node pick-box.mjs <url>   # หรือระบุหน้าเอง
```

เบราว์เซอร์จะเปิดขึ้นมาพร้อม HUD ที่มุมซ้ายบน

| คีย์ / การกระทำ | ผล |
| --- | --- |
| ลากเมาส์ | วาดกรอบ ตัวเลข `x y w h` อัปเดตสด ๆ |
| `E` | สลับโหมด **เลือกอิลิเมนต์** — เอาเมาส์ชี้ กรอบ snap เข้าขอบให้เอง คลิกเพื่อล็อก |
| `Esc` | ล้างกรอบ เริ่มใหม่ |
| `Enter` | ยืนยัน เซฟลง `box.json` แล้วปิดเบราว์เซอร์ |

โหมดเลือกอิลิเมนต์จะบันทึก CSS selector ติดมาให้ด้วย

### 3. เก็บภาพ (จากลิสต์ URL)

```powershell
npm run scrape        # ทุก URL ใน config.urls
node scrape.mjs 5 12  # เฉพาะลำดับที่ 5–12 ในลิสต์
```

- ไฟล์ออกที่ `vol1/0001.png`, `0002.png`, … (ตาม `pad`)
- รันซ้ำได้ ไฟล์ที่มีอยู่แล้วจะถูกข้าม (ตั้ง `overwrite: true` ถ้าอยากทับ)
- แต่ละหน้าลองใหม่ 1 ครั้งถ้าพลาด สุดท้ายที่ยังไม่ผ่านจะไปรวมใน `failed.json`

### 3b. เก็บภาพแบบกดลูกศรซ้าย

ทางหลักของโปรเจกต์นี้ เพราะ URL ไม่มีเลขหน้า ต้องกดลูกศรไล่ไปทีละหน้า

```powershell
npm run scrape:click                       # ใช้ config.click.startUrl
node scrape-click.mjs <url>                # เริ่มจาก url นี้
node scrape-click.mjs <url> 60             # จำกัด 60 หน้า
```

ลูปคือ **snapshot → กดลูกศรซ้าย → รอโหลด → วนใหม่**

วิธีไปหน้าถัดไป เลือกได้ 3 แบบใน `config.click` (ลำดับความสำคัญ `selector` > `key` > `point`)

| คีย์ | ความหมาย |
| --- | --- |
| `key: 'ArrowLeft'` | **ค่าเริ่มต้น** — กดลูกศรซ้ายบนคีย์บอร์ด |
| `selector: '.btn-prev'` | คลิกปุ่มตาม CSS selector |
| `point: { xPct: 0.25, yPct: 0.5 }` | คลิกพิกัดสัมพัทธ์ของ viewport (สำหรับ reader ที่ใช้โซนคลิกซ้าย/ขวา) |

ถ้าเซ็ต `key: null` และไม่ใส่อย่างอื่น สคริปต์จะเดาปุ่มลูกศรเองจาก `aria-label`/class/ข้อความ/ตำแหน่ง — หาไม่เจอจะพิมพ์ลิสต์อิลิเมนต์ที่เข้าข่ายพร้อมพิกัด/ขนาด และเซฟ `debug-page.png` ไว้ให้ดู

- `afterClickMs` (ค่าเริ่ม 5000) — รอหลังกด **นานสุด** เท่านี้ ถ้าเนื้อหาเปลี่ยนก่อนก็ไปต่อเลย ไม่รอเต็มเวลา
- `imgWaitMs` (ค่าเริ่ม 8000) — เพดานเวลารอรูปโหลด **อย่าเอาออก** รูปที่โหลดไม่ขึ้นจะไม่ยิง event `load` เลย ถ้ารอแบบไม่มีเพดานคือค้างถาวร
- URL ทุกหน้าถูก append ลง `pages.log` ทันทีที่แคปเสร็จ (crash แล้วยังเหลือของ) หน้าที่ URL เปลี่ยนจากหน้าก่อนจะมีมาร์ก `<- url เปลี่ยน` ต่อท้าย

```
0001	https://example.com/reader
0002	https://example.com/reader
0003	https://example.com/reader/ch2	<- url เปลี่ยน
```

- หยุดเองเมื่อ: ครบ `maxPages` / กดไม่ได้ / **ภาพที่แคปได้ซ้ำกับหน้าก่อนสองครั้งติด** (= สุดเล่ม) หน้าที่ซ้ำไม่กินเลขลำดับ ไม่มีไฟล์ซ้ำใน `vol1/`
  - จงใจเทียบจาก hash ของภาพ ไม่ใช่จาก DOM เพราะ reader ที่ preload รูปทั้งเล่มไว้ตั้งแต่แรกจะมี `src` เท่าเดิมทุกหน้า ดูจาก DOM แล้วจะเข้าใจผิดว่าจบเล่มตั้งแต่หน้าสอง
- resume: ตั้ง `click.startIndex` ให้ต่อจากเลขล่าสุด (ไฟล์ที่มีอยู่แล้วจะถูกข้ามถ้า `overwrite: false` แต่ยังต้องคลิกไล่ผ่านอยู่ดี)

### 4. ไล่ปัญหา (`debug.mjs`)

รันก่อนปล่อยยาวทุกครั้งที่เจอเว็บใหม่ หรือเวลาสคริปต์ค้าง/ได้ภาพผิด

```powershell
npm run debug                     # url จาก config, กดลูกศร 3 ครั้ง
node debug.mjs 5                  # กด 5 ครั้ง
node debug.mjs <url> 5            # ระบุ url เอง
node debug.mjs <url> 3 --headed   # เปิดหน้าจอให้เห็น แล้วค้างไว้จนกด Ctrl+C
```

รายงานที่ได้

| หัวข้อ | ใช้ดูอะไร |
| --- | --- |
| เวลา `domcontentloaded` / `waitFor` | `waitFor` ตรงหรือ timeout — ถ้าขึ้น "ไม่เจอ" คือเสียเวลาเปล่า 15 วิ/หน้า |
| `รอรูปโหลด ... ชนเพดาน imgWaitMs` | มีรูปที่ไม่ยิง `load`/`error` (จุดที่เคยทำให้ค้างถาวร) |
| ลิสต์ `img`/`canvas` ที่มองเห็น | ขนาด/ตำแหน่งจริง เอาไปเทียบกับ `clip` ใน `box.json` ได้ พร้อมมาร์ก `โหลดไม่ขึ้น!` |
| `iframe` | เนื้อหาอยู่ในเฟรมลูกหรือเปล่า |
| ปุ่มที่เข้าข่ายลูกศรซ้าย | ตัวเลือกสำหรับ `click.selector` พร้อมพิกัด |
| `keydown listener บน window/document` | เว็บรับคีย์บอร์ดจริงไหม (ถ้า "ไม่มี" ก็อย่าใช้ `click.key`) |
| ต่อการกดแต่ละครั้ง | ภาพในกรอบเปลี่ยนที่วินาทีไหน / url เปลี่ยนไหม / hash ของภาพ |
| `error` + `request ที่ล้ม` | console error, pageerror, request ที่ถูกบล็อก |

ไฟล์ที่ออกใน `debug/` — `full-N.png` (ทั้งหน้า) กับ `clip-N.png` (เฉพาะกรอบ) `N` คือจำนวนครั้งที่กด เอามาเรียงดูว่าหน้าเปลี่ยนจริงและกรอบตรงไหม

## โน้ตสำคัญ

### พิกัด vs selector — เลือกได้

`box.json` เก็บทั้งสองแบบ

```json
{
  "clip": { "x": 320, "y": 180, "width": 640, "height": 900 },
  "selector": "div.reader > img:nth-of-type(1)"
}
```

`scrape.mjs` จะใช้ `clip` เป็นหลัก **ถ้าลบคีย์ `clip` ออกเหลือแต่ `selector`** มันจะสลับไปใช้ `locator().screenshot()` ซึ่งทนกว่ามากเวลาเลย์เอาต์แต่ละหน้าไม่ตรงกันเป๊ะ เพราะกรอบขยับตามอิลิเมนต์เอง

แนะนำ: ถ้าเนื้อหาที่ต้องการอยู่ในกล่องเดียวชัดเจน ลองโหมด selector ก่อน แล้วค่อยถอยไปใช้พิกัดถ้า selector ไม่นิ่ง

### viewport ต้องล็อกค่าเดียวกัน

พิกัดที่ลากไว้ผูกกับ `viewport` + `deviceScaleFactor` ใน config **ถ้าไปแก้ค่าพวกนี้ทีหลังต้องรัน `pick` ใหม่** ไม่งั้นกรอบเลื่อน นี่คือเหตุผลที่ทั้งสองสคริปต์อ่านค่าจากไฟล์เดียวกัน

`deviceScaleFactor: 2` ทำให้ภาพคมขึ้นเท่าตัว (แลกกับไฟล์ใหญ่ขึ้น)

### พิกัดเป็น page space ไม่ใช่ viewport

`pick-box.mjs` บวก `scrollX/scrollY` เข้าไปแล้ว และ `scrape.mjs` แคปด้วย `fullPage: true` ให้ตรงกัน เลยตีกรอบส่วนที่อยู่ใต้ fold ได้ ไม่ต้องเลื่อนหน้าให้ตรงก่อน

### ถ้าเป้าหมายเป็นรูปเดี่ยว ๆ อย่า screenshot

screenshot ได้ภาพที่ผ่านการ resize/รีคอมเพรสจากเบราว์เซอร์ คมสู้ไฟล์ต้นฉบับไม่ได้ ถ้าสิ่งที่ต้องการคือตัวรูปตรง ๆ ให้ดึง `src` มาโหลดแทน จะได้คุณภาพเต็ม

```js
const src = await page.locator('#page-img').getAttribute('src');
const res = await context.request.get(new URL(src, url).href);
await writeFile(out, await res.body());
```

(`context.request` ใช้ cookie/header ชุดเดียวกับเบราว์เซอร์ เลยผ่านพวกเช็ก referer/auth ไปด้วย)

### ตัวเลือก clip อื่นที่ Playwright มี

```js
// เอาเฉพาะอิลิเมนต์
await page.locator('#card').screenshot({ path: 'card.png' });

// ขยาย padding รอบอิลิเมนต์
const b = await page.locator('#card').boundingBox();
await page.screenshot({
  clip: { x: b.x - 16, y: b.y - 16, width: b.width + 32, height: b.height + 32 },
});

// visual regression — mask ปิดส่วนที่เปลี่ยนตลอด กัน test แตก
await expect(page).toHaveScreenshot({ clip: {...}, mask: [page.locator('.ads')] });
```

## แก้ปัญหา

| อาการ | สาเหตุที่เจอบ่อย |
| --- | --- |
| ภาพว่าง / ขาวโพลน | `waitFor` ไม่ตรง หรือ `settleMs` น้อยเกิน ลองเพิ่มเป็น 1500 |
| ภาพครึ่งเดียว / รูปหายบางส่วน | lazy-load ยังไม่ยิง เช็กว่า `scrollToBottom: true` |
| กรอบเลื่อนไปจากที่ลาง | `viewport`/`deviceScaleFactor` ถูกแก้หลังตีกรอบ → รัน `pick` ใหม่ |
| ถูกบล็อก / 429 | เพิ่ม `politeDelayMs` และลองตั้ง `headless: false` |
| selector ใช้ไม่ได้บางหน้า | เปลี่ยนไปใช้โหมด `clip` หรือแก้ selector ใน `box.json` ให้กว้างขึ้น |

ดีบักด้วยการตั้ง `headless: false` ใน config จะเห็นว่าหน้าเว็บโหลดถึงไหนแล้ว

## ก่อนยิงจริง

เช็ก `robots.txt` กับเงื่อนไขการใช้งานของเว็บปลายทางก่อน และอย่าลด `politeDelayMs` ต่ำกว่าค่าเริ่มต้นมาก
