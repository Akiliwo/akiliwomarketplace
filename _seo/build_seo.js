#!/usr/bin/env node
/*
 * Akiliwo Marketplace: SEO page builder.
 *
 *     node _seo/build_seo.js
 *
 * Run it after adding, editing or removing a product in index.html. It reads the
 * PRODUCTS list from index.html and writes:
 *   p/<product-slug>.html   one indexable page per product (title, description, photos,
 *                           price, buy buttons, schema.org Product data)
 *   sitemap.xml             every page + its photos, for Google Search Console
 *   robots.txt              lets search engines crawl everything and points to the sitemap
 *   google-shopping-feed.xml  product feed for Google Merchant Center (free Shopping listings)
 *   facebook-catalog.csv      product feed for Meta Commerce Manager (Facebook/Instagram catalog)
 *   assets/checkout-products.json  product lookup for checkout.html (Facebook shop checkout URL)
 *   index.html              the plain-HTML product directory between the SEO-DIRECTORY markers
 *                           (links search engines can follow even without running JavaScript)
 *
 * No npm packages needed. `_seo/` starts with "_", so GitHub Pages does not publish it.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SITE = 'https://www.akiliwomarketplace.com';
const WA = '17207994089';
const INDEX = path.join(ROOT, 'index.html');

const html = fs.readFileSync(INDEX, 'utf8');
const start = html.indexOf('const PRODUCTS = [');
const end = html.indexOf('\n];', start);
if (start < 0 || end < 0) throw new Error('PRODUCTS list not found in index.html');
const PRODUCTS = new Function(html.slice(start, end + 3) + '\nreturn PRODUCTS;')();

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const slug = s => String(s).toLowerCase().replace(/&/g, 'and').replace(/['’]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80).replace(/-$/, '');
const bold = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
const plain = s => String(s || '').replace(/\*\*/g, '');
const priceNum = s => { const m = String(s || '').replace(/,/g, '').match(/\d+(\.\d+)?/); return m ? Number(m[0]).toFixed(2) : null; };
const isUsed = p => /\b(used|pre-owned)\b/i.test([p.title, p.badge, p.desc].join(' '));
const isSold = p => /sold/i.test(p.badge || '');
const SECTION = {shop: 'Shop', books: 'Books & Media', digital: 'Digital'};
// card checkout Worker address from assets/shop-config.js ('' = not set up yet: keep card link / WhatsApp buttons)
const CARD_CHECKOUT = ((fs.readFileSync(path.join(ROOT, 'assets', 'shop-config.js'), 'utf8').match(/AKILIWO_CARD_CHECKOUT\s*=\s*'([^']*)'/) || [])[1] || '').trim();
const abs = u => /^https?:/.test(u) ? u : `${SITE}/${u}`;
function imgVariant(src, w) {
  const m = src.match(/^(images\/.+)-1000\.webp$/);
  return m ? `${m[1]}-${w}.webp` : src;
}
function summary(p) {
  const base = plain(p.desc || [p.tagline, p.hook, ...(p.story || [])].filter(Boolean).join(' '));
  const t = base.replace(/\s+/g, ' ').trim();
  if (t.length <= 155) return t;
  const cut = t.slice(0, 152);
  return cut.slice(0, cut.lastIndexOf(' ')) + '…';
}

// stable, unique slugs
const used = new Set();
PRODUCTS.forEach(p => {
  let s = slug(p.title) || 'product', n = 2;
  while (used.has(s)) s = `${slug(p.title)}-${n++}`;
  used.add(s);
  p._slug = s;
  // only real photo files count (skip inline placeholder drawings)
  p.images = (p.images || []).filter(src => !/^data:/.test(src));
  p._url = `${SITE}/p/${s}.html`;
});

// Every product gets a short stable id (max 50 chars): used by both feeds, checkout.html and the card checkout.
const usedIds = new Set();
PRODUCTS.forEach(p => {
  let id = p._slug.slice(0, 50).replace(/-$/, ''), n = 2;
  while (usedIds.has(id)) id = `${p._slug.slice(0, 46)}-${n++}`;
  usedIds.add(id);
  p._id = id;
});
function productLD(p) {
  const opts = (p.formats && p.formats.length) ? p.formats : [{price: p.price, link: p.link}];
  const offers = opts.map(o => priceNum(o.price)).filter(Boolean).map(price => {
    const o = {'@type': 'Offer', price, priceCurrency: 'USD', url: p._url,
      availability: isSold(p) ? 'https://schema.org/SoldOut' : 'https://schema.org/InStock',
      seller: {'@type': 'Organization', name: 'Akiliwo Marketplace'}};
    if (isUsed(p)) o.itemCondition = 'https://schema.org/UsedCondition';
    return o;
  });
  const ld = {'@context': 'https://schema.org', '@type': p.category === 'books' && /book/i.test(p.sub || '') ? ['Product', 'Book'] : 'Product',
    name: p.title, description: summary(p), category: p.sub || SECTION[p.category], url: p._url};
  if (p.images && p.images.length) ld.image = p.images.map(abs);
  if (p.author) ld.author = {'@type': 'Person', name: p.author};
  if (offers.length) ld.offers = offers.length === 1 ? offers[0] : offers;
  return ld;
}

function page(p) {
  const imgs = (p.images || []);
  const opts = (p.formats && p.formats.length) ? p.formats : [{name: '', price: p.price, link: p.link}];
  const buy = isSold(p) ? '<span class="btn off">Sold out</span>' : CARD_CHECKOUT
    ? `<div class="opt"><span class="price">${esc(p.price)}</span><a class="btn card" href="../checkout.html?products=${encodeURIComponent(p._id + ':1')}" rel="nofollow">💳 Buy now with card</a></div>`
    : opts.map(o => {
    const wa = `https://wa.me/${WA}?text=` + encodeURIComponent(`Hello Akiliwo Marketplace, I would like to order: ${p.title}${o.name ? ' (' + o.name + ')' : ''} — ${o.price}. Is it available?`);
    return `<div class="opt">${o.name ? `<b>${esc(o.name)}</b> ` : ''}<span class="price">${esc(o.price)}</span>${o.note ? `<small>${esc(o.note)}</small>` : ''}
        ${o.link && o.link.trim() ? `<a class="btn card" href="${esc(o.link)}" rel="nofollow noopener" target="_blank">💳 Buy now with card</a>` : ''}
        <a class="btn wa" href="${wa}" rel="nofollow noopener" target="_blank">💬 Order on WhatsApp</a></div>`;
  }).join('\n      ');
  const related = PRODUCTS.filter(q => q !== p && q.sub && q.sub === p.sub).slice(0, 8);
  const catHash = '#cat-' + slug(p.sub || p.category);
  const crumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
    {'@type': 'ListItem', position: 1, name: 'Home', item: SITE + '/'},
    {'@type': 'ListItem', position: 2, name: p.sub || SECTION[p.category], item: SITE + '/' + catHash},
    {'@type': 'ListItem', position: 3, name: p.title, item: p._url}]};
  const title = `${p.title}${p.author ? ' by ' + p.author : ''} | ${p.sub || SECTION[p.category]} | Akiliwo Marketplace`;
  const vid = (p.videos || [])[0];
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)}</title>
<meta name="description" content="${esc(summary(p))}">
<link rel="canonical" href="${p._url}">
<meta property="og:type" content="product">
<meta property="og:site_name" content="Akiliwo Marketplace">
<meta property="og:url" content="${p._url}">
<meta property="og:title" content="${esc(p.title)} — ${esc(p.price)}">
<meta property="og:description" content="${esc(summary(p))}">
${imgs[0] ? `<meta property="og:image" content="${abs(imgs[0])}">\n` : ''}<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0c4434">
<script type="application/ld+json">${JSON.stringify(productLD(p))}</script>
<script type="application/ld+json">${JSON.stringify(crumbs)}</script>
<link rel="stylesheet" href="../assets/product.css">
<script src="../assets/shop-config.js"></script>
<script src="../assets/pixel.js"></script>
<script>window.akTrack('ViewContent', ${JSON.stringify({content_ids: [p._id], content_type: 'product', content_name: p.title, currency: 'USD', ...(priceNum(p.price) ? {value: Number(priceNum(p.price))} : {})}).replace(/</g, '\\u003c')});</script>
</head>
<body>
<header><div class="wrap"><a class="brand" href="../"><span class="mark">A</span> Akiliwo Marketplace</a><a class="back" href="../${catHash}">← All ${esc(p.sub || SECTION[p.category])}</a></div></header>
<main class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><a href="../">Home</a> › <a href="../${catHash}">${esc(p.sub || SECTION[p.category])}</a> › <span>${esc(p.title)}</span></nav>
  <article class="product">
    <div class="photos">
      ${imgs.length ? imgs.map((src, i) => `<img src="../${imgVariant(src, 1000)}" srcset="../${imgVariant(src, 500)} 500w, ../${imgVariant(src, 1000)} 1000w" sizes="(max-width: 760px) 92vw, 520px" alt="${esc(p.title)} — photo ${i + 1}"${i ? ' loading="lazy"' : ''} width="1000" height="1000">`).join('\n      ') : `<div class="emoji">${p.emoji || '📦'}</div>`}
      ${vid ? `<video controls preload="none" playsinline poster="../${esc(vid.poster || '')}" src="../${esc(vid.src)}"></video>` : ''}
    </div>
    <div class="info">
      ${p.sub ? `<div class="cat">${esc(p.sub)}</div>` : ''}
      <h1>${esc(p.title)}</h1>
      ${p.author ? `<p class="author">by ${esc(p.author)}</p>` : ''}
      ${p.badge ? `<span class="badge">${esc(p.badge)}</span>` : ''}
      <div class="buy">
      ${buy}
      </div>
      ${p.tagline ? `<p class="lead">${esc(p.tagline)}</p>` : ''}
      ${p.desc ? `<p>${esc(p.desc)}</p>` : ''}
      ${(p.story || []).map(t => `<p>${bold(t)}</p>`).join('\n      ')}
      ${(p.benefits || []).length ? `<h2>Features &amp; benefits</h2><ul>${p.benefits.map(b => `<li>${esc(b)}</li>`).join('')}</ul>` : ''}
      ${(p.highlights || []).length ? `<h2>${esc(p.highlightsTitle || 'Highlights')}</h2><ul>${p.highlights.map(b => `<li>${esc(b)}</li>`).join('')}</ul>` : ''}
      ${(p.details || []).length ? `<h2>${esc(p.detailsTitle || 'Details')}</h2><dl>${p.details.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
      ${p.disclaimer ? `<p class="fda">${esc(p.disclaimer)}</p>` : ''}
      <ul class="trust"><li>🔒 Secure checkout</li><li>🚚 Ships from Denver, Colorado (USA)</li><li><a href="../#returns">↩️ 30-day returns</a></li></ul>
      <p class="ask">Questions? Call or text <a href="tel:+17207994089">+1 720 799 4089</a> or email <a href="mailto:info@akiliwomarketplace.com">info@akiliwomarketplace.com</a></p>
    </div>
  </article>
  ${related.length ? `<section class="related"><h2>More ${esc(p.sub)}</h2><div class="rel-grid">${related.map(q => `<a href="${q._slug}.html">${q.images && q.images[0] ? `<img src="../${imgVariant(q.images[0], 200)}" alt="" loading="lazy" width="200" height="200">` : `<span class="emoji">${q.emoji || '📦'}</span>`}<span>${esc(q.title)}</span><b>${esc(q.price)}</b></a>`).join('')}</div></section>` : ''}
</main>
<footer><div class="wrap">© Akiliwo Marketplace LLC · Denver, Colorado · <a href="../">Home</a> · <a href="../#browse">All categories</a> · <a href="../#returns">Returns</a> · <a href="../#contact">Contact</a></div></footer>
</body>
</html>
`;
}

