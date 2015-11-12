##Synchrony
#####A peer-to-peer caching proxy that enables collaboration on hyperdocuments.
Installation:
<pre>
sudo python2 setup.py install
synchrony --help
synchrony --debug
</pre>
From another shell:
<pre>
synchrony --debug --port 8090 --bootstrap localhost:8080
</pre>

Visit localhost:8080 in a browser, make an account, hover over the scaled fish icon and
pull in http://news.ycombinator.com.

If you repeat this process from another browser window you should be able to edit the page collaboratively.

----

#####Pulling a resource from a peer

Visit :8080/v1/peers/test to tell peers you're serving whatever revision is found first.

Visit :8090/v1/peers/url_for_revision to pull the resource through the first peer and serve with the second peer.


This is all a work-in-progress at the moment but the project should be ready for sustained use within 2016.
