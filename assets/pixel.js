/* Ad tracking for Akiliwo Marketplace: Meta (Facebook/Instagram) Pixel + Google tag (GA4 / Google Ads).
   Needs assets/shop-config.js first. Each one stays off until its ID is set there.
   Pages call akTrack(event, params) with Meta event names; ids in content_ids match
   facebook-catalog.csv / google-shopping-feed.xml so ads can show the right products. */
(function () {
  var metaId = String(window.AKILIWO_META_PIXEL || '').replace(/\D/g, '');
  var gIds = String(window.AKILIWO_GOOGLE_TAG || '').split(/[\s,]+/).filter(function (x) { return /^(G|AW|GT)-[A-Za-z0-9-]+$/.test(x); });
  var gAdsPurchase = String(window.AKILIWO_GOOGLE_ADS_PURCHASE || '').trim();   // 'AW-123456789/AbCdEf' (conversion label)
  var senders = [];

  if (metaId) {
    !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
    n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
    document,'script','https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', metaId);
    fbq('track', 'PageView');
    senders.push(function (event, p) { fbq('track', event, p); });
  }

  if (gIds.length) {
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(gIds[0]);
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    gtag('js', new Date());
    gIds.forEach(function (id) { gtag('config', id); });
    var GA = {ViewContent: 'view_item', InitiateCheckout: 'begin_checkout', Purchase: 'purchase'};
    senders.push(function (event, p) {
      if (!GA[event]) return;
      var g = {currency: p.currency || 'USD', value: p.value,
        items: (p.content_ids || []).map(function (id) { return {item_id: id, item_name: p.content_name}; })};
      if (p.order_id) g.transaction_id = p.order_id;
      gtag('event', GA[event], g);
      if (event === 'Purchase' && gAdsPurchase)
        gtag('event', 'conversion', {send_to: gAdsPurchase, value: p.value, currency: g.currency, transaction_id: p.order_id || ''});
    });
  }

  window.akTrack = function (event, params) {
    senders.forEach(function (send) { try { send(event, params || {}); } catch (e) {} });
  };
})();