// ---- write product pages (and remove pages of products that no longer exist) ----
const outDir = path.join(ROOT, 'p');
fs.mkdirSync(outDir, {recursive: true});
const keep = new Set(PRODUCTS.map(p => p._slug + '.html'));
fs.readdirSync(outDir).filter(f => f.endsWith('.html') && !keep.has(f)).forEach(f => fs.unlinkSync(path.join(outDir, f)));
PRODUCTS.forEach(p => fs.writeFileSync(path.join(outDir, p._slug + '.html'), page(p)));

// ---- sitemap.xml + robots.txt ----
const today = new Date().toISOString().slice(0, 10);
const urlXml = (loc, imgs) => `  <url>\n    <loc>${esc(loc)}</loc>\n    <lastmod>${today}</lastmod>\n${(imgs || []).map(i => `    <image:image><image:loc>${esc(abs(i))}</image:loc></image:image>\n`).join('')}  </url>`;
fs.writeFileSync(path.join(ROOT, 'sitemap.xml'),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n` +
  [urlXml(SITE + '/'), ...PRODUCTS.map(p => urlXml(p._url, p.images))].join('\n') + '\n</urlset>\n');
fs.writeFileSync(path.join(ROOT, 'robots.txt'), `User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`);

// ---- Product feeds: Google Merchant Center (free Shopping listings) + Meta catalog (Facebook/Instagram) ----
// Shipping and returns are set in the Merchant Center / Commerce Manager accounts, not here.
// Products without a real photo are left out (both platforms reject them).
const feed = PRODUCTS.filter(p => p.images.length && priceNum(p.price)).map(p => {
  return {
    id: p._id, p,
    title: p.title.slice(0, 150),
    desc: plain([p.desc || [p.tagline, ...(p.story || [])].filter(Boolean).join(' '), ...(p.benefits || []), p.disclaimer].filter(Boolean).map(t => /[.!?…]$/.test(t.trim()) ? t.trim() : t.trim() + '.').join(' ')).replace(/\s+/g, ' ').slice(0, 4900),
    images: p.images.slice(0, 10).map(abs),
    inStock: !isSold(p),
    price: `${priceNum(p.price)} USD`,
    condition: isUsed(p) ? 'used' : 'new',
    // real brand only for Akiliwo's own products; others have none we can vouch for
    brand: /^Akiliwo\b/.test(p.title) || p.featured ? 'Akiliwo' : '',
    type: `${SECTION[p.category] || ''} > ${p.sub || ''}`,
  };
});
fs.writeFileSync(path.join(ROOT, 'google-shopping-feed.xml'),
  `<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n  <channel>\n    <title>Akiliwo Marketplace</title>\n    <link>${SITE}/</link>\n    <description>Akiliwo Marketplace products</description>\n` +
  feed.map(f => `    <item>
      <g:id>${esc(f.id)}</g:id>
      <g:title>${esc(f.title)}</g:title>
      <g:description>${esc(f.desc)}</g:description>
      <g:link>${esc(f.p._url)}</g:link>
      <g:image_link>${esc(f.images[0])}</g:image_link>
${f.images.slice(1).map(i => `      <g:additional_image_link>${esc(i)}</g:additional_image_link>\n`).join('')}      <g:availability>${f.inStock ? 'in_stock' : 'out_of_stock'}</g:availability>
      <g:price>${f.price}</g:price>
      <g:condition>${f.condition}</g:condition>
${f.brand ? `      <g:brand>${f.brand}</g:brand>\n` : ''}      <g:identifier_exists>no</g:identifier_exists>
      <g:product_type>${esc(f.type)}</g:product_type>
    </item>`).join('\n') + `\n  </channel>\n</rss>\n`);
// Meta's Commerce Policies prohibit ingestible supplements, so these sub-categories stay off
// the Facebook/Instagram catalog (they remain on the website and in the Google feed).
const META_EXCLUDED_SUBS = new Set(['Herbal Wellness']);
// Meta requires a brand on every item; items without a real brand carry the seller's name.
// Meta accepts only JPEG/PNG photos, so the Facebook feed points at JPEG copies in images/feed/.
const {execFileSync} = require('child_process');
const feedJpg = url => {
  const rel = url.slice(SITE.length + 1);
  if (!/^images\/.+\.webp$/.test(rel)) return url;
  const out = `images/feed/${path.basename(rel, '.webp').replace(/-1000$/, '')}.jpg`;
  if (!fs.existsSync(path.join(ROOT, out))) execFileSync('python3', [path.join(__dirname, 'feed_jpg.py'), path.join(ROOT, rel), path.join(ROOT, out)]);
  return `${SITE}/${out}`;
};
const csv = v => /[",\n]/.test(v) ? `"${String(v).replace(/"/g, '""')}"` : String(v);
fs.writeFileSync(path.join(ROOT, 'facebook-catalog.csv'),
  ['id,title,description,availability,condition,price,link,image_link,additional_image_link,brand,product_type',
   ...feed.filter(f => !META_EXCLUDED_SUBS.has(f.p.sub)).map(f => [f.id, f.title, f.desc, f.inStock ? 'in stock' : 'out of stock', f.condition, f.price, f.p._url,
     feedJpg(f.images[0]), f.images.slice(1).map(feedJpg).join(','), f.brand || 'Akiliwo Marketplace', f.type].map(csv).join(','))].join('\n') + '\n');

