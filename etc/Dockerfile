FROM alpine:latest

RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools
RUN pip3 install --no-cache pyyaml fastapi "uvicorn[standard]" sense-o-api==1.23 python-multipart

RUN apk add git

RUN mkdir -p /rucio-sense-sim
RUN mkdir -p /rucio-sense-dmm
WORKDIR /

RUN git clone https://github.com/jkguiang/rucio-sense-dmm

ENV PYTHONPATH="/rucio-sense-sim/northbound:$PYTHONPATH"
ENV PYTHONPATH="/rucio-sense-sim/southbound:$PYTHONPATH"
ENV PYTHONPATH="/rucio-sense-sim/utils:$PYTHONPATH"
ENV PYTHONPATH="/rucio-sense-dmm/src:$PYTHONPATH"

ENV HOME=/home
RUN cp /rucio-sense-dmm/.sense-o-auth.yaml.sim /home/.sense-o-auth.yaml

RUN apk add vim
ENV TERM=xterm-256color

ENTRYPOINT ["tail", "-f", "/dev/null"]
