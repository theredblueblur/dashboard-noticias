#!/usr/bin/env python3
"""Recopila titulares RSS públicos. Sin dependencias externas ni claves.
No descarga textos completos; solo titulares, enlaces, fechas y fuentes.
"""
import datetime as dt
import email.utils
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'noticias.json'
NOW = dt.datetime.now(dt.timezone.utc)


def google_rss(query, lang='es-419', country='MX', edition='MX:es-419'):
    params = urllib.parse.urlencode({'q': query, 'hl': lang, 'gl': country, 'ceid': edition})
    return 'https://news.google.com/rss/search?' + params

# Fuentes gratuitas de titulares. La disponibilidad de cada RSS puede variar.
# No se descargan textos completos ni cotizaciones.
SOURCES = [
    ('México', google_rss('Banxico OR inflación México OR economía mexicana when:2d'), 'Google News / México'),
    ('México', google_rss('site:eleconomista.com.mx (economía OR mercados) when:2d'), 'El Economista vía Google News'),
    ('Estados Unidos', google_rss('Federal Reserve OR US inflation OR Treasury yields when:2d', 'en-US', 'US', 'US:en'), 'Google News / EE. UU.'),
    ('Estados Unidos', 'https://www.federalreserve.gov/feeds/press_monetary.xml', 'Fed / Política monetaria'),
    ('Mercados', 'https://www.cnbc.com/id/10000664/device/rss/rss.html', 'CNBC / Finance'),
    ('Mercados', 'https://www.cnbc.com/id/15839069/device/rss/rss.html', 'CNBC / Investing'),
    ('Mercados', 'https://feeds.content.dowjones.io/public/rss/mw_topstories', 'MarketWatch'),
    ('Mercados', 'https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,MSFT,NVDA&region=US&lang=en-US', 'Yahoo Finance / Acciones'),
    ('Mercados', 'https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC,%5EIXIC&region=US&lang=en-US', 'Yahoo Finance / Índices'),
    ('Mercados', google_rss('site:finance.yahoo.com (stocks OR markets OR economy) when:2d','en-US','US','US:en'), 'Yahoo Finance vía Google News'),
    ('Mercados', google_rss('site:reuters.com (markets OR economy) when:2d','en-US','US','US:en'), 'Reuters vía Google News'),
    ('Política', 'https://www.cnbc.com/id/10000113/device/rss/rss.html', 'CNBC / Politics'),
    ('Política', google_rss('aranceles OR geopolítica OR política fiscal México when:2d'), 'Google News / Política'),
]



def get_text(node, name):
    val = node.findtext(name)
    return (val or '').strip()


def date_iso(raw):
    if not raw:
        return None
    try:
        d = email.utils.parsedate_to_datetime(raw)
        return d.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z')
    except (TypeError, ValueError):
        return None


def read_feed(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'MacroPulseEducationalRSS/1.0 (RSS reader)', 'Accept':'application/rss+xml, application/xml, text/xml, */*'})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read(2_000_000)
    root = ET.fromstring(data)
    items = root.findall('.//item')
    return items[:45]


def existing():
    if not OUT.exists():
        return []
    try:
        data = json.loads(OUT.read_text(encoding='utf-8'))
        return data.get('articles', []) if isinstance(data, dict) else []
    except (ValueError, OSError):
        return []


def main():
    cached = existing()
    by_id = {a.get('id'):a for a in cached if a.get('id')}
    success, errors, added = 0, [], 0
    for category, feed_url, label in SOURCES:
        try:
            items = read_feed(feed_url)
            success += 1
            for item in items:
                title = get_text(item,'title')
                link = get_text(item,'link')
                if not link or not title or not link.startswith(('https://','http://')):
                    continue
                ident = hashlib.sha256(link.encode('utf-8')).hexdigest()[:24]
                if ident in by_id:
                    continue
                date = date_iso(get_text(item,'pubDate'))
                source_node = item.find('source')
                source = (source_node.text or '').strip() if source_node is not None else label
                by_id[ident] = {'id':ident, 'title':re.sub(r'\s+',' ',title), 'url':link,
                                'source':source or label, 'category':category,
                                'published_at':date, 'collected_at':NOW.isoformat().replace('+00:00','Z')}
                added += 1
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
            errors.append(f'{label}: {type(exc).__name__}: {str(exc)[:150]}')
        time.sleep(0.7)
    articles = list(by_id.values())
    articles.sort(key=lambda x: x.get('published_at') or x.get('collected_at') or '', reverse=True)
    articles = articles[:300]
    payload = {'generated_at':NOW.isoformat().replace('+00:00','Z'), 'status':'ok' if not errors else ('partial' if success else 'error'),
               'sources_ok':success, 'sources_total':len(SOURCES), 'new_articles':added,
               'errors':errors, 'articles':articles}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Feeds OK: {success}/{len(SOURCES)}, nuevos: {added}, artículos: {len(articles)}')
    for e in errors:
        print('ADVERTENCIA:', e)
    if not articles:
        raise SystemExit('No hay noticias disponibles: revisa feeds y vuelve a ejecutar. No se publicará un dashboard vacío.')

if __name__ == '__main__':
    main()
