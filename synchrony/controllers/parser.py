import urlparse
from synchrony import log
from BeautifulSoup import BeautifulSoup

def parse(html, url):
	""
	domain = urlparse.urlparse(url).netloc

	append_text = '<script src="/static/synchrony.js"></script>\n<link rel="stylesheet" type="text/css" href="/static/synchrony.css" />'

	appendage = BeautifulSoup(append_text)

	soup = BeautifulSoup(html)

#	log('Requested %s (%s)' % (url, domain))

	request_endpoint = "/request/"

	for a in soup.findAll('a'):
		try:
			log(str(a['href']))
			if a['href'].startswith('https'): a['href'] = a['href'].replace("https://", request_endpoint)
			elif a['href'].startswith('http'): a['href'] = a['href'].replace("http://", request_endpoint)
			elif a['href'].startswith('/'): a['href'] = '%s%s%s' % (request_endpoint, domain, link['href'])
			else: a['href'] = '%s%s/%s' % (request_endpoint,domain, a['href'])
		except: continue
	for link in soup.findAll('link'):
		try:
			log(str(link['href']))
			if link['href'].startswith('https'): link['href'] = link['href'].replace("https://", request_endpoint)
			elif link['href'].startswith('http'): link['href'] = link['href'].replace("http://", request_endpoint)
			elif link['href'].startswith('/'): link['href'] = '%s%s%s' % (request_endpoint, domain, link['href'])
			else: link['href'] = '%s%s/%s' % (request_endpoint,domain, link['href'])
		except: continue
	log('Should have cycled through urls by now.')
	try:
		soup.head.append(appendage)
		log('Appended:\n%s' % append_text)
	except: pass
	return unicode(soup)
