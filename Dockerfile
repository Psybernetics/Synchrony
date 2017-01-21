FROM alpine:latest
MAINTAINER Luke Brooks

ENV PACKAGES="musl git build-base python python-dev py-pip libffi-dev libxml2-dev libxslt-dev libmagic"

RUN apk update && apk add $PACKAGES

RUN cd /tmp/ \
    && git clone https://github.com/miniupnp/miniupnp \
    && cd miniupnp \ 
    && cd miniupnpc \
    && make \
    && make install \ 
    && make pythonmodule \
    && make installpythonmodule

ADD . /srv/

RUN pip install -r /srv/requirements.txt

ENTRYPOINT ["/srv/synchrony.py"]

CMD ["-a 0.0.0.0 --debug"]
