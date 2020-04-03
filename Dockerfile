FROM python:3.8-alpine

MAINTAINER devops@rfranco.com

ADD scheduler.py /opt/
ADD requirements.txt /opt/

RUN pip install -r /opt/requirements.txt

ENTRYPOINT python /opt/scheduler.py -d
