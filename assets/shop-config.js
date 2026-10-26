/* Akiliwo Marketplace shop settings.
   CARD_CHECKOUT: address of the card-checkout Worker (see _stripe/worker.js). While it is empty,
   the site keeps the old buttons (card link where one exists, otherwise WhatsApp).
   After changing it, run `node _seo/build_seo.js` so the product pages pick it up. */
window.AKILIWO_CARD_CHECKOUT = '';
