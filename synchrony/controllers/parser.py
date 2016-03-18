import urlparse
from synchrony import log
from BeautifulSoup import BeautifulSoup

def parse(html, url):
    
    # TODO(ljb): Recognise licensensing attributes to prevent piracy.
    
    domain = urlparse.urlparse(url).netloc

    #append_text = '<script src="/static/js/iframe.js"></script>\n'
    #append_text = ''

    #appendage = BeautifulSoup(append_text)

    soup = BeautifulSoup(html)

#    log('Requested %s (%s)' % (url, domain))

    request_endpoint = "/request/"

    # Known to omit some images such as the main one on uk.reuters.com
    # Also far slower than the previous implementation (it's simply doing more).
    def correct(soup, element):
        for _ in soup.findAll(element):
            
            if _.has_key("href"):
                if _.has_key("license") and _['license'].lower() != "cc by":
                    log("Ignoring licensed object %s" % _['href'])
                    _['href'] = ""
                    continue
                log("%s -> %s%s%s" % (str(_['href']), request_endpoint, domain, str(_['href'])), "debug")
                if    _['href'].startswith('https'):  _['href'] = _['href'].replace("https://", request_endpoint)
                elif  _['href'].startswith('http'):   _['href'] = _['href'].replace("http://",  request_endpoint)
                elif  _['href'].startswith('/'):      _['href'] = '%s%s%s' % (request_endpoint, domain, _['href'])
                else: _['href'] = '%s%s/%s' % (request_endpoint, domain, _['href'])

            elif _.has_key("src"):
                if _.has_key("license") and _['license'].lower() != "cc by":
                    log("Ignoring licensed object %s" % _['src'])
                    _['src'] = ""
                    continue
                log("%s -> %s%s%s" % (str(_['src']), request_endpoint, domain, str(_['src'])), "debug")
                if    _['src'].startswith('https'):  _['src'] = _['src'].replace("https://", request_endpoint)
                elif  _['src'].startswith('http'):   _['src'] = _['src'].replace("http://",  request_endpoint)
                elif  _['src'].startswith('/'):      _['src'] = '%s%s%s' % (request_endpoint, domain, _['src'])
                else: _['src'] = '%s%s/%s' % (request_endpoint, domain, _['src'])
  

    [correct(soup, element) for element in ["a", "link", "img", "script", "audio", "video"]]

    log('Should have cycled through urls by now.')
    # try:
    #     soup.head.insert(0, appendage)
    # except:
    #     pass
    return unicode(soup)



