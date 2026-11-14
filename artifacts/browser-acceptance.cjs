const { chromium } = require('playwright');
(async()=>{
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1360,height:1000}});
await page.goto('http://127.0.0.1:5087');await page.screenshot({path:require('path').join(__dirname,'home.png'),fullPage:true});
await page.getByRole('link',{name:'Owner sign in'}).click();await page.getByLabel('Owner password').fill('preview-only-password');await page.getByRole('button',{name:'Sign in'}).click();
await page.getByLabel('Collection name').fill('Browser acceptance test');await page.getByRole('button',{name:'Create collection'}).click();await page.getByRole('link',{name:'Manage testimonials'}).first().click();
const collect=await page.getByRole('link',{name:'Open request form'}).getAttribute('href');const wall=await page.getByRole('link',{name:'View public wall'}).getAttribute('href');const admin=page.url();
const visitor=await browser.newPage({viewport:{width:390,height:844}});await visitor.goto('http://127.0.0.1:5087'+collect);await visitor.getByLabel('Your name',{exact:true}).fill('Demo contributor');await visitor.getByLabel('Role or company').fill('Sample only');await visitor.getByLabel('Your testimonial').fill('This is synthetic test content, not a customer endorsement.');await visitor.getByRole('checkbox').check();await visitor.screenshot({path:require('path').join(__dirname,'mobile-form.png'),fullPage:true});await visitor.getByRole('button',{name:'Send testimonial'}).click();
const removal=await visitor.getByRole('link',{name:'Manage removal'}).getAttribute('href');await page.goto(admin);await page.getByRole('button',{name:'Publish',exact:true}).click();await visitor.goto('http://127.0.0.1:5087'+wall);if(!await visitor.getByText('Demo contributor',{exact:true}).isVisible())throw Error('Publication failed');
await visitor.goto('http://127.0.0.1:5087'+removal);await visitor.getByRole('button',{name:'Yes, remove my testimonial'}).click();await visitor.goto('http://127.0.0.1:5087'+wall);if(await visitor.getByText('Demo contributor',{exact:true}).count())throw Error('Withdrawal failed');
console.log('PASS: browser owner login, collection, mobile consent form, approval, public wall, withdrawal');await browser.close();
})();
