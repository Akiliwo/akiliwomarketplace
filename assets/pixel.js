/* Meta Pixel for Akiliwo Marketplace. Needs assets/shop-config.js first.
   Does nothing until AKILIWO_META_PIXEL is set. Pages call akTrack(event, params);
   ids in content_ids match facebook-catalog.csv so ads can show the right products. */
(function () {
  var id = String(window.AKILIWO_META_PIXEL || '').replace(/\D/g, '');
  window.akTrack = function () {};
  if (!id) return;
  !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
  n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
  document,'script','https://connect.facebook.net/en_US/fbevents.js');
  fbq('init', id);
  fbq('track', 'PageView');
  window.akTrack = function (event, params) { try { fbq('track', event, params || {}); } catch (e) {} };
})();
