/*
 * Akiliwo Marketplace: card checkout (Cloudflare Worker -> Stripe Checkout).
 *
 * The website's checkout.html POSTs the cart here: {"items":[{"id":"<product id>","qty":1}, ...]}
 * This Worker looks every product up in the LIVE website's assets/checkout-products.json
 * (so prices can't be changed by the buyer), creates a Stripe Checkout Session and returns
 * {"url": "<stripe checkout page>"}; the website then sends the buyer there to pay by card.
 *
 * Setup (Cloudflare dashboard, free plan): Workers & Pages -> Create -> Worker -> paste this
 * file -> Deploy -> Settings -> Variables and Secrets -> add Secret STRIPE_SECRET_KEY.
 * The secret key lives ONLY in Cloudflare. Never put it in the website or the repository.
 *
 * `_stripe/` starts with "_", so GitHub Pages does not publish this file.
 */
const SITE = 'https://www.akiliwomarketplace.com';
const ALLOWED_ORIGINS = [SITE, 'https://akiliwomarketplace.com'];
const SHIPPING_CENTS = 599;            // standard shipping under the free-shipping minimum ($5.99)
const FREE_SHIPPING_FROM_CENTS = 5000; // free standard shipping from $50.00 (matches the Facebook shop)
const DELIVERY_DAYS = [5, 8];          // business days, matches the Facebook shipping profile
const MAX_QTY = 10;

function cors(origin) {
  return {
    'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(origin) ? origin : SITE,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Vary': 'Origin',
  };
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json', ...cors(origin)}});
}

// Stripe's API takes form-encoded nested fields: line_items[0][price_data][currency]=usd ...
function formEncode(obj, prefix, out = []) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}[${k}]` : k;
    if (v === undefined || v === null) continue;
    if (typeof v === 'object') formEncode(v, key, out);
    else out.push(`${encodeURIComponent(key)}=${encodeURIComponent(v)}`);
  }
  return out.join('&');
}

const shippingOption = (name, cents) => ({
  shipping_rate_data: {
    type: 'fixed_amount', display_name: name,
    fixed_amount: {amount: cents, currency: 'usd'},
    delivery_estimate: {
      minimum: {unit: 'business_day', value: DELIVERY_DAYS[0]},
      maximum: {unit: 'business_day', value: DELIVERY_DAYS[1]},
    },
  },
});

async function handle(request, env, fetchImpl = fetch) {
  const origin = request.headers.get('Origin') || '';
  if (request.method === 'OPTIONS') return new Response(null, {status: 204, headers: cors(origin)});
  if (request.method !== 'POST') return json({error: 'POST only'}, 405, origin);
  if (!env.STRIPE_SECRET_KEY) return json({error: 'Card checkout is not configured yet.'}, 500, origin);

  let body;
  try { body = await request.json(); } catch { return json({error: 'Bad request'}, 400, origin); }
  const wanted = Array.isArray(body && body.items) ? body.items.slice(0, 25) : [];

  const res = await fetchImpl(`${SITE}/assets/checkout-products.json`, {cf: {cacheTtl: 300}});
  if (!res.ok) return json({error: 'Could not load products. Please try again.'}, 502, origin);
  const catalog = await res.json();

  const lines = [];
  for (const w of wanted) {
    const p = catalog[String(w && w.id)];
    const qty = Math.floor(Number(w && w.qty));
    if (!p || p.sold || !(qty >= 1)) continue;
    const cents = Math.round(Number(p.price) * 100);
    if (!(cents > 0)) continue;
    lines.push({id: String(w.id), p, qty: Math.min(qty, MAX_QTY), cents});
  }
  if (!lines.length) return json({error: 'These items are not available. Please contact us.'}, 400, origin);

  const subtotal = lines.reduce((t, l) => t + l.cents * l.qty, 0);
  const shipping = subtotal >= FREE_SHIPPING_FROM_CENTS
    ? shippingOption('Free standard shipping', 0)
    : shippingOption('Standard shipping', SHIPPING_CENTS);

  const params = {
    mode: 'payment',
    success_url: `${SITE}/thank-you.html?order={CHECKOUT_SESSION_ID}`,
    cancel_url: `${SITE}/checkout.html?products=${encodeURIComponent(lines.map(l => `${l.id}:${l.qty}`).join(','))}`,
    shipping_address_collection: {allowed_countries: {0: 'US'}},
    shipping_options: {0: shipping},
    phone_number_collection: {enabled: 'true'},
    line_items: Object.fromEntries(lines.map((l, i) => [i, {
      quantity: l.qty,
      price_data: {
        currency: 'usd',
        unit_amount: l.cents,
        product_data: {name: l.p.title.slice(0, 250), ...(l.p.photo ? {images: {0: `${SITE}/${l.p.photo}`}} : {})},
      },
    }])),
  };

  const stripe = await fetchImpl('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: {'Authorization': `Bearer ${env.STRIPE_SECRET_KEY}`, 'Content-Type': 'application/x-www-form-urlencoded'},
    body: formEncode(params),
  });
  const session = await stripe.json();
  if (!stripe.ok || !session.url) return json({error: 'Card payment is unavailable right now. Please try again shortly.'}, 502, origin);
  return json({url: session.url}, 200, origin);
}

export default {fetch: (request, env) => handle(request, env)};
