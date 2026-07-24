import { mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import sharp from 'sharp';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const input = resolve(
  root,
  'desktop-wallpaper/assets/concepts/model-references-v3/xiao-qi-head-turnaround/front.png'
);
const output = resolve(
  root,
  'desktop-wallpaper/assets/faces/xiao-qi-curved-face-v1.webp'
);

const size = 1024;
const mask = Buffer.from(`
  <svg width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <filter id="soft-edge">
        <feGaussianBlur stdDeviation="12"/>
      </filter>
    </defs>
    <ellipse
      cx="512"
      cy="392"
      rx="438"
      ry="410"
      fill="white"
      filter="url(#soft-edge)"
    />
  </svg>
`);

await mkdir(dirname(output), { recursive: true });
const cropped = await sharp(input)
  .extract({ left: 256, top: 238, width: 772, height: 772 })
  .resize(size, size, { fit: 'fill', kernel: sharp.kernel.lanczos3 })
  .removeAlpha()
  .png()
  .toBuffer();
const alpha = await sharp(mask)
  .extractChannel('alpha')
  .png()
  .toBuffer();

await sharp(cropped)
  .joinChannel(alpha)
  .webp({ quality: 95, alphaQuality: 100, effort: 6 })
  .toFile(output);

console.log(output);
