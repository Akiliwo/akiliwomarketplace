# Card checkout (Stripe) — setup

The website sends the cart to a small Cloudflare Worker (`worker.js`), which creates a Stripe
Checkout page with the right prices and shipping ($5.99, FREE from $50, US only, 5–8 business days).
Until `assets/shop-config.js` has the Worker address, the site keeps its old buttons.

## One-time setup (owner, ~10 minutes)
1. Stripe Dashboard → Developers → API keys → **Create restricted key**
   - Name: `Akiliwo website checkout`; permission **Checkout Sessions: Write** (everything else None).
   - Copy the key (starts with `rk_live_`). Never send it to anyone or put it in the website.
2. dash.cloudflare.com (free account) → **Workers & Pages → Create → Create Worker**
   - Name: `akiliwo-checkout` → **Deploy** → **Edit code** → delete the sample, paste all of
     `worker.js` → **Deploy**.
3. Worker → **Settings → Variables and Secrets → Add** → Type **Secret**,
   name `STRIPE_SECRET_KEY`, value = the key from step 1 → **Deploy**.
4. Copy the Worker address (e.g. `https://akiliwo-checkout.<your-name>.workers.dev`) and give it to
   Claude, who sets it in `assets/shop-config.js`, runs `node _seo/build_seo.js` and publishes.

To change shipping, edit the constants at the top of `worker.js` (and `SHIPPING`/`FREE_FROM` in
`checkout.html`), then paste the new `worker.js` into Cloudflare again.
