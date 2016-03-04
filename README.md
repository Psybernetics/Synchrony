##Synchrony
#####A collaborative hyperdocument editor.

![Alt text](doc/img/synchrony1.png?raw=true "Collaborative Editor")
![Alt text](doc/img/synchrony2.png?raw=true "Revision Management")
![Alt text](doc/img/synchrony3.png?raw=true "Distributed HTTP")

Installation:
<pre>
sudo python2 setup.py install
synchrony --help
synchrony --debug --address 127.0.0.1
</pre>
From another shell:
<pre>
synchrony --debug --address 127.0.0.1 --port 8090 --bootstrap 127.0.0.1:8080
</pre>

Visit localhost:8080 in a browser, make an account, hover over the scaled fish icon and
pull in http://news.ycombinator.com.

If you repeat this process from another browser window you should be able to edit the page collaboratively.

----

#####Pulling a resource from a peer

Visit :8080/v1/peers/test to tell peers you're serving whatever revision is found first.

Visit :8090/v1/peers/url_for_revision to pull the resource through the first peer and serve with the second peer.

Currently a work-in-progess as RPCs undergo refinement.

----

#####How you can support this project

Suggestions can be made on IRC: irc.psybernetics.org #synchrony

Donations are accepted [here](https://paypal.me/LukeB42).

All contributions go towards the development of this software, including porting to Go.
