/* Akiliwo Marketplace shop settings.
   CARD_CHECKOUT: address of the card-checkout Worker (see _stripe/worker.js). While it is empty,
   the site keeps the old buttons (card link where one exists, otherwise WhatsApp).
   After changing it, run `node _seo/build_seo.js` so the product pages pick it up. */
window.AKILIWO_CARD_CHECKOUT = 'https://akiliwo-checkout.sweet-bread-5fc6.workers.dev/';

/* META_PIXEL: Meta (Facebook/Instagram) Pixel ID from Events Manager — digits only. Empty = no
   tracking. assets/pixel.js loads it on every page and sends PageView, ViewContent,
   InitiateCheckout and Purchase with the same product ids as facebook-catalog.csv. */
window.AKILIWO_META_PIXEL = '29222531567359894';

/* GOOGLE_TAG: Google Analytics 4 ID (G-XXXXXXXXXX) and/or Google Ads ID (AW-XXXXXXXXX),
   comma-separated. GOOGLE_ADS_PURCHASE: the Google Ads purchase conversion 'AW-XXXXXXXXX/label'.
   Empty = off. */
window.AKILIWO_GOOGLE_TAG = 'G-KEK21CHZGK';
window.AKILIWO_GOOGLE_ADS_PURCHASE = '';
