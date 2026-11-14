const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

(async () => {
  const base = process.env.TEST_URL || 'http://127.0.0.1:5087';
  const password = process.env.TEST_OWNER_PASSWORD || 'preview-only-password';
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'testimonial-browser-'));
  let wallURL;
  const site = http.createServer((request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html' });
    response.end(`<!doctype html><html lang="en"><head><title>Independent example site</title></head><body><h1>Example customer website</h1><iframe title="Customer testimonials" width="900" height="650" src="${wallURL}"></iframe></body></html>`);
  });
  await new Promise(resolve => site.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true,
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  try {
    const owner = await browser.newPage({ viewport: { width: 1360, height: 1000 }, acceptDownloads: true });
    await owner.goto(base);
    await owner.getByRole('link', { name: 'Owner sign in' }).click();
    await owner.getByLabel('Owner password').fill(password);
    await owner.getByRole('button', { name: /Sign in/ }).click();
    const collection = 'Browser acceptance ' + Date.now();
    await owner.getByLabel('Collection name').fill(collection);
    await owner.getByRole('button', { name: 'Create collection' }).click();
    await owner.locator('article').filter({ has: owner.getByRole('heading', { name: collection, exact: true }) }).getByRole('link', { name: /Manage testimonials/ }).click();
    const collect = new URL(await owner.getByRole('link', { name: 'Open request form' }).getAttribute('href'), base).href;
    wallURL = new URL(await owner.getByRole('link', { name: 'View public wall' }).getAttribute('href'), base).href;
    const admin = owner.url();
    const exportURL = new URL(await owner.getByRole('link', { name: 'Export CSV' }).getAttribute('href'), base).href;
    const visitor = await browser.newPage({ viewport: { width: 390, height: 844 } });
    await visitor.goto(collect);
    await visitor.getByLabel('Your name', { exact: true }).fill('Demo contributor');
    await visitor.getByLabel('Role or company').fill('Synthetic example');
    await visitor.getByLabel('Your testimonial').fill('Synthetic acceptance content, not a real customer endorsement.');
    await visitor.getByRole('checkbox').check();
    await visitor.getByRole('button', { name: 'Send testimonial' }).click();
    const removal = new URL(await visitor.getByRole('link', { name: 'Manage removal' }).getAttribute('href'), base).href;

    // A separate context and hostname demonstrate that embeds require no owner/guest session.
    const audience = await browser.newPage({ viewport: { width: 1100, height: 900 } });
    const embedURL = `http://localhost:${site.address().port}`;
    assert.notEqual(new URL(embedURL).origin, new URL(base).origin);
    await audience.goto(embedURL);
    const frame = audience.frameLocator('iframe');
    await frame.getByRole('heading', { name: collection, exact: true }).waitFor();
    assert.equal(await frame.getByText('Demo contributor', { exact: true }).count(), 0, 'Pending testimonials leaked');
    assert.equal((await audience.request.get(exportURL, { maxRedirects: 0 })).status(), 302, 'Anonymous CSV export was allowed');
    const ownerHeaders = (await owner.request.get(admin)).headers();
    assert.equal(ownerHeaders['x-frame-options'], 'DENY');
    const wallHeaders = (await audience.request.get(wallURL)).headers();
    assert.match(wallHeaders['content-security-policy'], /frame-ancestors \*/);
    assert.equal(wallHeaders['cache-control'], 'no-store');

    await owner.goto(admin);
    await owner.getByRole('button', { name: 'Publish', exact: true }).click();
    await audience.reload();
    await frame.getByText('Demo contributor', { exact: true }).waitFor();
    assert.equal((await audience.context().cookies(base)).length, 0, 'Embed unexpectedly depends on cookies');
    await audience.screenshot({ path: path.join(__dirname, 'cross-origin-embed.png'), fullPage: true });
    const event = owner.waitForEvent('download');
    await owner.getByRole('link', { name: 'Export CSV' }).click();
    const csvPath = path.join(tmp, 'testimonials.csv');
    await (await event).saveAs(csvPath);
    const csv = fs.readFileSync(csvPath, 'utf8');
    assert.match(csv, /name,role,quote,status,consent,created/);
    assert.match(csv, /Demo contributor/);
    assert.match(csv, /approved/);

    await owner.getByRole('button', { name: 'Keep private', exact: true }).click();
    await audience.reload();
    await frame.getByRole('heading', { name: collection, exact: true }).waitFor();
    assert.equal(await frame.getByText('Demo contributor', { exact: true }).count(), 0);
    await owner.getByRole('button', { name: 'Publish', exact: true }).click();
    await visitor.goto(removal);
    await visitor.getByRole('button', { name: 'Yes, remove my testimonial' }).click();
    await audience.reload();
    await frame.getByRole('heading', { name: collection, exact: true }).waitFor();
    assert.equal(await frame.getByText('Demo contributor', { exact: true }).count(), 0, 'Withdrawal did not remove embedded content');
    await owner.goto(admin);
    const lastDownload = owner.waitForEvent('download');
    await owner.getByRole('link', { name: 'Export CSV' }).click();
    await (await lastDownload).saveAs(csvPath);
    assert.ok(!fs.readFileSync(csvPath, 'utf8').includes('Demo contributor'), 'Withdrawal did not remove exported data');
    console.log('PASS: consent → pending hidden → approve → cross-origin cookie-free embed → CSV download → private hidden → republish → withdrawal removes embed and CSV; admin framing denied.');
  } finally {
    await browser.close();
    await new Promise(resolve => site.close(resolve));
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