// ---- checkout data: Facebook/Instagram shop "Buy" sends buyers to checkout.html?products=<id>:<qty>,...
// The ids are the feed ids above, so checkout.html can look each product up here.
fs.writeFileSync(path.join(ROOT, 'assets', 'checkout-products.json'), JSON.stringify(Object.fromEntries(PRODUCTS.filter(p => priceNum(p.price)).map(p => [p._id, {
  title: p.title, price: priceNum(p.price), page: `p/${p._slug}.html`,
  image: p.images[0] ? imgVariant(p.images[0], 200) : '',
  // full-size photo for the card checkout page (JPEG copy when one exists)
  photo: p.images[0] ? (fs.existsSync(path.join(ROOT, 'images/feed', path.basename(p.images[0], '.webp').replace(/-1000$/, '') + '.jpg')) ? `images/feed/${path.basename(p.images[0], '.webp').replace(/-1000$/, '')}.jpg` : p.images[0]) : '',
  link: ((p.formats && p.formats[0] && p.formats[0].link) || p.link || '').trim(),
  sold: isSold(p),
}]))) + '\n');

// ---- plain-HTML product directory inside index.html ----
const groups = [];
PRODUCTS.forEach(p => {
  const name = p.sub || SECTION[p.category];
  let g = groups.find(x => x.name === name);
  if (!g) groups.push(g = {name, items: []});
  g.items.push(p);
});
const dir = `<!-- SEO-DIRECTORY:START (generated by _seo/build_seo.js, do not edit by hand) -->
<section class="block directory" id="all-products" aria-label="All products">
  <div class="wrap">
    <details>
      <summary>📋 All products A–Z by category (${PRODUCTS.length} items)</summary>
      <div class="dir-grid">
${groups.map(g => `        <div><h3>${esc(g.name)}</h3><ul>${g.items.map(p => `<li><a href="p/${p._slug}.html">${esc(p.title)}</a> <span>${esc(p.price)}</span></li>`).join('')}</ul></div>`).join('\n')}
      </div>
    </details>
  </div>
</section>
<!-- SEO-DIRECTORY:END -->`;
const re = /<!-- SEO-DIRECTORY:START[\s\S]*?<!-- SEO-DIRECTORY:END -->/;
if (!re.test(html)) throw new Error('SEO-DIRECTORY markers not found in index.html');
fs.writeFileSync(INDEX, html.replace(re, () => dir));

console.log(`Wrote ${PRODUCTS.length} product pages in p/, sitemap.xml, robots.txt, the Google + Facebook feeds and the index.html directory.`);
